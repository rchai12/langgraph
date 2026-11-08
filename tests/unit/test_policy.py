from dataclasses import replace
from datetime import UTC, datetime

import pytest

from conductor import clock, ids
from conductor.contracts import FieldProblem
from conductor.contracts.approvals import ApprovalDecision, PlannedStep, steps_digest
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
PROPOSE = replace(NOTE, name="draft", effect="propose")
REGISTRY = Registry((demo.DOMAIN,))

ECHO_STEP = CheckedStep(number=1, action=ECHO, args=demo.EchoArgs(text="hi"))
NOTE_STEP = CheckedStep(number=2, action=NOTE, args=demo.NoteArgs(title="Milk", tags=("home",)))


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: AT)
    monkeypatch.setattr(ids, "new_id", lambda: APPROVAL)


@pytest.mark.parametrize(
    ("action", "attempt", "needed"),
    [
        (ECHO, 1, False),
        (PROPOSE, 1, True),
        (NOTE, 1, True),
        (NOTE, 2, True),
        (DELEGATE, 1, True),
        (DELEGATE, 3, False),
    ],
)
def test_what_needs_approval(action, attempt: int, needed: bool) -> None:
    assert needs_approval(action, attempt=attempt) is needed


def test_attempts_count_from_one() -> None:
    with pytest.raises(ValueError) as raised:
        needs_approval(NOTE, attempt=0)
    assert str(raised.value) == ATTEMPT_MESSAGE == "attempt must be at least 1"


def test_a_read_only_plan_needs_no_approval() -> None:
    assert plan_request("demo", (ECHO_STEP, replace(ECHO_STEP, number=2)), run_id=RUN) is None


def test_a_plan_with_a_side_effect_shows_every_step() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    steps = (
        PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"}),
        PlannedStep(
            number=2,
            action="demo.note",
            effect="write",
            args={"title": "Milk", "body": "", "tags": ["home"]},
        ),
    )
    assert request is not None
    assert (request.approval_id, request.run_id, request.stage) == (APPROVAL, RUN, "plan")
    assert request.steps == steps
    assert request.args_sha256 == steps_digest(steps)
    assert request.requested_at == AT


@pytest.mark.parametrize(
    ("step", "attempt", "asked"),
    [
        (ECHO_STEP, 1, False),
        (NOTE_STEP, 1, True),
        (CheckedStep(number=3, action=DELEGATE, args=demo.DelegateArgs(task="Build 4a")), 2, False),
    ],
)
def test_a_step_request(step: CheckedStep, attempt: int, asked: bool) -> None:
    request = step_request("demo", step, run_id=RUN, attempt=attempt)
    if not asked:
        assert request is None
        return
    assert request is not None
    assert request.stage == "step"
    assert [(s.number, s.action) for s in request.steps] == [(2, "demo.note")]


def decide_on(request, **changes: object) -> ApprovalDecision:
    fields = {
        "approval_id": request.approval_id,
        "verdict": "approve",
        "args_sha256": request.args_sha256,
        "channel": "terminal",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


def note_request():
    return step_request("demo", NOTE_STEP, run_id=RUN)


def test_an_approved_plan() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    assert apply_decision(request, decide_on(request), REGISTRY) == Approved(
        args=None, edited=False
    )


def test_an_approved_step_runs_with_its_own_arguments() -> None:
    request = note_request()
    outcome = apply_decision(request, decide_on(request), REGISTRY)
    assert outcome == Approved(args=demo.NoteArgs(title="Milk", tags=("home",)), edited=False)
    assert type(outcome.args) is demo.NoteArgs


def test_a_rejection_ends_with_the_note() -> None:
    request = note_request()
    decided = decide_on(request, verdict="reject", note="not today")
    assert apply_decision(request, decided, REGISTRY) == Rejected(note="not today")


def test_an_edit_approves_the_new_arguments() -> None:
    request = note_request()
    decided = decide_on(request, verdict="edit", edited_args={"title": "Eggs", "tags": ["home"]})
    assert apply_decision(request, decided, REGISTRY) == Approved(
        args=demo.NoteArgs(title="Eggs", tags=("home",)), edited=True
    )


@pytest.mark.parametrize(
    ("changes", "code", "problems"),
    [
        ({"approval_id": "2" * 32}, "other_request", ()),
        ({"args_sha256": "0" * 64}, "stale", ()),
        (
            {"verdict": "edit", "edited_args": {"title": "", "tags": ["Home"]}},
            "invalid_edit",
            (
                FieldProblem(loc="title", code="string_too_short"),
                FieldProblem(loc="tags.0", code="string_pattern_mismatch"),
            ),
        ),
    ],
)
def test_a_decision_that_is_refused(
    changes: dict[str, object], code: str, problems: tuple[FieldProblem, ...]
) -> None:
    request = note_request()
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, decide_on(request, **changes), REGISTRY)
    assert (raised.value.code, raised.value.problems) == (code, problems)
    assert str(raised.value) == f"decision refused: {code}"


def test_a_plan_cannot_be_edited() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    decided = decide_on(request, verdict="edit", edited_args={"text": "bye"})
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, decided, REGISTRY)
    assert raised.value.code == "edit_on_plan"
