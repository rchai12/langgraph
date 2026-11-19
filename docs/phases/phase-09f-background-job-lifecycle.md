# Phase 9f: Background job lifecycle

## Corrections

**2026-11-18, correction 1 (a spec error, not the coder's).** R2 makes workers daemon threads, but the existing test `tests/unit/test_resumer.py::test_a_second_start_waits_and_the_thread_is_not_a_daemon` asserts that they are not. The spec missed it, so the phase could not pass. That file is now in the Scope, for exactly these two one-line edits and nothing else:

| Old line | New line |
|---|---|
| `def test_a_second_start_waits_and_the_thread_is_not_a_daemon(monkeypatch) -> None:` | `def test_a_second_start_waits_and_the_thread_is_a_daemon(monkeypatch) -> None:` |
| `        assert calls == [(RUN, False)]` | `        assert calls == [(RUN, True)]` |

The file's other three tests stay as they are. They already hold under this design: a kept failure, the fixed text, `the tool check failed`, and a restart that clears the failure. N stays `1163` and the given count stays 18. Nothing was built before the stop, so every Acceptance row and search is live again. Run `scripts/accept.py --phase 9f` again; `progress.py` replaces the stopped entry.

## Goal

The approvals page's background resumer (`conductor.web.jobs.Resumer`) stops growing with every resume, and stopping `conductor web` no longer waits for a model call to time out. After this phase a finished resume that succeeded leaves nothing behind. A failed one leaves its message, and at most the newest 100 messages are kept. A running resume is never dropped. On shutdown the server waits at most 10 seconds for running resumes, then exits and names the runs that were still running. This implements audit finding 1's resumer part; 9e removed its graph-services part.

Decided with the owner (2026-11-18):
- **Keep failures only, capped at the newest 100.** A success is forgotten as soon as it finishes: the run page reads the outcome from the checkpoint. A burst of successes therefore cannot push out a failure message nobody has seen. 9h later makes failures durable.
- **Shutdown waits up to 10 seconds, then exits.** Workers are daemon threads. The wait lets a nearly finished resume complete. A run still running at the deadline stays at its last checkpoint, and `conductor resume` continues it once its lease (at most 600 seconds) expires. The wait is a constant, not a new setting.

Decided by the architect, within those answers:
- `close()` waits once for all running jobs together, using a threading wait's own timeout. It never waits once per job, and `jobs.py` never reads the clock (no `time` module).
- After `close()`, `start()` runs nothing and records `the server is stopping` as that run's failure. That failure counts against the same bound, so the page shows why nothing happened.
- `conductor web` closes the resumer in a `finally` around `uvicorn.run`. uvicorn re-raises Ctrl-C as `KeyboardInterrupt` after its graceful shutdown (see Facts), so a close placed after the call would never run. The names of unfinished runs go to stderr, as constant text plus the run id. The command owns the resumer and passes it to `create_app`. `create_app` does not change.
- The unexpected-failure text stays `the resume failed`. 9h replaces it with sanitized durable evidence.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/web/jobs.py` (all 51 lines: `Resumer.start`, `running`, `error`, `join`, `_run`).
- `src/conductor/cli/main.py`, `web()` (from line 441), and its imports.
- `tests/e2e/test_web_runs.py` (`test_a_decision_resumes_the_run_in_the_background`, `test_a_resume_that_fails_is_recorded_not_raised`) and `tests/e2e/test_cli_web.py`. They use the real `Resumer` and the `web` command and must keep passing unchanged.

## Starting state

Phase 9e is built and verified, and the workflow port is committed: N is `1163`. **Sections: cli, core.** `Resumer` keeps every thread in `_threads` and every outcome in `_errors`. Its workers are non-daemon threads. It has no `close` or `retained`, and `conductor web` never closes it. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/web/jobs.py` | the four constants, `retained`, `close`, daemon workers, retention (Part 1) |
| `src/conductor/cli/main.py` | `web()` owns, passes and closes one `Resumer` (Part 2) |
| `tests/unit/test_resumer.py` | only the two edits in Corrections, correction 1 |
| `tests/unit/test_web_jobs_lifecycle_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- Durable failure records, a resume control on the run page, a changed failure text, or logging an exception (9h).
- A shutdown-timeout or retention setting, or any change to `config.py`, doctor output or `docs/configuration.md`.
- Cancelling, interrupting or signalling a running resume, and making an interrupted step idempotent.
- A FastAPI lifespan, or any change to `web/app.py`, its templates or `create_app`'s signature.
- Releasing a lease on shutdown, or any change to `runtime.py` or `store.py`.
- Any change to a given file, `AGENTS.md` or the design docs, or to an existing test beyond Corrections, correction 1.

## Dependencies

None new.

## Design

### Part 1: `conductor.web.jobs`

New module constants, with exactly these values:

```python
MAX_FAILURES = 100
SHUTDOWN_SECONDS = 10.0
STOPPING_MESSAGE = "the server is stopping"
UNFINISHED_MESSAGE = "the resume did not finish before shutdown"
```

`Resumer(settings)` keeps its public methods and their signatures, and adds two:

| Method | Behaviour |
|---|---|
| `start(run_id) -> None` | After `close()`: starts nothing and records `STOPPING_MESSAGE` as the run's failure. If the run's job is held: does nothing (active-run exclusion, unchanged). Otherwise it forgets the run's previous failure and starts one **daemon** worker thread for it. |
| `running(run_id) -> bool` | `True` from `start` until its worker has recorded the outcome; then `False`. |
| `error(run_id) -> str \| None` | The run's kept failure message, else `None`. |
| `join(run_id, timeout=None) -> None` | Unchanged: waits for the run's held worker, if any. |
| `retained() -> tuple[int, int]` | `(jobs held, failure messages kept)`. A job is held exactly while `running` is `True`. |
| `close(timeout: float = SHUTDOWN_SECONDS) -> tuple[str, ...]` | Refuses later starts, then waits until no job is held or `timeout` seconds pass, **in one wait for all jobs**. Returns the run ids still held, sorted. It returns at once when nothing is held. |

The worker, when its resume ends:
- on success: drops the job and keeps nothing;
- on `RunError` or `ToolCheckFailed`: keeps `str(error)` (unchanged);
- on any other exception: keeps `"the resume failed"` (unchanged, no exception text).

A failure is kept as the run's newest one: a run that fails again moves to the newest place. While more than `MAX_FAILURES` messages are kept, the oldest is dropped. Held jobs are never dropped and do not count against the bound. A worker still running at `close`'s deadline records its outcome when it ends, as above. All bookkeeping happens under the existing lock.

### Part 2: `conductor web`

`web()` keeps its port check and its `Serving on ...` line. Only after the port check passes does it make one `Resumer(settings)` and pass it as `create_app(settings, resumer=resumer)`. It calls `uvicorn.run` with the same options as today. In a `finally` around that call it runs `resumer.close()`, with no arguments, and for each returned id prints `f"{UNFINISHED_MESSAGE}: run {run_id}"` to stderr (`typer.echo(..., err=True)`). The import is `from conductor.web.jobs import UNFINISHED_MESSAGE, Resumer`. The given tests replace `main.Resumer` and `main.create_app`, so both must be looked up by those names when `web()` runs.

## Facts

Checked on 2026-11-18 in the installed packages, with small offline synthetic spikes:
- uvicorn 0.54.0, `uvicorn/server.py` lines 332 to 349: `capture_signals` records SIGINT and SIGTERM during serving, and after the graceful shutdown it re-raises them with `signal.raise_signal`. Ctrl-C therefore surfaces as `KeyboardInterrupt` out of `uvicorn.run`, and SIGTERM's default action ends the process at once.
- typer with click 8.5.1, through `CliRunner`: when a command raises `KeyboardInterrupt`, the result is exit code 130, and stderr holds only what the command printed with `err=True`.
- The interpreter does not wait for daemon threads at exit; it does join non-daemon threads, which is why a 300-second model call held the server process open.
- `threading.Condition.wait_for(predicate, timeout)` waits at most `timeout` in total. `Thread.join(timeout)` called once per thread adds the timeouts up.
- `store.LEASE_SECONDS` is 600. A run whose worker ends with the process keeps its lease until it expires; then `conductor resume` continues it from its last checkpoint (Phase 5d).

## Requirements

### Part 1: the resumer

- **R1.** Constants `MAX_FAILURES`, `SHUTDOWN_SECONDS`, `STOPPING_MESSAGE`, `UNFINISHED_MESSAGE` have exactly the values in Design. `close`'s `timeout` defaults to `SHUTDOWN_SECONDS`.
- **R2.** Each worker is a daemon thread.
- **R3.** A resume that succeeds leaves nothing held or kept: after any number of them, `retained()` is `(0, 0)`.
- **R4.** A failure is kept: `RunError` and `ToolCheckFailed` by their text, any other exception as `the resume failed`.
- **R5.** At most `MAX_FAILURES` failure messages are kept. The oldest is dropped first, and a repeated failure counts as the newest.
- **R6.** `start` forgets the run's previous failure. A second `start` for a held run starts nothing.
- **R7.** A held job is never dropped, however many failures follow it.
- **R8.** `close(timeout)` waits once, at most `timeout` in total, for all held jobs, and returns the ids still held, sorted. It returns at once when none is held. A job still held at the deadline records its outcome when it ends.
- **R9.** After `close`, `start` runs nothing and keeps `STOPPING_MESSAGE` as the run's failure, under the same bound.

### Part 2: the command

- **R10.** `conductor web` makes one `Resumer` after the port check, passes it to `create_app`, and closes it with `close()` whether `uvicorn.run` returns or raises. It prints `the resume did not finish before shutdown: run <id>` to stderr, once per returned id, in order.

### Part 3: the rules

- **R11.** Only the Scope's paths change; given files stay byte-identical. `jobs.py` has no `time` import, no `print`, no new `noqa` or `pragma`.
- **R12.** `src/conductor/web/jobs.py` (critical) has 100% line and branch coverage.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, every given test fails or errors. With names-only stubs (the four constants, plus `retained` and `close` raising `NotImplementedError`), two pass: `test_the_limits_and_messages` only reads the constants, and `test_a_taken_port_starts_no_resumer` guards that no resumer is made before the port check, which already holds.

| File | What it is |
|---|---|
| `tests/unit/test_web_jobs_lifecycle.py` | R1 to R9 through a fake `runtime.open_runtime` and `runtime.resume` (14 tests from 13 functions) |
| `tests/e2e/test_cli_web_shutdown.py` | R10 with a fake `Resumer`, `create_app` and `uvicorn.run` (4 tests from 3 functions) |
| `docs/verification/probe-09f.py` | the probe, run by its path in Acceptance |

Given test count: **18**.

## Tests to write

In `tests/unit/test_web_jobs_lifecycle_more.py` (section `core`), with the given file's fake pattern:
- R4: a `ToolCheckFailed` raised by the fake resume is kept by its text, with a `ToolCheckFailed` built from synthetic problems.
- R8: a job held at `close(timeout=0.05)` that then fails is kept with its message, and `retained()` becomes `(0, 1)`.
- R9: a run that failed before `close` and is started after it keeps `the server is stopping`, not its old message.
- R12: any branch the given tests leave uncovered, tested for what it does.

## Rules for this phase

- Read the time only through `conductor.clock.now()`. `close` needs no clock: it uses a threading wait's timeout.
- Error messages are constant text plus ids. Never keep or print an unexpected exception's text.
- Tests touch no network and no real model; they replace `runtime.open_runtime` and `runtime.resume`. Each test releases every thread it holds.
- Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged, except the two lines in Corrections, correction 1.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9f` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1181 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/web/jobs.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_web_jobs_lifecycle.py tests/e2e/test_cli_web_shutdown.py --no-cov -q` | `18 passed` |
| `.venv/bin/python docs/verification/probe-09f.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_web_jobs_lifecycle.py tests/e2e/test_cli_web_shutdown.py docs/verification/probe-09f.py src/conductor/web/app.py src/conductor/web/templates src/conductor/runtime.py src/conductor/store.py src/conductor/config.py` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9f: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9f` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/web/jobs.py src/conductor/cli/main.py
git grep --untracked -n -E '(^|[^A-Za-z_.])time\.|import time([^A-Za-z_]|$)|from time import' -- src/conductor/web/jobs.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Background job lifecycle`, with `--tests-before 1163 --given 18`.
