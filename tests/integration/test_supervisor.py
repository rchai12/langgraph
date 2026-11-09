import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import utils

from conductor import clock, ids
from conductor.contracts import Contract
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import (
    NODES,
    RunError,
    RunState,
    Services,
    StepFailed,
    build_graph,
    resume_run,
    run_state,
    start_run,
)
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Registry
from conductor.routing.route import REQUEST_MESSAGE
from conductor.store import Store

RUN = "f" * 32
NOTE_ID = "e" * 32


class FakeRunner:
    """Runs demo steps in memory and records each call; fails the first `failures` calls."""

    def __init__(self, failures: int = 0, outputs: dict | None = None) -> None:
        self.calls: list[tuple[str, Contract]] = []
        self.tracing: list[bool] = []
        self.failures = failures
        self.outputs = outputs or {}

    def run(self, action: Action, args: Contract) -> dict:
        self.calls.append((action.name, args))
        self.tracing.append(utils.tracing_is_enabled())
        if len(self.calls) <= self.failures:
            raise StepFailed()
        if action.name in self.outputs:
            return self.outputs[action.name]
        if action.name == "echo":
            return {"text": args.text}
        if action.name == "note":
            return {"note_id": NOTE_ID}
        return {"summary": "done"}


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


class World:
    def __init__(self, tmp_path: Path, replies: list[tuple[str, object]], runner: FakeRunner):
        self.store = Store(tmp_path / "conductor.db")
        self.log = EventLog(tmp_path / "runs")
        self.model = ScriptedModel(
            [
                ScriptedReply(
                    point,
                    reply if isinstance(reply, ModelUnavailable) else ModelReply(content=reply),
                )
                for point, reply in replies
            ]
        )
        self.runner = runner
        self.graph = build_graph(
            Services(
                registry=Registry((demo.DOMAIN,)),
                store=self.store,
                log=self.log,
                model=self.model,
                model_name="test-model:1b",
                runner=runner,
            ),
            InMemorySaver(),
        )

    def start(self, request: str) -> RunState:
        return start_run(self.graph, request, run_id=RUN)

    def resume(self) -> RunState:
        return resume_run(self.graph, self.store, RUN)

    def decide(self, state: RunState, verdict: str = "approve", **extra: object) -> None:
        decide_approval(
            self.store,
            Registry((demo.DOMAIN,)),
            state.approval_id,
            verdict,
            channel="terminal",
            decided_by="owner",
            **extra,
        )

    def answer(self, state: RunState, answer: str) -> None:
        answer_escalation(
            self.store, state.escalation_id, answer, channel="terminal", decided_by="owner"
        )

    def events(self) -> list[tuple[EventKind, str | None]]:
        return [(event.kind, event.node) for event in self.log.read(RUN)]


ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
REPLY = '{"reply": "Done."}'


def test_the_nodes() -> None:
    assert NODES == (
        "route",
        "plan",
        "ask_plan",
        "ask_step",
        "wait_approval",
        "run_step",
        "answer",
        "record_escalation",
        "wait_escalation",
        "finish",
    )


def test_a_read_only_request_runs_to_its_answer(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", ECHO_PLAN), ("answer", REPLY)], FakeRunner())
    state = world.start("demo: say hi")
    assert state == RunState(run_id=RUN, status="done", reply="Done.")
    assert world.runner.calls == [("echo", demo.EchoArgs(text="hi"))]
    assert world.store.pending() == []
    assert world.events() == [
        (EventKind.RUN_STARTED, None),
        (EventKind.MODEL_REQUEST, "plan"),
        (EventKind.MODEL_REPLY, "plan"),
        (EventKind.TOOL_CALL, "run_step"),
        (EventKind.TOOL_RESULT, "run_step"),
        (EventKind.MODEL_REQUEST, "answer"),
        (EventKind.MODEL_REPLY, "answer"),
        (EventKind.RUN_FINISHED, "finish"),
    ]
    events = world.log.read(RUN)
    assert [events[i].payload for i in (0, 3, 4, 7)] == [
        {"request": "demo: say hi"},
        {"step": 1, "action": "demo.echo", "args": {"text": "hi"}},
        {"step": 1, "output": {"text": "hi"}},
        {"status": "done"},
    ]
    assert world.model.requests[1].user.startswith('{\n  "request": "say hi",')


def test_a_write_step_waits_for_the_plan_and_then_for_itself(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN), ("answer", REPLY)], FakeRunner())
    first = world.start("demo: note Milk")
    assert (first.status, first.escalation_id, world.runner.calls) == ("waiting", None, [])
    assert [request.stage for request in world.store.pending()] == ["plan"]
    world.decide(first)
    second = world.resume()
    assert second.status == "waiting" and second.approval_id != first.approval_id
    [step] = world.store.pending()
    assert (step.approval_id, step.stage, step.steps[0].args, world.runner.calls) == (
        second.approval_id,
        "step",
        {"title": "Milk", "body": "", "tags": []},
        [],
    )
    world.decide(second)
    assert world.resume() == RunState(run_id=RUN, status="done", reply="Done.")
    assert world.runner.calls == [("note", demo.NoteArgs(title="Milk"))]
    kinds = [kind for kind, _ in world.events()]
    assert kinds.count(EventKind.APPROVAL_REQUESTED) == 2
    assert kinds.count(EventKind.APPROVAL_DECIDED) == 2
    decided = [e for e in world.log.read(RUN) if e.kind == EventKind.APPROVAL_DECIDED]
    assert decided[0].payload == {
        "approval_id": first.approval_id,
        "verdict": "approve",
        "outcome": "approved",
    }
    assert decided[0].node == "wait_approval"


def test_resume_needs_a_recorded_decision(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN)], FakeRunner())
    state = world.start("demo: note Milk")
    with pytest.raises(RunError) as raised:
        world.resume()
    assert str(raised.value) == f"approval {state.approval_id} is not decided yet"
    assert run_state(world.graph, RUN) == state
    assert world.runner.calls == []


def test_an_edit_runs_the_edited_arguments(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN), ("answer", REPLY)], FakeRunner())
    world.decide(world.start("demo: note Milk"))
    world.decide(world.resume(), "edit", edited_args={"title": "Bread", "tags": ["home"]})
    assert world.resume().status == "done"
    assert world.runner.calls == [("note", demo.NoteArgs(title="Bread", tags=("home",)))]


def test_a_rejection_ends_the_run_with_its_note(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN)], FakeRunner())
    world.decide(world.start("demo: note Milk"), "reject", note="not now")
    assert world.resume() == RunState(run_id=RUN, status="rejected", note="not now")
    assert world.runner.calls == []
    assert world.log.read(RUN)[-1].payload == {"status": "rejected"}
    with pytest.raises(RunError) as raised:
        world.resume()
    assert str(raised.value) == f"run {RUN} is not waiting"


def test_an_escalation_waits_and_retry_runs_the_node_again(tmp_path: Path) -> None:
    replies = [
        ("route", ModelUnavailable("timeout")),
        ("route", '{"domain": "demo"}'),
        ("plan", ECHO_PLAN),
        ("answer", REPLY),
    ]
    world = World(tmp_path, replies, FakeRunner())
    state = world.start("Say hi back to me")
    assert (state.status, state.approval_id) == ("waiting", None)
    [open_one] = world.store.open_escalations()
    assert (open_one.escalation_id, open_one.escalation.kind) == (
        state.escalation_id,
        "model_unavailable",
    )
    with pytest.raises(RunError) as raised:
        world.resume()
    assert str(raised.value) == f"escalation {state.escalation_id} is not answered yet"
    world.answer(state, "retry")
    assert world.resume() == RunState(run_id=RUN, status="done", reply="Done.")
    escalated = [e for e in world.log.read(RUN) if e.kind == EventKind.ESCALATED]
    assert [(e.node, e.payload) for e in escalated] == [
        (
            "record_escalation",
            {
                "escalation_id": state.escalation_id,
                "kind": "model_unavailable",
                "retry_node": "route",
            },
        )
    ]


def test_cancel_ends_the_run(tmp_path: Path) -> None:
    world = World(tmp_path, [("route", '{"domain": "unknown"}')], FakeRunner())
    state = world.start("Book a flight to Lisbon")
    world.answer(state, "cancel")
    assert world.resume() == RunState(run_id=RUN, status="cancelled")
    assert world.log.read(RUN)[-1].payload == {"status": "cancelled"}


def test_a_failed_step_escalates_and_retry_asks_for_its_approval_again(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN), ("answer", REPLY)], FakeRunner(failures=1))
    world.decide(world.start("demo: note Milk"))
    step = world.resume()
    world.decide(step)
    failed = world.resume()
    assert failed.status == "waiting" and failed.escalation_id is not None
    stored = world.store.escalation(failed.escalation_id).escalation
    assert (stored.kind, stored.detail) == ("tool_error", "step 1 demo.note: the step failed")
    world.answer(failed, "retry")
    again = world.resume()
    assert again.approval_id not in (None, step.approval_id)
    assert world.store.approval(again.approval_id).request.args_sha256 == (
        world.store.approval(step.approval_id).request.args_sha256
    )
    assert len(world.runner.calls) == 1
    world.decide(again)
    assert world.resume().status == "done"
    assert len(world.runner.calls) == 2


def test_a_result_that_does_not_fit_escalates(tmp_path: Path) -> None:
    runner = FakeRunner(outputs={"echo": {"text": 5}})
    world = World(tmp_path, [("plan", ECHO_PLAN)], runner)
    state = world.start("demo: say hi")
    stored = world.store.escalation(state.escalation_id).escalation
    assert (stored.kind, stored.detail) == (
        "tool_error",
        "step 1 demo.echo: the result does not fit the action",
    )
    assert [(p.loc, p.code) for p in stored.problems] == [("text", "string_type")]


def test_tracing_is_off_inside_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_synthetic")
    world = World(tmp_path, [("plan", ECHO_PLAN), ("answer", REPLY)], FakeRunner())
    assert world.start("demo: say hi").status == "done"
    assert world.runner.tracing == [False]


def test_the_checkpoint_holds_only_json(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN)], FakeRunner())
    world.start("demo: note Milk")
    values = world.graph.get_state({"configurable": {"thread_id": RUN}}).values
    assert json.loads(json.dumps(values)) == values


def test_runs_are_checked(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", ECHO_PLAN), ("answer", REPLY)], FakeRunner())
    with pytest.raises(RunError) as unknown:
        run_state(world.graph, RUN)
    assert str(unknown.value) == f"no run {RUN}"
    with pytest.raises(RunError) as missing:
        world.resume()
    assert str(missing.value) == f"no run {RUN}"
    with pytest.raises(ValueError) as empty:
        world.start("   ")
    assert str(empty.value) == REQUEST_MESSAGE
    world.start("demo: say hi")
    with pytest.raises(RunError) as twice:
        world.start("demo: say hi")
    assert str(twice.value) == f"run {RUN} already exists"


def test_eight_read_steps_run_in_one_go(tmp_path: Path) -> None:
    steps = ", ".join(f'{{"action": "echo", "args": {{"text": "t{n}"}}}}' for n in range(1, 9))
    world = World(tmp_path, [("plan", f'{{"steps": [{steps}]}}'), ("answer", REPLY)], FakeRunner())
    assert world.start("demo: count to eight").status == "done"
    assert [args.text for _, args in world.runner.calls] == [f"t{n}" for n in range(1, 9)]
