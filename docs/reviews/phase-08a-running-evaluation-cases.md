# Review: Phase 8a

- Verdict: PASS
- Passed: 827
- Findings: 0
- Approved deviations: None
- For the architect: Spot 5 now fails on runs=101 with ScriptError. Spot 4 raised IndexError at the p95 index, and spot 6's visible difference was p95 0.00s. This run includes Phase 8b, so the suite is 827 while the 8a entry still says 788, and test_cli_eval.py has the three-line slice. The worktree also has uncommitted edits to the architect skill and the roadmap.

## Findings

None

Parts that needed a repair: None
Built beyond the spec: None

## Spots

1. Counting distinct outcomes made `consistent` `4` against `1`.
2. Requiring a plan for a route escalation made weather `plan_ok` `0` against `1`.
3. Summing every reply in the log gave seconds `(2.0, 6.0, 6.5, 9.5)` against `(2.0, 4.0, 0.5, 3.0)`.
4. The percentile index without the minus one raised `IndexError: list index out of range` at p95.
5. Checking `runs` after the loop made `test_runs_are_1_to_100[101]` raise `ScriptError: no scripted reply left for route`. The `0` case was not selected.
6. Building `OllamaModel` in the command failed the pinned lines. The visible difference was `p95 0.00s` against `p95 2.00s`.
7. The step form's buttons were `['Approve', 'Reject', 'Edit']` against `Edit and approve`.
8. The route message contained `SYNTHETIC-SECRET`.

## Coder tests

- R1: `test_an_id_from_an_earlier_file_is_used_twice`, `test_a_number_plan_and_args_on_an_escalation_are_refused`, `test_a_request_of_2000_characters_loads`
- R3: `test_args_missing_a_key_are_not_right`, `test_actions_in_another_order_are_not_right`, `test_an_invalid_model_output_is_not_the_expected_escalation`
- R4: `test_a_classifier_route_and_a_plan_sum_both_times`
- R5: `test_one_run_has_equal_percentiles_and_overall_without_args_prints_a_dash`
- R6: `test_too_many_runs_are_refused`, `test_a_folder_runs_each_file_in_order`

## Scope of this run

The 8a commit's given files equal the spec. `git diff HEAD` for the protected paths and for `src/conductor/web` is empty because that phase is committed. The 8a web diff is the button texts and the labels `Note` and `Arguments (JSON)`. Searches 1 and 2 have no output. The probe ended `FAILURES 0`.
