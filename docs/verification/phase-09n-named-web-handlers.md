# Verify Phase 9n: Named web handlers

Spec: `docs/phases/phase-09n-named-web-handlers.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09n-named-web-handlers.md`.

## First: establish that the coder ran

- No `## Phase 9n: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09n-named-web-handlers.md docs/verification/phase-09n-named-web-handlers.md tests/unit/test_web_security.py tests/unit/test_web_layout.py docs/verification/probe-09n.py` must succeed. The gates judge against a committed baseline.

The coder:
- moved the Host guard, the security headers, the form cookie and the id/origin/token check from `src/conductor/web/app.py` into `src/conductor/web/security.py`;
- turned every route body into a named handler taking a frozen `Context`, with `create_app` as wiring;
- shared `record_and_resume` between approvals and escalations;
- added `web/security.py` to `scripts/critical_modules.txt` and wrote `tests/unit/test_web_handlers_more.py`.

## 1. Gates

N is `1439`. Given count: 38. `.venv/bin/python scripts/accept.py --phase 9n --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1477 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/web/*' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_web_security.py tests/unit/test_web_layout.py --no-cov -q` | `38 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09n.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_web_security.py tests/unit/test_web_layout.py docs/verification/probe-09n.py src/conductor/web/jobs.py src/conductor/web/templates src/conductor/decisions.py src/conductor/runtime.py src/conductor/store.py src/conductor/views.py src/conductor/policy.py src/conductor/cli` | no output |
| G6 | `git diff d55b6db --stat -- tests ':!tests/unit/test_web_security.py' ':!tests/unit/test_web_layout.py' ':!tests/unit/test_web_handlers_more.py'` | no output |
| G7 | `grep -c '^web/security.py$' scripts/critical_modules.txt` | `1` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths |
| G9 | `grep -c '^## Phase 9n: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9n` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_web_package_has_a_security_module`, `test_security_imports_nothing_from_the_web_package`; search 10 | pass; silent |
| R2 | `test_a_post_is_checked_for_its_id_origin_and_form_token` (14 cases) | pass |
| R3 | `test_a_missing_or_malformed_cookie_gets_a_fresh_token` (4 cases), `test_a_valid_cookie_keeps_its_token`, `test_the_form_cookie_is_http_only_strict_and_site_wide` | pass |
| R4 | `test_the_guard_serves_only_this_host_and_always_adds_the_headers` (7 cases), `test_the_guard_passes_other_scopes_through`; searches 8 and 9 | pass; silent |
| R5 | `test_the_page_still_exports_the_cookie_and_headers`; the existing web tests (in G1) | pass |
| R6 | `test_the_handlers_are_named_functions_that_take_the_context`, `test_the_context_is_frozen_and_holds_three_things` | pass |
| R7 | `test_create_app_only_registers_one_line_routes` | pass |
| R8 | `test_each_decision_state_read_and_resume_start_is_written_once` and the three `record_and_resume` tests; the coder's 409 and bad-arguments tests | pass |
| R9 | probe (G4); `tests/e2e/test_web_*.py` (in G1); the coder's 503 run-state test | `ok`; pass; pass |
| R10 | G2, G5 to G8; search 7 | as given; silent |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

Read `security.py` against the spec's Part 1 table: each rule as listed, `secrets.token_hex` called through the module, and `hmac.compare_digest` for the token comparison. Read `record_and_resume` against Part 3: `record(store)` inside the `try`, `start` only after it returns.

## 3. Probe

The probe is the given file `docs/verification/probe-09n.py` (G4). Its oracle is the predecessor's `web/app.py`, read from commit d55b6db with `git show` and loaded as `conductor.web.app_before` beside a link to the real templates. Each session runs on the old app and then the new one, each in a fresh data directory with the same fixed clock, ids, form token (`secrets.token_hex` patched), scripted model replies and a fake resumer. Setup goes through the CLI: an empty store, a pending plan, a pending step, or an open escalation. Requests are raw ASGI calls with exact Host, Origin and Cookie headers and form bodies. It checks:
- the layout: the security functions are defined in `web/security.py`;
- 19 forced sessions, one per path (each post refusal, each decision, a repeat decision, a bad edit, a resume), and 400 random ones agree. A random session is a valid request sequence with at most one change: the Host, the cookie, the Origin, the token or the method. For every request, the status, the header list (names, values and order) and the body must agree, and so must the resume starts and the stored approvals and escalations read back through the store. The probe also requires that statuses 200, 303, 400, 403, 404 and 409 were each reached at least 5 times.

Before handover the architect ran it on today's code. The layout check printed `FAIL` and the session check printed `ok`, because both sides were the same file. When `samesite="strict"` became `"lax"` in a scratch copy, the session check printed `FAIL`. So a session failure on the build points at a changed response, cookie or stored decision.

A stop at its own `assert` lines, or a `git show` failure, is the probe's fault (or a missing commit). Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/web
git grep --untracked -n -E 'hmac|secrets|compare_digest|set_cookie\(|"Bad (host|origin|form token)"|b"host"' -- src/conductor/web ':!src/conductor/web/security.py'
git grep --untracked -n -E '^(SECURITY_HEADERS|FORM_COOKIE|NOT_FOUND|_HEADER_BYTES|_TOKEN) =' -- src/conductor/web ':!src/conductor/web/security.py'
git grep --untracked -n -E 'from secrets import|from hmac import|from conductor\.runtime import|import \*' -- src/conductor/web
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09n`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match). Then run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09n`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (module) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | in `check_post`, move the origin check above the id check (`security.py`) | `tests/unit/test_web_security.py::test_a_post_is_checked_for_its_id_origin_and_form_token[id before origin]` | `(404, 'Not found')` | `(403, 'Bad origin')` |
| S2 | `samesite="strict"` becomes `samesite="lax"` (`security.py`) | `tests/unit/test_web_security.py::test_the_form_cookie_is_http_only_strict_and_site_wide` | ends `SameSite=strict` | ends `SameSite=lax` |
| S3 | in `record_and_resume`, call `ctx.resumer.start(...)` on the 404 branch before returning (`app.py`) | `tests/unit/test_web_layout.py::test_a_missing_item_is_not_found_and_starts_nothing` | started `[]` | started not `[]` |
| S4 | in `HostGuard`, keep a header the inner app already set instead of replacing it (`security.py`) | `tests/unit/test_web_security.py::test_the_guard_serves_only_this_host_and_always_adds_the_headers[this server]` | `x-frame-options` once | `x-frame-options` twice |
| S5 | in `post_resume`, call `runtime.read_state` directly instead of the shared helper (`app.py`) | `tests/unit/test_web_layout.py::test_each_decision_state_read_and_resume_start_is_written_once` | `'.read_state': 1` | `'.read_state': 2` |

Notes for tracing:
- S1: the case sends the id `nope` and the origin `null`; both are refusals, so only the order decides.
- S2: the probe also catches this (the architect's mutation run).
- S3: in the 404 branch `run_id` is unknown; the mutation may start with any value (the item id, an empty string). Write it with whatever name is in scope; the started list stops being empty.
- S4: the inner app sets `x-frame-options: SAMEORIGIN`. If the coder replaces headers by filtering then appending, write the change as dropping the filter: the header then appears twice, and the count assertion fails before the value one.
- S5: the test counts calls in the source, so the mutation need not run; it only must parse.

Spot rows that make the same change in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers in either module beyond those the spec names, such as a shared problem-page builder or a `_store_refused` mapping.
- `record` written as a nested function, a lambda or a `functools.partial`.
- The run-state helper returning a response or raising; route functions named in any way that does not reuse a handler's name.
- `security.py` importing `PlainTextResponse` from `fastapi.responses` or `starlette.responses`.
- Extra behaviour tests in `tests/unit/test_web_handlers_more.py`.

## 7. Out of scope

Each must be absent:
- Any changed status, header, header order, body, template, cookie attribute, redirect, message, form field or route.
- New routes, middleware other than the Host guard, sessions, a CSRF library or rate limiting.
- Any change to `web/jobs.py`, the templates, `decisions`, `runtime`, `store`, `views`, `policy` or `cli`.
- Code shared between `conductor.web` and `conductor.cli`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09n-named-web-handlers.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9n`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9n` must print `Reports OK.`
