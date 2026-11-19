# Verify Phase 9f: Background job lifecycle

Spec: `docs/phases/phase-09f-background-job-lifecycle.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09f-background-job-lifecycle.md`.

## First: establish that the coder ran

- No `## Phase 9f: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09f-background-job-lifecycle.md docs/verification/phase-09f-background-job-lifecycle.md tests/unit/test_web_jobs_lifecycle.py tests/e2e/test_cli_web_shutdown.py docs/verification/probe-09f.py` must succeed: the gates judge against a committed baseline.

Correction 1 (2026-11-18): `tests/unit/test_resumer.py` is in the Scope for two lines only. `git diff HEAD -- tests/unit/test_resumer.py` must show exactly the rename to `test_a_second_start_waits_and_the_thread_is_a_daemon` and `assert calls == [(RUN, True)]`, and no other change. Any other change to that file is a finding against R11. The stopped entry from the first attempt is replaced by the rerun's; judge only the rerun's entry.

The coder:
- changed `src/conductor/web/jobs.py`: four constants, daemon workers, failure-only retention capped at 100, `retained()`, `close(timeout)`;
- changed `web()` in `src/conductor/cli/main.py` to own, pass and close one `Resumer` and name unfinished runs on stderr;
- edited two lines of `tests/unit/test_resumer.py` (correction 1);
- added `tests/unit/test_web_jobs_lifecycle_more.py` and one progress entry.

## 1. Gates

N is `1163`. Given count: 18. `.venv/bin/python scripts/accept.py --phase 9f --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1181 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/web/jobs.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_web_jobs_lifecycle.py tests/e2e/test_cli_web_shutdown.py --no-cov -q` | `18 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09f.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_web_jobs_lifecycle.py tests/e2e/test_cli_web_shutdown.py docs/verification/probe-09f.py src/conductor/web/app.py src/conductor/web/templates src/conductor/runtime.py src/conductor/store.py src/conductor/config.py` | no output |
| G6 | `git status --short --untracked-files=all` | only the Scope paths |
| G7 | `grep -c '^## Phase 9f: ' docs/progress.md` | `1` |
| G8 | `.venv/bin/python scripts/check_reports.py --phase 9f` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_limits_and_messages` | passes |
| R2 | `test_a_worker_is_a_daemon_thread`, `tests/unit/test_resumer.py::test_a_second_start_waits_and_the_thread_is_a_daemon`; read `start` | pass; the thread is made with `daemon=True` |
| R3 | `test_finished_resumes_are_forgotten`; probe check 1 | pass; `ok` |
| R4 | `test_a_failure_is_kept` (both cases); the coder's `ToolCheckFailed` test | pass; `_run` keeps no text of an unexpected exception |
| R5 | `test_failures_are_capped_oldest_first`, `test_a_repeated_failure_is_the_newest`; probe checks 1 and 5 | pass; `ok` |
| R6 | `test_starting_again_clears_the_last_failure`, `test_an_active_run_is_not_started_twice` | pass |
| R7 | `test_a_running_job_is_never_dropped` | passes |
| R8 | `test_close_waits_for_a_job_that_finishes`, `test_close_names_the_runs_still_running`, `test_close_with_nothing_running_returns_at_once`; probe checks 2 and 3 | pass; `ok`; read `close`: one wait with the given timeout, no loop of joins |
| R9 | `test_a_start_after_close_is_refused`; probe check 4; the coder's old-failure test | pass; `ok` |
| R10 | `test_the_page_gets_one_resumer_that_is_closed`, `test_runs_left_running_are_named_on_the_way_out` (both cases), `test_a_taken_port_starts_no_resumer`; read `web()` | pass; `close()` sits in a `finally` around `uvicorn.run` |
| R11 | G5, G6, the searches | as given |
| R12 | G2 | as given |

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09f.py` (G4). It checks:
- 600 random successes and failures over 150 runs against its own capped oldest-first table (the cap is reached and drops at least once), with `retained()` at the end;
- one `close(timeout=1.0)` over four held jobs takes from 0.9 to 2.5 seconds and returns all four ids sorted (a join per job would take about 4 seconds);
- a job held past `close`'s deadline records its failure afterwards;
- starts refused after `close` replace an old failure and count against the bound;
- 30 failing runs started at once by 30 threads are all kept.

A stop at its own `assert` lines, before its first check prints, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/web/jobs.py src/conductor/cli/main.py
git grep --untracked -n -E '(^|[^A-Za-z_.])time\.|import time([^A-Za-z_]|$)|from time import' -- src/conductor/web/jobs.py
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09f`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09f`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | make the worker non-daemon (`start`) | `tests/unit/test_web_jobs_lifecycle.py::test_a_worker_is_a_daemon_thread` | `[True]` | `[False]` |
| S2 | let one more failure than `MAX_FAILURES` stay (the pruning condition) | `tests/unit/test_web_jobs_lifecycle.py::test_failures_are_capped_oldest_first` | `(0, 100)` | `(0, 101)` |
| S3 | over the bound, drop the newest failure instead of the oldest (the pruning) | `tests/unit/test_web_jobs_lifecycle.py::test_failures_are_capped_oldest_first` | `[True, False, False]` | `[False, False, True]` |
| S4 | do not forget the run's previous failure on a new start (`start`) | `tests/unit/test_web_jobs_lifecycle.py::test_starting_again_clears_the_last_failure` | `(True, None)` | `(True, 'run 00000000000000000000000000000001 is busy')` |
| S5 | drop the held-job check, so a held run starts again (`start`) | `tests/unit/test_web_jobs_lifecycle.py::test_an_active_run_is_not_started_twice` | `['…01']` | `['…01', '…01']` |
| S6 | return the held ids unsorted (`close`) | `tests/unit/test_web_jobs_lifecycle.py::test_close_names_the_runs_still_running` | `('…01', '…02')` | `('…02', '…01')` |
| S7 | do not mark the resumer closed (`close`) | `tests/unit/test_web_jobs_lifecycle.py::test_a_start_after_close_is_refused` | `[]` | `['…01']` |
| S8 | wait with timeout 0 instead of `timeout` (`close`) | `tests/unit/test_web_jobs_lifecycle.py::test_close_waits_for_a_job_that_finishes` | `()` | `('…01',)` |
| S9 | close only after `uvicorn.run` returns, not in a `finally` (`web`) | `tests/e2e/test_cli_web_shutdown.py::test_runs_left_running_are_named_on_the_way_out[True-130]` | the two stderr lines | `''` |
| S10 | make the `Resumer` before the port check (`web`) | `tests/e2e/test_cli_web_shutdown.py::test_a_taken_port_starts_no_resumer` | `[]` | one `FakeResumer` |

Notes for tracing. S2 and S3 share a deciding test: S2 fails at its `retained()` line, S3 at the next one, since 101 failures leave 100 kept either way. A repeated failure's place (`test_a_repeated_failure_is_the_newest`) has no row: `start` forgets the old failure before the new one is recorded, so no single change in the recording reaches it; probe check 4 reaches the refused-start path. S5 and S7 race a worker thread against the test's first assertion: broken, S5 shows the calls `['…01', '…01']` at the first or the last assertion, and S7 shows `['…01']` or, if the worker has not called yet, `(…, None)` at the next line. Either is the Broken value. S6: the test holds run 2 before run 1, so insertion order is `('…02', '…01')`. If the coder's structure yields sorted order for another reason, S6 passing is a note, not a finding. S9: the fake `uvicorn.run` raises `KeyboardInterrupt`, so code after the call never runs.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.
- Any lock-guarded structure for held jobs and kept failures (dicts, an `OrderedDict`, a `deque` with a dict) that gives the specified order and bound.
- `close` waiting through a `threading.Condition`, an `Event`, or a join over a deadline the threading wait computes itself, as long as it is one bound in total and `jobs.py` reads no clock.
- A held job removed by its worker, or counted through `is_alive()`, as long as `running` and `retained()` agree.
- A second `close()` that waits again, or returns at once.

## 7. Out of scope

Each must be absent:
- durable failure records, a resume control on the page, a changed `the resume failed` text, or logging an exception;
- a shutdown or retention setting, and any change to `config.py`, doctor output or `docs/configuration.md`;
- cancelling or signalling a running resume;
- a FastAPI lifespan, or any change to `web/app.py`, its templates or `create_app`'s signature;
- releasing a lease on shutdown, or any change to `runtime.py` or `store.py`;
- any change to a given file, `AGENTS.md` or the design docs, or to an existing test beyond correction 1.

## 8. Verdict

Write `docs/reviews/phase-09f-background-job-lifecycle.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9f`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9f` must print `Reports OK.`
