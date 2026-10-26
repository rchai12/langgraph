from typing import Literal, Self

from pydantic import Field, model_validator

from conductor.contracts.base import ActionName, Contract, JsonObject, Name, RuleId

MAX_STEPS = 8
ROUTE_MESSAGE = "a rule route needs a rule_id and a model route has none"
ONE_DOMAIN_MESSAGE = "every step must be in one domain"
DecidedBy = Literal["rule", "model"]


class Route(Contract):
    domain: Name
    decided_by: DecidedBy
    rule_id: RuleId | None = None

    @model_validator(mode="after")
    def _rule_id_matches_who_decided(self) -> Self:
        has_rule = self.rule_id is not None
        if self.decided_by == "rule" and not has_rule:
            raise ValueError(ROUTE_MESSAGE)
        if self.decided_by == "model" and has_rule:
            raise ValueError(ROUTE_MESSAGE)
        return self


class Step(Contract):
    action: ActionName
    args: JsonObject

    @property
    def domain(self) -> str:
        return self.action.split(".", 1)[0]


class Plan(Contract):
    steps: tuple[Step, ...] = Field(min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _one_domain(self) -> Self:
        if len({step.domain for step in self.steps}) != 1:
            raise ValueError(ONE_DOMAIN_MESSAGE)
        return self

    @property
    def domain(self) -> str:
        return self.steps[0].domain
