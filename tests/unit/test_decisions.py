from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.config import SettingsError, get_settings
from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import NOTE_MESSAGE, answer_escalation, decide_approval
from conductor.domains import demo
from conductor.policy import Approved, DecisionRefused, Rejected
from conductor.registry import NotRegistered, Registry
from conductor.store import AlreadyDecided, NotFound, Store

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
REGISTRY = Registry((demo.DOMAIN,))
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
ID = "1" * 32


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setattr(clock, "now", lambda: AT)
    store = Store(tmp_path / "conductor.db")
    store.add_request(
        ApprovalRequest(
            approval_id=ID,
            run_id="a" * 32,
            stage="step",
            steps=(NOTE,),
            args_sha256=steps_digest((NOTE,)),
            requested_at=datetime(2026, 11, 8, 9, 0, tzinfo=UTC),
        )
    )
    return store


def decide(db: Store, verdict: str, **options: object):
    return decide_approval(
        db, REGISTRY, ID, verdict, channel="terminal", decided_by="owner", **options
    )


def test_an_approval_is_checked_then_recorded(db: Store) -> None:
    assert decide(db, "approve") == Approved(args=demo.NoteArgs(title="Milk"), edited=False)
    decision = db.approval(ID).decision
    assert decision is not None
    assert (decision.verdict, decision.channel, decision.decided_by, decision.decided_at) == (
        "approve",
        "terminal",
        "owner",
        AT,
    )
    assert decision.args_sha256 == steps_digest((NOTE,))
    assert db.pending() == []


def test_an_edit_and_a_rejection(db: Store, tmp_path: Path) -> None:
    outcome = decide(db, "edit", edited_args={"title": "Eggs"}, note="fewer")
    assert outcome == Approved(args=demo.NoteArgs(title="Eggs"), edited=True)
    stored = db.approval(ID).decision
    assert stored is not None and (stored.edited_args, stored.note) == ({"title": "Eggs"}, "fewer")
    other = Store(tmp_path / "other.db")
    other.add_request(db.approval(ID).request)
    assert decide(other, "reject", note="not now") == Rejected(note="not now")


def test_a_refused_edit_records_nothing(db: Store) -> None:
    with pytest.raises(DecisionRefused) as raised:
        decide(db, "edit", edited_args={"title": ""})
    assert raised.value.problems == (FieldProblem(loc="title", code="string_too_short"),)
    assert db.approval(ID).decision is None


def test_a_decided_request_is_refused_before_the_policy(db: Store) -> None:
    decide(db, "reject")
    with pytest.raises(AlreadyDecided) as raised:
        decide(db, "edit", edited_args={"title": ""})
    assert str(raised.value) == f"approval {ID} is already decided"


def test_an_unknown_request(db: Store) -> None:
    with pytest.raises(NotFound):
        decide_approval(db, REGISTRY, "9" * 32, "approve", channel="web", decided_by="owner")


def test_a_note_that_is_too_long(db: Store) -> None:
    with pytest.raises(ValueError) as raised:
        decide(db, "reject", note="x" * 501)
    assert str(raised.value) == NOTE_MESSAGE == "note must be at most 500 characters"
    assert db.approval(ID).decision is None


def test_an_escalation_is_answered_once(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id="a" * 32)
    )
    stored = answer_escalation(
        db, raised.escalation_id, "retry", note="back up", channel="web", decided_by="owner"
    )
    assert stored.answer is not None
    assert (stored.answer.answer, stored.answer.note, stored.answer.answered_at) == (
        "retry",
        "back up",
        AT,
    )
    with pytest.raises(AlreadyDecided):
        answer_escalation(db, raised.escalation_id, "cancel", channel="web", decided_by="owner")
    with pytest.raises(ValueError):
        answer_escalation(
            db, raised.escalation_id, "cancel", note="y" * 501, channel="web", decided_by="owner"
        )


def test_who_decides_is_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().decided_by == "owner"
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", "house_admin")
    assert get_settings().decided_by == "house_admin"


@pytest.mark.parametrize("label", ["", "Owner", "the owner", "x" * 33])
def test_a_bad_label_is_refused(monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", label)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == (
        "CONDUCTOR_DECIDED_BY: must be a lowercase name of up to 32 characters"
    )


RUN = "a" * 32


@pytest.fixture
def db_moved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
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


def test_a_note_of_500_is_kept_and_a_longer_one_is_refused_first(db_moved: Store) -> None:
    assert decide_approval(
        db_moved, REGISTRY, ID, "reject", channel="terminal", decided_by="owner", note="n" * 500
    ) == Rejected(note="n" * 500)
    assert db_moved.approval(ID).decision is not None
    assert db_moved.approval(ID).decision.note == "n" * 500
    with pytest.raises(ValueError) as raised:
        decide_approval(
            db_moved,
            REGISTRY,
            "9" * 32,
            "reject",
            channel="terminal",
            decided_by="owner",
            note="x" * 501,
        )
    assert str(raised.value) == NOTE_MESSAGE


def test_a_store_that_lost_the_race_passes_already_decided(
    db_moved: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost(decision: object) -> None:
        raise AlreadyDecided(f"approval {ID} is already decided")

    monkeypatch.setattr(db_moved, "record_decision", lost)
    with pytest.raises(AlreadyDecided) as raised:
        decide_approval(db_moved, REGISTRY, ID, "approve", channel="terminal", decided_by="owner")
    assert str(raised.value) == f"approval {ID} is already decided"
    assert db_moved.approval(ID).decision is None


def test_an_unregistered_action_records_nothing(db_moved: Store) -> None:
    with pytest.raises(NotRegistered) as raised:
        decide_approval(
            db_moved, Registry(()), ID, "approve", channel="terminal", decided_by="owner"
        )
    assert str(raised.value) == "no action demo.note"
    assert db_moved.pending() == [db_moved.approval(ID).request]


def test_an_unknown_escalation_is_missing_and_an_answered_one_skips_the_clock(
    db_moved: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(NotFound) as missing:
        answer_escalation(db_moved, "9" * 32, "retry", channel="terminal", decided_by="owner")
    assert str(missing.value) == f"no escalation {'9' * 32}"
    raised = db_moved.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    answer_escalation(db_moved, raised.escalation_id, "retry", channel="web", decided_by="owner")

    def fail() -> datetime:
        raise AssertionError("clock was read")

    monkeypatch.setattr(clock, "now", fail)
    with pytest.raises(AlreadyDecided) as answered:
        answer_escalation(
            db_moved, raised.escalation_id, "cancel", channel="web", decided_by="owner"
        )
    assert str(answered.value) == f"escalation {raised.escalation_id} is already answered"


def test_a_refused_edit_leaves_the_pending_list(db_moved: Store) -> None:
    before = db_moved.pending()
    with pytest.raises(DecisionRefused):
        decide_approval(
            db_moved,
            REGISTRY,
            ID,
            "edit",
            channel="terminal",
            decided_by="owner",
            edited_args={"title": ""},
        )
    assert db_moved.pending() == before
