# Phase 5c: the supervisor graph

## Goal

The supervisor itself, as a LangGraph `StateGraph` kept in memory (`InMemorySaver`; `checkpoints.db` is 5d):

- routing (5a), planning and the answer (5b) as nodes; plan and step approvals (4a) as **interrupts** that wait for a decision recorded in `conductor.db` (4b, 4c); escalations as interrupts that wait for `retry` or `cancel`;
- steps run through an **injected `StepRunner`**, with every result checked against its action's result contract by code;
- LangSmith tracing **forced off**, whatever the environment says.

Decided with the owner (2026-11-09): steps run through an **injected runner** (Phase 6 plugs in MCP, Phase 10 the coder, without changing the graph); a failed step **escalates**, earlier steps are not undone, and **retry runs from the failed step and asks for its approval again**; on resume the graph reads **the decision from the store** and applies the policy again (the resume value carries only the id); an escalation **waits at an interrupt**, `retry` runs the node that escalated again and `cancel` ends the run.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("The supervisor graph", "Approve", "Approvals and escalations", "Privacy and safety boundary")
- `src/conductor/routing/route.py`, `src/conductor/planning/plan.py`, `src/conductor/planning/answer.py`, `src/conductor/policy.py`, `src/conductor/plancheck.py`, `src/conductor/store.py`, `src/conductor/decisions.py`, `src/conductor/events.py`, `src/conductor/llm/decide.py`, `src/conductor/llm/scripted.py`

## Starting state

Phase 5b is built and verified, and everything is committed: N is `500`. **Sections: core.** No `conductor/graph/` exists and `langgraph` is not installed.

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | add `"langgraph>=1.2.20,<1.3",` to `dependencies`, after `typer`; then run `.venv/bin/python -m pip install -e ".[dev]"` once |
| `src/conductor/graph/__init__.py` | the tracing guard (Part 1) |
| `src/conductor/graph/supervisor.py` | the graph and its runs (Parts 2 to 4, critical) |
| `scripts/critical_modules.txt` | add the line `graph/supervisor.py` after `planning/answer.py` |
| `docs/testing.md` | under "Critical modules", add `` - `graph/supervisor.py` (no step with a side effect runs without its own approval; Phase 5c) `` after the `planning/answer.py` line |
| `tests/integration/test_supervisor.py` | given (the folder is new) |
| `tests/integration/test_supervisor_more.py`, `tests/unit/test_graph_guard.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- `checkpoints.db`, `SqliteSaver`, leases, crash recovery, `conductor ask` and `conductor resume` (5d).
- MCP sessions and tool calls (Phase 6), real agents and the coder's retry after a verifier FAIL (Phase 10): every step goes through the injected runner, with `attempt` 1.
- A thread holding more than one run: in 5c the thread id is the run id.
- Undoing earlier steps after a failure; replanning; passing results between steps.
- `NODE_STARTED` and `NODE_FINISHED` events; any new event or escalation kind; any change to a contract, `policy`, `store`, `decisions`, routing, or planning.
- Streaming, async nodes, parallel steps, subgraphs.

## Dependencies

`langgraph>=1.2.20,<1.3` (1.2.20 is current; it brings `langgraph-checkpoint`, `langchain-core`, and `langsmith`). The project uses only `langgraph.graph`, `langgraph.types`, `langgraph.checkpoint.memory` (in tests), and `langsmith.tracing_context` (for the guard).

## Design

```python
# conductor/graph/__init__.py
TRACING_VARIABLES = ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2")
def tracing_off() -> None: ...   # sets each variable to "false"; also called once when the package is imported
```

```python
# conductor/graph/supervisor.py (critical)
NODES = ("route", "plan", "ask_plan", "ask_step", "wait_approval", "run_step",
         "answer", "record_escalation", "wait_escalation", "finish")
RECURSION_LIMIT = 100
RunStatus = Literal["waiting", "done", "rejected", "cancelled"]

class StepFailed(Exception):
    """A runner raises it when a step could not be done; its text is never shown."""

class StepRunner(Protocol):
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...

class RunError(Exception): ...

@dataclass(frozen=True)
class Services:
    registry: Registry
    store: Store
    log: EventLog
    model: Model
    model_name: str
    runner: StepRunner

@dataclass(frozen=True)
class RunState:
    run_id: str
    status: RunStatus
    approval_id: str | None = None     # set while waiting at wait_approval
    escalation_id: str | None = None   # set while waiting at wait_escalation
    reply: str | None = None           # set when done
    note: str = ""                     # the rejection's note

def build_graph(services: Services, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph: ...
def start_run(graph: CompiledStateGraph, request: str, *, run_id: str) -> RunState: ...
def resume_run(graph: CompiledStateGraph, store: Store, run_id: str) -> RunState: ...
def run_state(graph: CompiledStateGraph, run_id: str) -> RunState: ...
```

The state is a `TypedDict` (`total=False`) of **JSON values only**: `request` (str), `routed` (the request planning sees), `route` (a `Route` as JSON), `plan` (a `Plan` as JSON), `step` (the 0-based index of the next step), `args` (the approved arguments of the current step, or `None`), `results` (a list of `StepOutcome` as JSON), `pending` (the waiting `ApprovalRequest` as JSON, or `None`), `escalation` (an `Escalation` as JSON, or `None`), `escalation_id`, `retry_node`, `status`, `reply`, `note`. Contracts are rebuilt from it with `from_json(json.dumps(...))` where a node needs them; checked steps are rebuilt with `plancheck.check_plan`.

The nodes, each named as in `NODES` (and as the `node` of its events):

| Node | Does | Then |
|---|---|---|
| `route` | `route_request(state.request, ...)` | `Routed`: store `routed`, `route` → `plan`; `Escalation` → `record_escalation` (retry node `route`) |
| `plan` | `plan_request(...)` on the stored route | `Planned`: store `plan`, `step` 0, `results` [] → `ask_plan`; `Escalation` → `record_escalation` (retry `plan`) |
| `ask_plan` | `policy.plan_request(domain, checked steps, run_id=...)`; a request is added to the store, logged, and kept in `pending` | a request → `wait_approval`; `None` → `ask_step` |
| `ask_step` | when `step` equals the number of steps → `answer`; otherwise `policy.step_request(domain, checked[step], run_id=...)`, handled as in `ask_plan` | a request → `wait_approval`; `None` → `run_step` with `args` `None` |
| `wait_approval` | `interrupt({"approval_id": ...})`; then reads the decision from the store, `policy.apply_decision(request, decision, registry)`, logs it, clears `pending` | `Rejected`: `status` `rejected`, `note` → `finish`; plan approved → `ask_step`; step approved → `run_step` with `args` the approved arguments as JSON |
| `run_step` | runs the current step (below) | success → `ask_step` with `step` + 1; failure → `record_escalation` (retry `ask_step`, same `step`) |
| `answer` | `answer_request(state.routed, results, ...)` | `Answered`: `reply`, `status` `done` → `finish`; `Escalation` → `record_escalation` (retry `answer`) |
| `record_escalation` | `store.add_escalation(escalation)`, logs it, keeps its id | → `wait_escalation` |
| `wait_escalation` | `interrupt({"escalation_id": ...})`; then reads the answer from the store | `retry` → the retry node, with `escalation`, `escalation_id`, and `args` cleared; `cancel` → `status` `cancelled` → `finish` |
| `finish` | logs `RUN_FINISHED` | → `END` |

Running a step: log `TOOL_CALL`; `services.runner.run(action, args)`, where `args` is the approved arguments parsed by the action's args contract, or the checked step's arguments when no approval was needed; `StepFailed` is a failure; otherwise the output is parsed with `action.result.from_json(json.dumps(output))`, and a `ValidationError` is a failure with `problems_from(error)`; success logs `TOOL_RESULT` and appends `StepOutcome(step=<number>, action=<domain>.<name>, output=<the parsed result as JSON>)`. A failure logs `ERROR` and becomes the escalation below.

The events (besides `decide`'s own, which carry `node` `route`, `plan`, or `answer`):

| Kind | Node | Payload |
|---|---|---|
| `RUN_STARTED` | `None` (written by `start_run`) | `{"request": <the request>}` |
| `APPROVAL_REQUESTED` | `ask_plan` or `ask_step` | `{"approval_id", "stage", "args_sha256"}` |
| `APPROVAL_DECIDED` | `wait_approval` | `{"approval_id", "verdict", "outcome": "approved" or "rejected"}` |
| `TOOL_CALL` | `run_step` | `{"step": <number>, "action": "<domain>.<name>", "args": <the arguments run, as JSON>}` |
| `TOOL_RESULT` | `run_step` | `{"step": <number>, "output": <the parsed result, as JSON>}` |
| `ERROR` | `run_step` | `{"step": <number>, "error": "tool_error", "problems": [{"loc", "code"}, ...]}` |
| `ESCALATED` | `record_escalation` | `{"escalation_id", "kind", "retry_node"}` |
| `RUN_FINISHED` | `finish` | `{"status": "done" or "rejected" or "cancelled"}` |

The step escalation: `Escalation(kind="tool_error", detail=f"step {number} {domain}.{name}: <the step failed | the result does not fit the action>", run_id=..., problems=<the result's problems, or none>)`.

The run functions, every `invoke` with `config={"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}` and inside `tracing_context(enabled=False)`, after `tracing_off()`:

| Function | Checks first, in order | Then |
|---|---|---|
| `start_run` | the request as `route_request` checks it (`ValueError(REQUEST_MESSAGE)`); a thread that already exists: `RunError(f"run {run_id} already exists")` | logs `RUN_STARTED`, invokes with `{"request": request}`, returns `run_state` |
| `resume_run` | `run_state` (an unknown run: `RunError(f"no run {run_id}")`); not waiting: `RunError(f"run {run_id} is not waiting")`; an approval with no decision: `RunError(f"approval {id} is not decided yet")`; an escalation with no answer: `RunError(f"escalation {id} is not answered yet")` | invokes with `Command(resume=<the id>)`, returns `run_state` |
| `run_state` | a thread with no checkpoint (`get_state(...).created_at is None`): `RunError(f"no run {run_id}")` | `waiting` with `approval_id` or `escalation_id` when the snapshot has interrupts (at `wait_approval` or `wait_escalation`); otherwise the stored `status`, `reply`, and `note` |

## Facts about LangGraph

Found on 2026-11-09 with langgraph 1.2.20, langgraph-checkpoint 4.3.1, langchain-core 1.7.6, langsmith 0.14.17:

- `invoke` returns the state with `"__interrupt__": [Interrupt(value=..., id=...)]` when a node calls `interrupt(value)`; `get_state(config).interrupts` holds them and `.next` names the waiting node. `invoke(Command(resume=v), config)` continues it.
- **A resumed node runs again from its first line**; earlier `interrupt` calls in it return their recorded resume values. Anything before an `interrupt` (an id, a time, a store write, an event) happens again on every resume. That is why requests and escalations are created in `ask_*` and `record_escalation`, and the `wait_*` nodes only read before they wait.
- **`Command(resume=...)` on a thread with no checkpoint starts a new run from `START`**, silently; `resume_run` checks first. `get_state` for such a thread gives empty values and `created_at` `None`.
- Resuming a finished thread does nothing and returns its final state.
- An exception in a node passes out of `invoke` unchanged.
- **Pydantic objects in the state** give `Deserializing unregistered type ... This will be blocked in a future version`; JSON-only state gives no warning.
- `recursion_limit` counts the steps of one `invoke` (it starts again at each resume). A plan of eight `read` steps takes 21; the default of 25 is too tight, hence `RECURSION_LIMIT`.
- **With `LANGSMITH_TRACING=true` and a key in the environment, a run sends its whole state to LangSmith** (a 34 KB multipart POST was attempted). Setting the tracing variables to `false`, before or after import, or running inside `langsmith.tracing_context(enabled=False)`, stops it; inside that context `langsmith.utils.tracing_is_enabled()` is `False` even when the environment says `true`. With no tracing variables, a run opens no connection.

## Requirements

### Part 1: the dependency and the guard

- **R1.** `langgraph` is added as under Scope and installed. `conductor.graph` sets each of `TRACING_VARIABLES` to `"false"` when imported (before anything imports `langgraph`), and `tracing_off()` does it again; every `invoke` runs inside `tracing_context(enabled=False)`.

### Part 2: the graph (critical)

- **R2.** `build_graph` builds a `StateGraph` over the JSON-only state with exactly the nodes of `NODES`, the edges of the node table, and `START` → `route`, compiled with the given checkpointer. Node functions close over `services`; nothing is read from settings.
- **R3.** `route`, `plan`, and `answer` call `route_request`, `plan_request`, and `answer_request` as the table says, and turn an `Escalation` into the state's `escalation` and `retry_node`.
- **R4.** `ask_plan` and `ask_step` build requests only through `policy.plan_request` and `policy.step_request` (attempt 1), add each to the store, log it, and keep it in `pending`; a `read` step, and a plan whose steps are all `read`, add nothing.
- **R5.** `wait_approval` and `wait_escalation` read the store and call `interrupt` before they write anything: no store write, event, id, or time comes before the `interrupt` returns. After it, `wait_approval` takes the decision from `store.approval(id).decision` and judges it with `policy.apply_decision` (not the resume value); `wait_escalation` takes the answer from `store.escalation(id).answer`.
- **R6.** `run_step` runs a step that is not `read` only with the arguments that `apply_decision` approved for that very step request, and runs each step at most once per approval; it logs and escalates as under Design, and passes any exception other than `StepFailed` and a result's `ValidationError` through.
- **R7.** A retry after a step escalation goes to `ask_step` for the same step, so a step that is not `read` asks for a new approval with the same arguments before it runs again. A retry after a `route`, `plan`, or `answer` escalation runs that node again. `cancel` ends the run.

### Part 3: runs

- **R8.** `start_run`, `resume_run`, and `run_state` check and act as in the Design's table, in that order, with those messages; the thread id is the run id.
- **R9.** `finish` logs `RUN_FINISHED` once per run, with the final status; the events are exactly the Design's, with those payloads and nodes.

### Part 4: the rules

- **R10.** `supervisor.py` imports from the project only `conductor.contracts`, `conductor.contracts.approvals`, `conductor.events`, `conductor.llm.model`, `conductor.plancheck` (as `from conductor import plancheck, policy`), `conductor.policy`, `conductor.planning.plan`, `conductor.planning.answer`, `conductor.registry`, `conductor.routing.route`, `conductor.store`, and `conductor.graph` (for `tracing_off`); from libraries only the standard library, `pydantic`, `langgraph`, and `langsmith` (`tracing_context`). It reads no settings, never calls Ollama or `decide` directly, and never reads `clock` or `ids` itself.
- **R11.** Every message of `RunError`, and every `detail` the graph builds, is constant text plus ids and action names; `StepFailed`'s text and any runner output are never put into a message.
- **R12.** `graph/supervisor.py` and `graph/__init__.py` reach 100% of lines and branches; `graph/supervisor.py` joins the critical modules.

## Given tests

14 tests in `tests/integration/test_supervisor.py`. Do not change them; if one fails, the code is wrong. They run the real graph with `InMemorySaver`, a real `Store` and `EventLog` under `tmp_path`, `ScriptedModel`, and a fake runner, and decide through `conductor.decisions` exactly as the terminal does.

```python
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
```

## Tests to write

In `tests/integration/test_supervisor_more.py`, each with its deciding input:

- R4: a `delegate` (`implement`) step asks for its own approval; a plan of `echo`, `note` asks for the plan, runs `echo` without asking, then asks for `note`.
- R5: resuming twice at the same approval (decide, resume, then call `resume_run` again at the next wait) leaves one request per stage in the store and one `APPROVAL_REQUESTED` per request (no duplicates from re-run nodes).
- R6: a runner that returns a list, and one that raises `RuntimeError` (passes through, the run stays at its last checkpoint).
- R7: a `plan` escalation (invalid planner output) retried with a valid reply plans and runs; an `answer` escalation retried answers.
- R8: `run_state` of a run waiting at an escalation names it; `resume_run` of a cancelled run says `is not waiting`.
- R9: the payloads of `APPROVAL_REQUESTED`, `ERROR`, and `RUN_FINISHED` for a rejected step (a step approval rejected).
- R11: a `StepFailed("SYNTHETIC-SECRET")` and a runner output containing `SYNTHETIC-SECRET` appear in no escalation.

In `tests/unit/test_graph_guard.py`:

- R1: with every tracing variable set to `"true"`, `tracing_off()` sets each to `"false"`; importing `conductor.graph` in a subprocess with `LANGSMITH_TRACING=true` leaves it `"false"`.

## Rules for this phase

- **Side effects need approval** (`AGENTS.md` rule 7): the runner is called for a `propose`, `write`, or `implement` step only after `policy.apply_decision` approved that step's own request, read from the store.
- **No telemetry** (`AGENTS.md` rule 2): the guard is part of this phase's acceptance; no test or probe opens a connection.
- **Critical module**: `graph/supervisor.py` joins `scripts/critical_modules.txt` and `docs/testing.md`.
- **Determinism** (`AGENTS.md`): the graph decides by code; the model is reached only through the 5a and 5b functions.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 14 = 514 passed; `critical coverage` passed (it now includes `graph/supervisor.py`);
- the given file: `.venv/bin/python -m pytest tests/integration/test_supervisor.py --no-cov`, exactly `14 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/graph/*.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 5c`, after the progress entry: `Reports OK.`;
- `.venv/bin/python -c "import langgraph, importlib.metadata as m; print(m.version('langgraph'))"` prints a version from 1.2.20 up to, not including, 1.3;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/graph/supervisor.py | grep -v -E "^[^:]+:[0-9]+:from conductor(\.contracts|\.contracts\.approvals|\.events|\.llm\.model|\.planning\.plan|\.planning\.answer|\.registry|\.routing\.route|\.store|\.graph)? import "`
  - `git grep --untracked -n -E "get_settings|clock\.|ids\.|OllamaModel|urllib|decide\(|from conductor\.plancheck import|langchain" -- src/conductor/graph`
  - `git grep --untracked -n -E "langgraph|langsmith" -- src | grep -v "^src/conductor/graph/"`
- `git diff --stat HEAD -- src/conductor/contracts src/conductor/policy.py src/conductor/store.py src/conductor/decisions.py src/conductor/routing src/conductor/planning src/conductor/plancheck.py src/conductor/events.py src/conductor/llm tests/unit tests/e2e tests/support.py` prints nothing (new files are untracked, so it does not show them).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 5c: the supervisor graph (YYYY-MM-DD)`, with `Tests: 500 -> <passed> (given 14)`.
