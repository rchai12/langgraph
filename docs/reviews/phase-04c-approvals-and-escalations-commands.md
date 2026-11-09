# Review: Phase 4c

- Verdict: PASS
- Passed: 423
- Findings: 0
- Approved deviations: progress.md also adds the missing Phase 4b entry, because check_reports rejects the committed 4b review without one
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` exited 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (cli,core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The `tests` step reported `423 passed` in 17.76s. No skipped, xfailed, or warnings summary. Sections, each with 0 failed:

```
Sections:
  cli            49 passed    0 failed    0 skipped
  core          374 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            49 passed    0 failed    0 skipped
  core          374 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100` exited 0. Both files are 100%, TOTAL 100%.

`.venv/bin/python -m pytest tests/unit/test_decisions.py tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py --no-cov` reported `33 passed`.

`grep` finds one progress heading, at `docs/progress.md:86`. `.venv/bin/python scripts/check_reports.py`, before this review, printed `Reports OK.`

The protected diff printed nothing. The three given files match the spec's blocks. Searches 1, 2, and 3 printed nothing. `git diff HEAD -- src/conductor/cli/main.py` adds the two command groups; the only removed line is the old typing import. `doctor` and `runs` are unchanged.

`git status --short` lists the 11 scope paths. It also lists `docs/reviews/phase-04b-store.md`, the Phase 4b review rewritten before this check. The progress entry's changed-files count is 11.

## Progress entry

```
## Phase 4c: the approvals and escalations commands (2026-11-08)
- Tests: 378 -> 423 (given 33)
- New public names: `decisions`: `NOTE_MESSAGE`, `decide_approval`, `answer_escalation`; `config`: `DECIDED_BY_MESSAGE`, `Settings.decided_by`
- Changed files: 11
- Deviations:
  - The Phase 4b progress entry was missing, so this phase adds it; `check_reports.py` rejects the committed 4b review without one.
- Follow-ups:
  - None
```

The heading and tests line match section 8. The listed deviation is real: this diff adds the Phase 4b entry as well as the Phase 4c entry. `decided_by` is checked after the timeout, against `^[a-z][a-z0-9_]{0,31}$`. `decisions.py` is the line after `store.py` in the critical-modules list and in `docs/testing.md`.

## Coder tests

Each bullet of "Tests to write" has a deciding assertion:

- R1 a 500-character note, and a 501-character note on an unknown id: `test_a_note_of_500_is_kept_and_a_longer_one_is_refused_first`
- R2 a store race that raises `AlreadyDecided`: `test_a_store_that_lost_the_race_passes_already_decided`
- R2 an empty registry records nothing: `test_an_unregistered_action_records_nothing`
- R3 an unknown escalation, and an answered one before `clock.now`: `test_an_unknown_escalation_is_missing_and_an_answered_one_skips_the_clock`
- R4 a refused edit leaves `pending()` unchanged: `test_a_refused_edit_leaves_the_pending_list`
- R6 `escalations show --json` includes the answer: `test_show_json_includes_an_answer`
- R7 a declined retry stays open: `test_a_declined_retry_records_nothing`
- R8 `Infinity` is refused and `{}` is judged: `test_infinity_is_refused_and_an_empty_object_is_judged`
- R9 `CONDUCTOR_DECIDED_BY=Owner` prints the settings error: `test_a_bad_decided_by_prints_the_settings_error`

`decide_approval` calls `store.record_decision` only after `apply_decision` returns. `edit` parses `--args` before `_run` opens the store. No `# pragma: no cover`.

## Probe

Saved outside the repo, run once from the repo root, then deleted:

```
ok   the JSON list round-trips into requests
ok   a declined prompt never records
ok   an edit is recorded exactly when the action accepts it
ok   the first decision stays; every second one fails
ok   errors go to stderr as one Error line, with no traceback
ok   declined retries stay open, cancels close
ok   every recorded decision is from the terminal, by the configured label
FAILURES 0
```

## Spot checks

Each change was made in the named function, the deciding test failed, and the file was restored from the saved bytes. `git diff` of `src/conductor/cli/main.py` afterwards has the same single removed line as before.

| # | Deciding result |
|---|---|
| 1 | `test_a_refused_edit_records_nothing` found a stored edit |
| 2 | `test_a_decided_request_is_refused_before_the_policy` raised `DecisionRefused` |
| 3 | `test_errors` for the 501-character note reported `already decided` |
| 4 | `test_cancel_does_not_ask` got `StopIteration` on the second retry, and stderr was empty |
| 5 | `test_approve_asks_first` printed `Approved` with no prompt |
| 6 | `test_approve_with_yes_and_reject_do_not_ask` stopped on `Reject? [y/N]` |
| 7 | `test_edit_arguments_must_be_a_json_object` for `NaN` reported a validation error |
| 8 | `test_approve_with_yes_and_reject_do_not_ask` did not print `Approved` |
| 9 | `test_show_a_decided_request` lost the `edited args:` line |
