# Review: Phase 5d

- Verdict: PASS
- Passed: 542
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first core` exited 0. The `tests` step reported `542 passed` in 20.55s. No skipped, xfailed, or warnings summary. `critical coverage` passed. Last lines:

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
  core          491 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            51 passed    0 failed    0 skipped
  core          491 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/*.py,*/conductor/config.py" --fail-under=100` exited 0. `TOTAL` is `100%` (418 statements, 68 branches).

`.venv/bin/python -m pytest tests/integration/test_runtime.py --no-cov -W error` printed `12 passed`.

`.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph-checkpoint-sqlite'))"` printed `3.1.3`.

`.venv/bin/python scripts/check_reports.py --phase 5d`, before this report, printed `Reports OK.`

The protected `git diff --stat` printed nothing. `git diff HEAD -- pyproject.toml` adds one line, `"langgraph-checkpoint-sqlite>=3.1.2,<3.2",`, after `langgraph`. `git diff HEAD -- src/conductor/graph/supervisor.py` adds `stopped` to `RunStatus`, `RunState.stopped_at`, the `snapshot.next` return in `run_state`, and `resume_run`'s first check. Searches 1 to 3 printed nothing. `git status --short` lists 9 lines, all in the Scope table. `tests/integration/test_runtime.py` is byte-equal to the spec fence. `docs/testing.md` and `scripts/critical_modules.txt` add `runtime.py` after `graph/supervisor.py`.

## Progress

`## Phase 5d: the runtime (2026-11-09)` with `Tests: 523 -> 542 (given 12)`. The 542 is 523 plus the 12 given tests plus 7 coder tests. Deviations: None. Follow-ups: None. Changed files: 9, the count of `git status --short` lines before this report.

## Requirements

- R1: `test_the_settings`, `test_the_demo_setting_is_true_or_false`. `Settings.demo` defaults to `"false"` after `decided_by`. `demo_on` is `demo == "true"`. `checkpoints_path` is `data_dir / "checkpoints.db"`. A value other than `true` or `false` appends `CONDUCTOR_DEMO: must be true or false` after the `decided_by` problem. The installed package is `3.1.3`.
- R2: `test_a_run_survives_a_restart_in_private_files`, `test_private_files_are_kept_and_the_connection_closes`. `open_runtime` creates the data folder at `0700` when it is missing, creates `checkpoints.db` at `0600` with `os.open` when it is missing, then `sqlite3.connect(..., check_same_thread=False)` and `SqliteSaver`. It then opens the store and the event log, builds the registry and the runner, takes `ids.new_id()` as the holder, builds the leased graph, yields, and closes the connection in `finally`. An existing database keeps its inode. A query after the block, including when the block raises, raises `sqlite3.ProgrammingError`. The probe's file-mode line passed on both runs.
- R3: `test_without_the_demo_setting_no_domain_is_registered`, `test_the_demo_runner`, `test_domains_and_the_runner_follow_the_setting`. The registry is `domains.DOMAINS` read at open time, plus `demo.DOMAIN` at the end only when `demo_on`. `DemoRunner` returns the echo text, a new note id, and `DEMO_SUMMARY`. `NoRunner` raises `StepFailed`. With no model argument, a classifier request reaches the closed loopback port and escalates as `model_unavailable`. The probe's registry line passed on both runs.
- R4: `test_a_busy_run_is_refused`, `test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step`, `test_a_run_that_raises_releases_its_lease_and_stops`, `test_a_blank_request_and_an_unknown_run_leave_no_lease`. `ask` and `resume` acquire the runtime's holder for the call and release it on every way out, including `LeaseLost`. `LeaseHeld` on `resume` becomes `run {id} is busy` before `resume_run`. The probe's race line passed on both runs: one `done`, the rest `is busy` or `is not waiting`, one `TOOL_RESULT`.
- R5: `test_a_lost_lease_stops_the_run_before_its_step_runs`, the three renewals in the lease test, `test_a_lease_taken_during_the_step_stops_the_answer`. `_LeasedModel.chat` and `_LeasedRunner.run` call `store.renew` first. `model_info` is forwarded. A failed renewal becomes `run {id} lost its lease` and leaves the run stopped at that node. The echo run records the plan chat, the step, and the answer chat.
- R6: `test_a_run_survives_a_restart_in_private_files`, `test_state_answers_while_another_holder_has_the_lease`. `state` calls `run_state` with no lease. A later runtime, including one in another process, sees the same waiting state. The probe's three-process line passed on both runs, with three different holders.
- R7: `test_a_run_that_raises_releases_its_lease_and_stops`, `test_a_classifier_error_stops_at_route`. With no interrupt and a next node, `run_state` returns `stopped` and `stopped_at`. `resume_run` refuses that state first: `run {id} stopped at {node} and cannot be resumed`. The probe's stop line passed for `plan` and `answer` on both runs.
- R8: searches 1 to 3. `runtime.py` reads settings only from the `Settings` argument.
- R9: `test_a_busy_run_is_refused`, `test_a_lost_lease_stops_the_run_before_its_step_runs`, `test_a_run_that_raises_releases_its_lease_and_stops`, `test_run_errors_name_the_run_and_the_node`, `test_a_blank_request_and_an_unknown_run_leave_no_lease`. The `RunError` texts are `run {id} is busy`, `run {id} lost its lease`, `run {id} stopped at {node} and cannot be resumed`, and the existing `no run {id}`.
- R10: the coverage gate and `critical coverage`. `runtime.py` and `graph/supervisor.py` are both at 100%.

## Probe

Run twice. Every line started with `ok` and both ended with `FAILURES 0`.

```
ok   a run waits, survives two restarts, and finishes in a third process
ok   every file under the data folder is 0600 and the folder 0700 ([...jsonl, checkpoints.db, conductor.db])
ok   of six resumes at once, one runs the step and the rest are refused (['done', 'is busy', 'is busy', 'is not waiting', 'is not waiting', 'is not waiting'])
ok   a run that raises stops where it was, frees its lease, and cannot be resumed
ok   without CONDUCTOR_DEMO the registry is exactly DOMAINS
FAILURES 0
```

The second run printed the same five lines, with a different event-file name.

## Spot checks

Each change failed its deciding test. Reverse edits left `runtime.py` and `supervisor.py` equal to the text from before the spots. `__pycache__` was removed afterwards.

| # | Result |
|---|---|
| 1 | failed: modes `(0o700, 0o644)` where the test requires `(0o700, 0o600)`. |
| 2 | failed with `LeaseHeld`. |
| 3 | failed: `RunError` was not raised. |
| 4 | failed: `TOOL_RESULT` was in the log. |
| 5 | failed: the renewal list was not the three `(run_id, holder)` pairs. |
| 6 | failed: `('demo',)` where the test requires `()`. |
| 7 | failed with `KeyError: 'status'` after both stopped checks were removed. |
| 8 | failed: `ProgrammingError` was not raised. |

## Out of scope

No command, `AsyncSqliteSaver`, WAL setting, migration, or checkpoint deletion. The protected paths are unchanged. The supervisor diff is only the stopped status.
