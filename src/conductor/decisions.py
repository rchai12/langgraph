from typing import Any

from conductor import clock
from conductor.contracts.approvals import (
    Answer,
    ApprovalDecision,
    Channel,
    EscalationAnswer,
    Verdict,
)
from conductor.policy import Approved, Rejected, apply_decision
from conductor.registry import Registry
from conductor.store import AlreadyDecided, Store, StoredEscalation

NOTE_MESSAGE = "note must be at most 500 characters"


def decide_approval(
    store: Store,
    registry: Registry,
    approval_id: str,
    verdict: Verdict,
    *,
    channel: Channel,
    decided_by: str,
    note: str = "",
    edited_args: dict[str, Any] | None = None,
) -> Approved | Rejected:
    _check_note(note)
    stored = store.approval(approval_id)
    if stored.decision is not None:
        raise AlreadyDecided(f"approval {approval_id} is already decided")
    decision = ApprovalDecision(
        approval_id=approval_id,
        verdict=verdict,
        args_sha256=stored.request.args_sha256,
        edited_args=edited_args,
        note=note,
        channel=channel,
        decided_by=decided_by,
        decided_at=clock.now(),
    )
    outcome = apply_decision(stored.request, decision, registry)
    store.record_decision(decision)
    return outcome


def answer_escalation(
    store: Store,
    escalation_id: str,
    answer: Answer,
    *,
    channel: Channel,
    decided_by: str,
    note: str = "",
) -> StoredEscalation:
    _check_note(note)
    stored = store.escalation(escalation_id)
    if stored.answer is not None:
        raise AlreadyDecided(f"escalation {escalation_id} is already answered")
    reply = EscalationAnswer(
        escalation_id=escalation_id,
        answer=answer,
        note=note,
        channel=channel,
        decided_by=decided_by,
        answered_at=clock.now(),
    )
    return store.answer(reply)


def _check_note(note: str) -> None:
    if len(note) > 500:
        raise ValueError(NOTE_MESSAGE)
