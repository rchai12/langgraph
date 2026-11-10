# Phase 7b: deciding on the page

## Goal

The approvals page can now decide, through exactly the path the terminal uses:

- forms under each pending approval (**approve**, **reject**, and, for a step, **edit** with the arguments as a JSON text box) and each open escalation (**retry**, **cancel**), each with an optional note;
- every form is checked first: **its origin**, then **a form token** that must match a cookie the page set (as `finances` does); a forged form records nothing;
- the decision is recorded by `conductor.decisions` with the channel `web` and `CONDUCTOR_DECIDED_BY`, then the run **resumes in a background thread** under its lease;
- a **run page**, `/runs/<run_id>`, shows where the run is, refreshing itself every 5 seconds while it is busy, and the last resume's error, if any.

Decided with the owner (2026-11-09): edited arguments come as **a JSON text box**, checked like the terminal's `--args`; the detail page **is the confirmation** (one press records, as the full block of what will be allowed is on that page); after a decision the browser goes to **a run page that refreshes while busy**. Earlier (7a): this Mac only, no login; resume in the background.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 7), `docs/architecture.md` ("Approvals and escalations")
- `src/conductor/web/app.py` (7a), `src/conductor/decisions.py`, `src/conductor/cli/main.py` (`_json_object`, the decision commands), `src/conductor/runtime.py`, `../finances/src/finances/web/forms.py` (`forged`: the origin and token check this phase copies)

## Starting state

Phase 7a is built and verified, and everything is committed: N is `704`. **Sections: cli, core.** No new dependency (`python-multipart`, which form parsing needs, is installed through `mcp`).

## Scope

| Path | What |
|---|---|
| `src/conductor/decisions.py` | `parse_json_object` (Part 1) |
| `src/conductor/cli/main.py` | `edit --args` parses through `parse_json_object` (unchanged output) |
| `src/conductor/web/app.py` | `FORM_COOKIE`, the forms, the `POST` routes, the run page, `create_app(settings, *, resumer=None)` (Parts 2 and 3, critical) |
| `src/conductor/web/jobs.py` | `Resumer` (Part 4, critical) |
| `src/conductor/web/templates/*.html` | the forms, the run page, the problem page |
| `scripts/critical_modules.txt` | add the line `web/jobs.py` after `web/app.py` |
| `docs/testing.md` | under "Critical modules", add `` - `web/jobs.py` (a run resumed from the page runs under its lease, and its failure is kept, not lost; Phase 7b) `` after the `web/app.py` line |
| `tests/e2e/test_web_decide.py`, `tests/e2e/test_web_runs.py` | given |
| `tests/e2e/test_web_decide_more.py`, `tests/unit/test_resumer.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- A login, sessions, remote access; a confirmation page; per-field edit forms; deciding several requests at once.
- Cancelling or stopping a run in progress; resuming a stopped run from the page beyond what `runtime.resume` already allows (5e).
- Scripts of any kind (the refresh is a `<meta>` tag); runs other than the one a decision belongs to; a list of runs.
- Changes to `decisions`' rules, the store, the policy, the runtime, or what the terminal prints.

## Dependencies

None new.

## Design

```python
# conductor/decisions.py: added
def parse_json_object(text: str) -> dict[str, Any] | None: ...
```

`json.loads(text, parse_constant=<refuse>)`: a result that is a dict is returned; anything else, including `NaN`, `Infinity`, `-Infinity`, and text that does not parse, gives `None`. The terminal's `edit --args` uses it and prints its 4c error on `None`.

```python
# conductor/web/app.py (critical): added
FORM_COOKIE = "conductor_form"

def create_app(settings: Settings, *, resumer: Resumer | None = None) -> ASGIApp: ...   # None: Resumer(settings)
```

**The form token.** Every HTML page reads the cookie `FORM_COOKIE`; when it is missing or does not fully match `^[0-9a-f]{64}$`, the page makes a new token with `secrets.token_hex(32)` and sets it with `set_cookie(FORM_COOKIE, token, httponly=True, samesite="strict", path="/")`. Every form on the page carries the token as `<input type="hidden" name="token" value="<token>">`.

**The forms**, each `<form method="post" action="<path>">` with an optional `note` field (`<textarea name="note">`) and a submit button:

| Page | When | Forms (`<path>`) |
|---|---|---|
| `/approvals/<id>` | the request has no decision | `/approvals/<id>/approve`, `/approvals/<id>/reject`, and, for a `step` request only, `/approvals/<id>/edit` with `<textarea name="args">` holding `json.dumps(<the step's args>, ensure_ascii=False, sort_keys=True)` |
| `/escalations/<id>` | the escalation has no answer | `/escalations/<id>/retry`, `/escalations/<id>/cancel` |

A decided request or an answered escalation shows no form.

**A `POST` to one of those paths**, in this order:

1. an `<id>` that does not fully match `^[0-9a-f]{32}$`: `404 Not found`;
2. an `Origin` header that is present and not `http://127.0.0.1:<port>` or `http://localhost:<port>`: `403 Bad origin`;
3. a `FORM_COOKIE` that does not fully match `^[0-9a-f]{64}$`, or a `token` field that is missing or not equal to it under `hmac.compare_digest`: `403 Bad form token`;
4. the decision, through `decide_approval` or `answer_escalation` with `Store(settings.db_path)`, `Registry(domains.registered(settings))`, `channel="web"`, `decided_by=settings.decided_by`, the `note`, and for `edit` the arguments from `parse_json_object` (`None` gives `400` with `The arguments must be a JSON object.` before anything is decided);
5. on success: `resumer.start(<the request's or escalation's run_id>)`, then `303` to `/runs/<run_id>`.

The other outcomes of step 4: `NotFound` is `404 Not found`; `AlreadyDecided` is `409`; a note too long (`ValueError`), `DecisionRefused`, and `NotRegistered` are `400`; `StoreError` is `503 The store is not available`. The `409` and `400` answers are an HTML page showing the error's message (`str(error)`, which `decisions`, the policy, and the store keep to constant text and ids), each of a `DecisionRefused`'s problems as `<loc>: <code>`, and a link back to the request or escalation.

**The run page**, `GET /runs/<run_id>`: an id that does not fully match is `404 Not found`. Otherwise it opens `runtime.open_runtime(settings)` and reads `runtime.state` (no tool check, no lease); a `RunError` is `404 Not found`. It shows, in order:

| Case | Shows |
|---|---|
| `resumer.running(run_id)` | `busy`, and `<meta http-equiv="refresh" content="5">` in the head |
| waiting at an approval or an escalation | `waiting`, and `<a href="/approvals/<id>">` or `<a href="/escalations/<id>">` |
| done, rejected, cancelled, stopped | the status, and the reply, the note, or the node |
| `resumer.error(run_id)` is not `None` | `The last resume failed: <error>` |

Only a busy run's page refreshes.

```python
# conductor/web/jobs.py (critical)
class Resumer:
    def __init__(self, settings: Settings) -> None: ...
    def start(self, run_id: str) -> None: ...      # one thread per run; a second start while it runs does nothing
    def running(self, run_id: str) -> bool: ...
    def error(self, run_id: str) -> str | None: ...
    def join(self, run_id: str, timeout: float | None = None) -> None: ...
```

`start` clears the run's last error and starts a thread (not a daemon, so a stopping server lets it finish) that runs `with runtime.open_runtime(settings) as opened: runtime.resume(opened, run_id)`, read through the module. A `RunError` or `ToolCheckFailed` is kept as `str(error)`; any other exception is kept as `the resume failed` (its text is never kept). The state is guarded by one lock.

## Facts about FastAPI and the test client

Found on 2026-11-09 with fastapi 0.162.2, starlette 1.10.0, python-multipart 0.0.33:

- `response.set_cookie(name, value, httponly=True, samesite="strict", path="/")` sends `name=value; HttpOnly; Path=/; SameSite=strict`.
- `TestClient(app, base_url="http://127.0.0.1:8766")` keeps a cookie the app sets for host `127.0.0.1` and sends it back; `client.cookies.clear()` and `client.cookies.set(name, value)` change what it sends.
- A form `POST` through `TestClient` arrives with its `data` as form fields (`await request.form()`, or `Form()` parameters) and its `headers` as given, `Origin` included; without `headers` no `Origin` is sent, as with some browsers on same-origin requests (hence step 2 refuses a wrong origin, not a missing one).
- The 7a test client lowercases a `Host` of `LOCALHOST:<port>` before the app sees it; a raw `LOCALHOST:<port>` is refused (the 7a verifier's note).

## Requirements

### Part 1: one parser

- **R1.** `parse_json_object` is as under Design; `edit --args` uses it and prints exactly what it printed in 4c.

### Part 2: the forms (critical)

- **R2.** Every HTML page sets the form token cookie when the request lacks a valid one, and every form carries the token in force.
- **R3.** The forms appear exactly as under Design: on undecided requests and unanswered escalations only, and `edit` only for a `step`.
- **R4.** A `POST` goes through the Design's five steps in order; a form refused at step 1, 2, or 3 reads nothing from the store and records nothing.
- **R5.** A decision is recorded only through `decide_approval` or `answer_escalation`, with `channel="web"` and the setting's `decided_by`; the page never calls the store's write methods, the policy, or the graph itself.
- **R6.** The outcomes of step 4 are answered as under Design; a refused edit records nothing.

### Part 3: the run page (critical)

- **R7.** `/runs/<run_id>` shows what the Design's table says, and refreshes only while busy.

### Part 4: the resumer (critical)

- **R8.** `Resumer` resumes through `runtime.resume` under the lease, in one non-daemon thread per run, keeps the last error as under Design, and never lets an exception out of its thread.
- **R9.** A decision answered `303` has started exactly one resume of its run; a refused one starts none.

### Part 5: the rules

- **R10.** `conductor/web/` imports from the project only `conductor` (for `domains` and `runtime`), `conductor.config`, `conductor.decisions`, `conductor.graph.supervisor` (`RunError`, `RunState`), `conductor.mcp_client.check` (`ToolCheckFailed`), `conductor.policy` (`DecisionRefused`), `conductor.registry`, `conductor.store`, and `conductor.views`.
- **R11.** `web/app.py` and `web/jobs.py` reach 100% of lines and branches, `web/jobs.py` joins the critical modules, and `decisions.py` and `cli/main.py` stay at 100%.

## Given tests

30 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong. The run tests make real runs with `runtime.ask` and `ScriptedModel`, and one resumes in a real background thread.

`tests/e2e/test_web_decide.py` (23 tests)

```python
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from conductor import clock
from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.store import Store
from conductor.web.app import FORM_COOKIE, create_app

FIRST = "1" * 32
RUN = "a" * 32
BASE = "http://127.0.0.1:8766"


class FakeResumer:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, run_id: str) -> bool:
        return False

    def error(self, run_id: str) -> str | None:
        return None


@pytest.fixture(autouse=True)
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 10, 0, tzinfo=UTC))


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


@pytest.fixture
def resumer() -> FakeResumer:
    return FakeResumer()


@pytest.fixture
def page(resumer: FakeResumer) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)


def add(db: Store, stage: str = "step", args: dict | None = None) -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args=args or {"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id=RUN,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )


def token(page: TestClient, path: str) -> str:
    """Open the page the form is on, as a browser would, and read its form token."""
    response = page.get(path)
    found = re.search(r'name="token" value="([0-9a-f]{64})"', response.text)
    assert found is not None
    assert page.cookies[FORM_COOKIE] == found.group(1)
    return found.group(1)


def post(page: TestClient, path: str, form: dict, origin: str | None = BASE):
    headers = {} if origin is None else {"origin": origin}
    return page.post(path, data=form, headers=headers, follow_redirects=False)


def test_a_pending_step_has_its_forms(db: Store, page: TestClient) -> None:
    add(db, args={"title": "<b>Milk</b>"})
    response = page.get(f"/approvals/{FIRST}")
    text = response.text
    for action in ("approve", "reject", "edit"):
        assert f'<form method="post" action="/approvals/{FIRST}/{action}">' in text
    assert str(escape(json.dumps({"title": "<b>Milk</b>"}, sort_keys=True))) in text
    cookie = response.headers["set-cookie"]
    assert f"{FORM_COOKIE}=" in cookie
    for flag in ("HttpOnly", "Path=/", "SameSite=strict"):
        assert flag in cookie


def test_a_plan_cannot_be_edited_and_a_decided_request_has_no_forms(
    db: Store, page: TestClient
) -> None:
    add(db, stage="plan")
    text = page.get(f"/approvals/{FIRST}").text
    assert f'action="/approvals/{FIRST}/approve"' in text
    assert f'action="/approvals/{FIRST}/edit"' not in text
    post(page, f"/approvals/{FIRST}/reject", {"token": token(page, f"/approvals/{FIRST}")})
    assert "<form" not in page.get(f"/approvals/{FIRST}").text


def test_approve_records_from_the_web_and_resumes(
    db: Store, page: TestClient, resumer: FakeResumer
) -> None:
    add(db)
    response = post(
        page, f"/approvals/{FIRST}/approve", {"token": token(page, f"/approvals/{FIRST}")}
    )
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{RUN}")
    decision = db.approval(FIRST).decision
    assert (decision.verdict, decision.channel, decision.decided_by) == ("approve", "web", "owner")
    assert resumer.started == [RUN]


def test_an_edit_carries_its_note_and_arguments(db: Store, page: TestClient) -> None:
    add(db)
    form = {
        "token": token(page, f"/approvals/{FIRST}"),
        "args": '{"title": "Eggs"}',
        "note": "fewer",
    }
    assert post(page, f"/approvals/{FIRST}/edit", form).status_code == 303
    decision = db.approval(FIRST).decision
    assert (decision.verdict, decision.edited_args, decision.note) == (
        "edit",
        {"title": "Eggs"},
        "fewer",
    )


@pytest.mark.parametrize("args", ["[1]", "not json", '{"title": NaN}'])
def test_edited_arguments_must_be_a_json_object(
    db: Store, page: TestClient, resumer: FakeResumer, args: str
) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "args": args}
    response = post(page, f"/approvals/{FIRST}/edit", form)
    assert response.status_code == 400
    assert "The arguments must be a JSON object." in response.text
    assert (db.approval(FIRST).decision, resumer.started) == (None, [])


def test_an_edit_the_action_refuses_lists_its_problems(db: Store, page: TestClient) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "args": '{"title": ""}'}
    response = post(page, f"/approvals/{FIRST}/edit", form)
    assert response.status_code == 400
    assert "decision refused: invalid_edit" in response.text
    assert "title: string_too_short" in response.text
    assert db.approval(FIRST).decision is None


@pytest.mark.parametrize("sent", [None, "0" * 64, "short"])
def test_a_form_without_its_token_is_refused(
    db: Store, page: TestClient, resumer: FakeResumer, sent: str | None
) -> None:
    add(db)
    token(page, f"/approvals/{FIRST}")
    form = {} if sent is None else {"token": sent}
    response = post(page, f"/approvals/{FIRST}/approve", form)
    assert (response.status_code, response.text) == (403, "Bad form token")
    assert response.headers["x-frame-options"] == "DENY"
    assert (db.approval(FIRST).decision, resumer.started) == (None, [])


def test_a_token_without_its_cookie_is_refused(db: Store, page: TestClient) -> None:
    add(db)
    sent = token(page, f"/approvals/{FIRST}")
    page.cookies.clear()
    response = post(page, f"/approvals/{FIRST}/approve", {"token": sent})
    assert (response.status_code, response.text) == (403, "Bad form token")


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        ("http://evil.example", 403),
        ("http://127.0.0.1:8765", 403),
        ("http://localhost:8766", 303),
        (None, 303),
    ],
)
def test_the_origin_of_a_form(db: Store, page: TestClient, origin: str | None, status: int) -> None:
    add(db)
    response = post(
        page, f"/approvals/{FIRST}/approve", {"token": token(page, f"/approvals/{FIRST}")}, origin
    )
    assert response.status_code == status
    if status == 403:
        assert response.text == "Bad origin"
        assert db.approval(FIRST).decision is None


def test_a_second_decision_is_refused(db: Store, page: TestClient, resumer: FakeResumer) -> None:
    add(db)
    sent = token(page, f"/approvals/{FIRST}")
    post(page, f"/approvals/{FIRST}/approve", {"token": sent})
    again = post(page, f"/approvals/{FIRST}/reject", {"token": sent})
    assert again.status_code == 409
    assert f"approval {FIRST} is already decided" in again.text
    assert db.approval(FIRST).decision.verdict == "approve"
    assert resumer.started == [RUN]


def test_a_note_too_long_is_refused(db: Store, page: TestClient) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "note": "x" * 501}
    response = post(page, f"/approvals/{FIRST}/reject", form)
    assert response.status_code == 400
    assert "note must be at most 500 characters" in response.text


@pytest.mark.parametrize("answer", ["retry", "cancel"])
def test_an_escalation_is_answered_from_the_web(
    db: Store, page: TestClient, resumer: FakeResumer, answer: str
) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    path = f"/escalations/{raised.escalation_id}"
    assert f'<form method="post" action="{path}/{answer}">' in page.get(path).text
    response = post(page, f"{path}/{answer}", {"token": token(page, path), "note": "ok"})
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{RUN}")
    stored = db.escalation(raised.escalation_id).answer
    assert (stored.answer, stored.channel, stored.note) == (answer, "web", "ok")
    assert resumer.started == [RUN]


@pytest.mark.parametrize(
    "path",
    [f"/approvals/{'9' * 32}/approve", "/approvals/nope/approve", f"/escalations/{'9' * 32}/retry"],
)
def test_deciding_what_is_not_there(db: Store, page: TestClient, path: str) -> None:
    add(db)
    response = post(page, path, {"token": token(page, f"/approvals/{FIRST}")})
    assert (response.status_code, response.text) == (404, "Not found")
```

`tests/e2e/test_web_runs.py` (7 tests)

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor import runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.web.app import create_app
from conductor.web.jobs import Resumer

BASE = "http://127.0.0.1:8766"
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'


class StillResuming:
    def __init__(self, *, busy: bool = False, error: str | None = None) -> None:
        self.busy = busy
        self.last = error

    def start(self, run_id: str) -> None:
        pass

    def running(self, run_id: str) -> bool:
        return self.busy

    def error(self, run_id: str) -> str | None:
        return self.last


@pytest.fixture(autouse=True)
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def waiting_run() -> runtime.RunState:
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE_PLAN))])
    with runtime.open_runtime(get_settings(), model=model) as opened:
        return runtime.ask(opened, "demo: note Milk")


def test_a_waiting_run_links_to_what_it_waits_for() -> None:
    state = waiting_run()
    page = TestClient(create_app(get_settings(), resumer=StillResuming()), base_url=BASE)
    text = page.get(f"/runs/{state.run_id}").text
    assert f'<a href="/approvals/{state.approval_id}">' in text
    assert "waiting" in text
    assert "refresh" not in text


def test_a_busy_run_refreshes_itself() -> None:
    state = waiting_run()
    page = TestClient(create_app(get_settings(), resumer=StillResuming(busy=True)), base_url=BASE)
    text = page.get(f"/runs/{state.run_id}").text
    assert '<meta http-equiv="refresh" content="5">' in text
    assert "busy" in text


def test_the_last_resume_error_is_shown() -> None:
    state = waiting_run()
    resumer = StillResuming(error=f"run {state.run_id} is busy")
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    assert (
        f"The last resume failed: run {state.run_id} is busy"
        in page.get(f"/runs/{state.run_id}").text
    )


@pytest.mark.parametrize("run_id", ["9" * 32, "nope"])
def test_a_run_that_is_not_there(run_id: str) -> None:
    page = TestClient(create_app(get_settings(), resumer=StillResuming()), base_url=BASE)
    response = page.get(f"/runs/{run_id}")
    assert (response.status_code, response.text) == (404, "Not found")


def test_a_decision_resumes_the_run_in_the_background(tmp_path: Path) -> None:
    state = waiting_run()
    resumer = Resumer(get_settings())
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    form_page = page.get(f"/approvals/{state.approval_id}").text
    sent = form_page.split('name="token" value="')[1].split('"')[0]
    response = page.post(
        f"/approvals/{state.approval_id}/approve",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert response.status_code == 303
    resumer.join(state.run_id, timeout=30)
    assert (resumer.running(state.run_id), resumer.error(state.run_id)) == (False, None)
    with runtime.open_runtime(get_settings()) as opened:
        after = runtime.state(opened, state.run_id)
        request = opened.store.approval(after.approval_id).request
    assert (after.status, request.stage) == ("waiting", "step")
    text = page.get(f"/runs/{state.run_id}").text
    assert f'<a href="/approvals/{after.approval_id}">' in text


def test_a_resume_that_fails_is_recorded_not_raised() -> None:
    resumer = Resumer(get_settings())
    resumer.start("9" * 32)
    resumer.join("9" * 32, timeout=30)
    assert resumer.error("9" * 32) == f"no run {'9' * 32}"
```

## Tests to write

In `tests/unit/test_resumer.py`, each with its deciding input:

- R8: a second `start` while the first resume runs starts no second thread (replace `runtime.resume` with one that waits on an event); an exception other than `RunError` is kept as `the resume failed` and its text is not; a `ToolCheckFailed` is kept as `the tool check failed`; `start` after a failure clears the error.
- R8: the thread is not a daemon.

In `tests/e2e/test_web_decide_more.py`:

- R1: `parse_json_object` of `{}`, `[]`, `"x"`, `{"a": Infinity}`, and `{"a": -Infinity}`.
- R2: a page opened with a valid cookie sets no new one and its forms carry that cookie's value.
- R4: a refused form (bad token) does not open the store (replace `Store` with one that fails).
- R6: `NotRegistered` (the demo setting off, so `demo.note` is not registered) is `400`; a store that cannot be read is `503`; the `409` page links back to the request.
- R7: done (with its reply escaped), rejected with a note, cancelled, and stopped at `answer` each show their line.
- R9: a `400` and a `409` start no resume.

## Rules for this phase

- **Side effects need approval** (`AGENTS.md` rule 7): the page records decisions only through `conductor.decisions`, after its origin and token checks, and every recorded decision is judged by the policy there.
- **Network**: unchanged (127.0.0.1 only); no scripts; the refresh is a `<meta>` tag the content policy allows.
- **`web` is thin**: forms, checks, `decisions`, `runtime`; no decision logic of its own.
- **Critical modules**: `web/jobs.py` joins `scripts/critical_modules.txt` and `docs/testing.md`; `web/app.py` stays critical.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 30 = 734 passed; `critical coverage` passed (it now includes `web/jobs.py`);
- the given files: `.venv/bin/python -m pytest tests/e2e/test_web_decide.py tests/e2e/test_web_runs.py --no-cov`, exactly `30 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 7b`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/web | grep -v -E ":from conductor(\.config|\.decisions|\.graph\.supervisor|\.mcp_client\.check|\.policy|\.registry|\.store|\.views)? import "`
  - `git grep --untracked -n -E "add_request|record_decision|\.answer\(|add_escalation|apply_decision|start_run|resume_run" -- src/conductor/web`
  - `git grep --untracked -n -i -E "<script|\bon[a-z]+=|https?://" -- src/conductor/web/templates`
  - `git grep --untracked -n -E "daemon=True" -- src/conductor/web`
- `git diff --stat HEAD -- src/conductor/store.py src/conductor/policy.py src/conductor/runtime.py src/conductor/graph tests/e2e/test_web_pages.py tests/e2e/test_cli_approvals.py tests/e2e/test_cli_ask.py tests/support.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 7b: deciding on the page (YYYY-MM-DD)`, with `Tests: 704 -> <passed> (given 30)`.
