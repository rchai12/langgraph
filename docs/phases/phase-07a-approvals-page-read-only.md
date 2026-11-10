# Phase 7a: the approvals page, read-only

## Goal

A page in the browser that shows what waits for the person, with nothing on it that can change anything yet:

- `conductor web` serves on **127.0.0.1 only**, on `CONDUCTOR_WEB_PORT` (default 8766), answering only to `127.0.0.1:<port>` and `localhost:<port>`;
- every answer carries strict **security headers** (no scripts at all, no framing, no caching);
- a home page lists **pending approvals and open escalations**, oldest first, and a page per approval and per escalation shows **the same lines** the terminal's `show` commands print;
- those lines move into one module, `conductor.views`, used by both the terminal and the page.

Decided with the owner (2026-11-09): Phase 7 has **two parts** (7a these read-only pages; 7b the deciding forms with a form token and an origin check, recording through `conductor.decisions`, then resuming the run in the background); **FastAPI and Jinja2**, as `finances`; **this Mac only, no login**; the pages are **pending items and their details**; the port is **a setting**; the home page **does not refresh itself**.

Corrected by the architect for this phase: the owner chose a default of 8765, on the stated belief that the `finances` UI used another port; its default is also 8765, and it was listening there on this Mac. The default is therefore **8766**, still a setting.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 3), `docs/architecture.md` ("Approvals and escalations", "Privacy and safety boundary")
- `src/conductor/cli/main.py` (`_request_block`, `_escalation_block`, and how `show` prints), `src/conductor/store.py`, `src/conductor/config.py`

## Starting state

Phase 6c is built and verified, and everything is committed: N is `664`. **Sections: cli, core.** `fastapi` and `jinja2` are not installed (`starlette`, `uvicorn`, `python-multipart`, and `httpx` are, through `mcp`).

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | add `"fastapi>=0.162,<0.163",` and `"jinja2>=3.1,<3.2",` to `dependencies`, after `mcp`; add `"web/templates/*.html"` to `[tool.setuptools.package-data]` `conductor`; then run `.venv/bin/python -m pip install -e ".[dev]"` once |
| `src/conductor/config.py` | `web_port`, `web_port_number`, and the check (Part 1) |
| `src/conductor/views.py` | `request_lines`, `escalation_lines` (Part 2) |
| `src/conductor/cli/main.py` | `show` and the prompts use `conductor.views` (unchanged output); the `web` command (Part 4) |
| `src/conductor/web/__init__.py` | empty |
| `src/conductor/web/app.py` | `SECURITY_HEADERS`, `create_app` (Part 3, critical) |
| `src/conductor/web/templates/*.html` | the page templates |
| `scripts/critical_modules.txt` | add the line `web/app.py` after `mcp_client/check.py` |
| `docs/testing.md` | under "Critical modules", add `` - `web/app.py` (only this machine is answered, and nothing it shows can run as markup; Phase 7a) `` after the `mcp_client/check.py` line |
| `tests/e2e/test_web_pages.py`, `tests/e2e/test_cli_web.py` | given |
| `tests/e2e/test_web_pages_more.py`, `tests/unit/test_views.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Any form, `POST` route, decision, or resume (7b); a login, sessions, remote access, a Tailscale name.
- Runs and their events on the page; refreshing; static files, CSS, scripts, images, fonts; any CDN.
- Changing what the terminal prints; changes to the store, `decisions`, the runtime, or the graph.

## Dependencies

`fastapi>=0.162,<0.163` (0.162.2 is current; it accepts the installed Starlette 1.10.0 and brings `annotated-doc` and `opentelemetry-api`, which records nothing without an SDK) and `jinja2>=3.1,<3.2` (3.1.6, with `markupsafe`). `uvicorn` (0.54.0) is already installed through `mcp`.

## Design

```python
# conductor/config.py: added
WEB_PORT_MESSAGE = "must be a port from 1024 to 65535"
class Settings(BaseSettings):
    ...
    web_port: str = "8766"            # after mcp_timeout

    @property
    def web_port_number(self) -> int: ...
```

`web_port` must fully match `^[1-9][0-9]{3,4}$` and be at most 65535 (`CONDUCTOR_WEB_PORT: must be a port from 1024 to 65535`), checked after the `CONDUCTOR_MCP_TIMEOUT` problem and before the `CONDUCTOR_MCP__<NAME>` problems.

```python
# conductor/views.py
def request_lines(stored: StoredApproval) -> tuple[str, ...]: ...
def escalation_lines(stored: StoredEscalation) -> tuple[str, ...]: ...
```

They return exactly the lines of 4c's request block and escalation block (the status line, the run line, the steps or the detail and problems, `edited args:`, `note:`), so that `"\n".join(request_lines(stored))` equals what `approvals show` prints today, byte for byte. `cli/main.py` prints through them and keeps no copy of the block code.

```python
# conductor/web/app.py (critical)
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "cache-control": "no-store",
}

def create_app(settings: Settings) -> FastAPI: ...
```

`create_app`:

- a `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` app, wrapped in a pure ASGI host check (as `finances` does, `finances/src/finances/web/app.py`): an HTTP request whose `Host` headers are not exactly one value in `{"127.0.0.1:<port>", "localhost:<port>"}` gets `400` with the plain text `Bad host`; every response, refused or not, carries `SECURITY_HEADERS` (replacing any header of the same name);
- Jinja2 templates from `conductor/web/templates/`, with autoescape on for `.html`; no template contains `<script`, an `on…=` attribute, or a URL to another host;
- the store is `Store(settings.db_path)`, opened per request; a `StoreError` gives `503` with the plain text `The store is not available`;
- the routes, all `GET`:

| Path | Shows |
|---|---|
| `/` | "Pending approvals", then one row per `store.pending()` request, oldest first, each with `<a href="/approvals/<id>"><id></a>`, its requested time (`%Y-%m-%dT%H:%M:%SZ`), its stage, and its actions joined by `, `; or `No pending approvals.`. Then "Open escalations", one row per `store.open_escalations()`, each with `<a href="/escalations/<id>"><id></a>`, its raised time, its kind, and `run <run_id>`; or `No open escalations.` |
| `/approvals/<id>` | the lines of `request_lines`, each escaped, inside one `<pre>`, and a link back to `/` |
| `/escalations/<id>` | the lines of `escalation_lines`, the same way |

An `<id>` that does not fully match `^[0-9a-f]{32}$`, or that the store does not have (`NotFound`), gives `404` with the plain text `Not found`, before or instead of reading the store.

`conductor web`: reads the settings (a `SettingsError` is the usual `Error:` line); checks the port is free by binding a plain socket (no options) to `("127.0.0.1", <port>)` and closing it, and on an `OSError` prints `Error: port <port> is taken` on stderr and exits 1; otherwise prints `Serving on http://127.0.0.1:<port>/` and calls `uvicorn.run(create_app(settings), host="127.0.0.1", port=<port>, server_header=False, proxy_headers=False, log_level="warning")`, through the module (`import uvicorn`) so tests can replace it.

## Facts about FastAPI, Starlette, and uvicorn

Found on 2026-11-09 with fastapi 0.162.2, starlette 1.10.0, jinja2 3.1.6, uvicorn 0.54.0:

- FastAPI 0.162.2 requires `starlette>=0.46.0` and installs without changing the Starlette 1.10.0 that `mcp` brought.
- `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` answers `/docs` and `/openapi.json` with `404`.
- `TestClient(app)` sends `Host: testserver`, which the host check refuses; `TestClient(app, base_url="http://127.0.0.1:8766")` sends `Host: 127.0.0.1:8766`.
- `uvicorn.run` takes `server_header` and `proxy_headers`; with `server_header=False` the response has no `server` header, and with `proxy_headers=False` it does not trust `X-Forwarded-*`.
- Jinja2 with autoescape turns `<script>` into `&lt;script&gt;` and `"` into `&#34;` (the same as `markupsafe.escape`, which the given tests use).
- The `finances` web UI's default port is 8765, and it was listening on `127.0.0.1:8765` on this Mac.

## Requirements

### Part 1: the setting

- **R1.** `web_port`, `web_port_number`, and the check are as under Design.

### Part 2: the shared lines

- **R2.** `request_lines` and `escalation_lines` give 4c's block lines exactly; the terminal prints through them, and every earlier CLI test passes unchanged.

### Part 3: the page (critical)

- **R3.** Only `127.0.0.1:<port>` and `localhost:<port>` are answered; any other `Host`, or none, or two, gives `400 Bad host`.
- **R4.** Every response carries `SECURITY_HEADERS`, including the `400`, `404`, `405`, and `503` ones.
- **R5.** The three routes show what the Design says; nothing else is served (`POST` is `405`, the docs `404`).
- **R6.** Every stored text (arguments, details, notes, problems) is escaped; no page contains a script, an event attribute, or another host's URL.
- **R7.** A bad or unknown id is `404 Not found`; an unreadable store is `503 The store is not available`; no message holds stored text.

### Part 4: the command

- **R8.** `conductor web` checks the settings and the port, then serves as under Design, on 127.0.0.1 only.

### Part 5: the rules

- **R9.** `conductor/web/` imports from the project only `conductor.config`, `conductor.store`, and `conductor.views`; it reads the store and never writes it, and never imports `decisions`, the runtime, or the graph.
- **R10.** `web/app.py` reaches 100% of lines and branches and joins the critical modules; `views.py`, `config.py`, and `cli/main.py` stay at 100%.

## Given tests

26 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/e2e/test_web_pages.py` (20 tests)

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from conductor import clock
from conductor.config import get_settings
from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.registry import Registry
from conductor.store import Store
from conductor.web.app import SECURITY_HEADERS, create_app

FIRST = "1" * 32
SECOND = "2" * 32
RUN = "a" * 32
BASE = "http://127.0.0.1:8766"


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 10, 0, tzinfo=UTC))


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


@pytest.fixture
def page() -> TestClient:
    return TestClient(create_app(get_settings()), base_url=BASE)


def add(db: Store, approval_id: str, args: dict, hour: int, stage: str = "step") -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args=args)
    db.add_request(
        ApprovalRequest(
            approval_id=approval_id,
            run_id=RUN,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, hour, 0, tzinfo=UTC),
        )
    )


def shown(args: dict) -> str:
    return str(escape(json.dumps(args, ensure_ascii=False, sort_keys=True)))


def test_an_empty_home_page(db: Store, page: TestClient) -> None:
    response = page.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "No pending approvals." in response.text
    assert "No open escalations." in response.text
    assert "<script" not in response.text


def test_the_home_page_lists_what_waits_oldest_first(db: Store, page: TestClient) -> None:
    add(db, SECOND, {"title": "Bread"}, 9)
    add(db, FIRST, {"title": "Milk"}, 10, stage="plan")
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    text = page.get("/").text
    assert text.index(f'<a href="/approvals/{SECOND}">{SECOND}</a>') < text.index(
        f'<a href="/approvals/{FIRST}">{FIRST}</a>'
    )
    assert "2026-11-09T09:00:00Z" in text and "demo.note" in text
    assert f'<a href="/escalations/{raised.escalation_id}">{raised.escalation_id}</a>' in text
    assert "model_unavailable" in text
    assert "No pending approvals." not in text


def test_a_pending_approval(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "Milk", "tags": ["home"]}, 9)
    text = page.get(f"/approvals/{FIRST}").text
    for part in (
        FIRST,
        "step",
        "pending",
        f"run {RUN}",
        "requested 2026-11-09T09:00:00Z",
        "1. demo.note",
        "write",
        shown({"title": "Milk", "tags": ["home"]}),
    ):
        assert part in text


def test_a_decided_approval_shows_who_decided_and_the_edit(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "Milk"}, 9)
    decide_approval(
        db,
        Registry((demo.DOMAIN,)),
        FIRST,
        "edit",
        channel="terminal",
        decided_by="owner",
        note="fewer",
        edited_args={"title": "Eggs"},
    )
    text = page.get(f"/approvals/{FIRST}").text
    assert "edited by owner (terminal) at 2026-11-09T10:00:00Z" in text
    assert f"edited args: {shown({'title': 'Eggs'})}" in text
    assert "note: fewer" in text


def test_an_escalation_and_its_answer(db: Store, page: TestClient) -> None:
    raised = db.add_escalation(
        Escalation(
            kind="invalid_plan",
            detail="decision 3: the plan does not fit the registry",
            run_id=RUN,
            problems=(FieldProblem(loc="steps.0.args.title", code="string_too_short"),),
        )
    )
    path = f"/escalations/{raised.escalation_id}"
    before = page.get(path).text
    for part in ("invalid_plan", "open", f"run {RUN}", "the plan does not fit the registry"):
        assert part in before
    assert "steps.0.args.title: string_too_short" in before
    answer_escalation(
        db, raised.escalation_id, "cancel", channel="terminal", decided_by="owner", note="later"
    )
    after = page.get(path).text
    assert "cancel by owner (terminal) at 2026-11-09T10:00:00Z" in after
    assert "note: later" in after


@pytest.mark.parametrize(
    "path", [f"/approvals/{'9' * 32}", f"/escalations/{'9' * 32}", "/approvals/not-an-id"]
)
def test_what_is_not_there(db: Store, page: TestClient, path: str) -> None:
    response = page.get(path)
    assert (response.status_code, response.text) == (404, "Not found")


def test_text_from_a_request_is_escaped(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "<script>alert(1)</script>"}, 9)
    text = page.get(f"/approvals/{FIRST}").text
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:8765", "localhost"])
def test_only_this_server_by_name_is_answered(db: Store, host: str) -> None:
    client = TestClient(create_app(get_settings()), base_url=f"http://{host}")
    response = client.get("/")
    assert (response.status_code, response.text) == (400, "Bad host")
    assert response.headers["x-frame-options"] == "DENY"


def test_localhost_by_port_is_answered(db: Store) -> None:
    client = TestClient(create_app(get_settings()), base_url="http://localhost:8766")
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("path", ["/", f"/approvals/{'9' * 32}"])
def test_every_answer_carries_the_security_headers(db: Store, page: TestClient, path: str) -> None:
    response = page.get(path)
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "server" not in response.headers


def test_the_headers(db: Store) -> None:
    assert SECURITY_HEADERS == {
        "content-security-policy": (
            "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        ),
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "cache-control": "no-store",
    }


@pytest.mark.parametrize(
    ("method", "path"), [("post", "/"), ("get", "/docs"), ("get", "/openapi.json")]
)
def test_nothing_else_is_served(db: Store, page: TestClient, method: str, path: str) -> None:
    assert getattr(page, method)(path).status_code in (404, 405)


def test_a_store_that_cannot_be_read(tmp_path: Path, page: TestClient) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "conductor.db").write_text("not a database")
    response = page.get("/")
    assert (response.status_code, response.text) == (503, "The store is not available")
```

`tests/e2e/test_cli_web.py` (6 tests)

```python
import socket

import pytest
import uvicorn

from conductor.config import SettingsError, get_settings
from tests.support import run


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake_run(app, **options) -> None:
        calls.append({"app": app, **options})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return calls


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_the_default_port() -> None:
    assert (get_settings().web_port, get_settings().web_port_number) == ("8766", 8766)


def test_the_web_command_serves_on_this_machine_only(
    served: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(port))
    result = run("web")
    assert (result.exit_code, result.stdout) == (0, f"Serving on http://127.0.0.1:{port}/\n")
    [call] = served
    assert {key: call[key] for key in ("host", "port", "server_header", "proxy_headers")} == {
        "host": "127.0.0.1",
        "port": port,
        "server_header": False,
        "proxy_headers": False,
    }


def test_a_port_in_use_is_refused(served: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    port = taken.getsockname()[1]
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(port))
    try:
        result = run("web")
    finally:
        taken.close()
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        f"Error: port {port} is taken\n",
    )
    assert served == []


@pytest.mark.parametrize("value", ["80", "65536", "87a5"])
def test_a_bad_port_setting(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == "CONDUCTOR_WEB_PORT: must be a port from 1024 to 65535"
```

## Tests to write

In `tests/unit/test_views.py`, each with its deciding input:

- R2: for a pending request, a rejected one with a note, an edited one, an open escalation with two problems, and an answered one, `"\n".join(...)` equals the 4c block text (write each expected text out in the test).

In `tests/e2e/test_web_pages_more.py`:

- R3: a request with two `Host` headers (send them through a raw ASGI call) gives `400`; `localhost:8766` is answered.
- R4: the `405` of `POST /` and the `503` carry every header.
- R5: a plan approval of two steps shows both step lines; the home page lists two escalations oldest first.
- R6: a note and an escalation detail holding `<img src=x onerror=1>` appear escaped; the home page's actions are escaped too; no page contains `<script`, ` on`-attributes, or `http://` / `https://` URLs.
- R7: an id in capitals (`"A" * 32`) is `404` without the store being opened (replace `Store` with one that fails).

## Rules for this phase

- **Network** (`AGENTS.md` rule 3): the page binds 127.0.0.1 only; tests use `TestClient` and bind only `127.0.0.1` sockets they close; no outside URL anywhere.
- **No telemetry** (`AGENTS.md` rule 2): no analytics, no CDN, no fonts or scripts from elsewhere; the content policy forbids scripts entirely.
- **`web` is thin** (`AGENTS.md`): it reads the store and renders; no decisions, no graph, no runtime.
- **Critical module**: `web/app.py` joins `scripts/critical_modules.txt` and `docs/testing.md`.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 26 = 690 passed; `critical coverage` passed (it now includes `web/app.py`);
- the given files: `.venv/bin/python -m pytest tests/e2e/test_web_pages.py tests/e2e/test_cli_web.py --no-cov`, exactly `26 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/views.py,*/conductor/config.py,*/conductor/cli/main.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 7a`, after the progress entry: `Reports OK.`;
- `.venv/bin/python -c "import importlib.metadata as m; print(m.version('fastapi'), m.version('jinja2'), m.version('starlette'))"` prints `0.162.x 3.1.x 1.10.0`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/web | grep -v -E ":(from conductor\.config|from conductor\.store|from conductor\.views) import "`
  - `git grep --untracked -n -i -E "<script|\bon[a-z]+=|https?://" -- src/conductor/web/templates`
  - `git grep --untracked -n -E "0\.0\.0\.0|host=\"(::|localhost)\"" -- src`
  - `git grep --untracked -n -E "add_request|record_decision|\.answer\(|add_escalation|acquire\(" -- src/conductor/web`
- `git diff --stat HEAD -- src/conductor/store.py src/conductor/decisions.py src/conductor/runtime.py src/conductor/graph tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py tests/e2e/test_cli_approvals_more.py tests/e2e/test_cli_ask.py tests/support.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 7a: the approvals page, read-only (YYYY-MM-DD)`, with `Tests: 664 -> <passed> (given 26)`.
