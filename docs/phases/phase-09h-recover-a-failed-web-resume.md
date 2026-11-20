# Phase 9h: Recover a failed web resume

## Corrections

**2026-11-19, correction 1 (a given-test error, not the coder's).** `test_a_post_that_cannot_start_only_redirects[undecided]` read `pending.decision`. `Store.pending()` returns `ApprovalRequest` records, and they have no `decision`, so the test could not pass on any implementation. The coder stopped on it, correctly. Line 176 of `tests/e2e/test_web_resume.py` now reads the stored approval instead: `assert Store(get_settings().db_path).approval(pending.approval_id).decision is None`. The line before it, `[pending] = Store(get_settings().db_path).pending()`, is unchanged and still fails if the route records a decision. With this line, all 43 given tests pass on the committed implementation (2f72d34). No requirement, code, probe, other given test or count changes: N stays `1222` and the given count stays 43.

Live again: every Acceptance row. Coverage and the full check never completed, so run them all. The implementation is committed, so continue from it: change nothing unless an Acceptance row fails, then rewrite your 9h progress entry with `scripts/progress.py` (it replaces the entry), removing the `Stopped:` item. `git status` then lists only the paths you change in this pass.

## Goal

When a resume started from the approvals page fails, the owner can see that it failed and start it again from the page. Today the failure lives only in the server's memory, so a restart loses it, and the page has no way to resume a run whose decision is already recorded. After this phase `runtime.resume` writes one sanitized `error` event to the run's event log for an unexpected failure, the run page shows that failure after a restart, and the page offers a protected Resume button whenever the run can be resumed and no resume is running. The button reuses the recorded decision; it never records one. This implements audit findings 3 (a failed page resume cannot be recovered) and 1 (failure evidence that cleanup can erase).

Decided with the owner (2026-11-19):
- **The evidence goes in the run's event log.** `runtime.resume` appends it while it still holds the run's lease, so it covers a resume from the terminal and from the page alike. A failure before the lease is taken (the tool check, a busy run) is not written; the page's in-memory message still covers it.
- **The evidence is a fixed code plus the exception's class name**, never its text: `{"error": "resume_failed", "type": "RuntimeError"}`.
- **The Resume button shows whenever the run is resumable and no resume is running**, not only after a failure.
- **A POST for a run that is not resumable, or already busy, redirects** with 303 to `/runs/<id>` and starts nothing.

Decided by the architect, within those answers:
- Only an `Exception` that is neither a `RunError` nor a `LeaseLost` is recorded. A `RunError` is a refusal or a state problem whose text the page already shows; `LeaseLost` means the lease is gone, so nothing may be written; a `BaseException` such as `KeyboardInterrupt` is not a failure of the run.
- If the record cannot be written, the original exception still propagates and the lease is still released. The write error is dropped.
- One rule decides whether a resume can start: `can_resume` in `graph/supervisor.py`, the same table `resume_run` applies. The page and the POST both use it, so the button and the POST never disagree.
- The page prefers the in-memory message from the resumer, which 9f pins. The record is a fallback: when the resumer keeps nothing, or keeps only the fixed `the resume failed`, and the log's last event is a record, the page shows `the resume failed (<Type>)`. A record followed by any other event is history, not the current state.
- `web/jobs.py` does not change: its text `the resume failed` is pinned by `tests/unit/test_resumer.py`, `tests/unit/test_web_jobs_lifecycle.py` and `probe-09f.py`.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/runtime.py`: `resume` (line 215) and `_call` (line 265).
- `src/conductor/graph/supervisor.py`: `RESUMABLE_STOPS` (line 33) and `resume_run` (line 122).
- `src/conductor/web/app.py`: `_with_store`, `_refused`, the `run` route (line 324) and `_post_escalation`; `src/conductor/web/templates/run.html`.
- `src/conductor/events.py`: `EventLog.read`, `EventLogCorrupt`, `RunNotFound`.
- `tests/e2e/test_web_run_status.py` (line 40) and `tests/e2e/test_web_run_status_cases.py` (line 84): the run page must never open the runtime, resume a run or record a decision. They stay unchanged and must pass.

## Starting state

Phase 9g is built and verified, and everything is committed: N is `1222`. **Sections: cli, core.** `runtime.resume` writes nothing when the graph call raises; the run page shows only `Resumer.error(run_id)`, which a restart loses; there is no `RESUME_FAILED`, no `can_resume` and no `/runs/{run_id}/resume` route. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/runtime.py` | `RESUME_FAILED` and the record in `resume` (Part 1) |
| `src/conductor/graph/supervisor.py` | `can_resume` (Part 2) |
| `src/conductor/web/app.py` | `resumable` and the recorded failure on the run page; the `POST /runs/{run_id}/resume` route (Part 3) |
| `src/conductor/web/templates/run.html` | the Resume form (Part 3) |
| `tests/integration/test_resume_evidence_more.py` | new: the coder's runtime tests |
| `tests/e2e/test_web_resume_more.py` | new: the coder's page tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Any change to `src/conductor/web/jobs.py`, its messages, its retention or its shutdown.
- A record from `ask`, from a failure before the lease is taken, or for a `RunError`.
- Exception text, a traceback or `repr` of an exception anywhere: in an event, a page or a log line.
- Sharing the approval and escalation record-and-resume plumbing (`_record_approval`, `_record_escalation`): that is 9n.
- Recording, re-recording or changing a decision or an answer from the Resume route.
- A setting, or any change to `config.py`, `events.py`, `store.py` or `decisions.py`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: `conductor.runtime`

```python
RESUME_FAILED = "resume_failed"
```

`resume(runtime, run_id)` keeps its signature, its tool check and its `run {run_id} is busy` refusal. While the call to `resume_run` runs, and before `_call` releases the lease, an exception from that call is handled like this:

| Raised by the call | Recorded | Then |
|---|---|---|
| an `Exception` that is not a `RunError` and not a `LeaseLost` | one event | the same exception object propagates |
| a `RunError` (also `RunStateUnavailable` and every refusal) | nothing | unchanged |
| a `LeaseLost` | nothing | unchanged: `_call` turns it into `RunError("run {run_id} lost its lease")` |
| a `BaseException` that is not an `Exception` | nothing | unchanged |

The event is exactly:

```python
runtime.log.append(
    run_id,
    EventKind.ERROR,
    payload={"error": RESUME_FAILED, "type": type(error).__name__},
)
```

with `node` left as `None`. When that `append` itself raises an `Exception`, it is dropped: the original exception propagates and the lease is released. `ask` does not change and never writes a record.

### Part 2: `conductor.graph.supervisor`

```python
def can_resume(state: RunState, store: Store) -> bool: ...
```

| `state` | Result | Lookup |
|---|---|---|
| `status == "stopped"` | `stopped_at in RESUMABLE_STOPS` | none |
| `status == "waiting"` with an `approval_id` | `store.approval(approval_id).decision is not None` | one |
| `status == "waiting"` with no `approval_id` | `store.escalation(escalation_id).answer is not None` | one |
| any other status | `False` | none |

A `NotFound` from the lookup gives `False`. A `StoreError` propagates. `can_resume` is `True` exactly when `resume_run` would call the graph instead of raising `RunError`; `resume_run` keeps its messages and may call `can_resume` or not.

### Part 3: the run page and the Resume route (`conductor.web.app`)

**`GET /runs/{run_id}`** keeps every check and message it has. It never opens the runtime, resumes a run, or records a decision. Its template gets one more value:

- `resumable`: `False` when `chosen.running(run_id)`; otherwise `can_resume(found, Store(settings.db_path))`. A `StoreError` from opening the store or from the lookup gives `False`, and the page is still `200`.

and the `error` value becomes the shown failure:

| `chosen.error(run_id)` | the run is busy | the log's last event is a record | `error` |
|---|---|---|---|
| a text other than `the resume failed` | any | any | that text |
| `None` or `the resume failed` | no | yes, with `type` T | `the resume failed (T)` |
| `None` or `the resume failed` | otherwise | | `chosen.error(run_id)` |

A record is an event with kind `EventKind.ERROR`, `node` `None`, `payload["error"] == RESUME_FAILED` and a `str` in `payload["type"]`. The log is read with `EventLog(settings.runs_dir).read(run_id)`; a `RunNotFound`, `EventLogCorrupt` or `OSError` from it, or an empty log, means there is no record. The failure is shown only through the existing line `<p>The last resume failed: {{ error }}</p>`, once.

**`run.html`** shows, when `resumable` is true, exactly these lines after the status block and before the failure line:

```html
<form method="post" action="/runs/{{ run_id }}/resume">
<input type="hidden" name="token" value="{{ token }}">
<button type="submit">Resume</button>
</form>
```

`run_id` is added to the template's values.

**`POST /runs/{run_id}/resume`**, in this order:

| Step | Result |
|---|---|
| `_refused(request, run_id, sent, settings)`, with `sent` the form's `token` | its response: `404 Not found` for a bad id, `403 Bad origin`, `403 Bad form token` |
| `runtime.read_state(settings, run_id)` raises `RunStateUnavailable` | `503 The run state is not available` |
| it raises any other `RunError` | `404 Not found` |
| `chosen.running(run_id)` | `303` to `/runs/{run_id}` |
| `can_resume(state, Store(settings.db_path))` raises `StoreError` | `503 The store is not available` |
| it is `True` | `chosen.start(run_id)`, then `303` to `/runs/{run_id}` |
| it is `False` | `303` to `/runs/{run_id}` |

The route never records a decision or an answer and never calls `runtime.resume` itself: the resumer does.

## Facts

Checked on 2026-11-19 against today's code, with `ScriptedModel` and synthetic requests only:
- A `RuntimeError` or `KeyboardInterrupt` raised by the model during a resume propagates out of `runtime.resume` unchanged; the run is left `stopped` at its node and the lease is released.
- A resume from `stopped` at `plan` whose model raises appends only `("model_request", "plan")` today.
- The demo request `note Milk` stops at a plan approval and then at a step approval.
- A lease taken over mid-run raises `LeaseLost` from `Store.renew` inside the graph call (`runtime.py` lines 143 and 155), not only from `release`.
- `Store(path)` creates the database when it is missing, as the approval pages already do.
- `EventLog.append` is safe here because the lease is held: no other process appends to that run.

## Requirements

### Part 1: the record

- **R1.** `RESUME_FAILED` is `"resume_failed"`.
- **R2.** A resume whose graph call raises an `Exception` that is not a `RunError` or `LeaseLost` appends exactly one event, `ERROR`, node `None`, payload exactly `{"error": "resume_failed", "type": <class name>}`, after the run's other events and while the lease is held; the same exception object then propagates. Each failed resume appends its own record.
- **R3.** Nothing is recorded for a `RunError`, a `LeaseLost`, a `BaseException` that is not an `Exception`, a failure before the lease is taken, or by `ask`.
- **R4.** When the record cannot be written, the original exception propagates and the lease is released.

### Part 2: the rule

- **R5.** `can_resume` follows its table: no lookup for a stopped or finished run, one lookup for a waiting run, `False` for `NotFound`, `StoreError` propagated, and `True` exactly when `resume_run` would call the graph.

### Part 3: the page

- **R6.** The run page shows the Resume form, with its token, exactly when the run is not busy and `can_resume` is true; a `StoreError` hides it and the page is still `200`. The page never opens the runtime, resumes or decides.
- **R7.** `POST /runs/{run_id}/resume` follows its table: checked like every form, starts a resume only for a resumable run that is not busy, redirects otherwise, and never records a decision.
- **R8.** The shown failure follows its table: the in-memory text first, the record only when the resumer keeps nothing or the fixed text, the run is not busy, and the record is the log's last event.

### Part 4: the rules

- **R9.** No exception text, `repr` or traceback is written to an event, a page or a log line. The class name is the only part of an exception kept.
- **R10.** Only the Scope's paths change; given files and existing tests stay byte-identical; `web/jobs.py`, `events.py`, `store.py`, `decisions.py` and `config.py` do not change.
- **R11.** `src/conductor/runtime.py`, `src/conductor/graph/supervisor.py` and `src/conductor/web/app.py` keep 100% line and branch coverage.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `tests/unit/test_can_resume.py` cannot be collected (`can_resume` does not exist), and of the other given tests these already pass: `test_a_start_that_fails_records_nothing`, `test_a_resume_that_loses_its_lease_records_nothing`, `test_an_interrupt_is_not_recorded`, `test_a_record_that_cannot_be_written_keeps_the_first_error`, `test_a_record_followed_by_a_success_is_not_shown`, and the four cases of `test_the_button_shows_only_when_a_resume_can_start` where no button is wanted. They are guards: each holds today and must keep holding. With names-only stubs, `test_the_failure_code` also passes.

| File | What it is |
|---|---|
| `tests/integration/test_resume_evidence.py` | R1 to R4: the record written by `runtime.resume` (9 tests from 9 functions) |
| `tests/unit/test_can_resume.py` | R5: `can_resume` over a store that allows only the expected lookup (16 tests from 5 functions) |
| `tests/e2e/test_web_resume.py` | R6 to R8: the run page and the Resume route (18 tests from 7 functions) |
| `docs/verification/probe-09h.py` | the probe, run by its path in Acceptance |

Given test count: **43**.

## Tests to write

In `tests/integration/test_resume_evidence_more.py` (section `core`):
- R2: `demo: note Milk` with its plan and its step approved, resumed while `DemoRunner.run` raises `ValueError`, records `{"error": "resume_failed", "type": "ValueError"}` once, and both approvals keep their decisions.
- R11: any branch of `runtime.py` the given tests leave uncovered, tested for what it does.

In `tests/e2e/test_web_resume_more.py` (section `core`):
- R6: a run waiting on an answered escalation shows the Resume form; one waiting on an open escalation does not.
- R7: a POST for a run whose `read_state` raises `RunStateUnavailable` gives `503 The run state is not available`; a POST for a well-formed id with no run gives `404 Not found`.
- R8: a log whose last line is not valid JSON, and a record whose `type` is `5`, each give a `200` page with no failure line.
- R11: any branch of `app.py` or `supervisor.py` the given tests leave uncovered, tested for what it does.

## Rules for this phase

- Side effects need approval: the Resume route only resumes a run whose decision or answer is already recorded, and never records one.
- Error messages are constant text plus identifiers. Never write or show the text of an exception.
- Time and ids come from `clock.now()` and `ids.new_id()` only, called through the module.
- The run page and the Resume route stay thin: the decision whether a run can resume is `can_resume`.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9h` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1265 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/runtime.py,*/conductor/graph/supervisor.py,*/conductor/web/app.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/integration/test_resume_evidence.py tests/unit/test_can_resume.py tests/e2e/test_web_resume.py --no-cov -q` | `43 passed` |
| `.venv/bin/python docs/verification/probe-09h.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/integration/test_resume_evidence.py tests/unit/test_can_resume.py tests/e2e/test_web_resume.py docs/verification/probe-09h.py src/conductor/web/jobs.py src/conductor/events.py src/conductor/store.py src/conductor/decisions.py src/conductor/config.py tests` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9h: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9h` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover' -- src/conductor/runtime.py src/conductor/graph/supervisor.py src/conductor/web/app.py
git grep --untracked -n -E 'noqa' -- src/conductor/runtime.py src/conductor/web/app.py
git grep --untracked -n -E 'traceback|format_exc|exc_info|repr\(|"type": *str\(|str\((error|exc|exception)\)\)' -- src/conductor/runtime.py src/conductor/graph/supervisor.py src/conductor/web
git grep --untracked -n -E 'jsonl|open\(' -- src/conductor/web
git grep --untracked -n -E 'open_runtime|runtime\.resume' -- src/conductor/web/app.py
```

The `tests` path in the diff row catches a changed existing test; the coder's two new test files are untracked, so they do not show there.

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Recover a failed web resume`, with `--tests-before 1222 --given 43`.
