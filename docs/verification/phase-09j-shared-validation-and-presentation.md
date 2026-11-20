# Verify Phase 9j: Shared validation and presentation contracts

Spec: `docs/phases/phase-09j-shared-validation-and-presentation.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09j-shared-validation-and-presentation.md`.

## First: establish that the coder ran

- No `## Phase 9j: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09j-shared-validation-and-presentation.md docs/verification/phase-09j-shared-validation-and-presentation.md tests/unit/test_contracts_base.py tests/unit/test_times.py docs/verification/probe-09j.py` must succeed: the gates judge against a committed baseline.

The coder:
- added `ID_PATTERN`, `MAX_REQUEST`, `REQUEST_MESSAGE`, `RequestText`, `UTC_MESSAGE`, `is_id`, `is_request`, `is_contract_type` and `is_utc` to `src/conductor/contracts/base.py`, and moved `UTC_MESSAGE` out of `approvals.py`;
- wrote `src/conductor/times.py` (`DISPLAY_FORMAT`, `STORED_FORMAT`, `display`, `stored`) and listed it in `scripts/critical_modules.txt`;
- replaced every copy of the id check, the request check, the Contract-type check and the time formats in the callers the spec lists.

## 1. Gates

N is `1309`. Given count: 33. `.venv/bin/python scripts/accept.py --phase 9j --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1342 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/contracts/base.py,*/conductor/times.py,*/conductor/views.py,*/conductor/evals/cases.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_contracts_base.py tests/unit/test_times.py --no-cov -q` | `33 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09j.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_contracts_base.py tests/unit/test_times.py docs/verification/probe-09j.py src/conductor/config.py src/conductor/clock.py src/conductor/ids.py src/conductor/private.py src/conductor/acceptance.py src/conductor/prompts src/conductor/web/templates` | no output |
| G6 | `git diff 8174b92 --stat -- tests ':!tests/unit/test_contracts_base.py' ':!tests/unit/test_times.py' ':!tests/unit/test_shared_rules_more.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9j: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9j` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_an_id_is_32_lowercase_hex` (7 cases), `test_the_id_pattern_is_one_rule`; probe check 1 | pass; `ok` |
| R2 | `test_a_request_has_1_to_2000_characters` (7 cases), `test_the_request_rule_has_one_message_and_one_schema`; probe check 2 | pass; `ok` |
| R3 | `test_a_contract_type` (6 cases); read `registry.py` and `llm/points.py` | pass; both call `is_contract_type` |
| R4 | `test_a_utc_time` (4 cases), `test_the_utc_message_is_one_rule`; the two cases of `test_a_time_that_is_not_utc_is_refused` in `tests/unit/test_events.py` (in G1) | pass |
| R5 | `test_the_display_and_stored_formats`, `test_a_zero_offset_time_is_utc`; probe check 3 | pass; `ok` |
| R6 | `test_a_time_that_is_not_utc_is_refused` (4 cases); probe check 4 | pass; `ok` |
| R7 | probe checks 1 and 3; `tests/e2e/test_cli_runs.py`, `tests/unit/test_views.py` and the web page tests (in G1); the coder's run-file and `str`-subclass tests; searches 8 to 11; read each call site in the spec's Part 3 table | pass; `ok`; silent; each site calls the shared rule and keeps its own message, and `graph/status.py` keeps `type(value) is not str` |
| R8 | probe check 2; `tests/unit/test_route.py`, `tests/unit/test_eval_cases.py` (in G1); the coder's case-file test; search 11; read the four request fields and the four request checks | pass; `ok`; silent; each check is `is_request` in the same place as before, each field is `RequestText` |
| R9 | searches 12 and 13; read `scripts/critical_modules.txt`; G5, G6, G7 | silent; `times.py` listed; as given |
| R10 | G1 (the critical gate), G2 | as given |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09j.py` (G4). It checks:
- 200 random ids (a valid id, or one with one change: a character replaced, dropped or added, upper case, a trailing newline, a leading space): `is_id`, the `Id` contract, `EventLog.append` (with `RUN_ID_MESSAGE`) and `Store.acquire` each accept exactly the ids the oracle accepts, and `EventLog.runs` skips a run file named after a refused one; at least 40 of each kind are reached;
- 150 random requests (letters, or empty, blank, padded with blanks, exactly 2000, or 2001 characters): `is_request`, `route_request` (`REQUEST_MESSAGE`) and `load_cases` (the case file's message) each refuse exactly what the oracle refuses; at least 40 of each kind;
- 60 random UTC times from 1970 to 2100 with microseconds: `times.display` and `times.stored` match the oracle's own formatting, and so do the event line's `at`, `conductor runs list` and `conductor runs show`;
- 100 random times with a non-zero offset or none: both formats raise `ValueError("time must be UTC")`.

Before handover the architect ran it on the predecessor with only the new names supplied from the probe's own oracle: every check printed `ok`. So a check that fails on the build points at a caller whose behaviour changed.

A stop at its own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

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

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09j`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09j`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | `fullmatch` becomes `match` (`is_id`) | `tests/unit/test_contracts_base.py::test_an_id_is_32_lowercase_hex[newline]` | `False` | `True` |
| S2 | drop the `isinstance(value, str)` test (`is_id`) | `tests/unit/test_contracts_base.py::test_an_id_is_32_lowercase_hex[none]` | `False` | `TypeError` |
| S3 | `value.strip() != ""` becomes `value != ""` (`is_request`) | `tests/unit/test_contracts_base.py::test_a_request_has_1_to_2000_characters[blank]` | `False` | `True` |
| S4 | `<= MAX_REQUEST` becomes `< MAX_REQUEST` (`is_request`) | `tests/unit/test_contracts_base.py::test_a_request_has_1_to_2000_characters[longest]` | `True` | `False` |
| S5 | drop the `isinstance(value, type)` test (`is_contract_type`) | `tests/unit/test_contracts_base.py::test_a_contract_type[instance]` | `False` | `TypeError` |
| S6 | compare `moment.tzinfo is UTC` instead of the offset (`is_utc`) | `tests/unit/test_contracts_base.py::test_a_utc_time[zero-offset]` | `True` | `False` |
| S7 | drop the UTC check from `display` | `tests/unit/test_times.py::test_a_time_that_is_not_utc_is_refused[plus-two-display]` | `ValueError` | `DID NOT RAISE` |
| S8 | `stored` formats with `DISPLAY_FORMAT` | `tests/unit/test_times.py::test_the_display_and_stored_formats` | `'2026-11-20T09:05:07.000123Z'` | `'2026-11-20T09:05:07Z'` |
| S9 | `approvals.py` defines `UTC_MESSAGE = "time must be UTC"` instead of importing it | `tests/unit/test_contracts_base.py::test_the_utc_message_is_one_rule` | `True` | `False` |
| S10 | `routing/route.py` defines `REQUEST_MESSAGE` as its own literal instead of importing it | `tests/unit/test_contracts_base.py::test_the_request_rule_has_one_message_and_one_schema` | `True` | `False` |
| S11 | `show` prints `times.display(event.at)` (`cli/main.py`) | `tests/e2e/test_cli_runs.py::test_show_a_run` | `2026-10-25T21:30:01.250000Z` | `2026-10-25T21:30:01Z` |
| S12 | drop the `is_id` check from the approval page route (`web/app.py`) | `tests/e2e/test_web_pages_more.py::test_a_capital_id_is_not_found_without_opening_the_store[/approvals/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA]` | `(404, 'Not found')` | `the store was opened` |

Notes for tracing. S1: with `$` in the pattern, `match` stops before a trailing newline, so `hex + "\n"` matches; `fullmatch` needs the newline consumed. S2 and S5: `re.fullmatch(None)` and `issubclass(instance, Contract)` raise `TypeError`. S6: the test's zero-offset zone is `timezone(timedelta(0), "GMT")`, a separate object; CPython returns the `UTC` singleton for an unnamed zero offset, which is why the test names it. S9 and S10: two equal string constants compiled in two modules are separate objects (text with spaces is not interned), so `is` fails; searches 11 would also match. S12: the capital id reaches `Store(...)`, whose replacement raises `AssertionError`. Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- `store._stamp` and `views._when` kept as one-line wrappers or replaced by the calls.
- `graph/supervisor.py` and `planning/answer.py` importing `REQUEST_MESSAGE` from `routing.route` or from `contracts.base`.
- `is_id` compiling `ID_PATTERN` once at module level under any private name.
- `times.py` sharing one private helper for the check and the `strftime`.
- Extra behaviour tests in `tests/unit/test_shared_rules_more.py`.

## 7. Out of scope

Each must be absent:
- Any changed message, printed line, event line, stored row, JSON schema, or check order.
- `RequestText` refusing blank text, or any other field's bounds changed.
- Moving the reply bound, the 64-hex form token, `Sha256`, `Name`, `ActionName`, `RuleId`, the case id pattern, or the report file name format.
- Splitting `cli/main.py` or `web/app.py`, or moving route bodies out of `create_app`.
- Converting a time to UTC, or any change to `clock.py`, `ids.py`, `config.py`, `private.py`, `acceptance.py`, the prompts or the web templates.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09j-shared-validation-and-presentation.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9j`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9j` must print `Reports OK.`
