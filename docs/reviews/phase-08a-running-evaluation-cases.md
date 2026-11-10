# Review: Phase 8a

- Verdict: FAIL
- Passed: 788
- Findings: 1
- Approved deviations: None
- For the architect: Moving the runs check below the loop still raises ValueError for runs=0, so that case passed. The selector also ran the 101 case, which failed with ScriptError. Spot 4 raised IndexError at p95, and spot 6's visible difference was p95 0.00s.

## Findings

R2 | tests/unit/test_eval_run.py:129 | expected test_runs_are_1_to_100 with runs=0 to fail when the check follows the loop | found that case still passed

Parts that needed a repair: the runs=0 case of test_runs_are_1_to_100

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` ended with `All checks passed.` The tests step passed 788, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary.

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            93 passed    0 failed    0 skipped
  core          695 passed    0 failed    0 skipped
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

The section run before the full tests step was the same: cli 93 passed, core 695 passed, 0 failed.

`.venv/bin/python -m coverage report --include="*/conductor/evals/*.py,*/conductor/cli/main.py,*/conductor/web/app.py" --fail-under=100` exited 0 with `TOTAL` at 100% (697 statements, 186 branches). `.venv/bin/python -m pytest tests/unit/test_eval_cases.py tests/unit/test_eval_run.py tests/e2e/test_cli_eval.py tests/e2e/test_web_labels.py --no-cov` printed `32 passed`. `.venv/bin/python scripts/check_reports.py --phase 8a`, run before this report, printed `Reports OK.` The protected diff printed nothing. `git diff HEAD -- src/conductor/web` is the button texts and the field labels. Both searches printed nothing.

## Scope

`git status --short` lists the 11 scope paths and nothing else. The given case file and the four given test files equal the spec fences.

## Requirements

- R1: `test_the_given_demo_cases_load`, `test_what_a_case_file_may_not_hold` (13 cases), `test_a_problem_never_quotes_the_request`, `test_an_id_from_an_earlier_file_is_used_twice`, `test_a_number_plan_and_args_on_an_escalation_are_refused`, and `test_a_request_of_2000_characters_loads`.
- R2: `test_runs_are_1_to_100` (2 cases) and `test_a_rule_route_asks_the_model_only_to_plan`. Search 1 printed nothing. The runs=0 spot is the finding above.
- R3: `test_three_runs_that_agree`, `test_runs_that_disagree`, `test_a_case_that_expects_escalations`, `test_args_missing_a_key_are_not_right`, `test_actions_in_another_order_are_not_right`, and `test_an_invalid_model_output_is_not_the_expected_escalation`.
- R4: `test_an_invalid_reply_and_an_unavailable_model`, the seconds in `test_runs_that_disagree`, `test_a_classifier_route_and_a_plan_sum_both_times`, and `test_runs_are_logged_under_the_data_folder`.
- R5: the line checks in `test_three_runs_that_agree`, `test_runs_that_disagree`, `test_the_overall_line`, and `test_one_run_has_equal_percentiles_and_overall_without_args_prints_a_dash`.
- R6: `test_eval_run_prints_a_line_per_case_and_overall`, `test_five_runs_by_default_from_one_file`, `test_errors` (2 cases), `test_a_bad_case_file_names_itself`, `test_too_many_runs_are_refused`, and `test_a_folder_runs_each_file_in_order`.
- R7: `test_each_approval_form_says_what_it_does` (2 cases) and `test_each_escalation_form_says_what_it_does`. The earlier web tests passed in the full check.
- R8: search 1 printed nothing.
- R9: search 2 printed nothing.
- R10: the coverage gate, as above.

## Probe

```
ok   200 random cases give the metrics the probe computes
ok   the given evals/cases/demo.toml loads (5 cases)
FAILURES 0
```

The script was saved outside the repository, run from the repository root, and deleted.

## Spot checks

The edits were reversed and the files matched their text from before the spots. `__pycache__` under `src`, `tests`, and `scripts` was removed before each pytest and again at the end.

| # | Printed failure |
|---|---|
| 1 | `assert (4, 3, 2, 1) == (1, 3, 2, 1)` |
| 2 | `assert (1, 0, None, 1) == (1, 1, None, 1)` for weather |
| 3 | `assert (2.0, 6.0, 6.5, 9.5) == (2.0, 4.0, 0.5, 3.0)` |
| 4 | `IndexError: list index out of range` in `_percentile` |
| 5 | `test_runs_are_1_to_100[0]` passed. `[101]` failed with `ScriptError: no scripted reply left for route` |
| 6 | the printed lines ended `p95 0.00s` against `p95 2.00s` |
| 7 | `['Approve', 'Reject', 'Edit']` against `Edit and approve` |
| 8 | `SYNTHETIC-SECRET` was in `case 1: route ... or escalate` |

## Progress

`## Phase 8a: running evaluation cases (2026-11-10)` has `Tests: 744 -> 788 (given 32)`, `Changed files: 11`, and no deviations.
