import hashlib
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from conductor.contracts.approvals import (
    DIGEST_MESSAGE,
    EDIT_MESSAGE,
    NUMBERS_MESSAGE,
    STEP_COUNT_MESSAGE,
    UTC_MESSAGE,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStage,
    Channel,
    PlannedStep,
    StepEffect,
    Verdict,
    steps_digest,
)
from conductor.registry import Effect

AT = datetime(2026, 11, 8, 9, 30, tzinfo=UTC)
ECHO = PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"})
NOTE = PlannedStep(
    number=2,
    action="demo.note",
    effect="write",
    args={"title": "Milk", "body": "", "tags": ["home"]},
)


def request(stage: str = "plan", steps=(ECHO, NOTE), **changes: object) -> ApprovalRequest:
    fields = {
        "approval_id": "1" * 32,
        "run_id": "a" * 32,
        "stage": stage,
        "steps": steps,
        "args_sha256": steps_digest(steps),
        "requested_at": AT,
    }
    return ApprovalRequest(**{**fields, **changes})


def decision(**changes: object) -> ApprovalDecision:
    fields = {
        "approval_id": "1" * 32,
        "verdict": "approve",
        "args_sha256": "e" * 64,
        "channel": "terminal",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


def test_the_closed_sets() -> None:
    assert get_args(ApprovalStage) == ("plan", "step")
    assert get_args(Verdict) == ("approve", "reject", "edit")
    assert get_args(Channel) == ("terminal", "web")
    assert get_args(StepEffect) == get_args(Effect)


def test_the_digest_is_pinned() -> None:
    text = (
        '[{"action":"demo.echo","args":{"text":"hi"},"effect":"read","number":1},'
        '{"action":"demo.note","args":{"body":"","tags":["home"],"title":"Milk"},'
        '"effect":"write","number":2}]'
    )
    assert steps_digest((ECHO, NOTE)) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert steps_digest((NOTE,)) != steps_digest((ECHO,))


def test_a_request_round_trips() -> None:
    for built in (request(), request("step", (NOTE,))):
        assert ApprovalRequest.from_json(built.model_dump_json()) == built


@pytest.mark.parametrize(
    ("stage", "steps", "changes", "message"),
    [
        ("step", (ECHO, NOTE), {}, STEP_COUNT_MESSAGE),
        ("plan", (ECHO, NOTE.model_copy(update={"number": 3})), {}, NUMBERS_MESSAGE),
        ("plan", (NOTE,), {}, NUMBERS_MESSAGE),
        ("plan", (ECHO, NOTE), {"args_sha256": "0" * 64}, DIGEST_MESSAGE),
        ("plan", (ECHO,), {"requested_at": "2026-11-08T09:30:00+02:00"}, UTC_MESSAGE),
    ],
)
def test_a_request_that_does_not_hold_together(
    stage: str, steps: tuple[PlannedStep, ...], changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        request(stage, steps, **changes)
    assert raised.value.errors()[0]["msg"] == f"Value error, {message}"


def test_a_request_time_must_say_its_zone() -> None:
    with pytest.raises(ValidationError) as raised:
        ApprovalRequest.from_json(
            request().model_dump_json().replace("2026-11-08T09:30:00Z", "2026-11-08T09:30:00")
        )
    assert raised.value.errors()[0]["type"] == "timezone_aware"


@pytest.mark.parametrize(
    ("changes", "kind"),
    [
        ({"verdict": "edit"}, EDIT_MESSAGE),
        ({"edited_args": {"title": "Eggs"}}, EDIT_MESSAGE),
        ({"note": "x" * 501}, "string_too_long"),
        ({"decided_by": "Owner"}, "string_pattern_mismatch"),
    ],
)
def test_a_decision_that_does_not_hold_together(changes: dict[str, object], kind: str) -> None:
    with pytest.raises(ValidationError) as raised:
        decision(**changes)
    error = raised.value.errors()[0]
    assert kind in (error["type"], error["msg"].removeprefix("Value error, "))


def test_a_decision_round_trips() -> None:
    edit = decision(verdict="edit", edited_args={"title": "Eggs"}, note="fewer", channel="web")
    for built in (decision(), decision(verdict="reject"), edit):
        assert ApprovalDecision.from_json(built.model_dump_json()) == built
    assert decision().note == ""
    assert decision().edited_args is None
