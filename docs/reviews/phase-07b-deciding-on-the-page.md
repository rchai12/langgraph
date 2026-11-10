# Review: Phase 7b

- Verdict: PASS
- Passed: 744
- Findings: 0
- Approved deviations: None
- For the architect: Spot 6 truncated both started lists, so the printed line did not show the second id. Spot 9 also printed the RunError as a warning while the assertion was None.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` ended with `All checks passed.` The tests step passed 744, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary. `critical coverage` passed, including `web/jobs.py`.

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            87 passed    0 failed    0 skipped
  core          657 passed    0 failed    0 skipped
```

```
Summary:
  lint: passed
  format: passed
  tests (cli,core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The section run before the full tests step was the same: cli 87 passed, core 657 passed, 0 failed.

`.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100` exited 0 with `TOTAL` at 100% (547 statements, 124 branches). `.venv/bin/python -m pytest tests/e2e/test_web_decide.py tests/e2e/test_web_runs.py --no-cov` printed `30 passed`. `.venv/bin/python scripts/check_reports.py --phase 7b`, run before this report, printed `Reports OK.` The protected diff printed nothing. `git diff HEAD -- src/conductor/decisions.py` only adds `parse_json_object`. All four searches printed nothing.

## Scope

`git status --short` lists the 14 scope paths and nothing else. Both given files equal the spec fences. `docs/testing.md` and `scripts/critical_modules.txt` add only the `web/jobs.py` line after `web/app.py`.

## Requirements

- R1: `test_parse_json_object_keeps_only_objects` (`{}`, `[]`, `"x"`, `Infinity`, `-Infinity`). `cli/main.py` parses `--args` through `parse_json_object`. The 4c edit tests passed in the full check.
- R2: `test_a_pending_step_has_its_forms` and `test_a_valid_cookie_is_kept_and_the_forms_carry_it`.
- R3: `test_a_pending_step_has_its_forms`, `test_a_plan_cannot_be_edited_and_a_decided_request_has_no_forms`, and `test_an_escalation_is_answered_from_the_web` (2 cases).
- R4: `test_a_form_without_its_token_is_refused` (3 cases), `test_a_token_without_its_cookie_is_refused`, `test_the_origin_of_a_form` (4 cases), `test_deciding_what_is_not_there` (3 cases), and `test_a_bad_token_does_not_open_the_store`.
- R5: `test_approve_records_from_the_web_and_resumes` and `test_an_edit_carries_its_note_and_arguments`. Search 2 printed nothing.
- R6: `test_edited_arguments_must_be_a_json_object` (3 cases), `test_an_edit_the_action_refuses_lists_its_problems`, `test_a_second_decision_is_refused`, `test_a_note_too_long_is_refused`, `test_an_unknown_action_is_refused_and_a_broken_store_is_unavailable`, and `test_a_second_decision_links_back_to_the_request`.
- R7: `test_a_waiting_run_links_to_what_it_waits_for`, `test_a_busy_run_refreshes_itself`, `test_the_last_resume_error_is_shown`, `test_a_run_that_is_not_there` (2 cases), and `test_finished_runs_show_their_line` (done with the reply escaped, rejected with a note, cancelled, stopped at `answer`).
- R8: `test_a_decision_resumes_the_run_in_the_background`, `test_a_resume_that_fails_is_recorded_not_raised`, `test_a_second_start_waits_and_the_thread_is_not_a_daemon`, `test_other_exceptions_are_kept_as_a_fixed_line_and_a_tool_check_is_its_text`, and `test_a_run_error_is_kept_and_the_next_start_clears_it`. Search 4 printed nothing.
- R9: `test_approve_records_from_the_web_and_resumes`, `test_a_second_decision_is_refused` (`started == [RUN]`), and `test_a_refused_edit_and_a_conflict_start_no_extra_resume`.
- R10: search 1 printed nothing.
- R11: the coverage gate, as above.

## Probe

The script was saved outside the repository, run from the repository root, and deleted.

```
ok   a decision is recorded exactly when origin, cookie, and token all fit (72 forms)
ok   of two decisions sent at once, one is recorded and one gets 409 (10 races)
ok   three plans approved on the page resume in the background to their step approval
FAILURES 0
```

## Spot checks

Each deciding test failed. The edits were reversed and the files matched their text from before the spots. `__pycache__` under `src`, `tests`, and `scripts` was removed before each pytest and again at the end.

| # | Printed failure |
|---|---|
| 1 | `(303, '')` against `(403, 'Bad form token')` |
| 2 | `(303, '')` against `(403, 'Bad form token')` for `"0" * 64` |
| 3 | `assert 303 == 403` for `http://evil.example` |
| 4 | `assert 403 == 303` for a missing origin |
| 5 | `('approve', 'terminal', 'owner')` against `('approve', 'web', 'owner')` |
| 6 | the started lists differed; pytest truncated both ids |
| 7 | an `/edit` action was present |
| 8 | `assert 'refresh' not in` the waiting page |
| 9 | `assert None == 'no run 9999...'`, and the thread printed `RunError: no run 9999...` |

## Progress

`## Phase 7b: deciding on the page (2026-11-09)` has `Tests: 704 -> 744 (given 30)`, `Changed files: 14`, and no deviations.
