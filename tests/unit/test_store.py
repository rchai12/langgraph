import json
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_args

import pytest

from conductor import clock, ids, store
from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import (
    Answer,
    ApprovalDecision,
    ApprovalRequest,
    EscalationAnswer,
    PlannedStep,
    steps_digest,
)
from conductor.store import (
    LEASE_SECONDS,
    SCHEMA_VERSION,
    AlreadyDecided,
    Lease,
    LeaseHeld,
    LeaseLost,
    NotFound,
    Store,
    StoredApproval,
    StoredEscalation,
    StoreError,
)

START = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
RUN = "a" * 32
THREAD = "7" * 32
ME, OTHER = "e" * 32, "f" * 32
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})


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


@pytest.fixture
def db(tmp_path: Path, time: Clock) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


def request(number: int, minutes: int = 0) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=f"{number:032x}",
        run_id=RUN,
        stage="step",
        steps=(NOTE,),
        args_sha256=steps_digest((NOTE,)),
        requested_at=START + timedelta(minutes=minutes),
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


ESCALATION = Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)


def answer(escalation_id: str, verdict: str = "retry") -> EscalationAnswer:
    return EscalationAnswer(
        escalation_id=escalation_id,
        answer=verdict,
        channel="web",
        decided_by="owner",
        answered_at=START,
    )


def test_a_new_store_is_private_and_versioned(tmp_path: Path, db: Store) -> None:
    path = tmp_path / "data" / "conductor.db"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with closing(sqlite3.connect(path)) as raw:
        assert raw.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        names = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {"approvals", "escalations", "leases"}
    assert (SCHEMA_VERSION, LEASE_SECONDS) == (1, 600)
    assert get_settings().db_path == get_settings().data_dir / "conductor.db"


def test_a_store_keeps_its_rows_across_openings(tmp_path: Path, db: Store) -> None:
    db.add_request(request(1))
    again = Store(tmp_path / "data" / "conductor.db")
    assert again.approval(f"{1:032x}") == StoredApproval(request=request(1), decision=None)


def write_foreign(path: Path, version: int, table: bool) -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as raw:
        if table:
            raw.execute("CREATE TABLE notes(id TEXT)")
        raw.execute(f"PRAGMA user_version = {version}")


@pytest.mark.parametrize(
    ("version", "table", "message"),
    [
        (2, False, "conductor.db: schema version 2 is not supported"),
        (0, True, "conductor.db: schema version 0 is not supported"),
    ],
)
def test_a_store_with_another_schema_is_refused(
    tmp_path: Path, time: Clock, version: int, table: bool, message: str
) -> None:
    path = tmp_path / "conductor.db"
    write_foreign(path, version, table)
    with pytest.raises(StoreError) as raised:
        Store(path)
    assert str(raised.value) == message


def test_a_file_that_is_not_a_database(tmp_path: Path, time: Clock) -> None:
    path = tmp_path / "conductor.db"
    path.write_bytes(b"synthetic text, not a database " * 8)
    with pytest.raises(StoreError) as raised:
        Store(path)
    assert str(raised.value) == "conductor.db: not a database"


def test_pending_requests_in_the_order_they_were_asked(db: Store) -> None:
    for number, minutes in [(3, 5), (2, 0), (1, 5)]:
        db.add_request(request(number, minutes))
    assert [r.approval_id for r in db.pending()] == [f"{n:032x}" for n in (2, 1, 3)]


def test_a_request_is_added_once(db: Store) -> None:
    db.add_request(request(1))
    with pytest.raises(StoreError) as raised:
        db.add_request(request(1))
    assert str(raised.value) == f"conductor.db: approval {1:032x} already exists"


def test_the_first_decision_wins(db: Store) -> None:
    db.add_request(request(1))
    stored = db.record_decision(decision(1, "reject"))
    assert stored == StoredApproval(request=request(1), decision=decision(1, "reject"))
    assert db.pending() == []
    with pytest.raises(AlreadyDecided) as raised:
        db.record_decision(decision(1))
    assert str(raised.value) == f"approval {1:032x} is already decided"
    assert db.approval(f"{1:032x}").decision == decision(1, "reject")


@pytest.mark.parametrize(
    "call",
    [lambda db: db.approval(f"{9:032x}"), lambda db: db.record_decision(decision(9))],
)
def test_an_unknown_approval(db: Store, call) -> None:
    with pytest.raises(NotFound) as raised:
        call(db)
    assert str(raised.value) == f"no approval {9:032x}"
    assert isinstance(raised.value, LookupError)


def tamper(path: Path, column: str, change) -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as raw:
        [(text,)] = raw.execute(f"SELECT {column} FROM approvals").fetchall()
        raw.execute(f"UPDATE approvals SET {column} = ?", (change(text),))


@pytest.mark.parametrize(
    "change",
    [
        lambda text: text.replace("Milk", "Eggs"),
        lambda text: text[:-2],
        lambda text: json.dumps({**json.loads(text), "approval_id": "b" * 32}),
    ],
)
def test_a_damaged_row_is_refused(tmp_path: Path, db: Store, change) -> None:
    db.add_request(request(1))
    tamper(tmp_path / "data" / "conductor.db", "request", change)
    for call in (lambda: db.approval(f"{1:032x}"), db.pending):
        with pytest.raises(StoreError) as raised:
            call()
        assert str(raised.value) == f"conductor.db: approval {1:032x} is damaged"


def test_an_escalation_is_raised_and_answered(db: Store, time: Clock) -> None:
    raised = db.add_escalation(ESCALATION)
    assert raised == StoredEscalation(
        escalation_id=f"{1:032x}", raised_at=START, escalation=ESCALATION, answer=None
    )
    time.advance(60)
    second = db.add_escalation(ESCALATION)
    assert [e.escalation_id for e in db.open_escalations()] == [f"{1:032x}", f"{2:032x}"]
    answered = db.answer(answer(raised.escalation_id, "cancel"))
    assert answered.answer == answer(raised.escalation_id, "cancel")
    assert db.open_escalations() == [second]
    assert db.escalation(raised.escalation_id) == answered


def test_an_escalation_is_answered_once(db: Store) -> None:
    raised = db.add_escalation(ESCALATION)
    db.answer(answer(raised.escalation_id))
    with pytest.raises(AlreadyDecided) as already:
        db.answer(answer(raised.escalation_id, "cancel"))
    assert str(already.value) == f"escalation {raised.escalation_id} is already answered"
    with pytest.raises(NotFound) as missing:
        db.answer(answer("9" * 32))
    assert str(missing.value) == f"no escalation {'9' * 32}"


def test_the_answers() -> None:
    assert get_args(Answer) == ("retry", "cancel")
    built = answer("1" * 32).model_copy(update={"note": "Ollama is back"})
    assert EscalationAnswer.from_json(built.model_dump_json()) == built


def test_a_lease_is_held_until_it_expires(db: Store, time: Clock) -> None:
    lease = db.acquire(THREAD, ME)
    assert lease == Lease(thread_id=THREAD, holder=ME, expires_at=START + timedelta(seconds=600))
    with pytest.raises(LeaseHeld) as held:
        db.acquire(THREAD, OTHER)
    assert str(held.value) == f"thread {THREAD} is leased"
    time.advance(599)
    with pytest.raises(LeaseHeld):
        db.acquire(THREAD, OTHER)
    time.advance(1)
    assert db.acquire(THREAD, OTHER).holder == OTHER


def test_a_lease_is_renewed_and_released_by_its_holder(db: Store, time: Clock) -> None:
    db.acquire(THREAD, ME)
    time.advance(300)
    assert db.renew(THREAD, ME).expires_at == START + timedelta(seconds=900)
    assert db.acquire(THREAD, ME).expires_at == START + timedelta(seconds=900)
    for call in (db.renew, db.release):
        with pytest.raises(LeaseLost) as lost:
            call(THREAD, OTHER)
        assert str(lost.value) == f"thread {THREAD} is not leased by this holder"
    db.release(THREAD, ME)
    assert db.acquire(THREAD, OTHER).holder == OTHER


@pytest.mark.parametrize("call", ["acquire", "renew", "release"])
def test_lease_ids_are_checked(db: Store, call: str) -> None:
    with pytest.raises(ValueError) as raised:
        getattr(db, call)("thread-1", ME)
    assert str(raised.value) == "thread id must be 32 lowercase hexadecimal characters"


def test_a_busy_store(tmp_path: Path, db: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "BUSY_SECONDS", 0.1)
    raw = sqlite3.connect(tmp_path / "data" / "conductor.db", isolation_level=None)
    raw.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(StoreError) as raised:
            db.add_request(request(1))
    finally:
        raw.execute("ROLLBACK")
        raw.close()
    assert str(raised.value) == "conductor.db: busy"
    db.add_request(request(1))
