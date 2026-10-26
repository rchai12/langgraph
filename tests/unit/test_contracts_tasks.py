import json
from typing import get_args

import pytest
from pydantic import ValidationError

from conductor.contracts import (
    MAX_ATTEMPTS,
    MAX_PROBLEMS,
    RESULT_MESSAGE,
    DecidedBy,
    Escalation,
    EscalationKind,
    FieldProblem,
    Plan,
    Step,
    TaskError,
    TaskErrorKind,
    TaskResult,
    TaskSpec,
    TaskStatus,
    problems_from,
)

TASK = "0123456789abcdef0123456789abcdef"
RUN = "fedcba9876543210fedcba9876543210"
THREAD = "00000000000000000000000000000001"
EARLIER = "00000000000000000000000000000002"


def reason(raised: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(raised.value.errors()[0]["ctx"]["error"])


def test_the_closed_sets() -> None:
    assert get_args(DecidedBy) == ("rule", "model")
    assert get_args(TaskStatus) == ("succeeded", "failed", "escalated")
    assert get_args(TaskErrorKind) == (
        "invalid_args",
        "invalid_result",
        "tool_error",
        "agent_failed",
        "timeout",
    )
    assert get_args(EscalationKind) == (
        "invalid_model_output",
        "unknown_route",
        "invalid_plan",
        "tool_error",
        "retries_exhausted",
        "rejected",
    )
    assert (MAX_ATTEMPTS, MAX_PROBLEMS) == (3, 20)


def test_a_task_spec_carries_earlier_results_and_round_trips() -> None:
    earlier = TaskResult(
        task_id=EARLIER, status="succeeded", output={"total_cents": -12345}, attempts=1
    )
    spec = TaskSpec(
        task_id=TASK,
        run_id=RUN,
        thread_id=THREAD,
        step=2,
        action="finance.get_spending",
        args={"month": "2026-09"},
        context=(earlier,),
    )
    assert (spec.max_attempts, spec.domain) == (1, "finance")
    assert TaskSpec.from_json(spec.model_dump_json()) == spec
    assert spec.model_dump(mode="json")["context"] == [
        {
            "task_id": EARLIER,
            "status": "succeeded",
            "output": {"total_cents": -12345},
            "error": None,
            "attempts": 1,
        }
    ]


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("task_id", TASK.upper(), "string_pattern_mismatch"),
        ("step", 9, "less_than_equal"),
        ("max_attempts", "2", "int_type"),
    ],
)
def test_a_task_spec_from_text_refuses_bad_values(field: str, value: object, kind: str) -> None:
    given = {
        "task_id": TASK,
        "run_id": RUN,
        "thread_id": THREAD,
        "step": 1,
        "action": "demo.echo",
        "args": {},
        field: value,
    }
    with pytest.raises(ValidationError) as raised:
        TaskSpec.from_json(json.dumps(given))
    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [((field,), kind)]


@pytest.mark.parametrize(
    ("status", "output", "error", "ok"),
    [
        ("succeeded", {"echo": "hi"}, None, True),
        ("failed", None, TaskError(kind="tool_error", message="server stopped"), True),
        ("succeeded", None, None, False),
        ("succeeded", {"echo": "hi"}, TaskError(kind="timeout", message="no answer"), False),
        ("failed", None, None, False),
        ("failed", {"partial": 1}, TaskError(kind="tool_error", message="server stopped"), False),
    ],
)
def test_a_result_has_output_or_an_error_never_both(
    status: str, output: dict | None, error: TaskError | None, ok: bool
) -> None:
    given = {"task_id": TASK, "status": status, "output": output, "error": error, "attempts": 1}
    if ok:
        assert TaskResult.model_validate(given).status == status
        return
    with pytest.raises(ValidationError) as raised:
        TaskResult.model_validate(given)
    assert reason(raised) == RESULT_MESSAGE
    assert RESULT_MESSAGE == (
        "a succeeded result has output and no error; any other result has an error and no output"
    )


def test_problems_never_carry_what_was_given() -> None:
    with pytest.raises(ValidationError) as raised:
        Step.model_validate(
            {"action": "Bad", "args": {"card 4417-1234": {1, 2}, "ok": b"secret 4417"}}
        )
    found = problems_from(raised.value)
    assert found == (
        FieldProblem(loc="action", code="string_pattern_mismatch"),
        FieldProblem(loc="args.*", code="invalid-json-value"),
        FieldProblem(loc="args.ok", code="invalid-json-value"),
    )
    assert "4417" not in repr(found)


def test_problems_name_list_positions_and_stop_at_twenty() -> None:
    with pytest.raises(ValidationError) as raised:
        Plan.model_validate({"steps": [{"action": "demo.echo", "args": {}}, {"action": "Bad"}]})
    assert problems_from(raised.value)[:2] == (
        FieldProblem(loc="steps.1.action", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.1.args", code="missing"),
    )
    with pytest.raises(ValidationError) as raised:
        Step.model_validate({"action": "demo.echo", "args": {f"k{n:02d}": {n} for n in range(25)}})
    found = problems_from(raised.value)
    assert len(found) == 20
    assert (found[0].loc, found[19].loc) == ("args.k00", "args.k19")


def test_an_escalation_points_at_its_run() -> None:
    escalation = Escalation(
        kind="invalid_plan",
        detail="the plan names an action the domain does not have",
        run_id=RUN,
        problems=(FieldProblem(loc="steps.0.action", code="unknown_action"),),
    )
    assert Escalation.from_json(escalation.model_dump_json()) == escalation
    assert Escalation(kind="unknown_route", detail="no domain fits", run_id=RUN).problems == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "gave_up"),
        ("detail", "x" * 501),
        ("problems", [{"loc": "a", "code": "missing"}] * 21),
    ],
)
def test_an_escalation_refuses_bad_values(field: str, value: object) -> None:
    given = {"kind": "rejected", "detail": "the person rejected the step", "run_id": RUN}
    given[field] = value
    with pytest.raises(ValidationError) as raised:
        Escalation.model_validate(given)
    assert [error["loc"][0] for error in raised.value.errors()] == [field]
