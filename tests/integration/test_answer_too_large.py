import itertools
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor import clock, ids
from conductor.contracts import Contract
from conductor.decisions import answer_escalation
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import RunState, Services, build_graph, resume_run, start_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Registry
from conductor.store import Store

RUN = "a" * 32
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'


class BigRunner:
    def run(self, action: Action, args: Contract) -> dict:
        return {"text": "y" * 30_000}


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 10, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def test_a_too_large_answer_waits_for_the_person_and_can_be_cancelled(tmp_path: Path) -> None:
    store = Store(tmp_path / "conductor.db")
    log = EventLog(tmp_path / "runs")
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))])
    graph = build_graph(
        Services(
            registry=Registry((demo.DOMAIN,)),
            store=store,
            log=log,
            model=model,
            model_name="test-model:1b",
            runner=BigRunner(),
        ),
        InMemorySaver(),
    )
    state = start_run(graph, "demo: say hi", run_id=RUN)
    assert state.status == "waiting" and state.escalation_id is not None
    stored = store.escalation(state.escalation_id).escalation
    assert stored.kind == "answer_too_large"
    assert stored.detail.startswith("the step results are ")
    assert stored.detail.endswith(" bytes, more than 24000; ask for less")
    assert [request.point for request in model.requests] == ["plan"]
    escalated = [event for event in log.read(RUN) if event.kind is EventKind.ESCALATED]
    assert [event.payload["kind"] for event in escalated] == ["answer_too_large"]
    assert escalated[0].payload["retry_node"] == "answer"
    answer_escalation(store, state.escalation_id, "cancel", channel="terminal", decided_by="owner")
    assert resume_run(graph, store, RUN) == RunState(run_id=RUN, status="cancelled")
