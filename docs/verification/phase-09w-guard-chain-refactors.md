# Verify Phase 9w: Guard-chain refactors for the complexity limits

Spec: `docs/phases/phase-09w-guard-chain-refactors.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09w-guard-chain-refactors.md`.

## First: establish that the coder ran

- No `## Phase 9w: ` entry in `docs/progress.md` and no Scope path changed since a838223: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09w-guard-chain-refactors.md docs/verification/phase-09w-guard-chain-refactors.md tests/unit/test_complexity_limits.py docs/verification/probe-09w.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff $(git log -1 --format=%h -- docs/phases/phase-09w-guard-chain-refactors.md)` plus untracked files. G5 and G6 use the spec's commit and a838223, so they hold either way.

The coder refactored six functions in five files, so that none is over the complexity limits and none answers differently.

## 1. Gates

N is `1614`. Given count: 5. `.venv/bin/python scripts/accept.py --phase 9w --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1619 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1467`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1619 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_complexity_limits.py --no-cov -q` | `5 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09w.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09w-guard-chain-refactors.md) --stat -- tests/unit/test_complexity_limits.py docs/verification/probe-09w.py` | no output |
| G6 | `git diff a838223 --stat -- src scripts tests pyproject.toml .claude ':!src/conductor/reports.py' ':!src/conductor/registry.py' ':!src/conductor/spotcheck.py' ':!src/conductor/cli/common.py' ':!src/conductor/routing/route.py' ':!tests/unit/test_complexity_limits.py' ':!.claude/skills/phase-architect/history.md' ':!.claude/skills/phase-architect/phase_status.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G8 | `grep -c '^## Phase 9w: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9w` | `Reports OK.` |

G1 includes the critical-module coverage check, which covers R6 for `reports.py`, `spotcheck.py` and `routing/route.py`.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_no_function_is_over_the_limits` (5 cases) | pass |
| R2 | probe check 1 | `ok` |
| R3 | probe check 2 | `ok` |
| R4 | probe checks 3 to 5 | `ok` |
| R5 | `tests/unit/test_route.py` within G1; `git diff a838223 -- tests` shows nothing but the given test | pass; as given |
| R6 | G1, G2 | as given |
| R7 | G5, G6, G7; search 7; `.venv/bin/python .claude/skills/phase-architect/code_map.py conductor.reports` and the other four modules, on the build and at a838223 | as given; silent; the same public names and signatures |

For R7's public names, run `code_map.py` for each of the five modules on the build and on a clone at a838223, and compare. A new public name, or a changed signature, is a finding.

Read each refactor:
- the checks run in today's order;
- every message is still a module constant or the same f-string;
- new helpers are private (`_`-named) and live in the same module;
- no behaviour was "fixed" along the way.

## 3. Probe

The probe is the given file `docs/verification/probe-09w.py` (G4). Its oracle is each module as it was at a838223, loaded from `git show` under another module name. Each check gives the old and new function the same inputs and compares the `repr` of the result, or the exception type and message:
1. `parse_review` on every review in `docs/reviews/`, then on one-change variants of them (a line dropped, doubled, blanked, swapped with the next, or edited by one character), 2000 trials in all;
2. `parse_progress` on 2000 pairs of adjacent entries from `docs/progress.md`, nine in ten of them with one change;
3. `spotcheck.verdict` on seven sample outputs and exit codes −1 to 7;
4. `registry._check_action` on 2000 actions, each the demo domain's first action with one field changed, with `seen`, the servers and the domain name varied;
5. `cli.common.state_text` on every combination of six statuses, approval id, escalation id and note, with `request_lines` and `escalation_lines` replaced by stubs in both modules;
6. the given test, run as a subprocess.

Each comparison also has a reach floor (distinct answers on the old side), so a probe that stopped reaching a branch fails. When a check fails, it prints up to three cases with the old and the new answer.

Before handover the architect ran the probe on today's code: checks 1 to 5 printed `ok` and check 6 printed `FAIL`, so the run reached `FAILURES 1`. Each of five one-line mutations of today's code (the spot checks S2 to S6 below) turned only its own comparison to `FAIL`.

A stop at its own `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/reports.py src/conductor/registry.py src/conductor/spotcheck.py src/conductor/cli/common.py src/conductor/routing/route.py
```

## 5. Spot checks

Make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09w`, then `rsync -a --delete src tests <scratch>/spot09w/`, and link `.venv`. The probe needs `git show a838223`, which the clone has. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=<scratch>/spot09w/src`. Before the next row, restore the copy with the same `rsync`.

The coder chose the refactors' shape, so the exact text of rows S2 to S6 is not known in advance. Each row names the behaviour to change. Find the one place in the coder's code that decides it, and change only that.

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | append a function `_extra(n: int) -> int` with six `if n == k: return k` lines and a final `return 7` (`src/conductor/spotcheck.py`) | `.venv/bin/python -m pytest 'tests/unit/test_complexity_limits.py::test_no_function_is_over_the_limits[spotcheck]' --no-cov -q` | `1 passed` | fails, `PLR0911` (7 > 6) |
| S2 | the `Approved deviations` line's problem names line 7 instead of 6 (`src/conductor/reports.py`) | `.venv/bin/python docs/verification/probe-09w.py` | `FAILURES 0` | check 1 (`parse_review`) `FAIL`, `FAILURES 1` |
| S3 | in `_one_entry`'s closing loop, a line that is only spaces counts as blank (`.strip() == ""`) (`src/conductor/reports.py`) | `.venv/bin/python docs/verification/probe-09w.py` | `FAILURES 0` | check 2 (`parse_progress`) `FAIL`, `FAILURES 1` |
| S4 | exit code 5 no longer gives `no test ran` (only 4 does) (`src/conductor/spotcheck.py`) | `.venv/bin/python docs/verification/probe-09w.py` | `FAILURES 0` | check 3 (`verdict`) `FAIL`, `FAILURES 1` |
| S5 | the `declared twice` check runs before the `not a valid name` check (`src/conductor/registry.py`) | `.venv/bin/python docs/verification/probe-09w.py` | `FAILURES 0` | check 4 (`_check_action`) `FAIL`, `FAILURES 1` |
| S6 | a rejected run shows its `note:` line when the note is not `None`, even when it is empty (`src/conductor/cli/common.py`) | `.venv/bin/python docs/verification/probe-09w.py` | `FAILURES 0` | check 5 (`state_text`) `FAIL`, `FAILURES 1` |
| S7 | replace `found.rule_ids[:MAX_PROBLEMS]` with `found.rule_ids[:MAX_PROBLEMS - 1]` (`src/conductor/routing/route.py`) | `.venv/bin/python -m pytest tests/unit/test_route.py::test_a_request_of_2000_characters_routes_and_a_wide_conflict_keeps_20 --no-cov -q` | `1 passed` | fails, `d19.ping` missing |

Notes for tracing:
- S1: Ruff counts seven `return` statements in `_extra`. The other functions in the file are under the limits, so this is the one finding.
- S2: every review with a bad line 6 now gets a different `Problem.line`.
- S3: an edit that inserts a space into an empty line between entries makes the old code refuse it with the unexpected-line message, and the changed code skip it.
- S4: the sample grid has exit code 5 for every output.
- S5: an action named `Echo` (not a valid name) with `seen = {"Echo"}` answered `not a valid name` and now answers `declared twice`.
- S6: the grid has notes `None`, `""` and `"a note"`, so the empty note shows the difference.
- S7: 21 domains match `ping`, and the escalation keeps 19 instead of 20 problems. The probe does not cover `route_request`. This row shows that the test does.

The architect ran S1 and S7 on today's code. S1 there gave two findings, because today's `verdict` is also over. It ran S2 to S6 as the same one-line edits of today's code, and each gave its "Broken" result. A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Any shape of refactor (a table of checks, private helpers, `match`), as long as the order of checks and every answer stay the same.
- A private constant that holds a check table.
- A short docstring on a new helper.

## 7. Out of scope

Each must be absent:
- A refactor of a 9x function or of the architect's tools.
- Any change to `pyproject.toml`, `tests/`, `scripts/` or `.claude/`.
- A new module, a new public name, or a changed signature, message or exception type.
- A behaviour change, even one that looks like a fix.
- A `noqa` or `pragma: no cover`.

## 8. Verdict

Write `docs/reviews/phase-09w-guard-chain-refactors.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9w`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9w` must print `Reports OK.`
