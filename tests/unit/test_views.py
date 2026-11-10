from datetime import UTC, datetime

from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    EscalationAnswer,
    PlannedStep,
    steps_digest,
)
from conductor.store import StoredApproval, StoredEscalation
from conductor.views import escalation_lines, request_lines

FIRST = "1" * 32
RUN = "a" * 32
AT = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
DECIDED = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})


def _request(steps: tuple[PlannedStep, ...] = (NOTE,), stage: str = "step") -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=FIRST,
        run_id=RUN,
        stage=stage,
        steps=steps,
        args_sha256=steps_digest(steps),
        requested_at=AT,
    )


def _decision(verdict: str, note: str = "", edited: dict | None = None) -> ApprovalDecision:
    return ApprovalDecision(
        approval_id=FIRST,
        verdict=verdict,
        args_sha256=steps_digest((NOTE,)),
        edited_args=edited,
        note=note,
        channel="terminal",
        decided_by="owner",
        decided_at=DECIDED,
    )


def test_a_pending_request() -> None:
    stored = StoredApproval(request=_request(), decision=None)
    assert "\n".join(request_lines(stored)) == (
        f"approval {FIRST}  step  pending\n"
        f"run {RUN}  requested 2026-11-09T09:00:00Z\n"
        '  1. demo.note  write  {"title": "Milk"}'
    )


def test_a_rejected_request_with_a_note() -> None:
    stored = StoredApproval(request=_request(), decision=_decision("reject", note="not today"))
    assert "\n".join(request_lines(stored)) == (
        f"approval {FIRST}  step  rejected by owner (terminal) at 2026-11-09T10:00:00Z\n"
        f"run {RUN}  requested 2026-11-09T09:00:00Z\n"
        '  1. demo.note  write  {"title": "Milk"}\n'
        "note: not today"
    )


def test_an_edited_request() -> None:
    stored = StoredApproval(
        request=_request(),
        decision=_decision("edit", note="fewer", edited={"title": "Eggs"}),
    )
    assert "\n".join(request_lines(stored)) == (
        f"approval {FIRST}  step  edited by owner (terminal) at 2026-11-09T10:00:00Z\n"
        f"run {RUN}  requested 2026-11-09T09:00:00Z\n"
        '  1. demo.note  write  {"title": "Milk"}\n'
        'edited args: {"title": "Eggs"}\n'
        "note: fewer"
    )


def test_an_approved_request_omits_an_empty_note() -> None:
    stored = StoredApproval(request=_request(), decision=_decision("approve"))
    assert "\n".join(request_lines(stored)) == (
        f"approval {FIRST}  step  approved by owner (terminal) at 2026-11-09T10:00:00Z\n"
        f"run {RUN}  requested 2026-11-09T09:00:00Z\n"
        '  1. demo.note  write  {"title": "Milk"}'
    )


def test_an_open_escalation_with_two_problems() -> None:
    stored = StoredEscalation(
        escalation_id=FIRST,
        raised_at=AT,
        escalation=Escalation(
            kind="invalid_plan",
            detail="decision 3: the plan does not fit the registry",
            run_id=RUN,
            problems=(
                FieldProblem(loc="steps.0.args.title", code="string_too_short"),
                FieldProblem(loc="steps.1.action", code="missing"),
            ),
        ),
        answer=None,
    )
    assert "\n".join(escalation_lines(stored)) == (
        f"escalation {FIRST}  invalid_plan  open\n"
        f"run {RUN}  raised 2026-11-09T09:00:00Z\n"
        "decision 3: the plan does not fit the registry\n"
        "  steps.0.args.title: string_too_short\n"
        "  steps.1.action: missing"
    )


def test_an_answered_escalation() -> None:
    stored = StoredEscalation(
        escalation_id=FIRST,
        raised_at=AT,
        escalation=Escalation(kind="tool_error", detail="the tool failed", run_id=RUN),
        answer=EscalationAnswer(
            escalation_id=FIRST,
            answer="cancel",
            note="later",
            channel="terminal",
            decided_by="owner",
            answered_at=DECIDED,
        ),
    )
    assert "\n".join(escalation_lines(stored)) == (
        f"escalation {FIRST}  tool_error  cancel by owner (terminal) at 2026-11-09T10:00:00Z\n"
        f"run {RUN}  raised 2026-11-09T09:00:00Z\n"
        "the tool failed\n"
        "note: later"
    )


def test_an_answer_without_a_note_omits_the_note_line() -> None:
    stored = StoredEscalation(
        escalation_id=FIRST,
        raised_at=AT,
        escalation=Escalation(
            kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN
        ),
        answer=EscalationAnswer(
            escalation_id=FIRST,
            answer="retry",
            channel="terminal",
            decided_by="owner",
            answered_at=DECIDED,
        ),
    )
    assert "\n".join(escalation_lines(stored)) == (
        f"escalation {FIRST}  model_unavailable  "
        "retry by owner (terminal) at 2026-11-09T10:00:00Z\n"
        f"run {RUN}  raised 2026-11-09T09:00:00Z\n"
        "model unavailable: timeout"
    )
