import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from conductor import clock, ids
from conductor.contracts import Contract, FieldProblem, problems_from
from conductor.contracts.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    PlannedStep,
    steps_digest,
)
from conductor.plancheck import CheckedStep
from conductor.registry import Action, Registry

ATTEMPT_MESSAGE = "attempt must be at least 1"
RefusalCode = Literal["other_request", "stale", "edit_on_plan", "invalid_edit"]


class DecisionRefused(Exception):
    def __init__(self, code: RefusalCode, problems: tuple[FieldProblem, ...] = ()) -> None:
        self.code = code
        self.problems = problems
        super().__init__(f"decision refused: {code}")


@dataclass(frozen=True)
class Approved:
    args: Contract | None
    edited: bool


@dataclass(frozen=True)
class Rejected:
    note: str


def needs_approval(action: Action, *, attempt: int = 1) -> bool:
    if attempt < 1:
        raise ValueError(ATTEMPT_MESSAGE)
    if action.effect == "read":
        return False
    if action.effect == "implement":
        return attempt == 1
    return True


def plan_request(
    domain: str, steps: Sequence[CheckedStep], *, run_id: str
) -> ApprovalRequest | None:
    if not any(needs_approval(step.action) for step in steps):
        return None
    return _request(domain, steps, run_id, "plan")


def step_request(
    domain: str, step: CheckedStep, *, run_id: str, attempt: int = 1
) -> ApprovalRequest | None:
    if not needs_approval(step.action, attempt=attempt):
        return None
    return _request(domain, (step,), run_id, "step")


def apply_decision(
    request: ApprovalRequest, decision: ApprovalDecision, registry: Registry
) -> Approved | Rejected:
    if decision.approval_id != request.approval_id:
        raise DecisionRefused("other_request")
    if decision.args_sha256 != request.args_sha256:
        raise DecisionRefused("stale")
    if decision.verdict == "reject":
        return Rejected(decision.note)
    if decision.verdict == "edit" and request.stage == "plan":
        raise DecisionRefused("edit_on_plan")
    if request.stage == "plan":
        return Approved(None, False)
    raw = decision.edited_args if decision.verdict == "edit" else request.steps[0].args
    try:
        parsed = registry.action(request.steps[0].action).args.from_json(json.dumps(raw))
    except ValidationError as error:
        raise DecisionRefused("invalid_edit", problems_from(error)) from None
    return Approved(parsed, decision.verdict == "edit")


def _request(domain: str, steps: Sequence[CheckedStep], run_id: str, stage: str) -> ApprovalRequest:
    planned = tuple(
        PlannedStep(
            number=step.number,
            action=f"{domain}.{step.action.name}",
            effect=step.action.effect,
            args=step.args.model_dump(mode="json"),
        )
        for step in steps
    )
    return ApprovalRequest(
        approval_id=ids.new_id(),
        run_id=run_id,
        stage=stage,
        steps=planned,
        args_sha256=steps_digest(planned),
        requested_at=clock.now(),
    )
