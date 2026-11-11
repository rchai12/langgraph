# Review: Phase 9d

- Verdict: PASS
- Passed: 1006
- Findings: 0
- Approved deviations: None
- For the architect: Spot 2 failed with '--1.95' against '-0.05', which contains 95. Spot 9 also compared Wednesday with Tuesday.

## Findings

None

Parts that needed a repair: None

Built beyond the spec: None

## Gates

Verified the committed tree at `f4a6858`. `scripts/check.py --first cli,core` ended with `All checks passed.` 1006 passed in 53.12s. Sections: scripts 0, cli 98, core 908. Summary: lint passed, format passed, tests (cli,core) passed, tests passed, critical coverage passed. The coverage gate is 322 statements at 100% (`answer.py` 67, `plan.py` 49, `cases.py` 84, `run.py` 122). The two given test files passed 29. `grep -c "^## Phase 9d: " docs/progress.md` is 1. `scripts/check_reports.py --phase 9d` printed `Reports OK.` before this report.

## Scope

The working tree was clean, so this review is of `bac3a20..f4a6858`. That diff is the ten scope paths and nothing else. The guide's protected `git diff --stat HEAD` is empty. The same protected paths, with `tests` left out, are also empty across the phase commit. The four new test files are the only paths under `tests`. Search 1 and search 2 are empty.

`evals/cases/finance.toml`, `tests/unit/test_answer_dollars.py`, and `tests/unit/test_eval_today.py` equal the spec fences. `with_dollars` keeps key order, skips booleans and a key whose `_dollars` form already exists, and does not change its argument. `answer_request` builds the message from copied results and measures the 24000-byte bound on that message. `EvalCase.today` is the last field. `_today` refuses anything whose type is not `date`, after the other case checks. `plan_fields` uses the given day, otherwise `clock.today()`. `run_case` passes `case.today` on every run.

## Probe

```
ok   3000 random JSON trees convert as the oracle says, in order, input unchanged
ok   200 answers send exactly the converted message, bounded on its own size
ok   today is accepted exactly when TOML reads a plain date
ok   30 cases plan every run on their own day while the clock moves
ok   a run over the fake keeps cents in its log and sends dollars to the answer
FAILURES 0
```

## Spots

Each deciding test failed, and the four source files matched the text taken before the edits. `git diff` was empty afterwards. No `__pycache__` directory remains under `src` or `tests`.

1. The minus sign left out. `[negative]` compared `'42.10'` with `'-42.10'`.
2. Signed division with the sign kept. `[minus-five-cents]` compared `'--1.95'` with `'-0.05'`.
3. `isinstance` without excluding booleans. `[bool]` compared `'flag_dollars': '0.01'` with `'flag_cents': True`.
4. A list returned unconverted. `[list]` compared `'bills_cents': -1299` with `'bills_dollars': '-12.99'`.
5. The bound measured before conversion. `test_the_bound_is_measured_on_the_dollars` compared `Answered(reply='Done.'` with `answer_too_large`.
6. `isinstance(value, date)` in the loader. `[local-datetime]` printed `Failed: DID NOT RAISE CaseFileError`.
7. `run_case` not passing `case.today`. `[given]` compared `[False, False]` with `[True, True]`.
8. The `_dollars` check removed. `[dollars-already]` was missing `'amount_cents': 4210`.
9. `plan_fields` ignoring `today`. The first pair was `'2031-01-01'` against `'2026-11-10'`.

## Coder tests

- R1, `-100`, `99`, and `-101`: `test_amounts_near_a_whole_dollar`
- R4, an invalid id reported before an invalid `today`: `test_an_invalid_id_is_reported_before_an_invalid_today`
- R5, `plan_request` on 2026-11-10 while `clock.today` raises: `test_plan_request_plans_on_the_given_day_without_the_clock`
- R3, one `get_spending` step, `"spent_dollars": "42.10"`, no `_cents` in the answer, and `spent_cents` 4210 in the first logged line: `test_a_spending_run_keeps_cents_in_the_log_and_sends_dollars`

## Requirements

- R1: `test_cents_become_dollars`, `test_the_keys_keep_their_order_and_the_input_is_unchanged`, `test_amounts_near_a_whole_dollar`, and the probe's 3000 trees.
- R2: `test_the_answer_reads_dollars`, `test_the_bound_is_measured_on_the_dollars`, and the probe's 200 answers.
- R3: `answer_request` copies each result before converting; `test_a_spending_run_keeps_cents_in_the_log_and_sends_dollars`; the probe's fake-server run.
- R4: `test_a_case_may_name_its_today`, `test_today_must_be_a_date`, `test_an_invalid_id_is_reported_before_an_invalid_today`, and the probe's eleven TOML values.
- R5: `test_plan_fields_take_a_given_day`, `test_plan_request_plans_on_the_given_day_without_the_clock`, and search 2.
- R6: `test_each_run_plans_on_the_case_day`, search 1, and the probe's 30 cases.
- R7: `finance.toml` equals the spec, and `test_the_finance_cases_load_and_plan_on_one_day`.
- R8: the phase commit is the ten scope paths.
- R9: the coverage gate at 100%.
