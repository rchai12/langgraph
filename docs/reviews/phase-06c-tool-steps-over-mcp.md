# Review: Phase 6c

- Verdict: PASS
- Passed: 664
- Findings: 0
- Approved deviations: DemoRunner reads the echo text with args.model_dump()["text"] so the acceptance search stays empty. The returned text is unchanged.
- For the architect: Spots 2 and 6 printed DID NOT RAISE StepFailed, spot 3 printed StepFailed with no message, and spot 7 truncated both RunState values.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first core` ended with `All checks passed.` The tests step passed 664, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary. `critical coverage` passed.

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            81 passed    0 failed    0 skipped
  core          583 passed    0 failed    0 skipped
```

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

`.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/supervisor.py" --fail-under=100` exited 0 with `TOTAL` at 100% (419 statements, 74 branches). `.venv/bin/python -m pytest tests/unit/test_mcp_runner.py tests/integration/test_mcp_steps.py --no-cov` printed `17 passed`. `.venv/bin/python scripts/check_reports.py --phase 6c`, run before this report, printed `Reports OK.` The protected diff printed nothing. `git diff HEAD -- src/conductor/graph/supervisor.py` is `FAILURE_CODES`, `FailureCode`, `StepFailed.__init__` and `code`, and the detail with the code in `run_step`. All three searches printed nothing. `pgrep -f mcp_fake_server` printed nothing.

## Scope

`git status --short` lists the two source files, the four test files, `docs/progress.md`, and four paths the progress follow-up names as edits this phase did not make: the skill, the spec, the verification guide, and this review. Changed files is 11. Both given files equal the corrected spec fences, including `.escalation.model_dump_json()`.

## Requirements

- R1: `test_the_failure_codes` and `test_an_unknown_code_is_dropped_and_the_detail_names_a_real_one` (`StepFailed(code="nonsense")` stays `None`; details `(no_result)` and the 5c text).
- R2: `test_a_call_with_the_declared_server_and_the_arguments_as_json`, `test_a_read_step_runs_over_mcp`, and `test_each_action_calls_its_own_server_once`.
- R3: `test_each_failure_has_its_code` (6 cases), `test_a_tool_error_escalates_with_its_code`, `test_a_step_that_takes_too_long_escalates_as_timeout`, `test_a_server_that_stops_escalates_as_closed_and_retry_asks_again`, and `test_a_failure_carries_no_secret_and_no_cause`.
- R4: `test_fields_the_contract_does_not_name_are_dropped`, `test_a_result_over_256_kb_fails` (both cases), and `test_unknown_keys_only_give_nothing_and_the_graph_refuses_it`.
- R5: `test_the_domain_runner_sends_each_action_to_its_runner`, `test_without_the_demo_setting_demo_actions_do_not_run`, `test_demo_and_lab_echo_use_their_own_runners`, and `tests/integration/test_resume_stopped.py` in the section run.
- R6: `test_a_write_call_starts_the_server_only_after_step_approval`. `call_tool` appears only in the client and `McpRunner.run`. `open_runtime` installs `DomainRunner` under the lease.
- R7: searches 1 and 2 printed nothing.
- R8: the coverage gate, as above.

## Probe

```
ok   1000 tool outcomes map to results and codes as the rules say
ok   real runs end done or at the first failing step, with its code ({'done': 3, 'tool_error': 5})
FAILURES 0
```

The script was saved outside the repository, run from the repository root, and deleted. `pgrep -f mcp_fake_server` printed nothing afterwards.

## Spot checks

Each deciding test failed. The edits were reversed and both files matched their text from before the spots. `__pycache__` under `src`, `tests`, and `scripts` was removed before each pytest and again at the end.

| # | Printed failure |
|---|---|
| 1 | `assert 'step 1 lab.fail: the step failed' == 'step 1 lab.fail: the step failed (tool_error)'` |
| 2 | `Failed: DID NOT RAISE StepFailed` on `test_a_result_over_256_kb_fails[1-too_large]` |
| 3 | `conductor.graph.supervisor.StepFailed` on `test_a_result_over_256_kb_fails[0-None]` |
| 4 | the result dict included `total_cents` |
| 5 | `assert None == 'no_command'` |
| 6 | `Failed: DID NOT RAISE StepFailed` |
| 7 | `AssertionError` comparing two `RunState` values; pytest truncated both before the status |

## Progress

`## Phase 6c: tool steps over MCP (2026-11-09)` has `Tests: 641 -> 664 (given 17)`. The listed deviation is the `DemoRunner` read above, and the returned text is still `{"text": ...}`.
