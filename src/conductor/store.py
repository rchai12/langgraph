import os
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from conductor import clock, ids
from conductor.contracts import Contract, Escalation
from conductor.contracts.approvals import ApprovalDecision, ApprovalRequest, EscalationAnswer

SCHEMA_VERSION = 1
LEASE_SECONDS = 600
BUSY_SECONDS = 5.0
ID_MESSAGE = "thread id must be 32 lowercase hexadecimal characters"

_SCHEMA = (
    """
    CREATE TABLE approvals (
        approval_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        request TEXT NOT NULL,
        decision TEXT
    )
    """,
    """
    CREATE TABLE escalations (
        escalation_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        raised_at TEXT NOT NULL,
        escalation TEXT NOT NULL,
        answer TEXT
    )
    """,
    """
    CREATE TABLE leases (
        thread_id TEXT PRIMARY KEY,
        holder TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
)
_ID = re.compile(r"^[0-9a-f]{32}$")
T = TypeVar("T")


class StoreError(Exception):
    pass


class NotFound(LookupError):
    pass


class AlreadyDecided(Exception):
    pass


class LeaseHeld(Exception):
    pass


class LeaseLost(Exception):
    pass


@dataclass(frozen=True)
class StoredApproval:
    request: ApprovalRequest
    decision: ApprovalDecision | None


@dataclass(frozen=True)
class StoredEscalation:
    escalation_id: str
    raised_at: datetime
    escalation: Escalation
    answer: EscalationAnswer | None


@dataclass(frozen=True)
class Lease:
    thread_id: str
    holder: str
    expires_at: datetime


class Store:
    def __init__(self, path: Path) -> None:
        self._path = path
        _prepare(path)
        self._run(self._ensure_schema)

    def add_request(self, request: ApprovalRequest) -> None:
        def work(connection: sqlite3.Connection) -> None:
            try:
                connection.execute(
                    "INSERT INTO approvals (approval_id, run_id, requested_at, request)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        request.approval_id,
                        request.run_id,
                        _stamp(request.requested_at),
                        request.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError:
                raise StoreError(
                    f"{self._path.name}: approval {request.approval_id} already exists"
                ) from None

        self._run(work)

    def approval(self, approval_id: str) -> StoredApproval:
        return self._run(lambda connection: self._approval(connection, approval_id))

    def pending(self) -> list[ApprovalRequest]:
        def work(connection: sqlite3.Connection) -> list[ApprovalRequest]:
            rows = connection.execute(
                "SELECT approval_id FROM approvals WHERE decision IS NULL"
                " ORDER BY requested_at, approval_id"
            ).fetchall()
            return [self._approval(connection, approval_id).request for (approval_id,) in rows]

        return self._run(work)

    def record_decision(self, decision: ApprovalDecision) -> StoredApproval:
        def work(connection: sqlite3.Connection) -> StoredApproval:
            stored = self._approval(connection, decision.approval_id)
            if stored.decision is not None:
                raise AlreadyDecided(f"approval {decision.approval_id} is already decided")
            connection.execute(
                "UPDATE approvals SET decision = ? WHERE approval_id = ?",
                (decision.model_dump_json(), decision.approval_id),
            )
            return self._approval(connection, decision.approval_id)

        return self._run(work)

    def add_escalation(self, escalation: Escalation) -> StoredEscalation:
        def work(connection: sqlite3.Connection) -> StoredEscalation:
            escalation_id = ids.new_id()
            connection.execute(
                "INSERT INTO escalations (escalation_id, run_id, raised_at, escalation)"
                " VALUES (?, ?, ?, ?)",
                (
                    escalation_id,
                    escalation.run_id,
                    _stamp(clock.now()),
                    escalation.model_dump_json(),
                ),
            )
            return self._escalation(connection, escalation_id)

        return self._run(work)

    def escalation(self, escalation_id: str) -> StoredEscalation:
        return self._run(lambda connection: self._escalation(connection, escalation_id))

    def open_escalations(self) -> list[StoredEscalation]:
        def work(connection: sqlite3.Connection) -> list[StoredEscalation]:
            rows = connection.execute(
                "SELECT escalation_id FROM escalations WHERE answer IS NULL"
                " ORDER BY raised_at, escalation_id"
            ).fetchall()
            return [self._escalation(connection, escalation_id) for (escalation_id,) in rows]

        return self._run(work)

    def answer(self, answer: EscalationAnswer) -> StoredEscalation:
        def work(connection: sqlite3.Connection) -> StoredEscalation:
            stored = self._escalation(connection, answer.escalation_id)
            if stored.answer is not None:
                raise AlreadyDecided(f"escalation {answer.escalation_id} is already answered")
            connection.execute(
                "UPDATE escalations SET answer = ? WHERE escalation_id = ?",
                (answer.model_dump_json(), answer.escalation_id),
            )
            return self._escalation(connection, answer.escalation_id)

        return self._run(work)

    def acquire(self, thread_id: str, holder: str) -> Lease:
        _require_ids(thread_id, holder)

        def work(connection: sqlite3.Connection) -> Lease:
            row = connection.execute(
                "SELECT holder, expires_at FROM leases WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            now = clock.now()
            expires_at = now + timedelta(seconds=LEASE_SECONDS)
            if row is None or row[0] == holder or _instant(row[1]) <= now:
                if row is None:
                    connection.execute(
                        "INSERT INTO leases (thread_id, holder, expires_at) VALUES (?, ?, ?)",
                        (thread_id, holder, _stamp(expires_at)),
                    )
                else:
                    connection.execute(
                        "UPDATE leases SET holder = ?, expires_at = ? WHERE thread_id = ?",
                        (holder, _stamp(expires_at), thread_id),
                    )
                return Lease(thread_id=thread_id, holder=holder, expires_at=expires_at)
            raise LeaseHeld(f"thread {thread_id} is leased")

        return self._run(work)

    def renew(self, thread_id: str, holder: str) -> Lease:
        _require_ids(thread_id, holder)

        def work(connection: sqlite3.Connection) -> Lease:
            row = connection.execute(
                "SELECT holder FROM leases WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if row is None or row[0] != holder:
                raise LeaseLost(f"thread {thread_id} is not leased by this holder")
            expires_at = clock.now() + timedelta(seconds=LEASE_SECONDS)
            connection.execute(
                "UPDATE leases SET expires_at = ? WHERE thread_id = ?",
                (_stamp(expires_at), thread_id),
            )
            return Lease(thread_id=thread_id, holder=holder, expires_at=expires_at)

        return self._run(work)

    def release(self, thread_id: str, holder: str) -> None:
        _require_ids(thread_id, holder)

        def work(connection: sqlite3.Connection) -> None:
            row = connection.execute(
                "SELECT holder FROM leases WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if row is None or row[0] != holder:
                raise LeaseLost(f"thread {thread_id} is not leased by this holder")
            connection.execute("DELETE FROM leases WHERE thread_id = ?", (thread_id,))

        self._run(work)

    def _run(self, work: Callable[[sqlite3.Connection], T]) -> T:
        connection = sqlite3.connect(self._path, isolation_level=None, timeout=BUSY_SECONDS)
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = work(connection)
                connection.execute("COMMIT")
                return result
            except Exception:
                connection.execute("ROLLBACK")
                raise
        except sqlite3.OperationalError:
            raise StoreError(f"{self._path.name}: busy") from None
        except sqlite3.DatabaseError:
            raise StoreError(f"{self._path.name}: not a database") from None
        finally:
            connection.close()

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT GLOB 'sqlite_*'"
        ).fetchall()
        if version == SCHEMA_VERSION:
            return
        if version == 0 and not rows:
            for statement in _SCHEMA:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 1")
            return
        raise StoreError(f"{self._path.name}: schema version {version} is not supported")

    def _approval(self, connection: sqlite3.Connection, approval_id: str) -> StoredApproval:
        row = connection.execute(
            "SELECT request, decision FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"no approval {approval_id}")
        request = self._parse("approval", approval_id, row[0], ApprovalRequest, "approval_id")
        decision = None
        if row[1] is not None:
            decision = self._parse("approval", approval_id, row[1], ApprovalDecision, "approval_id")
        return StoredApproval(request=request, decision=decision)

    def _escalation(self, connection: sqlite3.Connection, escalation_id: str) -> StoredEscalation:
        row = connection.execute(
            "SELECT raised_at, escalation, answer FROM escalations WHERE escalation_id = ?",
            (escalation_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"no escalation {escalation_id}")
        escalation = self._parse("escalation", escalation_id, row[1], Escalation, None)
        answer = None
        if row[2] is not None:
            answer = self._parse(
                "escalation", escalation_id, row[2], EscalationAnswer, "escalation_id"
            )
        return StoredEscalation(
            escalation_id=escalation_id,
            raised_at=_instant(row[0]),
            escalation=escalation,
            answer=answer,
        )

    def _parse(
        self,
        kind: str,
        row_id: str,
        text: str,
        model: type[Contract],
        field: str | None,
    ) -> Contract:
        try:
            parsed = model.from_json(text)
        except ValidationError:
            raise StoreError(f"{self._path.name}: {kind} {row_id} is damaged") from None
        if field is not None and getattr(parsed, field) != row_id:
            raise StoreError(f"{self._path.name}: {kind} {row_id} is damaged")
        return parsed


def _prepare(path: Path) -> None:
    folder = path.parent
    if not folder.exists():
        folder.mkdir(parents=True, mode=0o700)
        folder.chmod(0o700)
    if not path.exists():
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)


def _require_ids(thread_id: str, holder: str) -> None:
    if _ID.fullmatch(thread_id) is None:
        raise ValueError(ID_MESSAGE)
    if _ID.fullmatch(holder) is None:
        raise ValueError(ID_MESSAGE.replace("thread", "holder"))


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value)
