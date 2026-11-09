from dataclasses import dataclass
from typing import Literal

from pydantic import Field, create_model

from conductor.contracts import MAX_PROBLEMS, Contract, Escalation, FieldProblem, Route
from conductor.events import EventLog
from conductor.llm.decide import InvalidModelOutput, decide, escalation_for
from conductor.llm.model import Model, ModelUnavailable
from conductor.llm.points import DecisionPoint
from conductor.registry import Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

REQUEST_MESSAGE = "a request must have 1 to 2000 characters"
NO_DOMAINS_MESSAGE = "no domains are registered"
CONFLICT_MESSAGE = "rules of more than one domain match the request"
EMPTY_MESSAGE = "nothing follows the prefix"
NO_FIT_MESSAGE = "no domain fits the request"
ROUTE_REPLY_TOKENS = 2048


class RouteInputs(Contract):
    request: str = Field(min_length=1, max_length=2000)


@dataclass(frozen=True)
class Routed:
    route: Route
    request: str
    decision_id: str | None = None


def route_output(registry: Registry) -> type[Contract]:
    return create_model(
        "RouteOutput",
        __base__=Contract,
        domain=(Literal[(*registry.names, "unknown")], ...),
    )


def route_point(registry: Registry) -> DecisionPoint:
    return DecisionPoint(
        name="route",
        template="route.v1",
        inputs=RouteInputs,
        output=route_output(registry),
        think=True,
        max_reply_tokens=ROUTE_REPLY_TOKENS,
    )


def route_fields(registry: Registry) -> dict[str, str]:
    lines = [f"- {name}: {registry.domain(name).description}" for name in registry.names]
    return {"domains": "\n".join(lines)}


def route_request(
    request: str,
    registry: Registry,
    *,
    model: Model,
    model_name: str,
    log: EventLog,
    run_id: str,
) -> Routed | Escalation:
    if not request.strip() or len(request) > 2000:
        raise ValueError(REQUEST_MESSAGE)
    found = match_rules(request, registry)
    if isinstance(found, RuleRoute):
        if found.request == "":
            return Escalation(
                kind="unknown_route",
                detail=f"{EMPTY_MESSAGE} {found.route.domain}:",
                run_id=run_id,
            )
        return Routed(found.route, found.request)
    if isinstance(found, RuleConflict):
        problems = tuple(
            FieldProblem(loc=rule_id, code="matched") for rule_id in found.rule_ids[:MAX_PROBLEMS]
        )
        return Escalation(
            kind="unknown_route",
            detail=CONFLICT_MESSAGE,
            run_id=run_id,
            problems=problems,
        )
    if not registry.names:
        return Escalation(kind="unknown_route", detail=NO_DOMAINS_MESSAGE, run_id=run_id)
    try:
        decision = decide(
            route_point(registry),
            RouteInputs(request=request),
            fields=route_fields(registry),
            model=model,
            model_name=model_name,
            log=log,
            run_id=run_id,
            node="route",
        )
    except (InvalidModelOutput, ModelUnavailable) as error:
        return escalation_for(error, run_id)
    domain = decision.output.domain
    if domain == "unknown":
        return Escalation(
            kind="unknown_route",
            detail=f"decision {decision.decision_id}: {NO_FIT_MESSAGE}",
            run_id=run_id,
        )
    return Routed(Route(domain=domain, decided_by="model"), request, decision.decision_id)
