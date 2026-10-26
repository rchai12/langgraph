from typing import Literal, Self

from pydantic import Field, model_validator

from conductor.contracts.base import ActionName, Contract, Id, JsonObject
from conductor.contracts.plans import MAX_STEPS

MAX_ATTEMPTS = 3
RESULT_MESSAGE = (
    "a succeeded result has output and no error; any other result has an error and no output"
)
TaskStatus = Literal["succeeded", "failed", "escalated"]
TaskErrorKind = Literal["invalid_args", "invalid_result", "tool_error", "agent_failed", "timeout"]


class TaskError(Contract):
    kind: TaskErrorKind
    message: str = Field(min_length=1, max_length=500)


class TaskResult(Contract):
    task_id: Id
    status: TaskStatus
    output: JsonObject | None = None
    error: TaskError | None = None
    attempts: int = Field(ge=1, le=MAX_ATTEMPTS)

    @model_validator(mode="after")
    def _output_or_error(self) -> Self:
        if self.status == "succeeded":
            valid = self.output is not None and self.error is None
        else:
            valid = self.error is not None and self.output is None
        if not valid:
            raise ValueError(RESULT_MESSAGE)
        return self


class TaskSpec(Contract):
    task_id: Id
    run_id: Id
    thread_id: Id
    step: int = Field(ge=1, le=MAX_STEPS)
    action: ActionName
    args: JsonObject
    context: tuple[TaskResult, ...] = Field(default=(), max_length=MAX_STEPS - 1)
    max_attempts: int = Field(default=1, ge=1, le=MAX_ATTEMPTS)

    @property
    def domain(self) -> str:
        return self.action.split(".", 1)[0]
