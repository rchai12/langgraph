# Review: Phase 4b

- Verdict: FAIL
- Passed: 378
- Findings: 1
- Approved deviations: None
- For the architect: None

## Findings

8. Progress log | docs/progress.md:76 | expected a Phase 4b entry headed ## Phase 4b: the store (YYYY-MM-DD) with Tests: 349 -> 378 (given 22) | found the log ends at Phase 4a and docs/progress.md is unchanged

Parts that needed a repair: none

Built beyond the spec: none

## Gate output

`.venv/bin/python scripts/check.py --first core` exited 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The `tests` step reported `378 passed` in 16.18s. No skipped, xfailed, or warnings summary. Sections, both with 0 failed:

```
Sections:
  core          357 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          357 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/store.py,*/conductor/contracts/approvals.py" --fail-under=100` exited 0. `store.py` and `approvals.py` are both 100%, TOTAL 100%.

`.venv/bin/python -m pytest tests/unit/test_store.py --no-cov -W error::ResourceWarning` reported `22 passed`.

`.venv/bin/python scripts/check_reports.py`, before this review, printed `Reports OK.` After this review the same command prints `docs/reviews/phase-04b-store.md:1: no progress entry for Phase 4b`. The review's form is the one the checker accepts; the missing entry is the finding above.

`git diff --stat HEAD -- tests src/conductor/policy.py src/conductor/contracts/escalations.py src/conductor/contracts/__init__.py` printed nothing. `git diff HEAD -- src/conductor/contracts/approvals.py` is 12 added lines at the end (`Answer` and `EscalationAnswer`).

Searches 1, 2, and 3 printed nothing. `tests/unit/test_store.py` is byte-for-byte the spec's given block. The three tables and their columns match the spec. `db_path` is `data_dir / "conductor.db"` immediately after `runs_dir`. `store.py` is the next line after `policy.py` in `scripts/critical_modules.txt` and in the critical-modules list in `docs/testing.md`.

`git status --short` lists the other seven scope paths. `docs/progress.md` is not among them.

## Probe

The guide's probe was saved outside the repo, run three times from the repo root, then deleted. Each run:

```
ok   pending lists every request by time, then id
ok   decided requests leave the pending list
ok   of eight decisions at once, exactly one is recorded
ok   of eight acquires at once, exactly one holds the lease
ok   a lease holds for exactly 600 seconds
ok   every tampered request is refused when read
ok   only conductor.db is left, private to its owner
FAILURES 0
```

## Coder tests

Each bullet of "Tests to write" has a deciding assertion in `tests/unit/test_store_more.py`:

- R1 missing folder `0700` and empty `0600` file: `test_a_missing_folder_is_private_and_an_empty_file_gets_the_schema`
- R3 no journal and no open transaction after every public method: `test_operations_leave_no_journal_or_open_transaction`
- R3 a refused decision leaves the first one: `test_a_refused_decision_leaves_the_first_one`
- R7 damaged decision column and damaged escalation from `open_escalations()`: `test_a_damaged_decision_or_escalation_is_refused`
- R8 holder `"x"`: `test_a_holder_id_must_be_hexadecimal`
- R9 renew an expired lease, and `LeaseLost` when the thread has none: `test_an_expired_lease_can_be_renewed_and_a_missing_lease_is_lost`
- R6 a retry note kept through `escalation(id)`: `test_a_retry_note_is_kept`

No `# pragma: no cover`.

## Spot checks

Each change was made in `src/conductor/store.py`, the deciding test failed, and the file was restored from the saved bytes. `git status --short` afterwards was the same seven paths.

| # | Deciding result |
|---|---|
| 1 | `test_a_new_store_is_private_and_versioned` saw mode `0o644` (`420 == 384`) |
| 2 | `test_a_store_with_another_schema_is_refused[0-True-...]` did not raise `StoreError` |
| 3 | `test_the_first_decision_wins` did not raise `AlreadyDecided` |
| 4 | `test_a_damaged_row_is_refused` with the changed `approval_id` did not raise `StoreError`; the other two parameter sets still did |
| 5 | `test_pending_requests_in_the_order_they_were_asked` failed its `2, 1, 3` order |
| 6 | `test_a_lease_is_held_until_it_expires` raised `LeaseHeld` at 600 s |
| 7 | `test_a_lease_is_renewed_and_released_by_its_holder` raised `LeaseHeld` for the current holder |
| 8 | the same test, `OTHER`, did not raise `LeaseLost` on `release` |
| 9 | `test_a_busy_store` raised `sqlite3.OperationalError: database is locked` |

`record_decision`, `answer`, `acquire`, `renew`, and `release` each do the read and the write inside one `BEGIN IMMEDIATE` transaction. `release` deletes the lease row for its holder, which R9 requires.
