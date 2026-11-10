from dataclasses import dataclass
from typing import Annotated, Literal, Union

from pydantic import Field, create_model

from conductor import clock, plancheck
from conductor.contracts import MAX_STEPS, Contract, Escalation, Plan, Step
from conductor.events import EventLog
from conductor.llm.decide import InvalidModelOutput, decide, escalation_for
from conductor.llm.model import Model, ModelUnavailable
from conductor.llm.points import DecisionPoint
from conductor.plancheck import PLAN_REJECTED_MESSAGE, CheckedStep, PlanRejected
from conductor.registry import Domain, Registry
from conductor.routing.route import Routed

NO_FIT_MESSAGE = "no registered action fits the request"
PLAN_REPLY_TOKENS = 4096


class PlanInputs(Contract):
    request: str = Field(min_length=1, max_length=2000)


@dataclass(frozen=True)
class Planned:
    plan: Plan
    steps: tuple[CheckedStep, ...]
    decision_id: str


def plan_output(domain: Domain) -> type[Contract]:
    step_types = [
        create_model(
            f"{action.name}_step",
            __base__=Contract,
            action=(Literal[action.name], ...),
            args=(action.args, ...),
        )
        for action in domain.actions
    ]
    union = Annotated[
        Union.__getitem__(tuple(step_types)),
        Field(discriminator="action"),
    ]
    return create_model(
        "PlanOutput",
        __base__=Contract,
        steps=(tuple[union, ...], Field(max_length=MAX_STEPS)),
    )


def plan_point(domain: Domain) -> DecisionPoint:
    return DecisionPoint(
        name="plan",
        template="plan.v2",
        inputs=PlanInputs,
        output=plan_output(domain),
        think=True,
        max_reply_tokens=PLAN_REPLY_TOKENS,
    )


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def plan_fields(domain: Domain) -> dict[str, str]:
    day = clock.today()
    lines = [f"- {action.name}: {action.description}" for action in domain.actions]
    return {
        "domain": domain.name,
        "description": domain.description,
        "actions": "\n".join(lines),
        "today": day.isoformat(),
        "weekday": _WEEKDAYS[day.weekday()],
    }


def plan_request(
    routed: Routed,
    registry: Registry,
    *,
    model: Model,
    model_name: str,
    log: EventLog,
    run_id: str,
) -> Planned | Escalation:
    domain = registry.domain(routed.route.domain)
    try:
        decision = decide(
            plan_point(domain),
            PlanInputs(request=routed.request),
            fields=plan_fields(domain),
            model=model,
            model_name=model_name,
            log=log,
            run_id=run_id,
            node="plan",
        )
    except (InvalidModelOutput, ModelUnavailable) as error:
        return escalation_for(error, run_id)
    steps = decision.output.steps
    if not steps:
        return Escalation(
            kind="invalid_plan",
            detail=f"decision {decision.decision_id}: {NO_FIT_MESSAGE}",
            run_id=run_id,
        )
    plan = Plan(
        steps=tuple(
            Step(action=f"{domain.name}.{step.action}", args=step.args.model_dump(mode="json"))
            for step in steps
        )
    )
    try:
        checked = plancheck.check_plan(plan, routed.route, registry)
    except PlanRejected as error:
        return Escalation(
            kind="invalid_plan",
            detail=f"decision {decision.decision_id}: {PLAN_REJECTED_MESSAGE}",
            run_id=run_id,
            problems=error.problems,
        )
    return Planned(plan, checked, decision.decision_id)
