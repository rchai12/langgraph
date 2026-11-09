from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import NOTE_MESSAGE, answer_escalation, decide_approval
from conductor.domains import demo
from conductor.policy import DecisionRefused, Rejected
from conductor.registry import NotRegistered, Registry
from conductor.store import AlreadyDecided, NotFound, Store

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
REGISTRY = Registry((demo.DOMAIN,))
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
ID = "1" * 32
RUN = "a" * 32


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setattr(clock, "now", lambda: AT)
    store = Store(tmp_path / "conductor.db")
    store.add_request(
        ApprovalRequest(
            approval_id=ID,
            run_id=RUN,
            stage="step",
            steps=(NOTE,),
            args_sha256=steps_digest((NOTE,)),
            requested_at=datetime(2026, 11, 8, 9, 0, tzinfo=UTC),
        )
    )
    return store


def test_a_note_of_500_is_kept_and_a_longer_one_is_refused_first(db: Store) -> None:
    assert decide_approval(
        db, REGISTRY, ID, "reject", channel="terminal", decided_by="owner", note="n" * 500
    ) == Rejected(note="n" * 500)
    assert db.approval(ID).decision is not None
    assert db.approval(ID).decision.note == "n" * 500
    with pytest.raises(ValueError) as raised:
        decide_approval(
            db,
            REGISTRY,
            "9" * 32,
            "reject",
            channel="terminal",
            decided_by="owner",
            note="x" * 501,
        )
    assert str(raised.value) == NOTE_MESSAGE


def test_a_store_that_lost_the_race_passes_already_decided(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost(decision: object) -> None:
        raise AlreadyDecided(f"approval {ID} is already decided")

    monkeypatch.setattr(db, "record_decision", lost)
    with pytest.raises(AlreadyDecided) as raised:
        decide_approval(db, REGISTRY, ID, "approve", channel="terminal", decided_by="owner")
    assert str(raised.value) == f"approval {ID} is already decided"
    assert db.approval(ID).decision is None


def test_an_unregistered_action_records_nothing(db: Store) -> None:
    with pytest.raises(NotRegistered) as raised:
        decide_approval(db, Registry(()), ID, "approve", channel="terminal", decided_by="owner")
    assert str(raised.value) == "no action demo.note"
    assert db.pending() == [db.approval(ID).request]


def test_an_unknown_escalation_is_missing_and_an_answered_one_skips_the_clock(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(NotFound) as missing:
        answer_escalation(db, "9" * 32, "retry", channel="terminal", decided_by="owner")
    assert str(missing.value) == f"no escalation {'9' * 32}"
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    answer_escalation(db, raised.escalation_id, "retry", channel="web", decided_by="owner")

    def fail() -> datetime:
        raise AssertionError("clock was read")

    monkeypatch.setattr(clock, "now", fail)
    with pytest.raises(AlreadyDecided) as answered:
        answer_escalation(db, raised.escalation_id, "cancel", channel="web", decided_by="owner")
    assert str(answered.value) == f"escalation {raised.escalation_id} is already answered"


def test_a_refused_edit_leaves_the_pending_list(db: Store) -> None:
    before = db.pending()
    with pytest.raises(DecisionRefused):
        decide_approval(
            db,
            REGISTRY,
            ID,
            "edit",
            channel="terminal",
            decided_by="owner",
            edited_args={"title": ""},
        )
    assert db.pending() == before
