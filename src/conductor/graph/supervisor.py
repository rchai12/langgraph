import json
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, RunnableConfig, interrupt
from langsmith import tracing_context
from pydantic import ValidationError

from conductor import plancheck, policy
from conductor.contracts import Contract, Escalation, FieldProblem, Plan, Route, problems_from
from conductor.contracts.approvals import ApprovalDecision, ApprovalRequest, EscalationAnswer
from conductor.events import EventKind, EventLog, JsonValue
from conductor.graph import tracing_off
from conductor.llm.model import Model
from conductor.planning.answer import Answered, StepOutcome, answer_request
from conductor.planning.plan import Planned, plan_request
from conductor.registry import Action, Registry
from conductor.routing.route import REQUEST_MESSAGE, Routed, route_request
from conductor.store import Store

NODES = (
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
RECURSION_LIMIT = 100
RESUMABLE_STOPS = ("route", "plan", "answer")
RunStatus = Literal["waiting", "done", "rejected", "cancelled", "stopped"]
STEP_FAILED_DETAIL = "the step failed"
RESULT_DETAIL = "the result does not fit the action"


class StepFailed(Exception):
    """A runner raises it when a step could not be done; its text is never shown."""


class StepRunner(Protocol):
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...


class RunError(Exception):
    pass


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
    approval_id: str | None = None
    escalation_id: str | None = None
    reply: str | None = None
    note: str = ""
    stopped_at: str | None = None


class State(TypedDict, total=False):
    request: str
    routed: str
    route: dict[str, JsonValue]
    plan: dict[str, JsonValue]
    step: int
    args: dict[str, JsonValue] | None
    results: list[dict[str, JsonValue]]
    pending: dict[str, JsonValue] | None
    escalation: dict[str, JsonValue] | None
    escalation_id: str | None
    retry_node: str | None
    status: str
    reply: str | None
    note: str


_SERVICES: dict[int, Services] = {}


def build_graph(services: Services, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(State)
    graph.add_node("route", _route(services))
    graph.add_node("plan", _plan(services))
    graph.add_node("ask_plan", _ask_plan(services))
    graph.add_node("ask_step", _ask_step(services))
    graph.add_node("wait_approval", _wait_approval(services))
    graph.add_node("run_step", _run_step(services))
    graph.add_node("answer", _answer(services))
    graph.add_node("record_escalation", _record_escalation(services))
    graph.add_node("wait_escalation", _wait_escalation(services))
    graph.add_node("finish", _finish(services))
    graph.add_edge(START, "route")
    graph.add_edge("finish", END)
    compiled = graph.compile(checkpointer=checkpointer)
    _SERVICES[id(compiled)] = services
    return compiled


def start_run(graph: CompiledStateGraph, request: str, *, run_id: str) -> RunState:
    if not request.strip() or len(request) > 2000:
        raise ValueError(REQUEST_MESSAGE)
    if graph.get_state(_config(run_id)).created_at is not None:
        raise RunError(f"run {run_id} already exists")
    _SERVICES[id(graph)].log.append(run_id, EventKind.RUN_STARTED, payload={"request": request})
    _invoke(graph, {"request": request}, run_id)
    return run_state(graph, run_id)


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
    snapshot = graph.get_state(_config(run_id))
    if snapshot.created_at is None:
        raise RunError(f"no run {run_id}")
    if snapshot.interrupts:
        value = snapshot.interrupts[0].value
        if "approval_id" in value:
            return RunState(run_id=run_id, status="waiting", approval_id=value["approval_id"])
        return RunState(run_id=run_id, status="waiting", escalation_id=value["escalation_id"])
    if snapshot.next:
        return RunState(run_id=run_id, status="stopped", stopped_at=snapshot.next[0])
    values = snapshot.values
    return RunState(
        run_id=run_id,
        status=cast(RunStatus, values["status"]),
        reply=cast(str | None, values.get("reply")),
        note=cast(str, values.get("note") or ""),
    )


def _config(run_id: str) -> dict[str, object]:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}


def _invoke(graph: CompiledStateGraph, value: object, run_id: str) -> None:
    tracing_off()
    with tracing_context(enabled=False):
        graph.invoke(value, _config(run_id))


def _run_id(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


def _dump(model: Contract) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], model.model_dump(mode="json"))


def _load[T: Contract](kind: type[T], value: object) -> T:
    return kind.from_json(json.dumps(value))


def _checked(services: Services, state: State) -> tuple[plancheck.CheckedStep, ...]:
    return plancheck.check_plan(
        _load(Plan, state["plan"]), _load(Route, state["route"]), services.registry
    )


def _escalate(escalation: Escalation, retry_node: str) -> Command:
    return Command(
        update={"escalation": _dump(escalation), "retry_node": retry_node},
        goto="record_escalation",
    )


def _queue(services: Services, run_id: str, request: ApprovalRequest, node: str) -> Command:
    services.store.add_request(request)
    services.log.append(
        run_id,
        EventKind.APPROVAL_REQUESTED,
        node=node,
        payload={
            "approval_id": request.approval_id,
            "stage": request.stage,
            "args_sha256": request.args_sha256,
        },
    )
    return Command(update={"pending": _dump(request)}, goto="wait_approval")


def _tool_error(
    services: Services,
    run_id: str,
    number: int,
    action: str,
    reason: str,
    problems: tuple[FieldProblem, ...],
) -> Command:
    services.log.append(
        run_id,
        EventKind.ERROR,
        node="run_step",
        payload={
            "step": number,
            "error": "tool_error",
            "problems": [{"loc": problem.loc, "code": problem.code} for problem in problems],
        },
    )
    return _escalate(
        Escalation(
            kind="tool_error",
            detail=f"step {number} {action}: {reason}",
            run_id=run_id,
            problems=problems,
        ),
        "ask_step",
    )


def _route(services: Services):
    def route(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        found = route_request(
            state["request"],
            services.registry,
            model=services.model,
            model_name=services.model_name,
            log=services.log,
            run_id=run_id,
        )
        if isinstance(found, Escalation):
            return _escalate(found, "route")
        return Command(
            update={"routed": found.request, "route": _dump(found.route)},
            goto="plan",
        )

    return route


def _plan(services: Services):
    def plan(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        found = plan_request(
            Routed(_load(Route, state["route"]), state["routed"]),
            services.registry,
            model=services.model,
            model_name=services.model_name,
            log=services.log,
            run_id=run_id,
        )
        if isinstance(found, Escalation):
            return _escalate(found, "plan")
        planned = cast(Planned, found)
        return Command(
            update={"plan": _dump(planned.plan), "step": 0, "results": []},
            goto="ask_plan",
        )

    return plan


def _ask_plan(services: Services):
    def ask_plan(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        checked = _checked(services, state)
        request = policy.plan_request(_load(Route, state["route"]).domain, checked, run_id=run_id)
        if request is None:
            return Command(goto="ask_step")
        return _queue(services, run_id, request, "ask_plan")

    return ask_plan


def _ask_step(services: Services):
    def ask_step(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        checked = _checked(services, state)
        index = state["step"]
        if index == len(checked):
            return Command(goto="answer")
        request = policy.step_request(
            _load(Route, state["route"]).domain, checked[index], run_id=run_id
        )
        if request is None:
            return Command(update={"args": None}, goto="run_step")
        return _queue(services, run_id, request, "ask_step")

    return ask_step


def _wait_approval(services: Services):
    def wait_approval(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        pending = _load(ApprovalRequest, state["pending"])
        interrupt({"approval_id": pending.approval_id})
        decision = cast(ApprovalDecision, services.store.approval(pending.approval_id).decision)
        outcome = policy.apply_decision(pending, decision, services.registry)
        services.log.append(
            run_id,
            EventKind.APPROVAL_DECIDED,
            node="wait_approval",
            payload={
                "approval_id": pending.approval_id,
                "verdict": decision.verdict,
                "outcome": "rejected" if isinstance(outcome, policy.Rejected) else "approved",
            },
        )
        if isinstance(outcome, policy.Rejected):
            return Command(
                update={"pending": None, "status": "rejected", "note": outcome.note},
                goto="finish",
            )
        if pending.stage == "plan":
            return Command(update={"pending": None}, goto="ask_step")
        approved = cast(policy.Approved, outcome)
        return Command(
            update={"pending": None, "args": _dump(cast(Contract, approved.args))},
            goto="run_step",
        )

    return wait_approval


def _run_step(services: Services):
    def run_step(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        checked = _checked(services, state)
        step = checked[state["step"]]
        action = step.action
        domain = _load(Route, state["route"]).domain
        full_name = f"{domain}.{action.name}"
        if state.get("args") is None:
            args = step.args
        else:
            args = action.args.from_json(json.dumps(state["args"]))
        services.log.append(
            run_id,
            EventKind.TOOL_CALL,
            node="run_step",
            payload={"step": step.number, "action": full_name, "args": _dump(args)},
        )
        try:
            output = services.runner.run(action, args)
        except StepFailed:
            return _tool_error(services, run_id, step.number, full_name, STEP_FAILED_DETAIL, ())
        try:
            parsed = action.result.from_json(json.dumps(output))
        except ValidationError as error:
            return _tool_error(
                services, run_id, step.number, full_name, RESULT_DETAIL, problems_from(error)
            )
        services.log.append(
            run_id,
            EventKind.TOOL_RESULT,
            node="run_step",
            payload={"step": step.number, "output": _dump(parsed)},
        )
        results = [
            *state.get("results", []),
            _dump(StepOutcome(step=step.number, action=full_name, output=_dump(parsed))),
        ]
        return Command(update={"results": results, "step": state["step"] + 1}, goto="ask_step")

    return run_step


def _answer(services: Services):
    def answer(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        results = tuple(_load(StepOutcome, item) for item in state["results"])
        found = answer_request(
            state["routed"],
            results,
            model=services.model,
            model_name=services.model_name,
            log=services.log,
            run_id=run_id,
        )
        if isinstance(found, Escalation):
            return _escalate(found, "answer")
        answered = cast(Answered, found)
        return Command(update={"reply": answered.reply, "status": "done"}, goto="finish")

    return answer


def _record_escalation(services: Services):
    def record_escalation(state: State, config: RunnableConfig) -> Command:
        run_id = _run_id(config)
        escalation = _load(Escalation, state["escalation"])
        stored = services.store.add_escalation(escalation)
        services.log.append(
            run_id,
            EventKind.ESCALATED,
            node="record_escalation",
            payload={
                "escalation_id": stored.escalation_id,
                "kind": escalation.kind,
                "retry_node": state["retry_node"],
            },
        )
        return Command(update={"escalation_id": stored.escalation_id}, goto="wait_escalation")

    return record_escalation


def _wait_escalation(services: Services):
    def wait_escalation(state: State, config: RunnableConfig) -> Command:
        escalation_id = cast(str, state["escalation_id"])
        interrupt({"escalation_id": escalation_id})
        recorded = cast(EscalationAnswer, services.store.escalation(escalation_id).answer)
        cleared = {"escalation": None, "escalation_id": None, "args": None}
        if recorded.answer == "cancel":
            return Command(update={**cleared, "status": "cancelled"}, goto="finish")
        return Command(update=cleared, goto=cast(str, state["retry_node"]))

    return wait_escalation


def _finish(services: Services):
    def finish(state: State, config: RunnableConfig) -> dict[str, JsonValue]:
        services.log.append(
            _run_id(config),
            EventKind.RUN_FINISHED,
            node="finish",
            payload={"status": state["status"]},
        )
        return {}

    return finish
