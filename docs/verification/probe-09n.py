"""Probe for Phase 9n: the page answers every request exactly as the single module did.

The oracle is the predecessor's `web/app.py`, read from commit d55b6db with git and loaded as its
own module inside `conductor.web`. Sessions of raw ASGI requests (exact Host, Origin and Cookie
headers, form bodies) run on the old and the new app. Each app gets a fresh data directory with
the same fixed clock, ids, form token, scripted model and fake resumer. Every status, header, body,
resume start and the stored decisions afterwards must agree. Run from the repository root with
.venv/bin/python docs/verification/probe-09n.py. The last line is FAILURES <n>.
"""

import asyncio
import importlib.util
import itertools
import os
import random
import secrets
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from typer.testing import CliRunner

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.store import Store

failures = 0
rng = random.Random(14)
BEFORE = "d55b6db"


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
os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"
os.environ["CONDUCTOR_DEMO"] = "true"


def ID(n: int) -> str:
    return f"{n:032x}"


PORT = 8766
HOST = f"127.0.0.1:{PORT}"
TOKEN = "ab" * 32
FRESH = "ef" * 32
PLAN = ("plan", '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}')
QUEUE: list[tuple[str, str]] = []
counter = itertools.count(1)
runner = CliRunner(env={"COLUMNS": "200"})
real_open = runtime.open_runtime


@contextmanager
def scripted(settings, *, model=None):
    answers = [ScriptedReply(point, ModelReply(content=text)) for point, text in QUEUE]
    QUEUE.clear()
    with real_open(settings, model=ScriptedModel(answers)) as opened:
        yield opened


runtime.open_runtime = scripted
clock.now = lambda: datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
ids.new_id = lambda: f"{next(counter):032x}"
secrets.token_hex = lambda size=32: FRESH


class FakeResumer:
    """Records each start; reports a run busy or failed as the session says."""

    def __init__(self, busy: bool, error: str | None) -> None:
        self.started: list[str] = []
        self.busy = busy
        self.failed = error

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, run_id: str) -> bool:
        return self.busy

    def error(self, run_id: str) -> str | None:
        return self.failed


def load_before():
    text = subprocess.run(
        ["git", "show", f"{BEFORE}:src/conductor/web/app.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    import conductor.web

    folder = Path(tempfile.mkdtemp())
    # The pages' templates are not in this phase's scope: both apps read the same files.
    (folder / "templates").symlink_to(Path(conductor.web.__path__[0]) / "templates")
    path = folder / "app_before.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("conductor.web.app_before", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(app, method: str, path: str, headers: list[tuple[str, str]], form: dict | None) -> tuple:
    body = b"" if form is None else urlencode(form).encode()
    raw = [(name.encode(), value.encode()) for name, value in headers]
    if form is not None:
        raw.append((b"content-type", b"application/x-www-form-urlencoded"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", PORT),
    }
    sent: list[dict] = []
    chunks = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> dict:
        return chunks.pop(0) if chunks else {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    text = b"".join(
        message.get("body", b"") for message in sent if message["type"] != start["type"]
    )
    return (start["status"], tuple(start["headers"]), text)


def setup(start: str) -> None:
    from conductor.cli.main import app as cli

    if start in ("plan", "step"):
        QUEUE[:] = [PLAN]
        runner.invoke(cli, ["ask", "demo: note Milk"])
    if start == "step":
        runner.invoke(cli, ["approvals", "approve", ID(4), "--yes"])
    if start == "escalation":
        os.environ["CONDUCTOR_DEMO"] = "false"
        runner.invoke(cli, ["ask", "Say hi back to me"])
        os.environ["CONDUCTOR_DEMO"] = "true"


def stored() -> list:
    store = Store(get_settings().db_path)
    found = [[item.model_dump(mode="json") for item in store.pending()]]
    found.append([item.escalation_id for item in store.open_escalations()])
    for number in range(1, 12):
        for read in (store.approval, store.escalation):
            try:
                item = read(ID(number))
            except Exception as error:  # noqa: BLE001
                found.append(type(error).__name__)
                continue
            decided = getattr(item, "decision", None) or getattr(item, "answer", None)
            found.append(None if decided is None else decided.model_dump(mode="json"))
    return found


def play(module, session: dict) -> list:
    """One session on a fresh world: each request's response, the starts, and the stored state."""
    global counter
    os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()
    os.environ["CONDUCTOR_WEB_PORT"] = str(PORT)
    counter = itertools.count(1)
    setup(session["start"])
    resumer = FakeResumer(session["busy"], session["error"])
    app = module.create_app(get_settings(), resumer=resumer)
    seen = [call(app, *request) for request in session["requests"]]
    return [*seen, tuple(resumer.started), stored()]


def headers(*, host=HOST, cookie=TOKEN, origin=None) -> list[tuple[str, str]]:
    found = []
    if host is not None:
        found.append(("host", host))
    if cookie is not None:
        found.append(("cookie", f"conductor_form={cookie}"))
    if origin is not None:
        found.append(("origin", origin))
    return found


def post(path: str, **form: str) -> tuple:
    return ("POST", path, headers(origin=f"http://{HOST}"), {"token": TOKEN, **form})


def get(path: str) -> tuple:
    return ("GET", path, headers(), None)


def session(start: str, *requests: tuple, busy: bool = False, error: str | None = None) -> dict:
    return {"start": start, "requests": list(requests), "busy": busy, "error": error}


EGGS = '{"title": "Eggs"}'
FORCED = [
    session("plan", get("/"), post(f"/approvals/{ID(4)}/approve"), get(f"/runs/{ID(2)}")),
    session("plan", post(f"/approvals/{ID(4)}/reject", note="<b>not now</b>")),
    session("plan", post(f"/approvals/{ID(4)}/edit", args=EGGS)),
    session("step", get(f"/approvals/{ID(6)}"), post(f"/approvals/{ID(6)}/edit", args=EGGS)),
    session("step", post(f"/approvals/{ID(6)}/edit", args="[1]")),
    session("step", post(f"/approvals/{ID(6)}/edit", args='{"title": ""}')),
    session("step", post(f"/approvals/{ID(6)}/approve"), post(f"/approvals/{ID(6)}/approve")),
    session("escalation", get(f"/escalations/{ID(3)}"), post(f"/escalations/{ID(3)}/retry")),
    session("escalation", post(f"/escalations/{ID(3)}/cancel"), get(f"/escalations/{ID(3)}")),
    session("escalation", post(f"/runs/{ID(2)}/resume"), get(f"/runs/{ID(2)}")),
    session("plan", post(f"/runs/{ID(2)}/resume"), busy=True),
    session("plan", get(f"/runs/{ID(2)}"), error="the resume failed"),
    session("plan", get(f"/runs/{ID(2)}"), busy=True, error="no run here"),
    session("empty", get(f"/runs/{ID(2)}"), get(f"/approvals/{ID(9)}"), get("/runs/nope")),
    session("plan", ("GET", "/", headers(host="example.test"), None)),
    session(
        "plan", ("GET", "/", headers(host=None), None), ("GET", "/", headers(cookie=None), None)
    ),
    session(
        "plan", ("POST", f"/approvals/{ID(4)}/approve", headers(origin="null"), {"token": TOKEN})
    ),
    session("plan", ("POST", f"/approvals/{ID(4)}/approve", headers(), {"token": "cd" * 32})),
    session("plan", ("GET", f"/approvals/{ID(4)}/approve", headers(), None), get("/docs")),
]
PAGE_IDS = [ID(2), ID(3), ID(4), ID(5), ID(6), ID(9), "nope", ID(4).upper()]


def random_request() -> tuple:
    item = rng.choice(PAGE_IDS)
    kind = rng.choice(["page", "page", "approval", "approval", "escalation", "resume"])
    if kind == "page":
        path = rng.choice(["/", f"/approvals/{item}", f"/escalations/{item}", f"/runs/{item}"])
        method, form = "GET", None
    else:
        verb = {
            "approval": rng.choice(["approve", "reject", "edit"]),
            "escalation": rng.choice(["retry", "cancel"]),
            "resume": "resume",
        }[kind]
        group = {"approval": "approvals", "escalation": "escalations", "resume": "runs"}[kind]
        path = f"/{group}/{item}/{verb}"
        method = "POST"
        form = {"token": TOKEN, "note": rng.choice(["", "not now", "<i>x</i>"])}
        if verb == "edit":
            form["args"] = rng.choice([EGGS, "[1]", "{bad", '{"title": ""}', '{"x": 1}'])
    sent = headers(origin=f"http://{HOST}" if method == "POST" else None)
    change = rng.choice(["none", "none", "none", "host", "cookie", "origin", "token", "method"])
    if change == "host":
        sent = [("host", rng.choice(["localhost:8766", "127.0.0.1:9999", "x"]))] + sent[1:]
    elif change == "cookie":
        sent = [name_value for name_value in sent if name_value[0] != "cookie"]
        sent.append(("cookie", rng.choice(["conductor_form=" + TOKEN[:-1], "other=1"])))
    elif change == "origin":
        sent = [*sent, ("origin", rng.choice(["null", "http://localhost:8766", "http://x"]))]
    elif change == "token" and form is not None:
        form["token"] = rng.choice(["", "cd" * 32])
    elif change == "method":
        method = "POST" if method == "GET" else "GET"
    return (method, path, sent, form)


def random_session() -> dict:
    start = rng.choice(["empty", "plan", "step", "step", "escalation"])
    requests = [random_request() for _ in range(rng.randint(1, 4))]
    error = rng.choice([None, None, "the resume failed", "no run here"])
    return session(start, *requests, busy=rng.random() < 0.2, error=error)


before = load_before()
# The oracle on known cases: a pending plan approved through the page starts its run.
known = play(before, FORCED[0])
assert known[0][0] == 200 and ID(4).encode() in known[0][2]
assert known[1][0] == 303 and dict(known[1][1])[b"location"] == f"/runs/{ID(2)}".encode()
assert known[3] == (ID(2),)
assert play(before, FORCED[14])[0][0] == 400


def check_layout() -> bool:
    from conductor.web import app, security

    return app.FORM_COOKIE is security.FORM_COOKIE and hasattr(app, "record_and_resume")


def check_sessions() -> bool:
    from conductor.web import app

    statuses: dict[int, int] = {}
    agree = True
    for chosen in FORCED + [random_session() for _ in range(400)]:
        old = play(before, chosen)
        agree &= play(app, chosen) == old
        for status, _, _ in old[:-2]:
            statuses[status] = statuses.get(status, 0) + 1
    print(f"     statuses {dict(sorted(statuses.items()))}")
    return agree and all(statuses.get(code, 0) >= 5 for code in (200, 303, 400, 403, 404, 409))


section("the security code lives in web/security.py", check_layout)
section(
    "19 forced and 400 random sessions: every response and stored decision as before",
    check_sessions,
)

print(f"FAILURES {failures}")
