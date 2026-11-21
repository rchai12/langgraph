# Phase 9n: Named web handlers

## Goal

`src/conductor/web/app.py` is 461 lines. `create_app` is about 260 of them: ten routes and six helpers nested as closures over the settings, the templates and the resumer. Two of those helpers, `_record_approval` and `_record_escalation`, are near-copies: open the store, decide, map six exception types, start a resume, redirect. This phase does three things:
- moves the page's security rules (the Host guard, the security headers, the form cookie, and the id, origin and token check) into their own critical module, `web/security.py`;
- turns every route body into a named top-level handler that takes an explicit context;
- shares one record-and-resume function between approvals and escalations.

No status, header, body, cookie, redirect, escaping, resume start or stored decision changes. The 9h recovery stays as it is: the run page's resume button, the busy and failure rules, and the recorded failure type.

Decided with the owner (2026-11-20):
- **Layout.** `web/security.py` holds the Host guard, the security headers, the form token and the id/origin/token check. `web/app.py` keeps the pages, the decision handlers and `create_app` as wiring. Existing imports from `conductor.web.app` (`create_app`, `FORM_COOKIE`, `SECURITY_HEADERS`) keep working.
- **Handler dependencies.** A frozen dataclass `Context(settings, templates, resumer)` is built once in `create_app` and passed explicitly to each handler. `create_app` registers thin one-line routes.
- **Critical.** `web/security.py` joins the critical modules: every line and branch is covered, and it is listed in `scripts/critical_modules.txt` and `docs/testing.md`. The architect has added the `docs/testing.md` line; the coder adds the `critical_modules.txt` line.

Decided by the architect, within those answers:
- `security.py` imports only `conductor.config` and `conductor.contracts.base` from the project, never the rest of `conductor.web`. `app.py` imports it.
- The handler names are fixed: `home`, `approval_page`, `escalation_page`, `run_page`, `post_resume`, `post_approval`, `post_escalation` and `record_and_resume`. Every other helper in `app.py` stays private.
- The run state is read in one place: the run page and the resume post share a private helper that maps `RunStateUnavailable` to 503 and `RunError` to 404.
- `decide_approval` and `answer_escalation` stay imported by name into `app.py` and are called as module globals. `tests/e2e/test_web_run_status_cases.py` patches them there, so no existing test changes.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/web/app.py` (all of it) and `src/conductor/web/jobs.py` (`Resumer`: `start`, `running`, `error`).
- `tests/e2e/test_web_pages.py`, `test_web_decide.py`, `test_web_resume.py`, `test_web_run_status.py` and `test_web_run_status_cases.py`: they pin the pages' responses and must keep passing unchanged.
- `docs/architecture.md` ("Repository layout") only where this phase changes it.

## Starting state

Phase 9m is built and verified, and everything is committed: N is `1439`. **Sections: core.** `conductor.web` holds `__init__.py`, `app.py`, `jobs.py` and the templates. `web/app.py` and `web/jobs.py` are critical and 100% covered. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/web/security.py` | new: the security rules (Part 1) |
| `src/conductor/web/app.py` | `Context`, the named handlers, `record_and_resume`, `create_app` as wiring (Parts 2 and 3) |
| `scripts/critical_modules.txt` | one new line: `web/security.py` |
| `tests/unit/test_web_handlers_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Any change to a status, header, header order, body, template, cookie attribute, redirect, message, form field or route.
- New routes, a JSON API, CSRF libraries, sessions, middleware other than the Host guard, or rate limiting.
- Changes to `web/jobs.py`, the templates, `conductor.decisions`, `conductor.runtime`, `conductor.store`, `conductor.views`, `conductor.policy` or `conductor.cli`.
- Sharing code with `conductor.cli`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: `web/security.py`

Today's code moves here, renamed and otherwise unchanged:

| Today in `app.py` | In `security.py` |
|---|---|
| `SECURITY_HEADERS`, `FORM_COOKIE` | the same names |
| `_NOT_FOUND` | `NOT_FOUND = "Not found"` |
| `_HostGuard(app, port)` | `HostGuard(app: ASGIApp, port: int)` |
| `_prepare(request)` | `form_token(request: Request) -> tuple[str, bool]` |
| the `response.set_cookie(...)` call in `_page` | `set_form_cookie(response: Response, token: str) -> None` |
| `_refused(request, item_id, sent, settings)` | `check_post(request: Request, item_id: str, sent: str, settings: Settings) -> Response \| None` |
| `_HEADER_BYTES`, `_TOKEN`, `_origins` | private, unchanged |

The rules, as today:
- The guard answers `400 Bad host` unless exactly one Host header names `127.0.0.1:<port>` or `localhost:<port>`. It replaces any security header the app set and adds every one of them to every response, the refusal included. Non-HTTP scopes pass through.
- `form_token` keeps a cookie that is 64 lower-case hex characters and otherwise makes a fresh token with `secrets.token_hex(32)`, called through the module.
- `set_form_cookie` sets `conductor_form` with `httponly=True`, `samesite="strict"` and `path="/"`.
- `check_post` checks in order: the id (`404 Not found`), then the origin if present (`403 Bad origin` unless `http://127.0.0.1:<port>` or `http://localhost:<port>`), then the cookie and the sent token (`403 Bad form token` unless the cookie is a valid token equal to the sent one by `hmac.compare_digest`). It returns `None` when all pass.

### Part 2: the context and the handlers

```python
@dataclass(frozen=True)
class Context:
    settings: Settings
    templates: Jinja2Templates
    resumer: Resumer
```

`app.py` sets `__all__ = ["FORM_COOKIE", "SECURITY_HEADERS", "create_app"]` and imports `FORM_COOKIE` and `SECURITY_HEADERS` from `conductor.web.security`, so `ruff` accepts the re-exports without `noqa`.

Each route body becomes one top-level handler that takes the context first:

| Route | Handler |
|---|---|
| `GET /` | `home(ctx, request)` |
| `GET /approvals/{approval_id}` | `approval_page(ctx, approval_id, request)` |
| `GET /escalations/{escalation_id}` | `escalation_page(ctx, escalation_id, request)` |
| `GET /runs/{run_id}` | `run_page(ctx, run_id, request)` |
| `POST /runs/{run_id}/resume` | `async post_resume(ctx, run_id, request)` |
| `POST /approvals/{approval_id}/approve`, `/reject`, `/edit` | `async post_approval(ctx, approval_id, request, verdict)` |
| `POST /escalations/{escalation_id}/retry`, `/cancel` | `async post_escalation(ctx, escalation_id, request, answer)` |

Each handler annotates its first parameter as `Context` and returns a `Response`. The private helpers (`_with_store`, `_page`, `_home`, `_form`, `_detail`, `_problem`, `_fields`, `_failed`, `_resumable`, `_shown_failure`, `_recorded_type`) become top-level and take the context where they used a closure value. `_page` uses `security.form_token` and `security.set_form_cookie`, and the post handlers use `security.check_post`. `run_page` and `post_resume` read the run state through one private helper, so `runtime.read_state` is called once in the file.

`create_app(settings, *, resumer=None) -> ASGIApp` keeps its signature. It builds the context, with `Resumer(settings)` when `resumer` is `None` and today's template environment. It creates the `FastAPI` app with today's arguments and registers ten routes. Each route is a nested function whose body is one `return` of its handler. Nested names must not reuse a handler's name (`get_home`, not `home`). It returns `security.HostGuard(api, settings.web_port_number)`. It has no `try`.

### Part 3: `record_and_resume`

```python
def record_and_resume(
    ctx: Context, request: Request, back: str, record: Callable[[Store], str]
) -> Response:
```

1. Open `Store(ctx.settings.db_path)` and call `record(store)`, which returns the run id. Both happen inside one `try`.
2. On `NotFound`, `AlreadyDecided`, `DecisionRefused`, `ValueError`, `NotRegistered` or `StoreError`, return today's mapping: `404 Not found`, `409` problem page, `400` problem page with the problems, `400` problem page, and `503 The store is not available`. Nothing is started.
3. Otherwise call `ctx.resumer.start(run_id)` and return `RedirectResponse(f"/runs/{run_id}", status_code=303)`.

`post_approval` checks the post, parses `args` for an edit (today's `400` problem page on a bad object), and calls `record_and_resume` with a `record` that does three things: it loads the approval, calls `decide_approval` with `channel="web"` as today, and returns the approval's run id. `post_escalation` does the same with `answer_escalation`. So `decide_approval` and `answer_escalation` are each called once in the file, and `.start(` twice: once here and once in `post_resume`.

## Facts

Checked on 2026-11-20 with FastAPI 0.162.2 and Starlette 1.10.0, on today's code:
- Today `create_app` nests 16 functions and calls `.start(` three times, and `conductor.web` is 100% covered (lines and branches).
- `test_web_security.py` pins today's rules. A test-only shim pointed the new names at today's `_HostGuard`, `_prepare` and `_refused` and at the `set_cookie` call, and all 28 of its tests passed.
- Tests import only `create_app`, `FORM_COOKIE` and `SECURITY_HEADERS` from `conductor.web.app`. They patch `decide_approval` and `answer_escalation` there (`test_web_run_status_cases.py`) and patch nothing else in the module.
- A `starlette.requests.Request` built from a bare scope parses its `cookie` and `origin` headers, so the security functions can be tested without a server.
- The probe loads the predecessor's `web/app.py` from commit d55b6db with `git show`, as `conductor.web.app_before`, beside a link to the same templates. It sends raw ASGI requests to both apps: exact Host, Origin and Cookie headers, and form bodies. Each app runs in a fresh world with a fixed clock, ids and form token (`secrets.token_hex` patched), a scripted model and a fake resumer. On today's code, its session check prints `ok` and its layout check fails. When `samesite="strict"` became `"lax"` in a scratch copy, the session check failed.

## Requirements

### Part 1: the security module

- **R1.** `conductor.web` holds `__init__.py`, `app.py`, `jobs.py` and `security.py`. `security.py` imports nothing from `conductor.web` and only `conductor.config` and `conductor.contracts.base` from the rest of the project.
- **R2.** `check_post` refuses a bad id with `404 Not found`, a foreign origin with `403 Bad origin`, and a missing, malformed or unequal token with `403 Bad form token`, in that order. It returns `None` otherwise.
- **R3.** `form_token` keeps a valid cookie and replaces a missing or malformed one with a fresh 64-hex token. `set_form_cookie` sets the cookie HttpOnly, SameSite strict, path `/`.
- **R4.** `HostGuard` serves only exactly one Host of `127.0.0.1:<port>` or `localhost:<port>`, answers `400 Bad host` otherwise, puts each security header on every response exactly once with its fixed value, and passes non-HTTP scopes through.
- **R5.** `conductor.web.app` still exports `FORM_COOKIE` and `SECURITY_HEADERS` (the security module's objects) and `create_app`, with `__all__` naming exactly these three.

### Part 2: the handlers

- **R6.** `app.py`'s public top-level functions are exactly the eight handlers and `create_app`. Each handler takes `Context` first. `Context` is a frozen dataclass of `settings`, `templates` and `resumer`.
- **R7.** `create_app` registers ten routes, each a one-statement `return`, and contains no `try`.
- **R8.** `record_and_resume` starts the run and redirects (`303`, `/runs/<id>`) after a recorded decision. It maps every refusal as today and starts nothing. `decide_approval`, `answer_escalation` and `runtime.read_state` are each called once in `app.py`, and `.start(` twice.

### Part 3: the same page

- **R9.** For every request (any route, method, Host, Origin, cookie and form), the status, headers, body, resume starts and stored decisions are as before. The existing web tests pass unchanged.

### Part 4: the rules

- **R10.** Only the Scope's paths change. Given files and existing tests stay byte-identical. There is no `noqa` or `pragma: no cover` in `conductor.web`. `web/security.py` is listed in `scripts/critical_modules.txt`, and the package is 100% covered (lines and branches).

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `test_web_security.py` fails on every test (`conductor.web.security` is empty), and `test_web_layout.py` passes 2 of 10. With names-only stubs, 36 tests fail and 2 pass: the file list and the security import rule. They are guards: an empty `security.py` imports nothing.

| File | What it is |
|---|---|
| `tests/unit/test_web_security.py` | R2 to R4: the post check (14 cases), the form token and cookie, the Host guard (7 cases) and scopes passed through (28 tests from 6 functions) |
| `tests/unit/test_web_layout.py` | R1 and R5 to R8: the files, the import rule, the re-exports, the handlers, the context, the routes, the once-only calls and `record_and_resume` (10 tests from 10 functions) |
| `docs/verification/probe-09n.py` | the probe, run by its path in Acceptance |

Given test count: **38**.

## Tests to write

In `tests/unit/test_web_handlers_more.py` (section `core`):
- R8: through `create_app`, a second approve of an already-decided approval answers `409` and starts nothing, with a fake resumer that records starts.
- R8: `post_approval` for `edit` with `args` `{bad` answers `400` with `The arguments must be a JSON object.`, and never opens the store (`app.Store` patched to raise).
- R9: with `runtime.read_state` patched to raise `RunStateUnavailable`, both `GET /runs/<id>` and a valid `POST /runs/<id>/resume` answer `503 The run state is not available`.
- R10: any branch of `conductor.web` that the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- The page answers only this machine. Every response carries the security headers. Every post checks the id, the origin and the form token before it reads the store.
- A decision is recorded only through `conductor.decisions`. A `propose`, `write` or `implement` action still waits for its approval.
- Error messages stay constant text plus identifiers, exactly as today. Nothing echoes a request, a model reply or a tool result.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9n` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1477 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/web/*' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_web_security.py tests/unit/test_web_layout.py --no-cov -q` | `38 passed` |
| `.venv/bin/python docs/verification/probe-09n.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_web_security.py tests/unit/test_web_layout.py docs/verification/probe-09n.py src/conductor/web/jobs.py src/conductor/web/templates src/conductor/decisions.py src/conductor/runtime.py src/conductor/store.py src/conductor/views.py src/conductor/policy.py src/conductor/cli` | no output |
| `git diff d55b6db --stat -- tests ':!tests/unit/test_web_security.py' ':!tests/unit/test_web_layout.py' ':!tests/unit/test_web_handlers_more.py'` | no output |
| `grep -c '^web/security.py$' scripts/critical_modules.txt` | `1` |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9n: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9n` (after writing progress) | `Reports OK.` |

The second diff row compares against d55b6db (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Named web handlers`, with `--tests-before 1439 --given 38`.
