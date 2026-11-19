"""Probe for Phase 9g: one model-list parser for doctor and runs, and capped Ollama reads.

Run from the repository root with .venv/bin/python docs/verification/probe-09g.py.
The last line is FAILURES <n>. Every server it talks to is its own, on 127.0.0.1.
"""

import json
import os
import random
import socket
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

failures = 0
rng = random.Random(7)


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def section(label: str, body: Callable[[], bool]) -> None:
    try:
        ok = body()
    except Exception as error:  # noqa: BLE001
        print(f"     {label}: raised {type(error).__name__}")
        ok = False
    check(label, ok)


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables: written from the spec, never read from the code.
CAP = 1_048_576
HEX = "0123456789abcdef"
TEXT = {
    "no_digest": "listed without a valid digest",
    "bad_capabilities": "listed with invalid capabilities",
    "duplicate": "listed more than once",
}


def oracle_listing(entries: list[object]) -> dict[str, tuple]:
    """name -> (digest or None, capabilities, problem or None), in first-seen order."""
    out: dict[str, tuple] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or name == "":
            continue
        if name in out:
            out[name] = (None, (), "duplicate")
            continue
        digest = entry.get("digest")
        digest_ok = isinstance(digest, str) and len(digest) == 64 and set(digest) <= set(HEX)
        raw = entry.get("capabilities", [])
        caps_ok = isinstance(raw, list) and all(isinstance(part, str) for part in raw)
        problem = (
            None
            if digest_ok and caps_ok
            else ("no_digest" if not digest_ok else "bad_capabilities")
        )
        out[name] = (digest if digest_ok else None, tuple(sorted(raw)) if caps_ok else (), problem)
    return out


def oracle_find(listing: dict[str, tuple], name: str) -> str | None:
    if name in listing:
        return name
    if ":" not in name and f"{name}:latest" in listing:
        return f"{name}:latest"
    return None


def oracle_doctor(listing: dict[str, tuple], model: str) -> str:
    found = oracle_find(listing, model)
    if found is None:
        return f"FAIL  model {model}: not pulled (run: ollama pull {model})"
    digest, _caps, problem = listing[found]
    if problem is not None:
        return f"FAIL  model {model}: {TEXT[problem]}"
    return f"ok    model {model}: digest {digest[:12]}"


def oracle_run(listing: dict[str, tuple], model: str) -> object:
    found = oracle_find(listing, model)
    if found is None:
        return "not_installed"
    digest, caps, problem = listing[found]
    return "bad_answer" if problem is not None else (found, digest, caps)


# The oracle on known cases.
_A, _B = "a" * 64, "b" * 64
_known = oracle_listing(
    [
        {"name": "m:1", "digest": _A},
        "x",
        {"name": "m:1", "digest": _B},
        {"name": "n", "digest": "A" * 64},
        {"name": "k:latest", "digest": _B, "capabilities": ["t", "c"]},
        {"name": ""},
        {"name": "m:1"},
    ]
)
assert _known == {
    "m:1": (None, (), "duplicate"),
    "n": (None, (), "no_digest"),
    "k:latest": (_B, ("c", "t"), None),
}
assert list(_known) == ["m:1", "n", "k:latest"]
assert oracle_find(_known, "k") == "k:latest" and oracle_find(_known, "k:2") is None
assert oracle_run(_known, "n") == "bad_answer" and oracle_doctor(_known, "k").endswith(
    "digest bbbbbbbbbbbb"
)

NAMES = ["m:1", "m:latest", "m", "n:2"]
ASKED = ["m", "m:1", "n", "n:2", "m:latest"]


def digest() -> str:
    return "".join(rng.choice(HEX) for _ in range(64))


def base_entries() -> list[dict]:
    names = rng.sample(NAMES, rng.randint(1, len(NAMES)))
    entries = []
    for name in names:
        entry = {"name": name, "model": name, "size": 1, "digest": digest()}
        if rng.random() < 0.5:
            entry["capabilities"] = rng.sample(
                ["completion", "thinking", "tools"], rng.randint(0, 3)
            )
        entries.append(entry)
    return entries


def one_change(entries: list[dict]) -> list[object]:
    """The base listing with at most one change."""
    changed: list[object] = [dict(entry) for entry in entries]
    i = rng.randrange(len(changed))
    kind = rng.choice(
        [
            "none",
            "drop_digest",
            "upper",
            "prefixed",
            "caps_text",
            "caps_mixed",
            "name_number",
            "not_object",
            "duplicate",
            "junk",
            "empty_name",
        ]
    )
    target = changed[i]
    assert isinstance(target, dict)
    if kind == "drop_digest":
        del target["digest"]
    elif kind == "upper":
        target["digest"] = target["digest"].upper()
    elif kind == "prefixed":
        target["digest"] = "sha256:" + target["digest"]
    elif kind == "caps_text":
        target["capabilities"] = "thinking"
    elif kind == "caps_mixed":
        target["capabilities"] = ["thinking", 1]
    elif kind == "name_number":
        target["name"] = 3
    elif kind == "not_object":
        changed[i] = "x"
    elif kind == "duplicate":
        changed.insert(rng.randrange(len(changed) + 1), {**target, "digest": digest()})
    elif kind == "junk":
        changed.insert(rng.randrange(len(changed) + 1), {"model": "junk"})
    elif kind == "empty_name":
        target["name"] = ""
    return changed


class Fake:
    body = b'{"models": []}'


@contextmanager
def fake_ollama() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(Fake.body)))
            self.end_headers()
            self.wfile.write(Fake.body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def check_random_listings() -> bool:
    from conductor.diagnostics import check_ollama
    from conductor.llm.model import ModelUnavailable
    from conductor.llm.ollama import OllamaModel
    from conductor.llm.tags import find_model, parse_tags

    agree = True
    reached = {"bad_answer": 0, "not_installed": 0, "ok": 0}
    with fake_ollama() as host:
        model = OllamaModel(host, timeout=5)
        for _ in range(150):
            entries = one_change(base_entries())
            asked = rng.choice(ASKED)
            want = oracle_listing(entries)
            body = json.dumps({"models": entries}).encode()
            got = parse_tags(body)
            agree &= list(got) == list(want)
            agree &= all(
                (got[name].name, got[name].digest, got[name].capabilities, got[name].problem)
                == (name, *want[name])
                for name in want
            )
            found = find_model(got, asked)
            agree &= (found.name if found is not None else None) == oracle_find(want, asked)
            Fake.body = body
            try:
                info = model.model_info(asked)
                outcome: object = (info.name, info.digest, info.capabilities)
            except ModelUnavailable as error:
                outcome = error.code
            expected = oracle_run(want, asked)
            agree &= outcome == expected
            reached["ok" if isinstance(expected, tuple) else expected] += 1
            lines = [check.line for check in check_ollama(host, asked)]
            agree &= lines == [f"ok    ollama {host}", oracle_doctor(want, asked)]
    return agree and min(reached.values()) >= 10


@contextmanager
def raw_server(sent: bytes) -> Iterator[tuple[str, list[int]]]:
    """Answer each request with `sent`; the list gets how many bytes each answer got out."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(0.1)
    out: list[int] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                received = b""
                while b"\r\n\r\n" not in received:
                    part = connection.recv(65536)
                    if not part:
                        break
                    received += part
                length = 0
                for line in received.split(b"\r\n\r\n")[0].split(b"\r\n")[1:]:
                    key, _, value = line.partition(b":")
                    if key.strip().lower() == b"content-length":
                        length = int(value)
                rest = received.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in received else b""
                while len(rest) < length:
                    rest += connection.recv(65536)
                done = 0
                try:
                    for start in range(0, len(sent), 65536):
                        connection.sendall(sent[start : start + 65536])
                        done = start + 65536
                except OSError:
                    pass
                out.append(min(done, len(sent)))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}", out
    finally:
        stop.set()
        thread.join(5)
        listener.close()


def head(*lines: str) -> bytes:
    return (
        "HTTP/1.1 200 OK\r\n"
        + "".join(f"{line}\r\n" for line in lines)
        + "Connection: close\r\n\r\n"
    ).encode()


def check_a_flood_is_not_read_to_the_end() -> bool:
    from conductor.llm.model import ModelUnavailable
    from conductor.llm.ollama import OllamaModel

    flood = head() + b" " * (64 * CAP)
    codes = []
    with raw_server(flood) as (host, sent):
        for call in ("tags", "chat"):
            model = OllamaModel(host, timeout=5)
            try:
                if call == "tags":
                    model.model_info("m")
                else:
                    from conductor.domains import demo
                    from conductor.llm.points import build_request

                    model.chat(
                        build_request(
                            demo.PICK,
                            demo.PickInputs(request="x"),
                            model="m",
                            fields=demo.pick_fields(),
                        )
                    )
                codes.append("no error")
            except ModelUnavailable as error:
                codes.append(error.code)
    return codes == ["too_large", "too_large"] and len(sent) == 2 and max(sent) < 16 * CAP


def check_lengths_that_lie() -> bool:
    from conductor.llm.model import ModelUnavailable
    from conductor.llm.ollama import OllamaModel

    listing = json.dumps({"models": [{"name": "m:1", "digest": "c" * 64}]}).encode()
    cases = [
        (head(f"Content-Length: {len(listing) * 50}") + listing, ("m:1", "c" * 64, ())),
        (head("Content-Length: 5") + listing, "bad_answer"),
        (head(f"Content-Length: {CAP * 4}") + listing + b" " * (CAP + 1), "too_large"),
        (
            head("Transfer-Encoding: chunked")
            + f"{CAP + 1:x}\r\n".encode()
            + b" " * (CAP + 1)
            + b"\r\n0\r\n\r\n",
            "too_large",
        ),
        (head() + listing + b" " * (CAP - len(listing)), ("m:1", "c" * 64, ())),
    ]
    results = []
    for sent, want in cases:
        with raw_server(sent) as (host, _out):
            try:
                info = OllamaModel(host, timeout=5).model_info("m:1")
                got: object = (info.name, info.digest, info.capabilities)
            except ModelUnavailable as error:
                got = error.code
        results.append(got == want)
    return all(results) and len(results) == 5


def check_doctor_lengths_that_lie() -> bool:
    from conductor.diagnostics import check_ollama

    cases = [
        (head("Transfer-Encoding: chunked") + b"ff\r\n{", "unexpected answer"),
        (head() + b" " * (CAP + 1), "answer too large"),
        (head(f"Content-Length: {CAP * 4}") + b" " * (CAP + 1), "answer too large"),
    ]
    results = []
    for sent, detail in cases:
        with raw_server(sent) as (host, _out):
            lines = [item.line for item in check_ollama(host, "m")]
        results.append(lines == [f"FAIL  ollama {host}: {detail}", "SKIP  model m: needs ollama"])
    return all(results) and len(results) == 3


section(
    "150 one-change listings: parser, run and doctor all match the table", check_random_listings
)
section(
    "a 64 MiB answer is refused as too_large without being read",
    check_a_flood_is_not_read_to_the_end,
)
section("overstated, understated, chunked and exact lengths, for runs", check_lengths_that_lie)
section("broken and oversized answers, for doctor", check_doctor_lengths_that_lie)

print(f"FAILURES {failures}")
