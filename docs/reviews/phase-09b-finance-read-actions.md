# Review: Phase 9b

- Verdict: PASS
- Passed: 908
- Findings: 0
- Approved deviations: None
- For the architect: Spots 1 and 5 failed with the finance domain against an empty tuple, and spot 2's value started with the demo domain. The -vv diffs ran past the summary phrase.

## Findings

None

Parts that needed a repair: None
Built beyond the spec: None

## Spots

1. `is None` registered finance when the command was unset. The assertion was the finance domain against `()`.
2. Placing the demo first made `[finance-demo]` start with the demo domain.
3. `mcp_command("finance")` left `[finance]` as `()` against the finance domain.
4. Dropping `context_tokens` gave `(16384, 8192, 4096)` against `(16384, 16384, 4096)`.
5. `DOMAINS = (finance.DOMAIN,)` registered finance for `[none]`.
6. `le=41` made `transactions-limit-41` print `Failed: DID NOT RAISE ValidationError`.
7. `McpServer("finances")` compared `env ()` with `env ('FIN_DATA_DIR',)`.

## Coder tests

- R1: `test_a_left_out_argument_keeps_its_default_except_the_phrase`
- R2: `test_a_missing_program_still_registers_finance_and_the_doctor_fails`
- R3: `test_the_demo_plan_also_sends_16384`
- R5: `test_a_prefixed_balance_request_runs_to_done`
