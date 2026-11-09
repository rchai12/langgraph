# Review: Phase 5e

- Verdict: PASS
- Passed: 564
- Findings: 0
- Approved deviations: None
- For the architect: spot 1 printed RuntimeError during run_step; spot 6 left the plan approval as Approved and the step approval exited 1 with empty stdout; spot 8 printed a model_unavailable escalation for an unreachable model

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` ended with `All checks passed.` The tests step passed 564, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary.

```
Sections:
  cli            68 passed    0 failed    0 skipped
  core          496 passed    0 failed    0 skipped
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

`.venv/bin/python -m coverage report --include="*/conductor/cli/main.py,*/conductor/graph/supervisor.py" --fail-under=100` exited 0. TOTAL 533 statements, 122 branches, 100%.

`.venv/bin/python -m pytest tests/e2e/test_cli_ask.py tests/integration/test_resume_stopped.py --no-cov` printed `16 passed`. The three 4c files passed 28. `scripts/check_reports.py --phase 5e`, run before this report, printed `Reports OK.`

The five given files equal the spec fences, including the corrected `tests/e2e/test_cli_ask.py`. `git diff HEAD` of the three 4c files adds `--no-resume` and rewraps the lines that grew. `git diff HEAD` of `tests/integration/test_runtime.py` and `tests/integration/test_runtime_more.py` is the two given edits. `git diff HEAD` of `src/conductor/graph/supervisor.py` is `RESUMABLE_STOPS` and the stopped branch of `resume_run`. The protected diff is empty. Both searches printed nothing.

## Requirements

- R1: `test_the_resumable_stops`, `test_a_run_stopped_at_a_model_call_runs_that_node_again`, `test_a_run_stopped_at_a_step_stays_stopped`. Probe: `ok   a run stopped at answer resumes to done, without running its step again`.
- R2: `test_a_read_only_request_is_answered`, `test_json_output`, `test_a_finished_run_is_not_resumed`, `test_resume_json_of_a_waiting_run_and_a_bad_demo_setting`.
- R3: `test_each_decision_resumes_the_run`, `test_an_escalation_and_its_answers`, `test_a_rejection_ends_the_run`, `test_stopped_plain_rejection_and_escalation_problems`. `_state_text` calls `_request_block` and `_escalation_block`.
- R4: the three 4c files equal the spec; `test_an_edit_resumes_with_the_new_arguments_and_a_decline_waits`.
- R5: `test_no_resume_only_records_and_resume_continues`, `test_retry_without_resume_and_cancel_that_resumes`. Probe: `ok   every run reaches its end through ask, the decision commands, and resume ({'done': 69, 'rejected': 51})`.
- R6: `test_a_busy_run_keeps_the_decision_and_says_why`, `test_a_busy_reject_keeps_the_rejection`.
- R7: `test_errors`, `test_a_request_of_2001_characters_is_refused`.
- R8: both searches printed nothing. `cli/main.py` imports `RunError` and `RunState` from `conductor.graph.supervisor` and opens the runtime through `from conductor import runtime`.
- R9: the coverage gate, 100%.
- R10: the 4c files equal the spec, and the full check passed.

## Probe

Saved outside the repository, run with `.venv/bin/python`, then deleted. `FAILURES 0`.

```
ok   every run reaches its end through ask, the decision commands, and resume ({'done': 69, 'rejected': 51})
ok   every Next line names exactly the one pending approval
ok   no step ran twice
ok   resuming a finished run is refused on stderr, also with --json
ok   a run stopped at answer resumes to done, without running its step again
FAILURES 0
```

## Spot checks

Each deciding test failed. The two source files matched their pre-check text afterwards.

1. `run_step` added to `RESUMABLE_STOPS`. `test_a_run_stopped_at_a_step_stays_stopped` raised `RuntimeError: the runner broke` during `run_step`.
2. The resumable branch removed. The plan case raised `RunError: run ...0002 stopped at plan and cannot be resumed`.
3. `approve` passed `True` for no resume. Stdout was only `Approved ...0004.`.
4. `approve` passed `False` and ignored `--no-resume`. Stdout continued into the step block.
5. `_recorded` caught `RunError`. Exit 0, stdout `Approved ...0004.`, stderr empty.
6. The three `decide_approval` calls used `Registry(domains.DOMAINS)`. The plan approval still printed `Approved`; the step approval exited 1 with empty stdout. A plan decision returns before the registry lookup.
7. The approval block returned without `Next:`. The ask stdout ended at the step line.
8. `_session` called `open_runtime` imported by name. The ask printed `escalation ... model_unavailable ... model unavailable: unreachable`.

## Progress

`## Phase 5e: the run commands (2026-11-09)` with `Tests: 542 -> 564 (given 16)`. New public names are `RESUMABLE_STOPS`, `ask`, and `resume`. Changed files: 15, the current `git status --short` count. Deviations: None. The follow-up names four paths this phase did not produce: the spec, the verification guide, this review, and `.claude/skills/phase-architect/SKILL.md`.
