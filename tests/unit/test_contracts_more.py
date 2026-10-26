import pytest
from pydantic import ValidationError

from conductor.contracts import (
    NOT_FINITE_MESSAGE,
    Escalation,
    FieldProblem,
    Plan,
    Step,
    TaskError,
    TaskResult,
    TaskSpec,
    problems_from,
)

TASK = "0123456789abcdef0123456789abcdef"
RUN = "fedcba9876543210fedcba9876543210"
THREAD = "00000000000000000000000000000001"


def reason(raised: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(raised.value.errors()[0]["ctx"]["error"])


def _result(number: int) -> TaskResult:
    return TaskResult(task_id=f"{number:032x}", status="succeeded", output={}, attempts=1)


def test_assigning_to_a_field_is_refused() -> None:
    step = Step(action="demo.echo", args={})
    with pytest.raises(ValidationError):
        step.action = "demo.other"  # type: ignore[misc]
    assert step.action == "demo.echo"
    assert step.args == {}


def test_a_task_error_message_of_500_characters_is_kept() -> None:
    kept = "m" * 500
    assert TaskError(kind="timeout", message=kept).message == kept
    with pytest.raises(ValidationError) as empty:
        TaskError(kind="timeout", message="")
    assert empty.value.errors()[0]["loc"] == ("message",)
    with pytest.raises(ValidationError) as long:
        TaskError(kind="timeout", message="m" * 501)
    assert long.value.errors()[0]["loc"] == ("message",)


def test_task_output_and_args_refuse_nan_from_json() -> None:
    spec = (
        '{"task_id":"'
        + TASK
        + '","run_id":"'
        + RUN
        + '","thread_id":"'
        + THREAD
        + '","step":1,"action":"demo.echo","args":{"n":NaN}}'
    )
    with pytest.raises(ValidationError) as raised:
        TaskSpec.from_json(spec)
    assert reason(raised) == NOT_FINITE_MESSAGE
    result = (
        '{"task_id":"' + TASK + '","status":"succeeded","output":{"n":NaN},'
        '"error":null,"attempts":1}'
    )
    with pytest.raises(ValidationError) as raised:
        TaskResult.from_json(result)
    assert reason(raised) == NOT_FINITE_MESSAGE


def test_a_task_spec_keeps_seven_earlier_results() -> None:
    seven = tuple(_result(number) for number in range(1, 8))
    spec = TaskSpec(
        task_id=TASK,
        run_id=RUN,
        thread_id=THREAD,
        step=1,
        action="demo.echo",
        args={},
        context=seven,
    )
    assert [item.task_id for item in spec.context] == [f"{number:032x}" for number in range(1, 8)]
    with pytest.raises(ValidationError) as raised:
        TaskSpec(
            task_id=TASK,
            run_id=RUN,
            thread_id=THREAD,
            step=1,
            action="demo.echo",
            args={},
            context=(*seven, _result(8)),
        )
    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [
        (("context",), "too_long")
    ]


def test_an_escalation_refuses_an_empty_detail_and_a_bad_run_id() -> None:
    with pytest.raises(ValidationError) as empty:
        Escalation(kind="rejected", detail="", run_id=RUN)
    assert empty.value.errors()[0]["loc"] == ("detail",)
    with pytest.raises(ValidationError) as bad_id:
        Escalation(kind="rejected", detail="the person rejected the step", run_id="latest")
    assert [(error["loc"], error["type"]) for error in bad_id.value.errors()] == [
        (("run_id",), "string_pattern_mismatch")
    ]


def test_problems_name_the_whole_object_and_mask_long_or_unsafe_keys() -> None:
    with pytest.raises(ValidationError) as mixed:
        Plan(
            steps=(
                Step(action="demo.echo", args={}),
                Step(action="finance.list_accounts", args={}),
            )
        )
    assert problems_from(mixed.value) == (FieldProblem(loc="", code="value_error"),)
    safe = "k" * 64
    longer = "k" * 65
    with pytest.raises(ValidationError) as raised:
        Step(action="demo.echo", args={safe: {1}, longer: {2}, "café": {3}})
    assert [problem.loc for problem in problems_from(raised.value)] == [
        "args." + safe,
        "args.*",
        "args.*",
    ]
