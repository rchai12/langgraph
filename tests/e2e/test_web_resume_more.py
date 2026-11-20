import itertools
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import answer_escalation
from conductor.events import EventKind, EventLog
from conductor.graph.status import RunStateUnavailable
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.web.app import FORM_COOKIE, create_app

BASE = "http://127.0.0.1:8766"
TOKEN = "c" * 64
EMPTY = '{"steps":[]}'
BUTTON = '<button type="submit">Resume</button>'
FAILURE = "The last resume failed"


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

    def chat(self, request: object) -> ModelReply:
        raise RuntimeError("SYNTHETIC-SECRET")


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 3, 4, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def client(resumer: Still) -> TestClient:
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    page.cookies.set(FORM_COOKIE, TOKEN)
    return page


def post(page: TestClient, run_id: str):
    return page.post(
        f"/runs/{run_id}/resume",
        data={"token": TOKEN},
        follow_redirects=False,
    )


def escalation(answered: bool) -> str:
    with runtime.open_runtime(
        get_settings(),
        model=ScriptedModel([ScriptedReply("plan", ModelReply(content=EMPTY))]),
    ) as opened:
        state = runtime.ask(opened, "demo: do something")
        if answered:
            answer_escalation(
                opened.store,
                state.escalation_id,
                "cancel",
                channel="terminal",
                decided_by="owner",
            )
    return state.run_id


def failed_once() -> str:
    with runtime.open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        before = {item.run_id for item in opened.log.runs()}
        with pytest.raises(ScriptError):
            runtime.ask(opened, "demo: say hi")
        [run] = [item for item in opened.log.runs() if item.run_id not in before]
    run_id = run.run_id
    with runtime.open_runtime(get_settings(), model=Raising()) as opened:
        with pytest.raises(RuntimeError):
            runtime.resume(opened, run_id)
    return run_id


def test_an_answered_escalation_shows_the_button_and_an_open_one_does_not() -> None:
    answered = escalation(True)
    assert BUTTON in client(Still()).get(f"/runs/{answered}").text
    open_run = escalation(False)
    assert BUTTON not in client(Still()).get(f"/runs/{open_run}").text


def test_a_missing_or_unreadable_state_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    page = client(Still())
    missing = post(page, "b" * 32)
    assert (missing.status_code, missing.text) == (404, "Not found")

    def unavailable(settings: object, run_id: str) -> None:
        raise RunStateUnavailable(f"run {run_id} state is not available")

    monkeypatch.setattr(runtime, "read_state", unavailable)
    response = post(page, "a" * 32)
    assert (response.status_code, response.text) == (503, "The run state is not available")


def test_a_broken_log_and_a_non_text_type_show_no_failure() -> None:
    broken = failed_once()
    numbered = failed_once()
    path = get_settings().runs_dir / f"{broken}.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    broken_page = client(Still()).get(f"/runs/{broken}")
    assert (broken_page.status_code, FAILURE in broken_page.text) == (200, False)

    EventLog(get_settings().runs_dir).append(
        numbered,
        EventKind.ERROR,
        payload={"error": "resume_failed", "type": 5},
    )
    numbered_page = client(Still()).get(f"/runs/{numbered}")
    assert (numbered_page.status_code, FAILURE in numbered_page.text) == (200, False)


def test_a_busy_run_keeps_the_record_off_the_page() -> None:
    run_id = failed_once()
    text = client(Still(busy=True)).get(f"/runs/{run_id}").text
    assert FAILURE not in text
    assert BUTTON not in text
