# Verify Phase 9h: Recover a failed web resume

Spec: `docs/phases/phase-09h-recover-a-failed-web-resume.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09h-recover-a-failed-web-resume.md`.

## Correction 1 (2026-11-19)

The spec's correction 1 fixes line 176 of the given file `tests/e2e/test_web_resume.py`: it now reads the stored approval's `decision`, since `Store.pending()` returns `ApprovalRequest` records without one. Every gate is live. The implementation is committed (2f72d34) and the correction has its own commit, so G5 and G6 may print nothing. Judge Scope against the spec's commit instead: `git diff 14aec28 --stat` lists the Scope paths, plus this correction's spec, guide and test edit, `history.md` and your report. The given files must equal the correction's commit, so G5 still applies as written.

## First: establish that the coder ran

- No `## Phase 9h: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09h-recover-a-failed-web-resume.md docs/verification/phase-09h-recover-a-failed-web-resume.md tests/integration/test_resume_evidence.py tests/unit/test_can_resume.py tests/e2e/test_web_resume.py docs/verification/probe-09h.py` must succeed: the gates judge against a committed baseline.

The coder:
- added `RESUME_FAILED` to `src/conductor/runtime.py` and made `resume` append one sanitized `error` event for an unexpected failure while the lease is held;
- added `can_resume` to `src/conductor/graph/supervisor.py`;
- added `resumable`, `run_id` and the recorded failure to the run page in `src/conductor/web/app.py`, the Resume form to `src/conductor/web/templates/run.html`, and the `POST /runs/{run_id}/resume` route;
- added `tests/integration/test_resume_evidence_more.py`, `tests/e2e/test_web_resume_more.py` and one progress entry.

## 1. Gates

N is `1222`. Given count: 43. `.venv/bin/python scripts/accept.py --phase 9h --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1265 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/runtime.py,*/conductor/graph/supervisor.py,*/conductor/web/app.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/integration/test_resume_evidence.py tests/unit/test_can_resume.py tests/e2e/test_web_resume.py --no-cov -q` | `43 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09h.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/integration/test_resume_evidence.py tests/unit/test_can_resume.py tests/e2e/test_web_resume.py docs/verification/probe-09h.py src/conductor/web/jobs.py src/conductor/events.py src/conductor/store.py src/conductor/decisions.py src/conductor/config.py tests` | no output |
| G6 | `git status --short --untracked-files=all` | only the Scope paths |
| G7 | `grep -c '^## Phase 9h: ' docs/progress.md` | `1` |
| G8 | `.venv/bin/python scripts/check_reports.py --phase 9h` | `Reports OK.` |

Also read `git diff HEAD -- src/conductor/web/templates/run.html`: the only added lines are the four form lines of the spec, inside `{% if resumable %}` … `{% endif %}` (or an equivalent condition on the same value), placed after the status block and before the failure line.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_failure_code` | passes |
| R2 | `test_a_failed_resume_records_its_type_and_not_its_text`, `test_each_failed_resume_is_recorded_once`, `test_a_resume_that_then_succeeds_leaves_the_record_behind_it`; the coder's `note Milk` test; read `resume` | pass; the append happens before `_call` releases the lease, through `runtime.log` |
| R3 | `test_a_refused_resume_records_nothing`, `test_a_start_that_fails_records_nothing`, `test_a_resume_that_loses_its_lease_records_nothing`, `test_an_interrupt_is_not_recorded`; read `ask` | pass; `ask` is unchanged |
| R4 | `test_a_record_that_cannot_be_written_keeps_the_first_error` | passes |
| R5 | `tests/unit/test_can_resume.py` (16 tests); probe checks 1 and 2 | pass; `ok` |
| R6 | `test_the_button_shows_only_when_a_resume_can_start` (6 cases), `test_a_store_that_fails_hides_the_button_and_refuses_the_post`; the coder's escalation test; `tests/e2e/test_web_run_status.py`, `tests/e2e/test_web_run_status_cases.py` (in G1); probe check 3 | pass; `ok` |
| R7 | `test_a_resume_post_starts_the_run_and_records_nothing`, `test_a_post_that_cannot_start_only_redirects` (3 cases), `test_a_post_is_checked_like_every_form` (3 cases), `test_a_store_that_fails_hides_the_button_and_refuses_the_post`; the coder's 503 and 404 tests; probe check 4 | pass; `ok` |
| R8 | `test_the_recorded_failure_is_shown` (3 cases), `test_a_record_followed_by_a_success_is_not_shown`; the coder's corrupt-log and `type` 5 tests; probe checks 3 and 4 | pass; `ok` |
| R9 | the searches; `test_a_failed_resume_records_its_type_and_not_its_text`, `test_the_recorded_failure_is_shown`; probe check 4 | silent; pass; `ok` |
| R10 | G5, G6 | as given |
| R11 | G2 | as given |

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09h.py` (G4). It checks:
- 300 random run states, each a valid base with at most one change (status, stopped node, approval or escalation, decided, open or missing), against its own table for `can_resume`;
- the same states through `resume_run` with the graph call replaced: it calls the graph exactly when `can_resume` is true, and both outcomes are reached at least 50 times;
- 48 run pages (three kept messages, busy or not, eight log tails: a record of two types, a record whose `type` is a number, a record with a node, another error, a record followed by an event, a corrupt log, no log) against its own table for the shown failure and the button; each with exactly one failure line at most, and the record shown in exactly 4 cases;
- a real resume started by a POST through the real `Resumer`, whose model raises: the page shows `the resume failed (Boom)` before and after a restart (a new app and resumer), the button is back, the log holds one record and the exception's text appears nowhere.

A stop at its own `assert` lines, before its first check prints, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names. The last three find exception text kept or shown (R9), the page reading the log by hand instead of through `EventLog`, and the web layer running a resume itself instead of through the resumer (R6, R7).

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

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09h`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09h`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | record a `RunError` too (`runtime.resume`) | `tests/integration/test_resume_evidence.py::test_a_refused_resume_records_nothing` | events unchanged | one more event, `('error', None, …)` |
| S2 | record `str(error)` as the `type` (`runtime.resume`) | `tests/integration/test_resume_evidence.py::test_a_failed_resume_records_its_type_and_not_its_text` | `'RuntimeError'` | `'SYNTHETIC-SECRET'` |
| S3 | catch `BaseException` instead of `Exception` for the record (`runtime.resume`) | `tests/integration/test_resume_evidence.py::test_an_interrupt_is_not_recorded` | `[]` | `[{'error': 'resume_failed', 'type': 'KeyboardInterrupt'}]` |
| S4 | let an error from the record's `append` propagate (`runtime.resume`) | `tests/integration/test_resume_evidence.py::test_a_record_that_cannot_be_written_keeps_the_first_error` | the `RuntimeError` | `OSError` raised |
| S5 | treat `run_step` as resumable (`can_resume`) | `tests/unit/test_can_resume.py::test_a_stopped_run_by_its_node[run_step-False]` | `False` | `True` |
| S6 | return `True` for a waiting approval without reading its decision (`can_resume`) | `tests/unit/test_can_resume.py::test_a_run_waiting_on_an_approval[undecided]` | `False` | `True` |
| S7 | turn a `StoreError` into `False` (`can_resume`) | `tests/unit/test_can_resume.py::test_a_store_that_fails_is_not_hidden` | `StoreError` raised | `False` returned |
| S8 | set `resumable` from `can_resume` alone, ignoring `running` (the run page) | `tests/e2e/test_web_resume.py::test_the_button_shows_only_when_a_resume_can_start[decided-True-False]` | no form | form shown |
| S9 | skip the `running` check (the Resume route) | `tests/e2e/test_web_resume.py::test_a_post_that_cannot_start_only_redirects[busy]` | `started == []` | `started == [run_id]` |
| S10 | prefer the record over any kept text (the run page) | `tests/e2e/test_web_resume.py::test_the_recorded_failure_is_shown[newer-failure]` | `run … is busy` | `the resume failed (RuntimeError)` |
| S11 | look for a record anywhere in the log, not only as the last event (the run page) | `tests/e2e/test_web_resume.py::test_a_record_followed_by_a_success_is_not_shown` | no failure line | `The last resume failed` shown |
| S12 | skip `_refused` (the Resume route) | `tests/e2e/test_web_resume.py::test_a_post_is_checked_like_every_form[token-expected0]` | `(403, 'Bad form token')` | `(303, '')` |

Notes for tracing. S1: the run is stopped at `run_step`, so `resume_run` raises `RunError("… cannot be resumed")` while the lease is held; the busy refusal is before the lease and adds nothing either way. S3: `KeyboardInterrupt` is not an `Exception`, so only a `BaseException` clause reaches the record. S4: the test's `append` raises `OSError` only for an `ERROR` event with no node, which is the record alone. S6: the fake store returns `decision=None`; a body that never reads it returns `True` and `store.asked` stays `[]`, so the first assertion already fails. S8: the run's approval is decided, so `can_resume` is true and only `running` hides the form. S9: `Still(busy=True)` records every `start`. S10: the kept text `run … is busy` is not the fixed text, so it wins over the record. S11: the last event of a successful resume is not an `error` event. S12: the cookie is `d` × 64 and the form sends `c` × 64. Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside the Scope modules, and extra behaviour tests in the two `*_more.py` files.
- The record written by a wrapper around the call passed to `_call`, or by a new parameter of `_call`, as long as it runs before the release and only for `resume`.
- `resume_run` rewritten to call `can_resume` for its decision, keeping every message.
- The durable-message rule as a private function in `app.py`, reading the log once per page.
- The Resume route opening the store with `Store(settings.db_path)` directly or through a small helper; the run page treating a `StoreError` from either the constructor or the lookup alike.
- The form's condition written as `{% if resumable %}` or an equivalent test on the same value.

## 7. Out of scope

Each must be absent:
- any change to `src/conductor/web/jobs.py`, its messages, retention or shutdown;
- a record from `ask`, from before the lease, or for a `RunError`;
- exception text, a `repr` or a traceback in an event, a page or a log line;
- sharing the `_record_approval` and `_record_escalation` plumbing (9n);
- a decision or answer recorded or changed by the Resume route;
- a setting, or any change to `config.py`, `events.py`, `store.py` or `decisions.py`;
- any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09h-recover-a-failed-web-resume.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9h`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9h` must print `Reports OK.`
