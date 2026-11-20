# Phase 9j: Shared validation and presentation contracts

## Goal

Four small rules are each written once and imported everywhere they are used: the 32-hex id shape, the request bounds (1 to 2000 characters, not blank), the "is this a Contract class" check, and the UTC time formats. Today each has two to five copies in `contracts`, `events`, `store`, `graph/status`, `web`, `cli`, `views`, `routing`, `planning`, `graph/supervisor`, `evals/cases`, `registry` and `llm/points`, and a copy that drifts is how a privacy or display rule quietly changes. Every wire shape, validation order, message and printed line stays byte-identical. The one new behaviour is that the shared time formatter refuses a time that is not UTC, which no caller passes today.

Decided with the owner (2026-11-20):
- **Where the rules live.** The id shape, the request bounds, the Contract-type check and the UTC check go in `src/conductor/contracts/base.py`, beside `Id`. `contracts` still imports nothing from the project. The two time formats go in a new module `src/conductor/times.py`. Every copy elsewhere imports from these two.
- **A time that is not UTC is refused.** `times.display` and `times.stored` raise `ValueError("time must be UTC")` for a time with a non-zero offset or no offset. Today `strftime` appends `Z` whatever the offset, so a `+02:00` time would print two hours wrong. Every time the code formats today is already checked UTC, so no output changes.
- **Both formats move.** The display format (`%Y-%m-%dT%H:%M:%SZ`, in `views.py`, `web/app.py` and twice in `cli/main.py`) and the stored format (`%Y-%m-%dT%H:%M:%S.%fZ`, in `events.py`, `store.py` and `cli/main.py`) both live in `times.py`.

Decided by the architect, within those answers:
- `UTC_MESSAGE` moves from `contracts/approvals.py` to `contracts/base.py`, and `approvals.py` imports it, so `approvals.UTC_MESSAGE` still works. The event log's own `"time must be UTC"` literal and its offset check use the shared `UTC_MESSAGE` and `is_utc`.
- `REQUEST_MESSAGE` moves from `routing/route.py` to `contracts/base.py`, and `route.py` imports it, so `routing.route.REQUEST_MESSAGE` (imported by six existing tests) is the same object.
- The request field in the four input contracts (`RouteInputs`, `PlanInputs`, `AnswerInputs`, the demo's `PickInputs`) becomes the shared type `RequestText`, with the same schema: 1 to 2000 characters. It does not refuse blank text. The code check before each model call (`is_request`) refuses blank text first, as today.
- Each module keeps its own message: `RUN_ID_MESSAGE` in `events.py`, `ID_MESSAGE` in `store.py`, the web's `Not found`, the case file's `case N: request must have 1 to 2000 characters`.
- `times.py` and `contracts/base.py` are covered 100%. `times.py` is a critical module: it writes the time into every event line and every stored lease and approval.
- The reply bound (`AnswerOutput.reply` and `graph/status._reply`), the 64-hex form token and `Sha256`, the report file name format in `evals/report.py`, and the case id pattern are other rules, and they stay where they are.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/contracts/base.py` and `src/conductor/contracts/approvals.py` (`UTC_MESSAGE`, `_utc`, `UtcTime`).
- Every copy this phase replaces, by its search in Acceptance: `_RUN_ID`, `_RUN_FILE`, `Event._at_is_utc` and `_event_line` in `events.py`; `_ID` and `_stamp` in `store.py`; `_HEX` in `graph/status.py`; `_ID` and `_WHEN` in `web/app.py`; `_WHEN` in `views.py`; `_STORED_AT`, `_WHEN`, `_when` and the literal in `list_runs` in `cli/main.py`; `_is_contract` in `registry.py` and `llm/points.py`; the request checks in `routing/route.py`, `graph/supervisor.py`, `planning/answer.py` and `evals/cases.py`; the request fields in `routing/route.py`, `planning/plan.py`, `planning/answer.py` and `domains/demo.py`.
- The tests that pin today's messages, which must keep passing unchanged: `tests/unit/test_route.py` (`REQUEST_MESSAGE`), `tests/unit/test_events.py` (`RUN_ID_MESSAGE`, `test_a_time_that_is_not_utc_is_refused`), `tests/unit/test_eval_cases.py` (the case file's request message), `tests/e2e/test_cli_runs.py` and `tests/unit/test_views.py` (printed times).

## Starting state

Phase 9i is built and verified, and everything is committed: N is `1309`. **Sections: cli, core.** `conductor.times` does not exist, and `contracts/base.py` has `Id` with its pattern written inline and no shared helpers. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/contracts/base.py` | the shared rules (Part 1) |
| `src/conductor/contracts/approvals.py` | imports `UTC_MESSAGE`, `_utc` uses `is_utc` (Part 1) |
| `src/conductor/times.py` | new: the two formats (Part 2) |
| `src/conductor/events.py` | ids, run file names, the UTC check and the stored time (Part 3) |
| `src/conductor/store.py` | ids and the stored time (Part 3) |
| `src/conductor/graph/status.py` | ids (Part 3) |
| `src/conductor/web/app.py` | ids and the display time (Part 3) |
| `src/conductor/views.py` | the display time (Part 3) |
| `src/conductor/cli/main.py` | the display and stored times (Part 3) |
| `src/conductor/registry.py`, `src/conductor/llm/points.py` | the Contract-type check (Part 3) |
| `src/conductor/routing/route.py`, `src/conductor/graph/supervisor.py`, `src/conductor/planning/answer.py`, `src/conductor/planning/plan.py`, `src/conductor/evals/cases.py`, `src/conductor/domains/demo.py` | the request rule and field (Part 3) |
| `scripts/critical_modules.txt` | one new line, `times.py` |
| `tests/unit/test_shared_rules_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Any change to a message, a printed line, an event line, a stored row, a JSON schema, or the order in which checks run.
- Tightening `RequestText` to refuse blank text, or changing any other field's bounds.
- The reply bound, the 64-hex form token, `Sha256`, `Name`, `ActionName`, `RuleId`, the case id pattern, and the report file name format.
- Splitting `cli/main.py` or `web/app.py` into modules, or moving route bodies out of `create_app` (a later phase).
- Converting a time to UTC anywhere, or any change to `clock.py`, `ids.py` or `config.py`.
- Any change to `private.py`, `acceptance.py`, the prompts, the web templates, a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: `contracts/base.py`

Add, beside the existing names (`re` and `timedelta` from the standard library; still no project import):

```python
ID_PATTERN = r"^[0-9a-f]{32}$"
Id = Annotated[str, Field(pattern=ID_PATTERN)]   # replaces the inline pattern

MAX_REQUEST = 2000
REQUEST_MESSAGE = "a request must have 1 to 2000 characters"
RequestText = Annotated[str, Field(min_length=1, max_length=MAX_REQUEST)]

UTC_MESSAGE = "time must be UTC"

def is_id(value: object) -> bool: ...
def is_request(value: object) -> bool: ...
def is_contract_type(value: object) -> bool: ...
def is_utc(moment: datetime) -> bool: ...
```

- `is_id(value)` is `isinstance(value, str) and _ID.fullmatch(value) is not None`, with `_ID = re.compile(ID_PATTERN)`. `fullmatch` refuses a trailing newline that `$` alone would allow.
- `is_request(value)` is `isinstance(value, str) and value.strip() != "" and len(value) <= MAX_REQUEST`.
- `is_contract_type(value)` is `isinstance(value, type) and issubclass(value, Contract)`. `Contract` itself counts; an instance, a plain `BaseModel` and `list[Contract]` do not.
- `is_utc(moment)` is `moment.utcoffset() == timedelta(0)`. A naive time has no offset (`None`), so it is not UTC.

`contracts/approvals.py` imports `UTC_MESSAGE` and `is_utc` from `base` and drops its own `UTC_MESSAGE`. `_utc` raises `ValueError(UTC_MESSAGE)` when `not is_utc(value)`.

### Part 2: `conductor.times`

`src/conductor/times.py` imports `datetime` and, from the project, only `conductor.contracts.base`.

```python
DISPLAY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
STORED_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

def display(moment: datetime) -> str: ...
def stored(moment: datetime) -> str: ...
```

Each raises `ValueError(UTC_MESSAGE)` when `not is_utc(moment)`, and otherwise returns `moment.strftime(...)` with its format. Callers import the module (`from conductor import times`) and call `times.display(...)` and `times.stored(...)`.

### Part 3: the callers

Each caller imports the shared rule and drops its own copy. Its behaviour is otherwise unchanged.

| Where | Today | After |
|---|---|---|
| `events.check_run_id` | `_RUN_ID.fullmatch(run_id) is None` | `not is_id(run_id)`, same `RUN_ID_MESSAGE` |
| `EventLog.runs` | `_RUN_FILE.fullmatch(path.name) is None` | skip unless `path.name.endswith(".jsonl") and is_id(path.name.removesuffix(".jsonl"))` |
| `Event._at_is_utc` | its own offset check and literal | `if not is_utc(value): raise ValueError(UTC_MESSAGE)` |
| `events._event_line` | `event.at.strftime(...)` | `times.stored(event.at)` |
| `store._require_ids` | `_ID.fullmatch(...) is None` | `not is_id(...)`, same messages |
| `store._stamp` | `value.strftime(...)` | `times.stored(value)` (the helper may stay as a one-line wrapper or be replaced by the call) |
| `graph/status.py` (the interrupt value) | `type(value) is not str or _HEX.fullmatch(value) is None` | `type(value) is not str or not is_id(value)`: the exact `str` type check stays |
| `web/app.py` (`_refused` and the three GET routes) | `_ID.fullmatch(...) is None` | `not is_id(...)` |
| `web/app.py` `_home` rows | `.strftime(_WHEN)` | `times.display(...)` |
| `views._when` | `moment.strftime(_WHEN)` | `times.display(moment)` (or the call in its place) |
| `cli/main.py` `list_runs`, `show`, `_when` | two `_WHEN`-style literals and `_STORED_AT` | `times.display(...)` in `list_runs` and `_when`, `times.stored(event.at)` in `show` |
| `registry._is_contract`, `points._is_contract` | their own copies | `is_contract_type` |
| `route_request`, `start_run`, `answer_request` | `not request.strip() or len(request) > 2000` | `not is_request(request)`, same `REQUEST_MESSAGE`, same place |
| `evals/cases._case` | `not isinstance(request, str) or not request.strip() or len(request) > 2000` | `not is_request(request)`, same message |
| `RouteInputs`, `PlanInputs`, `AnswerInputs`, demo `PickInputs` | `request: str = Field(min_length=1, max_length=2000)` | `request: RequestText` |

`routing/route.py` imports `REQUEST_MESSAGE` from `contracts.base` instead of defining it. `graph/supervisor.py` and `planning/answer.py` may keep importing it from `routing.route` or import it from `contracts.base`.

After this, outside `contracts/base.py` and `times.py`, no module under `src/` writes the id pattern, a `%Y-%m-%dT` or `%H:%M:%S` format, an `issubclass(` or a `utcoffset(` call, a `len(request)` check, a `request: str = Field`, or its own `"time must be UTC"` or `"a request must have` literal (searches in Acceptance).

## Facts

Checked on 2026-11-20 with the project's Python 3.12.16 and pydantic 2, in a scratch folder with no project code:
- `datetime.strftime("%Y-%m-%dT%H:%M:%SZ")` on a `+02:00` time and on a naive time both print the clock reading with `Z` and no conversion: today's copies would print a wrong time without complaint.
- `isinstance(list[C], type)`, `isinstance(type[C], type)` and `isinstance(int | None, type)` are all false on Python 3.12, so `is_contract_type` never reaches `issubclass` with a generic alias.
- `re.compile(r"^[0-9a-f]{32}$").fullmatch(hex + "\n")` and `re.compile(r"[0-9a-f]{32}").fullmatch(hex + "\n")` are both `None`, so the anchored pattern with `fullmatch` behaves exactly like today's unanchored one in `events.py`. Pydantic's `Id` pattern also refuses the trailing newline (the probe checks it).
- `timezone(timedelta(0))` is the `UTC` singleton itself in CPython, so the given tests use `timezone(timedelta(0), "GMT")` for a zero offset that is a different object: `is_utc` must compare the offset, not the zone.
- The four input contracts' `request` schema today is `{"maxLength": 2000, "minLength": 1, "title": "Request", "type": "string"}`, and `TypeAdapter(Id).json_schema()` is `{"pattern": "^[0-9a-f]{32}$", "type": "string"}` (pinned by the given tests).
- The probe, run on today's code with only the new names supplied from its own oracle, prints `ok` for every check: today's callers already agree with the one rule. So the refactor must not change what any caller accepts.

## Requirements

### Part 1: `contracts/base.py`

- **R1.** `ID_PATTERN` is `^[0-9a-f]{32}$` and is `Id`'s pattern. `is_id` is true exactly for a `str` of 32 lowercase hexadecimal characters, with no trailing newline.
- **R2.** `MAX_REQUEST` is `2000` and `REQUEST_MESSAGE` is the one message, also reachable as `routing.route.REQUEST_MESSAGE`. `is_request` is true exactly for a `str` of at most 2000 characters that is not blank. The four input contracts' request schema is unchanged.
- **R3.** `is_contract_type` is true exactly for `Contract` and its subclasses.
- **R4.** `is_utc` is true exactly for a time whose offset is zero. `UTC_MESSAGE` is one object, also reachable as `contracts.approvals.UTC_MESSAGE`.

### Part 2: `conductor.times`

- **R5.** `DISPLAY_FORMAT` and `STORED_FORMAT` are the two formats; `display` and `stored` format a UTC time with them.
- **R6.** `display` and `stored` refuse a time with a non-zero offset, or no offset, with `ValueError(UTC_MESSAGE)`.

### Part 3: the callers

- **R7.** The event log, the store, the checkpoint status, the web app, the views and the CLI check ids only through `is_id`, and format times only through `times`. Every message and printed line is unchanged, and a run file whose name is not `<id>.jsonl` is still skipped when runs are listed.
- **R8.** Routing, the supervisor, the answer step and case files check requests only through `is_request`, and the four input contracts use `RequestText`. The registry and decision points check Contract types only through `is_contract_type`. Messages and their order are unchanged.

### Part 4: the rules

- **R9.** `contracts/base.py` imports nothing from the project, and `times.py` imports only `conductor.contracts.base`. `times.py` is listed in `scripts/critical_modules.txt`. Only the Scope's paths change; given files and existing tests stay byte-identical.
- **R10.** `contracts/base.py`, `times.py`, `views.py` and `evals/cases.py` are covered 100% (lines and branches), and the critical-module gate passes.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, both test files fail to import (`ImportError` for the new names in `contracts.base`, and no `times.display`). With names-only stubs every test fails.

| File | What it is |
|---|---|
| `tests/unit/test_contracts_base.py` | R1 to R4: the shared rules, the one message and the one schema (27 tests from 7 functions) |
| `tests/unit/test_times.py` | R5, R6: the two formats and the refusal (6 tests from 3 functions) |
| `docs/verification/probe-09j.py` | the probe, run by its path in Acceptance |

Given test count: **33**.

## Tests to write

In `tests/unit/test_shared_rules_more.py` (section `core`):
- R7: a runs folder holding an event file for one valid id and three files named `<id>.JSONL`, `<id>.jsonl.jsonl` and `<id>x.jsonl`: `EventLog.runs()` lists only the valid one.
- R7: the checkpoint status refuses an interrupt whose id is a `str` subclass holding a valid id, as today (the exact type check stays). Build it the way `tests/unit/test_checkpoint_status_cases.py` builds its interrupt cases.
- R8: `load_cases` refuses a request of 2001 characters and one of only spaces and tabs with the existing message, and accepts one of exactly 2000.
- R10: any branch of `contracts/base.py`, `times.py`, `views.py` or `evals/cases.py` the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- Messages are constant text plus identifiers. No message or printed line changes.
- `contracts` imports nothing from the project. `times.py` imports only `conductor.contracts.base`.
- Read the current time only through `clock.now()`. Nothing here reads the clock.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9j` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1342 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/contracts/base.py,*/conductor/times.py,*/conductor/views.py,*/conductor/evals/cases.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_contracts_base.py tests/unit/test_times.py --no-cov -q` | `33 passed` |
| `.venv/bin/python docs/verification/probe-09j.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_contracts_base.py tests/unit/test_times.py docs/verification/probe-09j.py src/conductor/config.py src/conductor/clock.py src/conductor/ids.py src/conductor/private.py src/conductor/acceptance.py src/conductor/prompts src/conductor/web/templates` | no output |
| `git diff 8174b92 --stat -- tests ':!tests/unit/test_contracts_base.py' ':!tests/unit/test_times.py' ':!tests/unit/test_shared_rules_more.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9j: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9j` (after writing progress) | `Reports OK.` |

The second diff row compares against 8174b92 (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/contracts/base.py src/conductor/times.py
git grep --untracked -n -E '\[0-9a-f\]\{32\}' -- src ':!src/conductor/contracts/base.py'
git grep --untracked -n -E '%Y-%m-%dT|%H:%M:%S' -- src ':!src/conductor/times.py'
git grep --untracked -n -E 'issubclass\(|utcoffset\(' -- src ':!src/conductor/contracts/base.py'
git grep --untracked -n -E 'len\(request\)|request: str = Field|"time must be UTC"|"a request must have' -- src ':!src/conductor/contracts/base.py'
git grep --untracked -n -E '^(from|import) (conductor|\.)' -- src/conductor/contracts/base.py
git grep --untracked -n -E '^import conductor|^from conductor[^.]|^from conductor\.[^c]|^from conductor\.c[^o]|^from conductor\.co[^n]|^from conductor\.con[^t]|^from conductor\.contracts( |\.[^b])' -- src/conductor/times.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Shared validation and presentation contracts`, with `--tests-before 1309 --given 33`.
