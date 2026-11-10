# Review: Phase 8b

- Verdict: PASS
- Passed: 827
- Findings: 0
- Approved deviations: None
- For the architect: Spots 2, 4, 6, and 8 failed on truncated assertions, so the extra digest, the old model name, each case line, and the ending removed line were not fully visible. Spot 9 printed exit 1 with stdout starting at the say-hi line.

## Findings

None

Parts that needed a repair: None
Built beyond the spec: None

## Spots

1. `compare=True` made `result == CaseResult(...)` fail because the two `run_ids` differ.
2. Reading every run of `log.runs()` failed `test_the_fingerprint_reads_only_these_runs`. Both sides of the assertion were truncated.
3. The name without UTC was `20261110T043015250000Z.json`.
4. The smallest name was `20261109...` against the expected `20261110...`. Both sides were truncated, so `old:1b` was not visible.
5. `latest_report` raised `ReportError: zzz.json is not a report`.
6. The same shares printed case lines (`5/5 -> 10/10`) instead of `no change`. The full list was truncated.
7. The weather line was `weather  route 5/5 -> 9/10`, without `args - -> 2/10`.
8. Leaving out the added lines failed `test_every_kind_of_change_in_order`. Both lists were truncated.
9. Reading the previous report after the runs left stdout starting `say-hi  ... p95 1.00s` with exit 1.

## Coder tests

- R1: `test_one_run_keeps_its_id`
- R3: `test_two_files_and_two_results_keep_their_order`
- R4: `test_two_digests_are_kept_sorted`
- R6: `test_a_report_that_is_not_utf8_is_refused`
- R8: `test_a_removed_case_and_an_escalation_are_named_alone`
- R9: `test_notes_are_not_a_previous_report`, `test_a_bad_run_count_wins_over_an_unreadable_report`
