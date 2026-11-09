# Review: Phase 5c

- Verdict: PASS
- Passed: 523
- Findings: 0
- Approved deviations: None
- For the architect: spots 2, 6, and 8 still pass (resume_run rejects before wait_approval; tracing_off alone keeps tracing disabled; eight read steps finish under LangGraph 1.2.20's default recursion limit of 10007); spots 1, 5, and 7 fail with a different symptom

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first core` exited 0. The `tests` step reported `523 passed` in 18.61s. No skipped, xfailed, or warnings summary. `critical coverage` passed. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

Sections, each with 0 failed. The first section run, then the full run:

```
Sections:
  core          472 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            51 passed    0 failed    0 skipped
  core          472 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/graph/*.py" --fail-under=100` exited 0. `TOTAL` is `100%` (250 statements, 40 branches).

`.venv/bin/python -m pytest tests/integration/test_supervisor.py --no-cov -W error` printed `14 passed`.

`.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph'))"` printed `1.2.20`.

`.venv/bin/python scripts/check_reports.py --phase 5c`, before this report, printed `Reports OK.`

The protected `git diff --stat` printed nothing. `git diff HEAD -- pyproject.toml` adds one line, `"langgraph>=1.2.20,<1.3",`, after `typer`. Searches 1 to 3 printed nothing. `git status --short` lists 7 lines, all in the Scope table. `tests/integration/test_supervisor.py` is byte-equal to the spec fence. `docs/testing.md` and `scripts/critical_modules.txt` add `graph/supervisor.py` after `planning/answer.py`.

## Progress

`## Phase 5c: the supervisor graph (2026-11-09)` with `Tests: 500 -> 523 (given 14)`. The 523 is 500 plus the 14 given tests plus 9 coder tests. Deviations: None. Follow-ups: None. Changed files: 7, the count of `git status --short` lines before this report.

## Requirements

- R1: `test_tracing_is_off_inside_a_run`, `test_tracing_off_sets_each_variable_false`, `test_importing_the_package_turns_tracing_off`. `conductor.graph` sets the four variables to `"false"` at import, before `supervisor.py` imports `langgraph`. `_invoke` calls `tracing_off()` and runs `graph.invoke` inside `tracing_context(enabled=False)`. The probe's tracing line passed.
- R2: `test_the_nodes`, `test_the_checkpoint_holds_only_json`. `build_graph` adds the ten names in `NODES`, `START` to `route`, and `finish` to `END`. The other edges are `Command(goto=...)`, which the guide allows. State fields are JSON values; contracts are rebuilt with `from_json`. The probe's JSON line passed.
- R3: `test_a_read_only_request_runs_to_its_answer`, `test_an_escalation_waits_and_retry_runs_the_node_again`, `test_cancel_ends_the_run`, `test_retry_runs_a_plan_and_an_answer_again`. `route`, `plan`, and `answer` call `route_request`, `plan_request`, and `answer_request`. An `Escalation` is stored with `retry_node` `route`, `plan`, or `answer`.
- R4: `test_a_write_step_waits_for_the_plan_and_then_for_itself`, `test_a_delegate_step_asks_and_a_mixed_plan_runs_the_read_first`. Requests come from `policy.plan_request` and `policy.step_request` (attempt defaults to 1), then `_queue` stores, logs, and sets `pending`. A read step, and a plan of only reads, get `None` and add nothing.
- R5: `test_resume_needs_a_recorded_decision`, `test_resuming_twice_does_not_duplicate_an_approval`. `wait_approval` loads the pending request and calls `interrupt` before any store write, event, id, or time. After the interrupt it reads `store.approval(id).decision` and calls `policy.apply_decision`. `wait_escalation` interrupts, then reads `store.escalation(id).answer`. The probe's one-pending line passed.
- R6: `test_an_edit_runs_the_edited_arguments`, `test_a_result_that_does_not_fit_escalates`, `test_eight_read_steps_run_in_one_go`, `test_a_list_result_escalates_and_a_runner_error_passes`. A step with `args` set runs those approved arguments. `args` `None` uses the checked step. `StepFailed` and a result `ValidationError` become `tool_error`. `RuntimeError` propagates and the checkpoint stays at `run_step`. The probe's approval line passed.
- R7: `test_a_failed_step_escalates_and_retry_asks_for_its_approval_again`, `test_retry_runs_a_plan_and_an_answer_again`. A step failure retries at `ask_step` with the same `step`. `cancel` sets `status` `cancelled` and goes to `finish`.
- R8: `test_runs_are_checked`, `test_a_rejection_ends_the_run_with_its_note`, `test_run_state_names_an_escalation_and_a_cancelled_run_is_not_waiting`. Checks and messages match the Design table. The thread id is the run id. `RECURSION_LIMIT` is 100 on every invoke.
- R9: payload checks in `test_a_read_only_request_runs_to_its_answer`, `test_a_write_step_waits_for_the_plan_and_then_for_itself`, `test_an_escalation_waits_and_retry_runs_the_node_again`, and `test_a_rejected_step_logs_the_request_the_error_and_the_finish`. `finish` logs `RUN_FINISHED` with the final status. The probe's once-per-run line passed (`done` 207, `rejected` 70, `cancelled` 23).
- R10: searches 1 to 3. No settings, `decide(`, Ollama, `clock`, or `ids` in `conductor.graph`.
- R11: `test_a_secret_stays_out_of_every_escalation`. `RunError` texts are the Design's messages. Step details are `step {number} {domain}.{name}: the step failed` and `step {number} {domain}.{name}: the result does not fit the action`. `StepFailed`'s text is not copied.
- R12: the coverage gate and `critical coverage`.

## Probe

Every line started with `ok` and the last line was `FAILURES 0`.

```
ok   every run ends done, rejected, or cancelled, once ({'done': 207, 'rejected': 70, 'cancelled': 23})
ok   no propose, write, or implement step ran without its own decided approval
ok   the checkpoint holds only JSON at every pause
ok   at most one approval is pending at a time
ok   with tracing asked for by the environment, a run opens no connection
FAILURES 0
```

## Spot checks

Each change was restored. `supervisor.py` matched the text from before the spots. `__pycache__` was removed afterwards.

| # | Result |
|---|---|
| 1 | failed. Pending stages were `['plan', 'step']` at the first wait, before a resume. |
| 2 | passed. `resume_run` raises `is not decided yet` before `wait_approval` runs. |
| 3 | failed. The runner received the checked note (`tags=()`), where the intact code runs `Bread` and `tags=('home',)`. |
| 4 | failed. After retry, `approval_id` was `None`, so there was no new approval. |
| 5 | failed with `ScriptError: no scripted reply left for answer`, and pytest reported 1 warning. Status was not `done`. |
| 6 | passed. `tracing_off()` still runs before `invoke`, and the runner recorded `[False]`. |
| 7 | failed with `KeyError: 'request'` in `route`. The resume started a thread that had no request. |
| 8 | passed. LangGraph 1.2.20's `DEFAULT_RECURSION_LIMIT` is 10007, so eight read steps still finish. |
| 9 | failed with `TypeError: Object of type Plan is not JSON serializable`. |

## Out of scope

No `checkpoints.db`, `SqliteSaver`, lease, `conductor ask`, `conductor resume`, MCP call, `NODE_STARTED`, `NODE_FINISHED`, streaming, or async node. The protected paths are unchanged. `tests/integration/` holds the given test and `test_supervisor_more.py` only.
