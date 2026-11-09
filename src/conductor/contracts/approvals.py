import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from conductor.contracts.base import ActionName, Contract, Id, JsonObject, Name
from conductor.contracts.plans import MAX_STEPS

STEP_COUNT_MESSAGE = "a step approval holds exactly one step"
NUMBERS_MESSAGE = "plan steps are numbered from 1 in order"
DIGEST_MESSAGE = "args_sha256 does not match the steps"
EDIT_MESSAGE = "edited_args go with an edit, and only with an edit"
UTC_MESSAGE = "time must be UTC"

ApprovalStage = Literal["plan", "step"]
Verdict = Literal["approve", "reject", "edit"]
Channel = Literal["terminal", "web"]
StepEffect = Literal["read", "propose", "write", "implement"]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(UTC_MESSAGE)
    return value


UtcTime = Annotated[AwareDatetime, AfterValidator(_utc)]


class PlannedStep(Contract):
    number: int = Field(ge=1, le=MAX_STEPS)
    action: ActionName
    effect: StepEffect
    args: JsonObject


def steps_digest(steps: Sequence[PlannedStep]) -> str:
    text = json.dumps(
        [step.model_dump(mode="json") for step in steps],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ApprovalRequest(Contract):
    approval_id: Id
    run_id: Id
    stage: ApprovalStage
    steps: tuple[PlannedStep, ...] = Field(min_length=1, max_length=MAX_STEPS)
    args_sha256: Sha256
    requested_at: UtcTime

    @model_validator(mode="after")
    def _steps_match_the_stage_and_the_digest(self) -> Self:
        if self.stage == "step" and len(self.steps) != 1:
            raise ValueError(STEP_COUNT_MESSAGE)
        if self.stage == "plan":
            numbers = tuple(step.number for step in self.steps)
            if numbers != tuple(range(1, len(self.steps) + 1)):
                raise ValueError(NUMBERS_MESSAGE)
        if self.args_sha256 != steps_digest(self.steps):
            raise ValueError(DIGEST_MESSAGE)
        return self


class ApprovalDecision(Contract):
    approval_id: Id
    verdict: Verdict
    args_sha256: Sha256
    edited_args: JsonObject | None = None
    note: str = Field(default="", max_length=500)
    channel: Channel
    decided_by: Name
    decided_at: UtcTime

    @model_validator(mode="after")
    def _edited_args_belong_to_an_edit(self) -> Self:
        if (self.verdict == "edit") != (self.edited_args is not None):
            raise ValueError(EDIT_MESSAGE)
        return self


Answer = Literal["retry", "cancel"]


class EscalationAnswer(Contract):
    escalation_id: Id
    answer: Answer
    note: str = Field(default="", max_length=500)
    channel: Channel
    decided_by: Name
    answered_at: UtcTime
