import itertools
from datetime import UTC, datetime

import pytest

from conductor import clock, ids
from conductor.config import get_settings
from conductor.events import EventKind
from conductor.graph.supervisor import RESUMABLE_STOPS, RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import DemoRunner, ask, open_runtime, resume, state

ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def model(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies])


def test_the_resumable_stops() -> None:
    assert RESUMABLE_STOPS == ("route", "plan", "answer")


@pytest.mark.parametrize(
    ("request_text", "first", "then", "node"),
    [
        ("Say hi back to me", [], [("route", '{"domain": "demo"}'), ("plan", ECHO_PLAN)], "route"),
        ("demo: say hi", [], [("plan", ECHO_PLAN)], "plan"),
        ("demo: say hi", [("plan", ECHO_PLAN)], [], "answer"),
    ],
)
def test_a_run_stopped_at_a_model_call_runs_that_node_again(
    request_text: str, first: list, then: list, node: str
) -> None:
    with open_runtime(get_settings(), model=model(*first)) as one:
        with pytest.raises(Exception, match="no scripted reply left"):
            ask(one, request_text)
        [summary] = one.log.runs()
        assert state(one, summary.run_id).stopped_at == node
    with open_runtime(get_settings(), model=model(*then, ("answer", REPLY))) as two:
        assert resume(two, summary.run_id) == RunState(
            run_id=summary.run_id, status="done", reply="Done."
        )
        results = [e for e in two.log.read(summary.run_id) if e.kind == EventKind.TOOL_RESULT]
        assert len(results) == 1


def test_a_run_stopped_at_a_step_stays_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def broken(self, action, args):
        calls.append(action.name)
        raise RuntimeError("the runner broke")

    monkeypatch.setattr(DemoRunner, "run", broken)
    with open_runtime(get_settings(), model=model(("plan", ECHO_PLAN))) as opened:
        with pytest.raises(RuntimeError):
            ask(opened, "demo: say hi")
        [summary] = opened.log.runs()
        assert state(opened, summary.run_id).stopped_at == "run_step"
        with pytest.raises(RunError) as raised:
            resume(opened, summary.run_id)
        assert str(raised.value) == (
            f"run {summary.run_id} stopped at run_step and cannot be resumed"
        )
    assert calls == ["echo"]
