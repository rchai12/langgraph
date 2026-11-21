import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict, cast

from langgraph.types import Command, RunnableConfig, interrupt

from conductor import plancheck, policy
from conductor.contracts import Contract, Escalation, Plan, Route
from conductor.contracts.approvals import ApprovalDecision, ApprovalRequest, EscalationAnswer
from conductor.events import EventKind, EventLog, JsonValue
from conductor.graph import steps
from conductor.graph.status import NODES
from conductor.llm.model import Model
from conductor.planning.answer import Answered, StepOutcome, answer_request
from conductor.planning.plan import Planned, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed, route_request
from conductor.store import Store


@dataclass(frozen=True)
class Services:
    registry: Registry
    store: Store
    log: EventLog
    model: Model
    model_name: str
    runner: steps.StepRunner


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


def build_nodes(services: Services) -> dict[str, Callable[..., object]]:
    built = {
        "route": _route(services),
        "plan": _plan(services),
        "ask_plan": _ask_plan(services),
        "ask_step": _ask_step(services),
        "wait_approval": _wait_approval(services),
        "run_step": _run_step(services),
        "answer": _answer(services),
        "record_escalation": _record_escalation(services),
        "wait_escalation": _wait_escalation(services),
        "finish": _finish(services),
    }
    return {name: built[name] for name in NODES}


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
        domain = _load(Route, state["route"]).domain
        if state.get("args") is None:
            args = step.args
        else:
            args = step.action.args.from_json(json.dumps(state["args"]))
        found = steps.run_step(
            step, domain, args, runner=services.runner, log=services.log, run_id=run_id
        )
        if isinstance(found, Escalation):
            return _escalate(found, "ask_step")
        results = [*state.get("results", []), _dump(found)]
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
