import itertools
from datetime import UTC, datetime, timedelta

import pytest

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import RunError
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.runtime import DemoRunner, ask, open_runtime, resume, state

ECHO = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'
OTHER = "f" * 32
SECRET = "SYNTHETIC-SECRET"
START = datetime(2031, 3, 4, 9, 0, tzinfo=UTC)
NOW = [START]


class Raising(ScriptedModel):
    """Raises `error` from every chat, after an optional `before()`."""

    def __init__(self, error: BaseException, before=None) -> None:
        super().__init__([])
        self.error = error
        self.before = before

    def chat(self, request):
        if self.before is not None:
            self.before()
        raise self.error


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    NOW[0] = START
    monkeypatch.setattr(clock, "now", lambda: NOW[0])
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def stopped_at_plan() -> str:
    with open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        with pytest.raises(ScriptError):
            ask(opened, "demo: say hi")
        [run] = opened.log.runs()
    return run.run_id


def events(run_id: str) -> list[tuple[str, str | None, dict]]:
    log = EventLog(get_settings().runs_dir)
    return [(event.kind.value, event.node, event.payload) for event in log.read(run_id)]


def records(run_id: str) -> list[dict]:
    return [
        payload
        for kind, node, payload in events(run_id)
        if kind == "error" and payload.get("error") == "resume_failed"
    ]


def test_the_failure_code() -> None:
    assert runtime.RESUME_FAILED == "resume_failed"


def test_a_failed_resume_records_its_type_and_not_its_text() -> None:
    run_id = stopped_at_plan()
    before = events(run_id)
    error = RuntimeError(SECRET)
    with open_runtime(get_settings(), model=Raising(error)) as opened:
        with pytest.raises(RuntimeError) as raised:
            resume(opened, run_id)
        assert raised.value is error
        assert state(opened, run_id).stopped_at == "plan"
        opened.store.acquire(run_id, OTHER)
    after = events(run_id)
    assert after[: len(before)] == before
    assert after[-1] == ("error", None, {"error": "resume_failed", "type": "RuntimeError"})
    assert [(kind, node) for kind, node, _payload in after[len(before) :]] == [
        ("model_request", "plan"),
        ("error", None),
    ]
    path = get_settings().runs_dir / f"{run_id}.jsonl"
    assert SECRET not in path.read_text(encoding="utf-8")


def test_each_failed_resume_is_recorded_once() -> None:
    run_id = stopped_at_plan()
    for error in (RuntimeError("one"), ValueError("two")):
        with open_runtime(get_settings(), model=Raising(error)) as opened:
            with pytest.raises(type(error)):
                resume(opened, run_id)
    assert records(run_id) == [
        {"error": "resume_failed", "type": "RuntimeError"},
        {"error": "resume_failed", "type": "ValueError"},
    ]


def test_a_resume_that_then_succeeds_leaves_the_record_behind_it() -> None:
    run_id = stopped_at_plan()
    with open_runtime(get_settings(), model=Raising(RuntimeError("x"))) as opened:
        with pytest.raises(RuntimeError):
            resume(opened, run_id)
    replies = [ScriptedReply("plan", ModelReply(content=ECHO))]
    replies.append(ScriptedReply("answer", ModelReply(content=REPLY)))
    with open_runtime(get_settings(), model=ScriptedModel(replies)) as opened:
        assert resume(opened, run_id).status == "done"
    assert len(records(run_id)) == 1
    assert events(run_id)[-1][0] != "error"


def test_a_refused_resume_records_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def broken(self, action, args):
        calls.append(action.name)
        raise RuntimeError(SECRET)

    monkeypatch.setattr(DemoRunner, "run", broken)
    with open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        with pytest.raises(ScriptError):
            ask(opened, "demo: say hi")
    [stopped] = EventLog(get_settings().runs_dir).runs()
    with open_runtime(
        get_settings(), model=ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO))])
    ) as opened:
        with pytest.raises(RuntimeError):
            resume(opened, stopped.run_id)
        assert state(opened, stopped.run_id).stopped_at == "run_step"
    before = events(stopped.run_id)
    with open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        with pytest.raises(RunError) as refused:
            resume(opened, stopped.run_id)
        opened.store.acquire(stopped.run_id, OTHER)
        with pytest.raises(RunError) as busy:
            resume(opened, stopped.run_id)
    assert str(refused.value) == f"run {stopped.run_id} stopped at run_step and cannot be resumed"
    assert str(busy.value) == f"run {stopped.run_id} is busy"
    assert events(stopped.run_id) == before
    assert calls == ["echo"]
    assert records(stopped.run_id) == [{"error": "resume_failed", "type": "RuntimeError"}]


def test_a_start_that_fails_records_nothing() -> None:
    run_id = stopped_at_plan()
    assert records(run_id) == []


class Stealing(ScriptedModel):
    """Answers like ScriptedModel, then calls `steal` (set by the test) after each chat."""

    steal = None

    def chat(self, request):
        reply = super().chat(request)
        if self.steal is not None:
            self.steal()
        return reply


def test_a_resume_that_loses_its_lease_records_nothing() -> None:
    run_id = stopped_at_plan()
    model = Stealing([ScriptedReply("plan", ModelReply(content=ECHO))])
    with open_runtime(get_settings(), model=model) as opened:

        def steal() -> None:
            NOW[0] = START + timedelta(seconds=601)
            opened.store.acquire(run_id, OTHER)

        model.steal = steal
        with pytest.raises(RunError) as raised:
            resume(opened, run_id)
    assert str(raised.value) == f"run {run_id} lost its lease"
    assert records(run_id) == []


def test_an_interrupt_is_not_recorded() -> None:
    run_id = stopped_at_plan()
    with open_runtime(get_settings(), model=Raising(KeyboardInterrupt())) as opened:
        with pytest.raises(KeyboardInterrupt):
            resume(opened, run_id)
        opened.store.acquire(run_id, OTHER)
    assert records(run_id) == []


def test_a_record_that_cannot_be_written_keeps_the_first_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = stopped_at_plan()
    real_append = EventLog.append

    def failing(self, run, kind, *, node=None, payload=None):
        if kind == EventKind.ERROR and node is None:
            raise OSError("disk full")
        return real_append(self, run, kind, node=node, payload=payload)

    monkeypatch.setattr(EventLog, "append", failing)
    error = RuntimeError(SECRET)
    with open_runtime(get_settings(), model=Raising(error)) as opened:
        with pytest.raises(RuntimeError) as raised:
            resume(opened, run_id)
        assert raised.value is error
        opened.store.acquire(run_id, OTHER)
    assert records(run_id) == []
