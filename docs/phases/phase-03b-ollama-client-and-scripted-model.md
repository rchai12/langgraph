# Phase 3b: the Ollama client and the scripted model

## Goal

The two models that `decide()` (Phase 3c) will call, behind one small interface:

- `conductor.llm.model`: the interface `Model` (`model_info(name)` and `chat(request)`), the values `ModelInfo` and `ModelReply`, and the one error `ModelUnavailable` with a fixed code;
- `conductor.llm.ollama`: `OllamaModel`, which sends a 3a `ModelRequest` to `POST /api/chat` and reads the model's digest and capabilities from `GET /api/tags`, through the standard library's proxy-free opener, turning every failure into `ModelUnavailable`;
- `conductor.llm.scripted`: `ScriptedModel`, which hands out recorded replies in order, each naming the decision point it is for, for tests and later for replaying a run (Phase 11);
- the setting `CONDUCTOR_MODEL_TIMEOUT` (whole seconds, 1 to 3600, default 300).

Decided with the owner (2026-11-08): the digest and capabilities are read **before every call**, not cached, so each reply is logged with the model installed at that moment (3c does the calling); the timeout is a **setting**; `keep_alive` is **not sent**, leaving Ollama's own default; `ScriptedModel` replies come **in order and name their point**. From 2026-10-27: the standard library, not the `ollama` package; a failing Ollama is never retried in code.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Model client")
- `src/conductor/llm/tags.py` (the proxy-free opener), `src/conductor/llm/points.py` (`ModelRequest`, 3a), `src/conductor/config.py`, `tests/support.py`

## Starting state

Phase 3a is built and committed: N is `242`. **Sections: core, cli.** No `model.py`, `ollama.py`, or `scripted.py` exists in `src/conductor/llm/`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/llm/model.py` | `UnavailableCode`, `ModelUnavailable`, `ModelInfo`, `ModelReply`, `Model` (Part 1) |
| `src/conductor/llm/ollama.py` | `OllamaModel` (Part 2) |
| `src/conductor/llm/scripted.py` | `SCRIPTED_INFO`, `ScriptError`, `ScriptedReply`, `ScriptedModel` (Part 3) |
| `src/conductor/config.py` | the field `model_timeout`, the property `model_timeout_seconds`, its check (Part 4) |
| `tests/support.py` | given: replace it with the version below (the fake also answers `POST`) |
| `tests/unit/test_ollama.py`, `tests/unit/test_scripted.py`, `tests/unit/test_config_timeout.py` | given |
| `tests/unit/test_ollama_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- `decide()`, choosing `think` from the capabilities, validating a reply's content, `done_reason` rules, event logging, escalations (Phase 3c).
- Retrying, caching `model_info`, streaming, `keep_alive`, `/api/show`, `/api/ps`, or pulling a model.
- The `ollama` or `httpx` packages; any header other than `Content-Type`.
- Changing `conductor.llm.tags` or the doctor (they keep their own messages), `conductor.llm.points`, `conductor.llm.prompts`, or `conductor.contracts`.

## Dependencies

None new.

## Design

```python
# conductor/llm/model.py
UnavailableCode = Literal["unreachable", "timeout", "http_error", "bad_answer", "not_installed"]

class ModelUnavailable(Exception):
    def __init__(self, code: UnavailableCode, status: int | None = None) -> None: ...
    code: UnavailableCode
    status: int | None         # the HTTP status, for http_error only
    # str(): "model unavailable: <code>", or "model unavailable: http_error <status>"

@dataclass(frozen=True)
class ModelInfo:
    name: str                  # as Ollama lists it, "plain:latest"
    digest: str                # 64 lowercase hexadecimal characters
    capabilities: tuple[str, ...]   # sorted; () when Ollama lists none

@dataclass(frozen=True)
class ModelReply:
    content: str
    thinking: str = ""
    done_reason: str = "stop"
    total_ns: int = 0          # total_duration
    load_ns: int = 0           # load_duration
    prompt_tokens: int = 0     # prompt_eval_count
    prompt_ns: int = 0         # prompt_eval_duration
    reply_tokens: int = 0      # eval_count
    reply_ns: int = 0          # eval_duration

class Model(Protocol):
    def model_info(self, name: str) -> ModelInfo: ...
    def chat(self, request: ModelRequest) -> ModelReply: ...
```

```python
# conductor/llm/ollama.py
class OllamaModel:
    def __init__(self, host: str, *, timeout: float) -> None: ...   # host as settings give it
    _opener: urllib.request.OpenerDirector   # built in __init__; tests may replace it
    def model_info(self, name: str) -> ModelInfo: ...
    def chat(self, request: ModelRequest) -> ModelReply: ...
```

```python
# conductor/llm/scripted.py
SCRIPTED_INFO = ModelInfo(name="scripted", digest="0" * 64, capabilities=("completion", "thinking"))

class ScriptError(Exception): ...

@dataclass(frozen=True)
class ScriptedReply:
    point: str                 # the decision point this reply answers
    reply: ModelReply | ModelUnavailable

class ScriptedModel:
    def __init__(
        self, replies: Sequence[ScriptedReply], *, info: ModelInfo | ModelUnavailable = SCRIPTED_INFO
    ) -> None: ...
    requests: list[ModelRequest]   # every request chat() was given, in order
    @property
    def remaining(self) -> int: ...
    def model_info(self, name: str) -> ModelInfo: ...
    def chat(self, request: ModelRequest) -> ModelReply: ...
```

```python
# conductor/config.py: added
TIMEOUT_MESSAGE = "must be whole seconds from 1 to 3600"

class Settings(BaseSettings):
    ...
    model_timeout: str = "300"         # after `model`

    @property
    def model_timeout_seconds(self) -> int: ...
```

`tests/support.py` (given; replaces the file):

```python
"""Helpers shared by tests: running a command, fixed times, and a fake Ollama on 127.0.0.1.

New tests import these instead of copying them.
"""

import json
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from typer.testing import CliRunner

from conductor import clock
from conductor.cli.main import app

runner = CliRunner(env={"COLUMNS": "200"})


def run(*args: object):
    """Run `conductor` with these arguments, each turned into text."""
    return runner.invoke(app, [str(arg) for arg in args])


def fixed_times(monkeypatch: pytest.MonkeyPatch, *moments: str) -> None:
    """Make `clock.now()` return these ISO moments, one per call, in order."""
    times = iter([datetime.fromisoformat(moment) for moment in moments])
    monkeypatch.setattr(clock, "now", lambda: next(times))


class FakeOllama:
    """What the fake answers to every GET: `status` and `body`. `paths` lists what was asked.

    To every POST it answers `chat_status` and `chat_body`, and records
    `(path, headers with lower-case names, body)` in `posts`.
    """

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"models": []}'
        self.paths: list[str] = []
        self.chat_status = 200
        self.chat_body = b"{}"
        self.posts: list[tuple[str, dict[str, str], bytes]] = []

    def answer(self, **fields: object) -> None:
        """Answer chat posts with this JSON object."""
        self.chat_body = json.dumps(fields).encode()

    def models(self, *names: str) -> None:
        listed = [{"name": name, "model": name, "size": 1} for name in names]
        self.body = json.dumps({"models": listed}).encode()


class _LocalServer(HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer looks up the machine's name here, which costs seconds on macOS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


@contextmanager
def fake_ollama() -> Iterator[tuple[FakeOllama, str]]:
    """Start a fake Ollama on 127.0.0.1; yield it and its host, such as http://127.0.0.1:50123."""
    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.paths.append(self.path)
            self.send_response(fake.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(fake.body)))
            self.end_headers()
            self.wfile.write(fake.body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            headers = {name.lower(): value for name, value in self.headers.items()}
            fake.posts.append((self.path, headers, body))
            self.send_response(fake.chat_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(fake.chat_body)))
            self.end_headers()
            self.wfile.write(fake.chat_body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _LocalServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
```

### Facts (from spikes: Ollama 0.40.11, Python 3.12, pydantic-settings 2.16)

- A chat answer (`stream: false`) is one JSON object: `model`, `created_at`, `message` (`role`, `content`, and `thinking` only when thinking was on), `done` (`true`), `done_reason` (`stop`, or `length` when `num_predict` cut the reply), `total_duration`, `load_duration`, `prompt_eval_count`, `prompt_eval_duration`, `prompt_eval_cached_count`, `eval_count`, `eval_duration` (durations in nanoseconds). It carries no digest.
- `GET /api/tags` lists `models`, each with `name` (always with a tag: a model pulled as `plain` is listed as `plain:latest`), `digest` (64 hexadecimal characters), `capabilities` (for example `["completion", "vision", "tools", "thinking"]`), and more. Older Ollama versions leave `capabilities` out.
- Errors: a model that is not installed gives `404` on `/api/chat`; a bad schema or `think` for a model without the `thinking` capability gives `400`. The answer's body names the model, so it is never read into a message.
- `urllib`: a refused connection raises `URLError` (its `reason` a `ConnectionRefusedError`); a server that accepts and stays silent raises a bare `TimeoutError` while the answer is awaited, and a timeout while connecting arrives as `URLError` with a `TimeoutError` as its `reason`. `HTTPError`, `URLError`, and `TimeoutError` are all `OSError`s, so the order of the `except` clauses matters. `http.client` can also raise `HTTPException`s (`RemoteDisconnected` is an `OSError` too, `IncompleteRead` and `BadStatusLine` are not).
- pydantic-settings parses an `int` field leniently (`" 30 "` and `"30.0"` become 30) and its error for `"abc"` contains the value, hence a text field checked by a pattern.
- The `ollama` package would send `OLLAMA_API_KEY` as a bearer token and use the system proxy for 127.0.0.1; `test_the_chat_request` checks that this client does neither.

## Requirements

### Part 1: the interface

- **R1.** `ModelUnavailable(code, status)` keeps both; `str()` is `model unavailable: <code>`, followed by ` <status>` for `http_error`. `ModelInfo`, `ModelReply`, and `ScriptedReply` are frozen dataclasses exactly as under Design; `Model` is a `typing.Protocol` that both models satisfy.

### Part 2: the Ollama client

- **R2.** Every request goes through one opener, `self._opener`, built in `__init__` with `urllib.request.build_opener(urllib.request.ProxyHandler({}))`, to `host` + the path, with the client's `timeout`, and with no header but `Content-Type: application/json` on the `POST`. No environment variable is read.
- **R3.** Failures, from opening the request and from reading the answer alike, checked in this order for both calls: `HTTPError` gives `not_installed` for a `404` from `/api/chat` and `http_error` with its status otherwise; `TimeoutError`, or a `URLError` whose `reason` is a `TimeoutError`, gives `timeout`; any other `OSError` gives `unreachable`; an `http.client.HTTPException` gives `bad_answer`. Nothing of the answer's body or the exception's text goes into the error.
- **R4.** `model_info(name)` asks `GET /api/tags` on every call (no cache). The answer must be a JSON object whose `models` is a list of objects, each with a `name` that is a `str`, a `digest` that fully matches `^[0-9a-f]{64}$`, and, when present, `capabilities` as a list of `str`; anything else gives `bad_answer`. The entry whose `name` equals `name`, or, when `name` has no `:`, equals `name + ":latest"`, gives `ModelInfo(entry name, digest, sorted capabilities)`; no such entry gives `not_installed`.
- **R5.** `chat(request)` sends `json.dumps(request.body(), ensure_ascii=False).encode("utf-8")` to `POST /api/chat`. The answer must be a JSON object with `done` exactly `true`, `done_reason` a `str`, and `message` an object whose `content` is a `str` and whose `thinking`, when present and not `null`, is a `str`; each of the six counts and durations of the Design, when present, is an `int` (not a `bool`) of at least 0. Anything else gives `bad_answer`. Missing `thinking` gives `""`, a missing count or duration `0`. Other keys are ignored.
- **R6.** A body that is not UTF-8 or not JSON gives `bad_answer`; parse with `json.loads` on the decoded text, never Pydantic's error text.

### Part 3: the scripted model

- **R7.** `chat(request)` records the request in `requests`, then takes the next reply: none left raises `ScriptError(f"no scripted reply left for {request.point}")`; a reply whose `point` differs from `request.point` raises `ScriptError(f"scripted reply {n} is for {point}, not {request.point}")`, `n` counting from 1; a `ModelUnavailable` is raised (the very object); a `ModelReply` is returned (the very object). Each of these uses up the reply, except "none left".
- **R8.** `model_info(name)` raises `info` when it is a `ModelUnavailable`, and otherwise returns `info` itself when it was given, or `SCRIPTED_INFO` with `name` replaced by the name asked. `remaining` is the number of replies not yet used. The model keeps its own copy of `replies`.

### Part 4: the timeout setting

- **R9.** `Settings.model_timeout` is text, default `"300"`. `get_settings` adds the problem `CONDUCTOR_MODEL_TIMEOUT: must be whole seconds from 1 to 3600` unless it fully matches `^[1-9][0-9]{0,3}$` and is at most 3600; the problem comes after the model's, in the same `; `-joined `SettingsError`. `model_timeout_seconds` is `int(model_timeout)`.

### Part 5: rules

- **R10.** `model.py`, `ollama.py`, and `scripted.py` import only the standard library and `conductor.llm` modules (`ollama.py` and `scripted.py` may import `conductor.llm.points` for `ModelRequest`); no `ollama`, `httpx`, or `requests` package anywhere.

## Given tests

32 tests in three files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_ollama.py` (18 tests)

```python
import json
import socket

import pytest

from conductor.domains import demo
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.ollama import OllamaModel
from conductor.llm.points import build_request
from tests.support import fake_ollama

QWEN = {"name": "qwen3.8:27b", "digest": "4" * 64, "capabilities": ["thinking", "completion"]}
PLAIN = {"name": "plain:latest", "digest": "a" * 64}
TAGS = json.dumps({"models": [QWEN, PLAIN]}).encode()


def request():
    return build_request(
        demo.PICK,
        demo.PickInputs(request="Please repeat: hello"),
        model="qwen3.8:27b",
        fields=demo.pick_fields(),
    )


def unavailable(call) -> ModelUnavailable:
    with pytest.raises(ModelUnavailable) as raised:
        call()
    return raised.value


def test_the_model_info_is_read_from_the_tags() -> None:
    with fake_ollama() as (fake, host):
        fake.body = TAGS
        model = OllamaModel(host, timeout=5)
        assert model.model_info("qwen3.8:27b") == ModelInfo(
            name="qwen3.8:27b", digest="4" * 64, capabilities=("completion", "thinking")
        )
        assert model.model_info("plain") == ModelInfo(
            name="plain:latest", digest="a" * 64, capabilities=()
        )
    assert fake.paths == ["/api/tags", "/api/tags"]


@pytest.mark.parametrize("name", ["qwen3.8", "qwen3.8:7b"])
def test_a_model_that_is_not_installed(name: str) -> None:
    with fake_ollama() as (fake, host):
        fake.body = TAGS
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info(name))
    assert (error.code, error.status, str(error)) == (
        "not_installed",
        None,
        "model unavailable: not_installed",
    )


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"models": [{**QWEN, "digest": "4" * 63}]}).encode(),
        json.dumps({"models": [PLAIN, {**QWEN, "capabilities": "thinking"}]}).encode(),
    ],
)
def test_tags_that_do_not_fit(body: bytes) -> None:
    with fake_ollama() as (fake, host):
        fake.body = body
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert str(error) == "model unavailable: bad_answer"


def test_tags_with_an_http_error() -> None:
    with fake_ollama() as (fake, host):
        fake.status = 500
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert (error.code, error.status, str(error)) == (
        "http_error",
        500,
        "model unavailable: http_error 500",
    )


def test_the_chat_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "synthetic-key")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    with fake_ollama() as (fake, host):
        fake.answer(done=True, done_reason="stop", message={"role": "assistant", "content": "{}"})
        OllamaModel(host, timeout=5).chat(request())
    [(path, headers, body)] = fake.posts
    assert path == "/api/chat"
    assert json.loads(body) == request().body()
    assert headers["content-type"] == "application/json"
    assert "authorization" not in headers


def test_a_chat_answer_becomes_a_reply() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(
            model="qwen3.8:27b",
            done=True,
            done_reason="stop",
            message={"role": "assistant", "content": '{"action": "echo"}', "thinking": "Hm."},
            total_duration=900,
            load_duration=100,
            prompt_eval_count=40,
            prompt_eval_duration=300,
            prompt_eval_cached_count=0,
            eval_count=6,
            eval_duration=500,
        )
        reply = OllamaModel(host, timeout=5).chat(request())
    assert reply == ModelReply(
        content='{"action": "echo"}',
        thinking="Hm.",
        done_reason="stop",
        total_ns=900,
        load_ns=100,
        prompt_tokens=40,
        prompt_ns=300,
        reply_tokens=6,
        reply_ns=500,
    )


def test_a_short_chat_answer_gets_defaults() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(done=True, done_reason="length", message={"content": '{"act'})
        reply = OllamaModel(host, timeout=5).chat(request())
    assert reply == ModelReply(content='{"act', done_reason="length")
    assert (reply.thinking, reply.total_ns, reply.reply_tokens) == ("", 0, 0)


@pytest.mark.parametrize(
    ("status", "code", "text"),
    [
        (404, "not_installed", "model unavailable: not_installed"),
        (400, "http_error", "model unavailable: http_error 400"),
    ],
)
def test_a_chat_http_error(status: int, code: str, text: str) -> None:
    with fake_ollama() as (fake, host):
        fake.chat_status = status
        fake.answer(error="model 'qwen3.8:27b' not found")
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request()))
    assert (error.code, str(error)) == (code, text)


GOOD = {"done": True, "done_reason": "stop", "message": {"content": "{}"}}


@pytest.mark.parametrize(
    "answer",
    [
        {**GOOD, "done": False},
        {"done": True, "done_reason": "stop"},
        {**GOOD, "message": {"content": None}},
        {**GOOD, "eval_count": "6"},
    ],
)
def test_a_chat_answer_that_does_not_fit(answer: dict[str, object]) -> None:
    with fake_ollama() as (fake, host):
        fake.answer(**answer)
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request()))
    assert str(error) == "model unavailable: bad_answer"


def test_nothing_listening() -> None:
    model = OllamaModel("http://127.0.0.1:9", timeout=5)
    assert str(unavailable(lambda: model.chat(request()))) == "model unavailable: unreachable"
    assert str(unavailable(lambda: model.model_info("plain"))) == "model unavailable: unreachable"


def test_a_silent_server_times_out() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        model = OllamaModel(f"http://127.0.0.1:{port}", timeout=0.3)
        error = unavailable(lambda: model.chat(request()))
    finally:
        listener.close()
    assert (error.code, str(error)) == ("timeout", "model unavailable: timeout")
```

`tests/unit/test_scripted.py` (5 tests)

```python
from dataclasses import replace

import pytest

from conductor.domains import demo
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import build_request
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply, ScriptError

ECHO = ModelReply(content='{"action": "echo"}')
NOTE = ModelReply(content='{"action": "note"}', thinking="A note.")


def request(point: str = "demo_pick"):
    built = build_request(
        demo.PICK, demo.PickInputs(request="x"), model="test-model:1b", fields=demo.pick_fields()
    )
    return replace(built, point=point)


def test_replies_come_in_order() -> None:
    model = ScriptedModel([ScriptedReply("demo_pick", ECHO), ScriptedReply("demo_pick", NOTE)])
    assert model.remaining == 2
    first, second = request(), request()
    assert model.chat(first) is ECHO
    assert model.chat(second) is NOTE
    assert model.remaining == 0
    assert model.requests == [first, second]


def test_a_reply_for_another_point() -> None:
    model = ScriptedModel([ScriptedReply("demo_pick", ECHO), ScriptedReply("route", NOTE)])
    model.chat(request())
    with pytest.raises(ScriptError) as raised:
        model.chat(request())
    assert str(raised.value) == "scripted reply 2 is for route, not demo_pick"


def test_no_reply_left() -> None:
    model = ScriptedModel([])
    with pytest.raises(ScriptError) as raised:
        model.chat(request())
    assert str(raised.value) == "no scripted reply left for demo_pick"


def test_a_scripted_failure_is_raised_in_its_turn() -> None:
    down = ModelUnavailable("unreachable")
    model = ScriptedModel([ScriptedReply("demo_pick", down), ScriptedReply("demo_pick", ECHO)])
    with pytest.raises(ModelUnavailable) as raised:
        model.chat(request())
    assert raised.value is down
    assert model.chat(request()) is ECHO
    assert len(model.requests) == 2


def test_the_model_info() -> None:
    assert SCRIPTED_INFO == ModelInfo(
        name="scripted", digest="0" * 64, capabilities=("completion", "thinking")
    )
    assert ScriptedModel([]).model_info("qwen3.8:27b") == replace(SCRIPTED_INFO, name="qwen3.8:27b")
    plain = ModelInfo(name="plain:latest", digest="a" * 64, capabilities=("completion",))
    assert ScriptedModel([], info=plain).model_info("plain") == plain
    missing = ModelUnavailable("not_installed")
    with pytest.raises(ModelUnavailable) as raised:
        ScriptedModel([], info=missing).model_info("plain")
    assert raised.value is missing
```

`tests/unit/test_config_timeout.py` (9 tests)

```python
import pytest

from conductor.config import SettingsError, get_settings

TIMEOUT_REFUSED = "CONDUCTOR_MODEL_TIMEOUT: must be whole seconds from 1 to 3600"


def test_the_default_timeout() -> None:
    settings = get_settings()
    assert (settings.model_timeout, settings.model_timeout_seconds) == ("300", 300)


@pytest.mark.parametrize(("given", "seconds"), [("1", 1), ("3600", 3600)])
def test_a_timeout_in_range(monkeypatch: pytest.MonkeyPatch, given: str, seconds: int) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", given)
    assert get_settings().model_timeout_seconds == seconds


@pytest.mark.parametrize("given", [" 30 ", "30.0", "0", "3601", "0300"])
def test_a_timeout_out_of_range_or_not_whole(monkeypatch: pytest.MonkeyPatch, given: str) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", given)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == TIMEOUT_REFUSED


def test_the_timeout_problem_comes_last(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL", "")
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", "fast")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == f"CONDUCTOR_MODEL: must not be empty; {TIMEOUT_REFUSED}"
```

## Tests to write

In `tests/unit/test_ollama_more.py`, each with its deciding input:

- R3: a `404` from `/api/tags` gives `http_error 404`, not `not_installed`.
- R3: a timeout while connecting (`URLError` with a `TimeoutError` reason) gives `timeout`; a `ConnectionResetError` gives `unreachable`; an `http.client.IncompleteRead` gives `bad_answer` (each raised by a replacement for `model._opener` whose `open` raises it).
- R4: a name with a tag never matches `:latest` (`plain:7b` against `plain:latest` is `not_installed`); tags `{"models": "x"}` and a `name` of `3` give `bad_answer`.
- R5: `eval_count: true` and `eval_count: -1` give `bad_answer`; `thinking: null` gives `""`; a `done_reason` of `7` gives `bad_answer`.
- R6: a body of the bytes `b"\xff"` gives `bad_answer`.
- R2: the `POST` body is UTF-8 with non-ASCII text as is (a request with `"Résumé"` arrives as those bytes, not `é`).
- R8: changing the list given to `ScriptedModel` after building it changes nothing; `remaining` after a `ScriptError` for the wrong point is one less.

`model.py`, `ollama.py`, and `scripted.py` reach 100% of lines and branches.

## Rules for this phase

- **Only loopback, only `/api/chat` and `/api/tags`**: the host comes from settings, which already refuse anything off the machine.
- **No retry**: every failure raises at once (the owner's decision); 3c turns it into an escalation the person can retry.
- **Constant messages**: errors carry codes and the HTTP status, never Ollama's text, a model name from an answer, or `str()` of an exception.
- **Tests start their own servers** on 127.0.0.1 (the fake, or a silent listener); none reaches a real Ollama.
- Earlier tests stay unchanged; `tests/support.py` changes only as given.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core,cli`; at least N + 32 = 274 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_ollama.py tests/unit/test_scripted.py tests/unit/test_config_timeout.py --no-cov`, exactly `32 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/llm/model.py,*/conductor/llm/ollama.py,*/conductor/llm/scripted.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/llm/model.py src/conductor/llm/ollama.py src/conductor/llm/scripted.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|dataclasses|http\.client|json|re|typing|collections\.abc|urllib\.error|urllib\.request|conductor\.llm\.model|conductor\.llm\.points)( |$)"`
  - `git grep --untracked -n -E "^(from|import) (ollama|httpx|requests)|os\.environ|getenv|keep_alive" -- src/conductor`
- `git diff --stat HEAD -- src/conductor/llm/tags.py src/conductor/llm/points.py src/conductor/llm/prompts.py src/conductor/contracts tests/unit tests/e2e tests/conftest.py` prints nothing (the new test files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 3b: the Ollama client and the scripted model (YYYY-MM-DD)`, with `Tests: 242 -> <passed> (given 32)`.
