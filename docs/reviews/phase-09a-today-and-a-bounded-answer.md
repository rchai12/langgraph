# Review: Phase 9a

- Verdict: PASS
- Passed: 859
- Findings: 0
- Approved deviations: None
- For the architect: Spot 1 failed on the real date 2026-11-10 against the local day 2031-03-03. Spot 8 failed because one answer request was sent; the assertion diff was truncated before the log. The Monday case's node id is day0-Monday.

## Findings

None

Parts that needed a repair: None
Built beyond the spec: None

## Spots

1. `datetime.now()` gave `2026-11-10` against the local day `2031-03-03`.
2. `isoweekday()` named Monday `Tuesday`.
3. The cached day left the second prompt as `Today is 2026-12-31, a Thursday.`
4. `32768` raised `PromptError: point demo_pick: context_tokens must be 8192 to 32768`.
5. `num_ctx` stayed `8192` against `16384`.
6. Counting characters answered `24002-é` with `Hi.`
7. `>=` escalated exactly 24000 bytes as `answer_too_large`.
8. Checking the size after `decide` sent one answer request. The diff stopped at that request.
9. `answer_too_large` came before `model_unavailable`.

## Coder tests

- R1: `test_a_late_offset_just_after_midnight_is_the_local_day`
- R2: `test_plan_fields_reads_today_once_and_leap_day_is_tuesday`
- R3: `test_both_caps_at_8192_are_sent_and_a_missing_context_is_refused`
- R5: `test_no_results_are_refused_and_two_results_together_escalate`
