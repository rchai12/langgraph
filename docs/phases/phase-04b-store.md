# Phase 4b: the store

## Goal

Where approvals, escalations, and thread leases live between processes, so the terminal and the approvals page can see and decide the same requests:

- `conductor.store` (critical): a `Store` over `conductor.db` (SQLite through the standard library's `sqlite3`), created private (`0600`) and versioned (`PRAGMA user_version = 1`), with three tables:
  - **approvals**: add a request, read one, list the pending ones, record the first decision (a second is refused);
  - **escalations**: add one (the store gives it an id and a time), read one, list the open ones, record the first answer;
  - **leases**: acquire, renew, and release a thread's lease, which expires 600 seconds after it was last taken or renewed;
- `EscalationAnswer` in `conductor.contracts.approvals`: `retry` or `cancel`, with a note, the channel, who answered, and when;
- `Settings.db_path`: `<data_dir>/conductor.db`.

Every row holds a contract's JSON and is parsed strictly when read, so a row changed behind the store's back is refused with its id, as the event log refuses a damaged line.

Decided with the owner (2026-11-08): leases **expire** (a crashed process never blocks a thread for long); an escalation is answered with **retry or cancel** only; LangGraph's checkpoints (Phase 5) go in a **separate `checkpoints.db`**, so `conductor.db` holds only these tables under its own schema version.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("State, threads, and storage", "Approvals and escalations")
- `src/conductor/contracts/approvals.py` and `src/conductor/policy.py` (4a), `src/conductor/contracts/escalations.py` (`Escalation`), `src/conductor/events.py` (how it creates its folder and files privately), `src/conductor/config.py`

## Starting state

Phase 4a is built and committed: N is `349`. **Sections: core.** No `store.py` exists. No new dependency (`sqlite3` is in the standard library).

## Scope

| Path | What |
|---|---|
| `src/conductor/store.py` | everything under Design (critical) |
| `src/conductor/contracts/approvals.py` | add `Answer` and `EscalationAnswer` at the end |
| `src/conductor/config.py` | add the property `db_path` after `runs_dir` |
| `scripts/critical_modules.txt` | add the line `store.py` after `policy.py` |
| `docs/testing.md` | under "Critical modules", add `` - `store.py` (approvals, escalations, and leases kept between processes; Phase 4b) `` after the `policy.py` line |
| `tests/unit/test_store.py` | given |
| `tests/unit/test_store_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Deciding whether a decision is valid: the caller runs `policy.apply_decision` first and records only a decision it accepted (an invalid edit is never recorded, so the request stays pending).
- Commands (4c), the approvals page (Phase 7), the graph and `interrupt` (Phase 5), events about any of this.
- `checkpoints.db` or anything of LangGraph; WAL mode; migrations from another schema version; deleting or archiving rows; expiry of approvals.
- A clarify answer to an escalation; renewing leases on a timer.

## Dependencies

None new.

## Design

```python
# conductor/contracts/approvals.py: added at the end
Answer = Literal["retry", "cancel"]

class EscalationAnswer(Contract):
    escalation_id: Id
    answer: Answer
    note: str = Field(default="", max_length=500)
    channel: Channel
    decided_by: Name
    answered_at: UtcTime
```

```python
# conductor/store.py
SCHEMA_VERSION = 1
LEASE_SECONDS = 600
BUSY_SECONDS = 5.0            # sqlite3's timeout; read at each connection, so tests can lower it
ID_MESSAGE = "thread id must be 32 lowercase hexadecimal characters"   # and "holder id must ..."

class StoreError(Exception): ...          # "<file name>: <problem>"
class NotFound(LookupError): ...          # "no approval <id>", "no escalation <id>"
class AlreadyDecided(Exception): ...      # "approval <id> is already decided", "escalation <id> is already answered"
class LeaseHeld(Exception): ...           # "thread <id> is leased"
class LeaseLost(Exception): ...           # "thread <id> is not leased by this holder"

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
    def __init__(self, path: Path) -> None: ...
    def add_request(self, request: ApprovalRequest) -> None: ...
    def approval(self, approval_id: str) -> StoredApproval: ...
    def pending(self) -> list[ApprovalRequest]: ...
    def record_decision(self, decision: ApprovalDecision) -> StoredApproval: ...
    def add_escalation(self, escalation: Escalation) -> StoredEscalation: ...
    def escalation(self, escalation_id: str) -> StoredEscalation: ...
    def open_escalations(self) -> list[StoredEscalation]: ...
    def answer(self, answer: EscalationAnswer) -> StoredEscalation: ...
    def acquire(self, thread_id: str, holder: str) -> Lease: ...
    def renew(self, thread_id: str, holder: str) -> Lease: ...
    def release(self, thread_id: str, holder: str) -> None: ...
```

The schema (created in one transaction with `PRAGMA user_version = 1`; times are text `YYYY-MM-DDTHH:MM:SS.ffffffZ`, so text order is time order):

```sql
CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    request TEXT NOT NULL,          -- ApprovalRequest JSON
    decision TEXT                   -- ApprovalDecision JSON, NULL while pending
);
CREATE TABLE escalations (
    escalation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    raised_at TEXT NOT NULL,
    escalation TEXT NOT NULL,       -- Escalation JSON
    answer TEXT                     -- EscalationAnswer JSON, NULL while open
);
CREATE TABLE leases (
    thread_id TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
```

### Facts (from a spike: Python 3.12, SQLite 3.54.1)

- `sqlite3.connect(path)` on a missing file creates it with the process's umask (`0644` here): create it first with `os.open(path, O_WRONLY | O_CREAT | O_EXCL, 0o600)`. The journal (`conductor.db-journal`, default `DELETE` mode) is created with the database's own permissions and removed after each transaction.
- With `isolation_level=None`, `BEGIN IMMEDIATE` takes the write lock at once; a second connection's `BEGIN IMMEDIATE` waits `timeout` seconds, then raises `sqlite3.OperationalError("database is locked")`.
- A file that is not a database opens, then fails on its first statement with `sqlite3.DatabaseError("file is not a database")`. A new file reads `PRAGMA user_version` as `0`.
- A connection used as a context manager (`with sqlite3.connect(...)`) commits but does **not** close; close every connection (`contextlib.closing`), one per operation.
- A duplicate primary key raises `sqlite3.IntegrityError`.

## Requirements

### Part 1: opening

- **R1.** `Store(path)` creates the parent folder with mode `0700` when it is missing (as `EventLog` does) and the file with mode `0600` (see Facts) when it is missing. On an empty schema (`user_version` 0 and no table) it creates the three tables and sets `user_version` to `SCHEMA_VERSION` in one `BEGIN IMMEDIATE` transaction.
- **R2.** It refuses, with `StoreError(f"{path.name}: <problem>")`: `not a database` for a `sqlite3.DatabaseError` while opening; `schema version <n> is not supported` for any `user_version` other than 1, or 0 with tables already present.
- **R3.** Every operation opens its own connection with `isolation_level=None` and `timeout=BUSY_SECONDS` (read from the module at that moment), does its reads and writes inside one `BEGIN IMMEDIATE` … `COMMIT` (rolled back on any error), and closes it. A locked database gives `StoreError(f"{path.name}: busy")`.

### Part 2: approvals and escalations

- **R4.** `add_request` inserts the request; an existing `approval_id` gives `StoreError(f"{path.name}: approval {id} already exists")`. `pending()` returns the requests without a decision, ordered by `requested_at`, then `approval_id`.
- **R5.** `record_decision(decision)` gives `NotFound(f"no approval {id}")` when there is no such request, `AlreadyDecided(f"approval {id} is already decided")` when it has a decision, and otherwise stores it and returns the `StoredApproval`. The check and the write are in the same transaction, so of two decisions at once exactly one is recorded. `approval(id)` returns the stored request and decision, or `NotFound`.
- **R6.** `add_escalation(escalation)` stores it with `escalation_id = ids.new_id()` and `raised_at = clock.now()` (through the modules) and returns the `StoredEscalation`. `open_escalations()` lists the unanswered ones by `raised_at`, then id. `answer(answer)` gives `NotFound(f"no escalation {id}")`, `AlreadyDecided(f"escalation {id} is already answered")`, or stores it and returns the `StoredEscalation`; `escalation(id)` reads one or gives `NotFound`.
- **R7.** Each row is parsed when read with the contract's strict `from_json`. A row that does not parse, or whose JSON's id differs from its id column, gives `StoreError(f"{path.name}: approval {id} is damaged")` (or `escalation {id} is damaged`), from any method that reads it, `pending()` and `open_escalations()` included. No Pydantic or SQLite text reaches a message.

### Part 3: leases

- **R8.** `thread_id` and `holder` must fully match `^[0-9a-f]{32}$`, or `ValueError(ID_MESSAGE)` (with `holder` in place of `thread` for the holder), checked before any connection.
- **R9.** `acquire` succeeds when the thread has no lease, its lease has expired (`expires_at <= clock.now()`), or `holder` already holds it; it then sets `expires_at = clock.now() + LEASE_SECONDS` and returns the `Lease`. Otherwise `LeaseHeld`. `renew` does the same only for the holder of the row (expired or not), else `LeaseLost`; `release` deletes the row only for its holder, else `LeaseLost`. Each is one transaction, so of two acquires at once exactly one succeeds.

### Part 4: the rest

- **R10.** `EscalationAnswer` and `Answer` are exactly as under Design. `Settings.db_path` is `data_dir / "conductor.db"`.
- **R11.** `store.py` imports only the standard library, `pydantic` (for `ValidationError`), `conductor.contracts` and `conductor.contracts.approvals`, and `clock` and `ids` as modules (`from conductor import clock, ids`). SQL is written with `?` parameters only, never with values formatted into the text.

## Given tests

22 tests in `tests/unit/test_store.py` (counting each parameter set). Do not change them; if one fails, the code is wrong.

```python
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
```

## Tests to write

In `tests/unit/test_store_more.py`, each with its deciding input:

- R1: a missing folder is created `0700`; an existing empty `conductor.db` (0 bytes, made by the test with mode `0600`) gets the schema.
- R3: after every public method, no `conductor.db-journal` is left and `sqlite3` reports no open transaction (open the file again and `BEGIN IMMEDIATE` at once with `timeout=0`).
- R3: an error inside a transaction rolls it back: a `record_decision` refused as `AlreadyDecided` leaves the first decision as it was.
- R7: a damaged decision column (not the request) gives the damaged message; a damaged escalation row gives `escalation <id> is damaged` from `open_escalations()`.
- R8: a holder id of `"x"` gives `holder id must be 32 lowercase hexadecimal characters`.
- R9: `renew` of an expired lease by its holder succeeds when nobody took it; `renew` and `release` of a thread with no lease give `LeaseLost`.
- R6: answering a `retry` with a note keeps the note through `escalation(id)`.

`store.py` reaches 100% of lines and branches (critical).

## Rules for this phase

- **Critical module**: `store.py` joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **First decision wins**, inside one transaction; the store never decides what a decision means (that is `policy.apply_decision`).
- **Private files**: `conductor.db` is `0600` in a `0700` folder; tests make their databases under `tmp_path` only.
- **Constant messages**: file name, ids, and fixed text; never a row's contents, SQL, or a library's error text.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 22 = 371 passed; `critical coverage` passed (it now includes `store.py`); no warnings summary (an unclosed connection shows as a `ResourceWarning`);
- the given file: `.venv/bin/python -m pytest tests/unit/test_store.py --no-cov`, exactly `22 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/store.py,*/conductor/contracts/approvals.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/store.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|contextlib|dataclasses|datetime|os|pathlib|re|sqlite3|typing|pydantic|conductor\.contracts|conductor\.contracts\.approvals|conductor import clock, ids)( |$)"`
  - `git grep --untracked -n -E "execute\(f|execute\([^)]*%|execute\([^)]*\.format\(" -- src/conductor/store.py`
  - `git grep --untracked -n -E "journal_mode|WAL" -- src/conductor/store.py`
- `git diff --stat HEAD -- tests src/conductor/policy.py src/conductor/contracts/escalations.py src/conductor/contracts/__init__.py` prints nothing; `git diff HEAD -- src/conductor/contracts/approvals.py` only adds lines at the end.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 4b: the store (YYYY-MM-DD)`, with `Tests: 349 -> <passed> (given 22)`.
