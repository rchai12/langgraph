import itertools
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.runtime import DemoRunner
from conductor.store import Store, StoreError
from conductor.web.app import FORM_COOKIE, create_app

BASE = "http://127.0.0.1:8766"
NOTE = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
ECHO = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'
TOKEN = "c" * 64
SECRET = "SYNTHETIC-SECRET"
BUTTON = '<button type="submit">Resume</button>'


class Still:
    def __init__(self, *, busy: bool = False, error: str | None = None) -> None:
        self.busy = busy
        self.last = error
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, run_id: str) -> bool:
        return self.busy

    def error(self, run_id: str) -> str | None:
        return self.last


class Raising(ScriptedModel):
    def __init__(self) -> None:
        super().__init__([])

    def chat(self, request):
        raise RuntimeError(SECRET)


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 3, 4, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def scripted(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel(
        [ScriptedReply(point, ModelReply(content=text)) for point, text in replies]
    )


def waiting(decided: bool) -> runtime.RunState:
    with runtime.open_runtime(get_settings(), model=scripted(("plan", NOTE))) as opened:
        state = runtime.ask(opened, "demo: note Milk")
        if decided:
            decide_approval(
                opened.store,
                opened.registry,
                state.approval_id,
                "approve",
                channel="terminal",
                decided_by="owner",
                note="",
            )
    return state


def stopped_at_plan() -> str:
    with runtime.open_runtime(get_settings(), model=scripted()) as opened:
        with pytest.raises(ScriptError):
            runtime.ask(opened, "demo: say hi")
        [run] = opened.log.runs()
    return run.run_id


def make(case: str, monkeypatch: pytest.MonkeyPatch) -> str:
    if case in ("decided", "undecided"):
        return waiting(case == "decided").run_id
    if case == "stopped at plan":
        return stopped_at_plan()
    if case == "stopped at a step":

        def broken(self, action, args):
            raise RuntimeError(SECRET)

        working = DemoRunner.run
        monkeypatch.setattr(DemoRunner, "run", broken)
        run_id = stopped_at_plan()
        with runtime.open_runtime(get_settings(), model=scripted(("plan", ECHO))) as opened:
            with pytest.raises(RuntimeError):
                runtime.resume(opened, run_id)
        monkeypatch.setattr(DemoRunner, "run", working)
        return run_id
    with runtime.open_runtime(
        get_settings(), model=scripted(("plan", ECHO), ("answer", REPLY))
    ) as opened:
        return runtime.ask(opened, "demo: say hi").run_id


def failed_once() -> str:
    run_id = stopped_at_plan()
    with runtime.open_runtime(get_settings(), model=Raising()) as opened:
        with pytest.raises(RuntimeError):
            runtime.resume(opened, run_id)
    return run_id


def client(resumer: Still) -> TestClient:
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    page.cookies.set(FORM_COOKIE, TOKEN)
    return page


def post(page: TestClient, run_id: str, **headers: str):
    return page.post(
        f"/runs/{run_id}/resume", data={"token": TOKEN}, headers=headers, follow_redirects=False
    )


@pytest.mark.parametrize(
    ("case", "busy", "shown"),
    [
        ("decided", False, True),
        ("decided", True, False),
        ("undecided", False, False),
        ("stopped at plan", False, True),
        ("stopped at a step", False, False),
        ("done", False, False),
    ],
)
def test_the_button_shows_only_when_a_resume_can_start(
    monkeypatch: pytest.MonkeyPatch, case: str, busy: bool, shown: bool
) -> None:
    run_id = make(case, monkeypatch)
    resumer = Still(busy=busy)
    text = client(resumer).get(f"/runs/{run_id}").text
    form = f'<form method="post" action="/runs/{run_id}/resume">'
    token = f'<input type="hidden" name="token" value="{TOKEN}">'
    assert (form in text, token in text, BUTTON in text) == (shown, shown, shown)
    assert resumer.started == []


def test_a_resume_post_starts_the_run_and_records_nothing() -> None:
    state = waiting(decided=True)
    store = Store(get_settings().db_path)
    before = store.approval(state.approval_id)
    resumer = Still()
    response = post(client(resumer), state.run_id)
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{state.run_id}")
    assert resumer.started == [state.run_id]
    assert store.approval(state.approval_id) == before


@pytest.mark.parametrize("case", ["busy", "undecided", "done"])
def test_a_post_that_cannot_start_only_redirects(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    run_id = make("decided" if case == "busy" else case, monkeypatch)
    resumer = Still(busy=case == "busy")
    response = post(client(resumer), run_id)
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{run_id}")
    assert resumer.started == []
    if case == "undecided":
        [pending] = Store(get_settings().db_path).pending()
        assert Store(get_settings().db_path).approval(pending.approval_id).decision is None


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("token", (403, "Bad form token")),
        ("origin", (403, "Bad origin")),
        ("id", (404, "Not found")),
    ],
)
def test_a_post_is_checked_like_every_form(change: str, expected: tuple[int, str]) -> None:
    state = waiting(decided=True)
    resumer = Still()
    page = client(resumer)
    run_id = "X" * 32 if change == "id" else state.run_id
    if change == "token":
        page.cookies.set(FORM_COOKIE, "d" * 64)
    headers = {"origin": "http://evil.example"} if change == "origin" else {}
    response = post(page, run_id, **headers)
    assert (response.status_code, response.text) == expected
    assert resumer.started == []


@pytest.mark.parametrize(
    ("kept", "shown"),
    [
        (None, "The last resume failed: the resume failed (RuntimeError)"),
        ("the resume failed", "The last resume failed: the resume failed (RuntimeError)"),
        ("run {run_id} is busy", "The last resume failed: run {run_id} is busy"),
    ],
    ids=["after-restart", "same-failure", "newer-failure"],
)
def test_the_recorded_failure_is_shown(kept: str | None, shown: str) -> None:
    run_id = failed_once()
    error = None if kept is None else kept.format(run_id=run_id)
    text = client(Still(error=error)).get(f"/runs/{run_id}").text
    assert shown.format(run_id=run_id) in text
    assert text.count("The last resume failed") == 1
    assert SECRET not in text
    assert BUTTON in text


def test_a_record_followed_by_a_success_is_not_shown() -> None:
    run_id = failed_once()
    with runtime.open_runtime(
        get_settings(), model=scripted(("plan", ECHO), ("answer", REPLY))
    ) as opened:
        assert runtime.resume(opened, run_id).status == "done"
    text = client(Still()).get(f"/runs/{run_id}").text
    assert "The last resume failed" not in text


def test_a_store_that_fails_hides_the_button_and_refuses_the_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = waiting(decided=True)

    def unavailable(self, approval_id):
        raise StoreError("conductor.db: busy")

    monkeypatch.setattr(Store, "approval", unavailable)
    resumer = Still()
    page = client(resumer)
    shown = page.get(f"/runs/{state.run_id}")
    assert (shown.status_code, BUTTON in shown.text) == (200, False)
    response = post(page, state.run_id)
    assert (response.status_code, response.text) == (503, "The store is not available")
    assert resumer.started == []
