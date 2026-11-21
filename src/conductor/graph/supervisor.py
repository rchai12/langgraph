from typing import cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from langsmith import tracing_context

from conductor.contracts.base import is_request
from conductor.events import EventKind, EventLog, check_run_id
from conductor.graph import tracing_off
from conductor.graph.nodes import (  # noqa: F401
    Services,
    State,
    build_nodes,
)
from conductor.graph.status import (  # noqa: F401
    NODES,
    RunError,
    RunState,
    RunStateUnavailable,
    RunStatus,
    checkpoint_state,
)
from conductor.graph.steps import (  # noqa: F401
    FAILURE_CODES,
    RESULT_DETAIL,
    STEP_FAILED_DETAIL,
    FailureCode,
    StepFailed,
    StepRunner,
)
from conductor.routing.route import REQUEST_MESSAGE
from conductor.store import NotFound, Store

RECURSION_LIMIT = 100
RESUMABLE_STOPS = ("route", "plan", "answer")


def build_graph(services: Services, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(State)
    for name, node in build_nodes(services).items():
        graph.add_node(name, node)
    graph.add_edge(START, "route")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


def start_run(graph: CompiledStateGraph, request: str, *, run_id: str, log: EventLog) -> RunState:
    if not is_request(request):
        raise ValueError(REQUEST_MESSAGE)
    if graph.get_state(_config(run_id)).created_at is not None:
        raise RunError(f"run {run_id} already exists")
    log.append(run_id, EventKind.RUN_STARTED, payload={"request": request})
    _invoke(graph, {"request": request}, run_id)
    return run_state(graph, run_id)


def can_resume(state: RunState, store: Store) -> bool:
    if state.status == "stopped":
        return state.stopped_at in RESUMABLE_STOPS
    if state.status != "waiting":
        return False
    try:
        if state.approval_id is not None:
            return store.approval(state.approval_id).decision is not None
        escalation_id = cast(str, state.escalation_id)
        return store.escalation(escalation_id).answer is not None
    except NotFound:
        return False


def resume_run(graph: CompiledStateGraph, store: Store, run_id: str) -> RunState:
    state = run_state(graph, run_id)
    if state.status == "stopped":
        if state.stopped_at in RESUMABLE_STOPS:
            _invoke(graph, None, run_id)
            return run_state(graph, run_id)
        raise RunError(f"run {run_id} stopped at {state.stopped_at} and cannot be resumed")
    if state.status != "waiting":
        raise RunError(f"run {run_id} is not waiting")
    if state.approval_id is not None:
        if store.approval(state.approval_id).decision is None:
            raise RunError(f"approval {state.approval_id} is not decided yet")
        token = state.approval_id
    else:
        escalation_id = cast(str, state.escalation_id)
        if store.escalation(escalation_id).answer is None:
            raise RunError(f"escalation {escalation_id} is not answered yet")
        token = escalation_id
    _invoke(graph, Command(resume=token), run_id)
    return run_state(graph, run_id)


def run_state(graph: CompiledStateGraph, run_id: str) -> RunState:
    check_run_id(run_id)
    try:
        saved = graph.checkpointer.get_tuple(
            {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
        )
    except Exception:
        raise RunStateUnavailable(f"run {run_id} state is not available") from None
    return checkpoint_state(saved, run_id)


def _config(run_id: str) -> dict[str, object]:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}


def _invoke(graph: CompiledStateGraph, value: object, run_id: str) -> None:
    tracing_off()
    with tracing_context(enabled=False):
        graph.invoke(value, _config(run_id))
