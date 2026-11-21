import json
from typing import Literal, Protocol, cast

from pydantic import ValidationError

from conductor.contracts import Contract, Escalation, FieldProblem, problems_from
from conductor.events import EventKind, EventLog, JsonValue
from conductor.plancheck import CheckedStep
from conductor.planning.answer import StepOutcome
from conductor.registry import Action, Effect

FAILURE_CODES = (
    "tool_error",
    "no_command",
    "start_failed",
    "timeout",
    "closed",
    "no_result",
    "too_large",
)
FailureCode = Literal[
    "tool_error",
    "no_command",
    "start_failed",
    "timeout",
    "closed",
    "no_result",
    "too_large",
]
STEP_FAILED_DETAIL = "the step failed"
RESULT_DETAIL = "the result does not fit the action"
INVALID_RESULT = "invalid_result"
NOT_DONE_CODES = ("no_command", "start_failed", "tool_error")


class StepFailed(Exception):
    """A runner raises it when a step could not be done; its text is never shown."""

    def __init__(self, *args: object, code: FailureCode | None = None) -> None:
        self.code: FailureCode | None = code if code in FAILURE_CODES else None
        super().__init__(*args)


class StepRunner(Protocol):
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...


def failure_fields(effect: Effect, code: str | None) -> dict[str, JsonValue]:
    return {
        "code": code,
        "effect": effect,
        "unknown_outcome": effect != "read" and code not in NOT_DONE_CODES,
    }


def run_step(
    step: CheckedStep,
    domain: str,
    args: Contract,
    *,
    runner: StepRunner,
    log: EventLog,
    run_id: str,
) -> StepOutcome | Escalation:
    action = step.action
    full_name = f"{domain}.{action.name}"
    log.append(
        run_id,
        EventKind.TOOL_CALL,
        node="run_step",
        payload={"step": step.number, "action": full_name, "args": _dump(args)},
    )
    try:
        output = runner.run(action, args)
    except StepFailed as error:
        reason = STEP_FAILED_DETAIL
        if error.code is not None:
            reason = f"{STEP_FAILED_DETAIL} ({error.code})"
        return _failed(step, full_name, reason, error.code, (), log=log, run_id=run_id)
    try:
        parsed = action.result.from_json(json.dumps(output))
    except ValidationError as error:
        return _failed(
            step,
            full_name,
            RESULT_DETAIL,
            INVALID_RESULT,
            problems_from(error),
            log=log,
            run_id=run_id,
        )
    dumped = _dump(parsed)
    log.append(
        run_id,
        EventKind.TOOL_RESULT,
        node="run_step",
        payload={"step": step.number, "output": dumped},
    )
    return StepOutcome(step=step.number, action=full_name, output=dumped)


def _dump(model: Contract) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], model.model_dump(mode="json"))


def _failed(
    step: CheckedStep,
    full_name: str,
    reason: str,
    code: str | None,
    problems: tuple[FieldProblem, ...],
    *,
    log: EventLog,
    run_id: str,
) -> Escalation:
    log.append(
        run_id,
        EventKind.ERROR,
        node="run_step",
        payload={
            "step": step.number,
            "error": "tool_error",
            **failure_fields(step.action.effect, code),
            "problems": [{"loc": problem.loc, "code": problem.code} for problem in problems],
        },
    )
    return Escalation(
        kind="tool_error",
        detail=f"step {step.number} {full_name}: {reason}",
        run_id=run_id,
        problems=problems,
    )
