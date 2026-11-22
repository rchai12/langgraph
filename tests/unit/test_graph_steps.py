from pathlib import Path

import pytest

from conductor.contracts import Escalation, FieldProblem
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph import steps, supervisor
from conductor.plancheck import CheckedStep
from conductor.planning.answer import StepOutcome

RUN = "a" * 32
ECHO, NOTE, DELEGATE = demo.DOMAIN.actions


class Runner:
    def __init__(self, output: object = None, error: steps.StepFailed | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[str] = []

    def run(self, action, _args):
        self.calls.append(action.name)
        if self.error is not None:
            raise self.error
        return self.output


def test_the_codes_and_the_old_names() -> None:
    assert steps.FAILURE_CODES == (
        "tool_error",
        "no_command",
        "start_failed",
        "timeout",
        "closed",
        "no_result",
        "too_large",
    )
    assert (steps.NOT_DONE_CODES, steps.INVALID_RESULT) == (
        ("no_command", "start_failed", "tool_error"),
        "invalid_result",
    )
    assert (steps.STEP_FAILED_DETAIL, steps.RESULT_DETAIL) == (
        "the step failed",
        "the result does not fit the action",
    )
    moved = ("FAILURE_CODES", "STEP_FAILED_DETAIL", "RESULT_DETAIL", "StepFailed", "StepRunner")
    assert [getattr(supervisor, name) is getattr(steps, name) for name in moved] == [True] * 5


@pytest.mark.parametrize(
    ("effect", "code", "unknown"),
    [
        ("read", "timeout", False),
        ("read", None, False),
        ("read", "invalid_result", False),
        ("write", "timeout", True),
        ("write", "closed", True),
        ("write", "no_result", True),
        ("write", "too_large", True),
        ("write", "invalid_result", True),
        ("write", None, True),
        ("write", "no_command", False),
        ("write", "start_failed", False),
        ("write", "tool_error", False),
        ("propose", "closed", True),
        ("propose", "tool_error", False),
        ("implement", None, True),
        ("implement", "start_failed", False),
    ],
    ids=lambda value: str(value),
)
def test_which_failures_leave_the_outcome_unknown(
    effect: str, code: str | None, unknown: bool
) -> None:
    assert steps.failure_fields(effect, code) == {
        "code": code,
        "effect": effect,
        "unknown_outcome": unknown,
    }


def test_a_step_that_runs_returns_its_outcome(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    step = CheckedStep(number=1, action=ECHO, args=ECHO.args(text="hi"))
    found = steps.run_step(
        step, "demo", step.args, runner=Runner({"text": "hi"}), log=log, run_id=RUN
    )
    assert found == StepOutcome(step=1, action="demo.echo", output={"text": "hi"})
    assert [(event.kind, event.node, event.payload) for event in log.read(RUN)] == [
        (
            EventKind.TOOL_CALL,
            "run_step",
            {"step": 1, "action": "demo.echo", "args": {"text": "hi"}},
        ),
        (EventKind.TOOL_RESULT, "run_step", {"step": 1, "output": {"text": "hi"}}),
    ]


@pytest.mark.parametrize(
    ("number", "action", "runner", "detail", "fields", "problems"),
    [
        (
            2,
            NOTE,
            Runner(error=steps.StepFailed("SYNTHETIC-SECRET", code="timeout")),
            "step 2 demo.note: the step failed (timeout)",
            {"code": "timeout", "effect": "write", "unknown_outcome": True},
            (),
        ),
        (
            1,
            ECHO,
            Runner(error=steps.StepFailed("SYNTHETIC-SECRET")),
            "step 1 demo.echo: the step failed",
            {"code": None, "effect": "read", "unknown_outcome": False},
            (),
        ),
        (
            1,
            NOTE,
            Runner({}),
            "step 1 demo.note: the result does not fit the action",
            {"code": "invalid_result", "effect": "write", "unknown_outcome": True},
            (FieldProblem(loc="note_id", code="missing"),),
        ),
    ],
    ids=["write-timeout", "read-uncoded", "write-bad-result"],
)
def test_a_failed_step_escalates_and_records_its_cause(
    tmp_path: Path,
    number: int,
    action,
    runner: Runner,
    detail: str,
    fields: dict,
    problems: tuple[FieldProblem, ...],
) -> None:
    log = EventLog(tmp_path)
    args = {"echo": {"text": "hi"}, "note": {"title": "Milk"}}[action.name]
    step = CheckedStep(number=number, action=action, args=action.args(**args))
    found = steps.run_step(step, "demo", step.args, runner=runner, log=log, run_id=RUN)
    assert found == Escalation(kind="tool_error", detail=detail, run_id=RUN, problems=problems)
    error = log.read(RUN)[-1]
    assert (error.kind, error.node) == (EventKind.ERROR, "run_step")
    assert error.payload == {
        "step": number,
        "error": "tool_error",
        **fields,
        "problems": [{"loc": problem.loc, "code": problem.code} for problem in problems],
    }
    assert "SYNTHETIC-SECRET" not in (tmp_path / f"{RUN}.jsonl").read_text(encoding="utf-8")
