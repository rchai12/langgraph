# Verify Phase 4b: the store

Spec: `docs/phases/phase-04b-store.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.store` (critical), added `Answer` and `EscalationAnswer` to `conductor.contracts.approvals` and `Settings.db_path` to `conductor.config`, added `store.py` to the critical modules, copied the given `tests/unit/test_store.py` (22 tests), and wrote `tests/unit/test_store_more.py`.

## 1. Gates

N is `349`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 371 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `store.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/store.py,*/conductor/contracts/approvals.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_store.py --no-cov -W error::ResourceWarning` | exactly `22 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- tests src/conductor/policy.py src/conductor/contracts/escalations.py src/conductor/contracts/__init__.py` | no output |
| `git diff HEAD -- src/conductor/contracts/approvals.py` | only added lines, at the end |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/store.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|contextlib|dataclasses|datetime|os|pathlib|re|sqlite3|typing|pydantic|conductor\.contracts|conductor\.contracts\.approvals|conductor import clock, ids)( |$)"`
2. `git grep --untracked -n -E "execute\(f|execute\([^)]*%|execute\([^)]*\.format\(" -- src/conductor/store.py`
3. `git grep --untracked -n -E "journal_mode|WAL" -- src/conductor/store.py`

## 2. Scope paths

`git status --short` lists only: `src/conductor/store.py`, `src/conductor/contracts/approvals.py`, `src/conductor/config.py`, `scripts/critical_modules.txt`, `docs/testing.md`, `tests/unit/test_store.py`, `tests/unit/test_store_more.py`, `docs/progress.md`. The given file equals the spec's block; the schema in `store.py` has exactly the spec's tables and columns.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_new_store_is_private_and_versioned`, `test_a_store_keeps_its_rows_across_openings`; the coder's missing-folder and empty-file tests | pass |
| R2 | `test_a_store_with_another_schema_is_refused`, `test_a_file_that_is_not_a_database` | pass |
| R3 | `test_a_busy_store`; the coder's no-journal and rollback tests; probe "only conductor.db is left, private to its owner"; read every method for one connection, one `BEGIN IMMEDIATE`, and a close | pass; ok; the same |
| R4 | `test_pending_requests_in_the_order_they_were_asked`, `test_a_request_is_added_once`; probe "pending lists every request by time, then id" | pass; ok |
| R5 | `test_the_first_decision_wins`, `test_an_unknown_approval`; probes "decided requests leave the pending list", "of eight decisions at once, exactly one is recorded" | pass; ok |
| R6 | `test_an_escalation_is_raised_and_answered`, `test_an_escalation_is_answered_once`; the coder's note test | pass |
| R7 | `test_a_damaged_row_is_refused`; the coder's decision-column and escalation tests; probe "every tampered request is refused when read" | pass; ok |
| R8 | `test_lease_ids_are_checked`; the coder's holder test | pass |
| R9 | `test_a_lease_is_held_until_it_expires`, `test_a_lease_is_renewed_and_released_by_its_holder`; the coder's expired-renew and no-lease tests; probes "of eight acquires at once, exactly one holds the lease", "a lease holds for exactly 600 seconds" | pass; ok |
| R10 | `test_the_answers`, `test_a_new_store_is_private_and_versioned` (`db_path`) | pass |
| R11 | searches 1 and 2 | no output |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It works in its own temporary folder, and runs eight threads at once against one file twice (decisions, then leases). Run it three times; a concurrency check that fails even once is a finding.

```python
"""Independent probe for Phase 4b. Run from the repository root with .venv/bin/python."""

import random
import sqlite3
import stat
import tempfile
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from conductor import clock
from conductor.contracts.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    PlannedStep,
    steps_digest,
)
from conductor.store import AlreadyDecided, LeaseHeld, Store, StoreError

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


START = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
NOW = [START]
clock.now = lambda: NOW[0]  # type: ignore[assignment]
STEP = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
folder = Path(tempfile.mkdtemp())
path = folder / "conductor.db"
db = Store(path)


def request(i: int, minutes: int) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=f"{i:032x}",
        run_id="a" * 32,
        stage="step",
        steps=(STEP,),
        args_sha256=steps_digest((STEP,)),
        requested_at=START + timedelta(minutes=minutes),
    )


def decision(i: int) -> ApprovalDecision:
    return ApprovalDecision(
        approval_id=f"{i:032x}",
        verdict="approve",
        args_sha256=steps_digest((STEP,)),
        channel="web",
        decided_by="owner",
        decided_at=START,
    )


rng = random.Random(8)
made = [request(i, rng.randint(0, 20)) for i in range(1, 101)]
for r in rng.sample(made, len(made)):
    db.add_request(r)
expected = sorted(made, key=lambda r: (r.requested_at, r.approval_id))
check("pending lists every request by time, then id", db.pending() == expected)
for r in made[::2]:
    db.record_decision(decision(int(r.approval_id, 16)))
check(
    "decided requests leave the pending list",
    db.pending() == [r for r in expected if r not in made[::2]],
)

db.add_request(request(500, 0))
results: list[str] = []


def decide_once() -> None:
    try:
        Store(path).record_decision(decision(500))
        results.append("won")
    except AlreadyDecided:
        results.append("already")
    except StoreError as error:
        results.append(str(error))


threads = [threading.Thread(target=decide_once) for _ in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(
    "of eight decisions at once, exactly one is recorded",
    sorted(results) == ["already"] * 7 + ["won"],
)

holders = [f"{i:032x}" for i in range(1000, 1008)]
leases: list[str] = []


def lease_once(holder: str) -> None:
    try:
        Store(path).acquire("7" * 32, holder)
        leases.append("got")
    except LeaseHeld:
        leases.append("held")


threads = [threading.Thread(target=lease_once, args=(h,)) for h in holders]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(
    "of eight acquires at once, exactly one holds the lease",
    sorted(leases) == ["got"] + ["held"] * 7,
)

DAY = START + timedelta(days=1)
NOW[0] = DAY
db.acquire("8" * 32, holders[0])
boundary = True
for offset in (0, 1, 299, 599):
    NOW[0] = DAY + timedelta(seconds=offset)
    try:
        db.acquire("8" * 32, holders[1])
        boundary = False
    except LeaseHeld:
        pass
NOW[0] = DAY + timedelta(seconds=600)
boundary = boundary and db.acquire("8" * 32, holders[1]).holder == holders[1]
check("a lease holds for exactly 600 seconds", boundary)

with closing(sqlite3.connect(path, isolation_level=None)) as raw:
    ids = [row[0] for row in raw.execute("SELECT approval_id FROM approvals")]
    for approval_id in rng.sample(ids, 20):
        raw.execute(
            "UPDATE approvals SET request = replace(request, 'Milk', 'Mild') WHERE approval_id = ?",
            (approval_id,),
        )
damaged = 0
for approval_id in ids:
    try:
        db.approval(approval_id)
    except StoreError:
        damaged += 1
check("every tampered request is refused when read", damaged == 20)

files = sorted(p.name for p in folder.iterdir())
mode = stat.S_IMODE(path.stat().st_mode)
check(
    "only conductor.db is left, private to its owner",
    files == ["conductor.db"] and mode == 0o600,
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_store_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named method, run the deciding test, see it fail, restore.

| # | Change (method) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the file left for `sqlite3.connect` to create (`Store.__init__`) | `test_a_new_store_is_private_and_versioned` | `0o600` | `0o644` |
| 2 | `user_version` 0 accepted even with tables (`Store.__init__`) | `test_a_store_with_another_schema_is_refused`, `(0, True)` | refused | accepted |
| 3 | the decision written without checking for an earlier one (`record_decision`) | `test_the_first_decision_wins` | `AlreadyDecided` | overwritten |
| 4 | the id-column comparison removed (row reading) | `test_a_damaged_row_is_refused`, the changed `approval_id` | damaged | accepted |
| 5 | `pending()` ordered by `approval_id` only | `test_pending_requests_in_the_order_they_were_asked` | `2, 1, 3` | `1, 2, 3` |
| 6 | an expired lease is one with `expires_at < now` (`acquire`) | `test_a_lease_is_held_until_it_expires`, at 600 s | acquired | `LeaseHeld` |
| 7 | the current holder refused by `acquire` | `test_a_lease_is_renewed_and_released_by_its_holder` | `900` s | `LeaseHeld` |
| 8 | `release` deletes whatever lease the thread has | `test_a_lease_is_renewed_and_released_by_its_holder`, `OTHER` | `LeaseLost` | released |
| 9 | `OperationalError` passed through instead of mapped (any method) | `test_a_busy_store` | `conductor.db: busy` | `database is locked` |

Reasonable variations that are correct: one private `_transaction()` context manager; `executescript` for the schema inside the transaction; `INSERT ... ON CONFLICT` for leases; rows read with `sqlite3.Row`; the time format written by a private helper.

## 6. Project rules

- Searches 1 to 3.
- Every write that depends on a read (`record_decision`, `answer`, `acquire`, `renew`, `release`) does both inside one `BEGIN IMMEDIATE` transaction.
- Every message is one of the spec's: the file name, ids, and fixed text.
- No real data: the tests and the probe build their databases under temporary folders.

## 7. Out of scope

Each must be absent: validating a decision's meaning (that is `policy`), commands, the graph, events, `checkpoints.db`, WAL, migrations, deleting rows, approval expiry, a clarify answer, timers.

## 8. Progress log

The entry exists, headed `## Phase 4b: the store (...)`, with `Tests: 349 -> <passed> (given 22)`, and each deviation it lists is real and justified.
