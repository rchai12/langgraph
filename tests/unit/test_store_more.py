import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.contracts import Escalation
from conductor.contracts.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    EscalationAnswer,
    PlannedStep,
    steps_digest,
)
from conductor.store import (
    LEASE_SECONDS,
    AlreadyDecided,
    LeaseLost,
    Store,
    StoreError,
)

START = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
RUN = "a" * 32
THREAD = "7" * 32
ME = "e" * 32
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
ESCALATION = Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def time(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", lambda: fake.now)
    numbers = iter(range(1, 100))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(numbers):032x}")
    return fake


def request(number: int) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=f"{number:032x}",
        run_id=RUN,
        stage="step",
        steps=(NOTE,),
        args_sha256=steps_digest((NOTE,)),
        requested_at=START,
    )


def decision(number: int, verdict: str = "approve") -> ApprovalDecision:
    return ApprovalDecision(
        approval_id=f"{number:032x}",
        verdict=verdict,
        args_sha256=steps_digest((NOTE,)),
        channel="terminal",
        decided_by="owner",
        decided_at=START,
    )


def answer(escalation_id: str, note: str = "") -> EscalationAnswer:
    return EscalationAnswer(
        escalation_id=escalation_id,
        answer="retry",
        note=note,
        channel="web",
        decided_by="owner",
        answered_at=START,
    )


def settled(path: Path) -> None:
    assert not (path.parent / f"{path.name}-journal").exists()
    with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as raw:
        raw.execute("BEGIN IMMEDIATE")
        raw.execute("ROLLBACK")


def test_a_missing_folder_is_private_and_an_empty_file_gets_the_schema(tmp_path: Path) -> None:
    missing = tmp_path / "fresh" / "conductor.db"
    Store(missing)
    assert stat.S_IMODE(missing.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(missing.stat().st_mode) == 0o600

    folder = tmp_path / "empty"
    folder.mkdir()
    path = folder / "conductor.db"
    descriptor = path.open("wb")
    descriptor.close()
    path.chmod(0o600)
    assert path.stat().st_size == 0
    Store(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with closing(sqlite3.connect(path)) as raw:
        assert raw.execute("PRAGMA user_version").fetchone() == (1,)
        tables = raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row[0] for row in tables}
    assert names == {"approvals", "escalations", "leases"}


def test_operations_leave_no_journal_or_open_transaction(tmp_path: Path, time: Clock) -> None:
    path = tmp_path / "data" / "conductor.db"
    db = Store(path)
    settled(path)
    db.add_request(request(1))
    settled(path)
    db.approval(f"{1:032x}")
    settled(path)
    db.pending()
    settled(path)
    db.record_decision(decision(1, "reject"))
    settled(path)
    raised = db.add_escalation(ESCALATION)
    settled(path)
    db.escalation(raised.escalation_id)
    settled(path)
    db.open_escalations()
    settled(path)
    db.answer(answer(raised.escalation_id))
    settled(path)
    db.acquire(THREAD, ME)
    settled(path)
    db.renew(THREAD, ME)
    settled(path)
    db.release(THREAD, ME)
    settled(path)


def test_a_refused_decision_leaves_the_first_one(tmp_path: Path, time: Clock) -> None:
    path = tmp_path / "conductor.db"
    db = Store(path)
    db.add_request(request(1))
    first = decision(1, "reject")
    db.record_decision(first)
    with pytest.raises(AlreadyDecided):
        db.record_decision(decision(1))
    assert db.approval(f"{1:032x}").decision == first
    settled(path)


def test_a_damaged_decision_or_escalation_is_refused(tmp_path: Path, time: Clock) -> None:
    path = tmp_path / "conductor.db"
    db = Store(path)
    db.add_request(request(1))
    db.record_decision(decision(1))
    with closing(sqlite3.connect(path, isolation_level=None)) as raw:
        [(text,)] = raw.execute("SELECT decision FROM approvals").fetchall()
        raw.execute("UPDATE approvals SET decision = ?", (text[:-2],))
    with pytest.raises(StoreError) as raised:
        db.approval(f"{1:032x}")
    assert str(raised.value) == f"conductor.db: approval {1:032x} is damaged"

    stored = db.add_escalation(ESCALATION)
    with closing(sqlite3.connect(path, isolation_level=None)) as raw:
        [(text,)] = raw.execute("SELECT escalation FROM escalations").fetchall()
        raw.execute("UPDATE escalations SET escalation = ?", (text[:-2],))
    with pytest.raises(StoreError) as raised:
        db.open_escalations()
    assert str(raised.value) == f"conductor.db: escalation {stored.escalation_id} is damaged"


def test_a_holder_id_must_be_hexadecimal(tmp_path: Path) -> None:
    db = Store(tmp_path / "conductor.db")
    for call in (db.acquire, db.renew, db.release):
        with pytest.raises(ValueError) as raised:
            call(THREAD, "x")
        assert str(raised.value) == "holder id must be 32 lowercase hexadecimal characters"


def test_an_expired_lease_can_be_renewed_and_a_missing_lease_is_lost(
    tmp_path: Path, time: Clock
) -> None:
    db = Store(tmp_path / "conductor.db")
    db.acquire(THREAD, ME)
    time.advance(LEASE_SECONDS)
    renewed = db.renew(THREAD, ME)
    assert renewed.holder == ME
    assert renewed.expires_at == START + timedelta(seconds=LEASE_SECONDS * 2)
    missing = "8" * 32
    for call in (db.renew, db.release):
        with pytest.raises(LeaseLost) as lost:
            call(missing, ME)
        assert str(lost.value) == f"thread {missing} is not leased by this holder"


def test_a_retry_note_is_kept(tmp_path: Path, time: Clock) -> None:
    db = Store(tmp_path / "conductor.db")
    raised = db.add_escalation(ESCALATION)
    reply = answer(raised.escalation_id, "Ollama is back")
    assert db.answer(reply).answer == reply
    stored = db.escalation(raised.escalation_id)
    assert stored.answer is not None
    assert stored.answer.note == "Ollama is back"
    assert stored.answer.answer == "retry"
    assert db.open_escalations() == []
