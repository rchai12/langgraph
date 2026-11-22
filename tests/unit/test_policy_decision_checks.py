from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from conductor import clock, ids
from conductor.contracts.approvals import (
    NUMBERS_MESSAGE,
    ApprovalDecision,
    ApprovalRequest,
    PlannedStep,
    steps_digest,
)
from conductor.domains import demo
from conductor.plancheck import CheckedStep
from conductor.policy import (
    ATTEMPT_MESSAGE,
    Approved,
    DecisionRefused,
    Rejected,
    apply_decision,
    needs_approval,
    plan_request,
    step_request,
)
from conductor.registry import Registry

AT = datetime(2026, 11, 8, 9, 30, tzinfo=UTC)
RUN = "a" * 32
APPROVAL = "1" * 32
ECHO, NOTE, DELEGATE = demo.DOMAIN.actions
REGISTRY = Registry((demo.DOMAIN,))
ECHO_STEP = CheckedStep(number=1, action=ECHO, args=demo.EchoArgs(text="hi"))
NOTE_STEP = CheckedStep(number=2, action=NOTE, args=demo.NoteArgs(title="Milk", tags=("home",)))


def decide_on(request, **changes: object):
    fields = {
        "approval_id": request.approval_id,
        "verdict": "approve",
        "args_sha256": request.args_sha256,
        "channel": "terminal",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


def test_a_lone_step_keeps_its_number_and_a_repeated_plan_number_is_refused() -> None:
    for number in range(1, 9):
        step = PlannedStep(number=number, action="demo.echo", effect="read", args={"text": "hi"})
        built = ApprovalRequest(
            approval_id=APPROVAL,
            run_id=RUN,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=AT,
        )
        assert built.steps[0].number == number
    repeated = (
        PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"}),
        PlannedStep(
            number=1,
            action="demo.note",
            effect="write",
            args={"title": "Milk", "body": "", "tags": ["home"]},
        ),
    )
    with pytest.raises(ValidationError) as raised:
        ApprovalRequest(
            approval_id=APPROVAL,
            run_id=RUN,
            stage="plan",
            steps=repeated,
            args_sha256=steps_digest(repeated),
            requested_at=AT,
        )
    assert raised.value.errors()[0]["msg"] == f"Value error, {NUMBERS_MESSAGE}"


def test_a_negative_attempt_is_refused_and_one_is_the_default() -> None:
    with pytest.raises(ValueError) as raised:
        needs_approval(DELEGATE, attempt=-1)
    assert str(raised.value) == ATTEMPT_MESSAGE
    assert needs_approval(DELEGATE) is True


def test_a_plan_shows_the_read_step_beside_a_propose_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"id": 0, "now": 0}

    def new_id() -> str:
        calls["id"] += 1
        return APPROVAL

    def now() -> datetime:
        calls["now"] += 1
        return AT

    monkeypatch.setattr(ids, "new_id", new_id)
    monkeypatch.setattr(clock, "now", now)
    propose = replace(NOTE, name="draft", effect="propose")
    propose_step = CheckedStep(number=2, action=propose, args=demo.NoteArgs(title="Milk"))
    request = plan_request("demo", (ECHO_STEP, propose_step), run_id=RUN)
    assert request is not None
    assert [(step.action, step.effect) for step in request.steps] == [
        ("demo.echo", "read"),
        ("demo.draft", "propose"),
    ]
    assert calls == {"id": 1, "now": 1}


def test_the_approval_id_is_checked_before_the_digest() -> None:
    request = step_request("demo", NOTE_STEP, run_id=RUN)
    assert request is not None
    other = decide_on(request, approval_id="2" * 32, args_sha256="0" * 64)
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, other, REGISTRY)
    assert raised.value.code == "other_request"
    plan = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    assert plan is not None
    edited = decide_on(plan, verdict="edit", edited_args={"text": "bye"}, args_sha256="0" * 64)
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(plan, edited, REGISTRY)
    assert raised.value.code == "stale"


def test_a_plan_rejection_keeps_an_empty_note() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    assert request is not None
    assert apply_decision(request, decide_on(request, verdict="reject"), REGISTRY) == Rejected(
        note=""
    )


def test_an_approved_step_parses_a_fresh_copy_of_its_arguments() -> None:
    request = step_request("demo", NOTE_STEP, run_id=RUN)
    assert request is not None
    outcome = apply_decision(request, decide_on(request), REGISTRY)
    assert isinstance(outcome, Approved)
    assert outcome.args == NOTE_STEP.args
    assert outcome.args is not NOTE_STEP.args
    assert type(outcome.args) is type(NOTE_STEP.args)


def test_an_invalid_edit_does_not_echo_the_value() -> None:
    request = step_request("demo", NOTE_STEP, run_id=RUN)
    assert request is not None
    decided = decide_on(
        request,
        verdict="edit",
        edited_args={"title": "Milk", "tags": ["SYNTHETIC-SECRET"]},
    )
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, decided, REGISTRY)
    assert raised.value.code == "invalid_edit"
    assert "SYNTHETIC-SECRET" not in str(raised.value)
    assert "SYNTHETIC-SECRET" not in raised.value.code
    assert "SYNTHETIC-SECRET" not in repr(raised.value.problems)
