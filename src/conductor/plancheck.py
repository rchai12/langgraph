import json
from dataclasses import dataclass

from pydantic import ValidationError

from conductor.contracts import MAX_PROBLEMS, Contract, FieldProblem, Plan, Route, problems_from
from conductor.registry import Action, NotRegistered, Registry

PLAN_REJECTED_MESSAGE = "the plan does not fit the registry"


@dataclass(frozen=True)
class CheckedStep:
    number: int
    action: Action
    args: Contract


class PlanRejected(Exception):
    problems: tuple[FieldProblem, ...]

    def __init__(self, problems: tuple[FieldProblem, ...]) -> None:
        super().__init__(PLAN_REJECTED_MESSAGE)
        self.problems = problems


def check_plan(plan: Plan, route: Route, registry: Registry) -> tuple[CheckedStep, ...]:
    try:
        registry.domain(route.domain)
    except NotRegistered:
        raise PlanRejected((FieldProblem(loc="route.domain", code="unknown_domain"),)) from None
    if plan.domain != route.domain:
        raise PlanRejected((FieldProblem(loc="steps", code="wrong_domain"),))
    problems: list[FieldProblem] = []
    checked: list[CheckedStep] = []
    for index, step in enumerate(plan.steps):
        try:
            action = registry.action(step.action)
        except NotRegistered:
            problems.append(FieldProblem(loc=f"steps.{index}.action", code="unknown_action"))
            continue
        try:
            parsed = action.args.from_json(json.dumps(step.args))
        except ValidationError as error:
            problems.extend(_argument_problems(index, error))
            continue
        checked.append(CheckedStep(number=index + 1, action=action, args=parsed))
    if problems:
        raise PlanRejected(tuple(problems[:MAX_PROBLEMS]))
    return tuple(checked)


def _argument_problems(index: int, error: ValidationError) -> tuple[FieldProblem, ...]:
    prefix = f"steps.{index}.args"
    located: list[FieldProblem] = []
    for problem in problems_from(error):
        loc = f"{prefix}.{problem.loc}" if problem.loc else prefix
        located.append(FieldProblem(loc=loc, code=problem.code))
    return tuple(located)
