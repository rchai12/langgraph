# Review: Phase 9c

- Verdict: PASS
- Passed: 971
- Findings: 0
- Approved deviations: None
- For the architect: Spot 5 printed the whole action tuple, starting with propose_category against list_accounts, and did not print the phrase At index 0 diff. Spot 8 printed the whole argument dict, with match equals against contains, and -k propose_rule also ran propose_rule_change, which passed.

## Findings

None

Parts that needed a repair: None

Built beyond the spec: None

## Gates

`scripts/check.py --first cli,core` ended with `All checks passed.` 971 passed in 54.04s. Sections: scripts 0, cli 98, core 873. Summary: lint passed, format passed, tests (cli,core) passed, tests passed, critical coverage passed. Coverage of `src/conductor/domains/finance.py` is 202 statements, 100%. The two given test files passed 50. `grep -c "^## Phase 9c: " docs/progress.md` is 1. `scripts/check_reports.py --phase 9c` printed `Reports OK.` before this report.

## Scope

`git status --short` lists the ten scope paths. `git diff --stat HEAD -- tests` is the four files `tests/fake_finances_server.py`, `tests/finances_tools.json`, `tests/unit/test_finance_domain.py`, and `tests/unit/test_finance_more.py`. The zero-context diff of the two unit files is the four removed lines and the four added lines from the spec table. The protected diff is empty. Search 1 and search 2 are empty.

The given `finances_tools.json`, `fake_finances_server.py`, `test_finance_proposals.py`, and `test_finance_proposal_steps.py` equal the spec fences. The head, `_propose`, and tail blocks are each present in `finance.py`. `READS` equals the 20 `_read(...)` entries of `ACTIONS` at HEAD. The 11 contracts match the spec table, including field order. `TransferProposalArgs` is shared by both transfer tools.

## Probe

```
ok   the 11 actions after the 20 reads are the proposal tools, each with effect propose
ok   3000 random proposal argument sets are accepted exactly when every field fits
ok   1000 random proposal results are accepted exactly when the top field is an object
ok   2000 random requests route as the phrase list says
ok   the tool check finds 31 tools, 31 actions, no problems on the fake
ok   40 random runs call each step only as the plan and step decisions allow
FAILURES 0
```

## Spots

Each deciding test failed, and `finance.py` was restored to the text taken before the edits. No `__pycache__` directory remains under `src`, `tests`, or `scripts`.

1. `Reason` without its pattern. `[reason-two-lines]` printed `Failed: DID NOT RAISE ValidationError`.
2. `Id` with `ge=0`. `[id-0]` printed `Failed: DID NOT RAISE ValidationError`.
3. `"read"` in `_propose`. The sets differ, with `('tool', True, 'read', 'finances')` on the left.
4. `"categorize"` removed from the proposals rule. `[categorize]` printed `assert None == RuleRoute(...)`.
5. `ACTIONS = (*PROPOSALS, *READS)`. The tuple comparison starts with `propose_category` against `list_accounts`.
6. `priority: int | None = None`. `[change-priority]` printed `Failed: DID NOT RAISE ValidationError`.
7. `NoteArgs.text` without its pattern. `[text-blank]` printed `Failed: DID NOT RAISE ValidationError`.
8. `match: Match = "equals"`. `[propose_rule]` compared `{'match': 'equals'}` with `{'match': 'contains'}`.

## Coder tests

- R2, each of the nine finding types with status `ignored`: `test_each_finding_type_can_be_ignored`
- R2, a deleted rule sends the other fields as `None`, and a 101-character rename is refused: `test_a_deleted_rule_sends_no_other_change_and_a_long_rename_is_refused`
- R2, a 101-character subject is refused and a line break in the text is kept: `test_advice_keeps_a_line_break_and_refuses_a_long_subject`
- R6, `log_advice` waits for both approvals and keeps `advice.text`: `test_advice_waits_for_both_approvals_and_keeps_its_text`
- R6, a rejected plan of `get_balances` then `propose_category` ends `rejected` with no `TOOL_CALL`: `test_a_rejected_plan_calls_no_tool`

## Requirements

- R1: `test_eleven_proposal_actions_after_the_reads`, and the three block checks plus the `READS` comparison.
- R2: `test_the_required_fields_and_the_defaults` and `test_arguments_past_their_bounds_are_refused`.
- R3: `test_the_fake_server_returns_a_result_each_proposal_accepts`.
- R4: `test_eleven_proposal_actions_after_the_reads`, and search 1.
- R5: the four given files equal the spec, and the four-line diff.
- R6: `test_finance_proposal_steps.py`, plus the two coder integration tests. Probe line `40 random runs call each step only as the plan and step decisions allow`.
- R7: the scope status and the empty protected diff.
- R8: search 2, and the fake's invented results.
- R9: coverage of `domains/finance.py` at 100%.
