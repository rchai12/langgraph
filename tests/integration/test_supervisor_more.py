import itertools
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor import clock, ids
from conductor.contracts import Contract
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import (
    RunError,
    RunState,
    Services,
    StepFailed,
    build_graph,
    resume_run,
    run_state,
    start_run,
)
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Registry
from conductor.routing.route import REQUEST_MESSAGE
from conductor.store import Store

RUN = "a" * 32
SECRET = "SYNTHETIC-SECRET"
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
DELEGATE_PLAN = '{"steps": [{"action": "delegate", "args": {"task": "Sweep"}}]}'
MIXED_PLAN = (
    '{"steps": [{"action": "echo", "args": {"text": "hi"}},'
    ' {"action": "note", "args": {"title": "Milk"}}]}'
)
REPLY = '{"reply": "Done."}'


class Runner:
    def __init__(
        self, output: dict | list | None = None, error: BaseException | None = None
    ) -> None:
        self.calls: list[tuple[str, Contract]] = []
        self.output = output
        self.error = error

    def run(self, action: Action, args: Contract) -> dict | list:
        self.calls.append((action.name, args))
        if isinstance(self.error, StepFailed) or isinstance(self.error, RuntimeError):
            raise self.error
        if self.output is not None:
            return self.output
        if action.name == "echo":
            return {"text": args.text}
        if action.name == "note":
            return {"note_id": "e" * 32}
        return {"summary": "done"}


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


class World:
    def __init__(self, tmp_path: Path, replies: list[tuple[str, str]], runner: Runner) -> None:
        self.store = Store(tmp_path / "conductor.db")
        self.log = EventLog(tmp_path / "runs")
        self.runner = runner
        self.graph = build_graph(
            Services(
                registry=Registry((demo.DOMAIN,)),
                store=self.store,
                log=self.log,
                model=ScriptedModel(
                    [ScriptedReply(point, ModelReply(content=reply)) for point, reply in replies]
                ),
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


def test_a_delegate_step_asks_and_a_mixed_plan_runs_the_read_first(tmp_path: Path) -> None:
    delegate = World(tmp_path / "delegate", [("plan", DELEGATE_PLAN), ("answer", REPLY)], Runner())
    plan = delegate.start("demo: sweep the floor")
    delegate.decide(plan)
    step = delegate.resume()
    [pending] = delegate.store.pending()
    assert (step.status, pending.stage, pending.steps[0].action, delegate.runner.calls) == (
        "waiting",
        "step",
        "demo.delegate",
        [],
    )
    delegate.decide(step)
    assert delegate.resume().status == "done"
    assert delegate.runner.calls == [("delegate", demo.DelegateArgs(task="Sweep"))]

    mixed = World(tmp_path / "mixed", [("plan", MIXED_PLAN), ("answer", REPLY)], Runner())
    mixed.decide(mixed.start("demo: say hi and note Milk"))
    waiting = mixed.resume()
    assert mixed.runner.calls == [("echo", demo.EchoArgs(text="hi"))]
    [note] = mixed.store.pending()
    assert (waiting.status, note.stage, note.steps[0].action) == ("waiting", "step", "demo.note")


def test_resuming_twice_does_not_duplicate_an_approval(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN), ("answer", REPLY)], Runner())
    plan = world.start("demo: note Milk")
    world.decide(plan)
    step = world.resume()
    with pytest.raises(RunError) as raised:
        world.resume()
    assert str(raised.value) == f"approval {step.approval_id} is not decided yet"
    requested = [
        event for event in world.log.read(RUN) if event.kind == EventKind.APPROVAL_REQUESTED
    ]
    assert [event.payload["stage"] for event in requested] == ["plan", "step"]
    assert len({event.payload["approval_id"] for event in requested}) == 2
    assert [item.stage for item in world.store.pending()] == ["step"]
    assert run_state(world.graph, RUN) == step


def test_a_list_result_escalates_and_a_runner_error_passes(tmp_path: Path) -> None:
    listed = World(tmp_path / "list", [("plan", ECHO_PLAN)], Runner(output=["nope"]))
    state = listed.start("demo: say hi")
    stored = listed.store.escalation(state.escalation_id).escalation
    assert (stored.kind, stored.detail) == (
        "tool_error",
        "step 1 demo.echo: the result does not fit the action",
    )

    broken = World(tmp_path / "boom", [("plan", ECHO_PLAN)], Runner(error=RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        broken.start("demo: say hi")
    snapshot = broken.graph.get_state({"configurable": {"thread_id": RUN}})
    assert snapshot.next == ("run_step",)
    assert "status" not in snapshot.values
    assert broken.store.open_escalations() == []


def test_retry_runs_a_plan_and_an_answer_again(tmp_path: Path) -> None:
    planned = World(
        tmp_path / "plan",
        [("plan", '{"steps": [{"action": "missing"}]}'), ("plan", ECHO_PLAN), ("answer", REPLY)],
        Runner(),
    )
    failed = planned.start("demo: say hi")
    assert planned.store.escalation(failed.escalation_id).escalation.kind == "invalid_model_output"
    planned.answer(failed, "retry")
    assert planned.resume() == RunState(run_id=RUN, status="done", reply="Done.")
    assert planned.runner.calls == [("echo", demo.EchoArgs(text="hi"))]

    answered = World(
        tmp_path / "answer",
        [("plan", ECHO_PLAN), ("answer", '{"reply": 1}'), ("answer", REPLY)],
        Runner(),
    )
    failed = answered.start("demo: say hi")
    assert answered.store.escalation(failed.escalation_id).escalation.kind == "invalid_model_output"
    answered.answer(failed, "retry")
    assert answered.resume() == RunState(run_id=RUN, status="done", reply="Done.")


def test_run_state_names_an_escalation_and_a_cancelled_run_is_not_waiting(tmp_path: Path) -> None:
    world = World(tmp_path, [("route", '{"domain": "unknown"}')], Runner())
    with pytest.raises(ValueError) as raised:
        world.start("y" * 2001)
    assert str(raised.value) == REQUEST_MESSAGE
    state = world.start("Book a flight to Lisbon")
    assert run_state(world.graph, RUN) == RunState(
        run_id=RUN, status="waiting", escalation_id=state.escalation_id
    )
    world.answer(state, "cancel")
    assert world.resume() == RunState(run_id=RUN, status="cancelled")
    with pytest.raises(RunError) as refused:
        world.resume()
    assert str(refused.value) == f"run {RUN} is not waiting"


def test_a_rejected_step_logs_the_request_the_error_and_the_finish(tmp_path: Path) -> None:
    world = World(tmp_path / "reject", [("plan", NOTE_PLAN)], Runner())
    world.decide(world.start("demo: note Milk"))
    step = world.resume()
    world.decide(step, "reject", note="not this")
    assert world.resume() == RunState(run_id=RUN, status="rejected", note="not this")
    requested = [
        event for event in world.log.read(RUN) if event.kind == EventKind.APPROVAL_REQUESTED
    ]
    assert requested[1].node == "ask_step"
    assert requested[1].payload == {
        "approval_id": step.approval_id,
        "stage": "step",
        "args_sha256": world.store.approval(step.approval_id).request.args_sha256,
    }
    assert world.log.read(RUN)[-1].payload == {"status": "rejected"}
    assert world.log.read(RUN)[-1].node == "finish"
    assert world.runner.calls == []

    failed = World(tmp_path / "error", [("plan", ECHO_PLAN)], Runner(error=StepFailed("hidden")))
    state = failed.start("demo: say hi")
    error = [event for event in failed.log.read(RUN) if event.kind == EventKind.ERROR]
    assert [(event.node, event.payload) for event in error] == [
        ("run_step", {"step": 1, "error": "tool_error", "problems": []})
    ]
    failed.answer(state, "cancel")
    assert failed.resume().status == "cancelled"
    assert failed.log.read(RUN)[-1].payload == {"status": "cancelled"}


def test_a_secret_stays_out_of_every_escalation(tmp_path: Path) -> None:
    failed = World(tmp_path / "failed", [("plan", NOTE_PLAN)], Runner(error=StepFailed(SECRET)))
    failed.decide(failed.start("demo: note Milk"))
    step = failed.resume()
    failed.decide(step)
    state = failed.resume()
    stored = failed.store.escalation(state.escalation_id).escalation
    assert SECRET not in stored.model_dump_json()
    assert stored.detail == "step 1 demo.note: the step failed"

    unfit = World(
        tmp_path / "unfit",
        [("plan", ECHO_PLAN)],
        Runner(output={"text": SECRET, "extra": 1}),
    )
    state = unfit.start("demo: say hi")
    stored = unfit.store.escalation(state.escalation_id).escalation
    assert SECRET not in stored.model_dump_json()
    assert stored.detail == "step 1 demo.echo: the result does not fit the action"
