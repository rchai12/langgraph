# Verify Phase 9x: Complexity refactors and rules

Spec: `docs/phases/phase-09x-complexity-rules.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09x-complexity-rules.md`.

## First: establish that the coder ran

- No `## Phase 9x: ` entry in `docs/progress.md` and no Scope path changed since e92eadd: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09x-complexity-rules.md docs/verification/phase-09x-complexity-rules.md tests/unit/test_complexity_rules.py docs/verification/probe-09x.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff $(git log -1 --format=%h -- docs/phases/phase-09x-complexity-rules.md)` plus untracked files. G5 and G6 use the spec's commit and e92eadd, so they hold either way.

The spec has a correction 1 (2026-11-22): the routes moved into the private `_add_pages` and `_add_forms`, and `tests/unit/test_web_layout.py::test_create_app_only_registers_one_line_routes` got the exact edit it gives. Read it before judging `web/app.py`.

The coder refactored five functions in five files, so that none is over the complexity limits and none answers differently, then turned the rules on in `pyproject.toml`.

## 1. Gates

N is `1619`. Given count: 7. `.venv/bin/python scripts/accept.py --phase 9x --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1626 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1474`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1626 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_complexity_rules.py --no-cov -q` | `7 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09x.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09x-complexity-rules.md) --stat -- tests/unit/test_complexity_rules.py docs/verification/probe-09x.py` | no output |
| G6 | `git diff e92eadd --stat -- src scripts tests pyproject.toml .claude ':!src/conductor/config.py' ':!src/conductor/evals/report.py' ':!src/conductor/web/app.py' ':!scripts/check.py' ':!tests/integration/test_run_status_cases.py' ':!tests/unit/test_lint_rules.py' ':!tests/unit/test_web_layout.py' ':!pyproject.toml' ':!tests/unit/test_complexity_rules.py' ':!.claude/skills/phase-architect/history.md' ':!.claude/skills/phase-architect/phase_tools.py' ':!.claude/skills/phase-architect/SKILL.md'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G8 | `grep -c '^## Phase 9x: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9x` | `Reports OK.` |

G1 includes Ruff's lint step, now with the complexity rules, and the critical-module coverage check, which covers R8 for `config.py` and `web/app.py`.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_no_function_is_over_the_limits` (5 cases), `test_nothing_in_the_tree_is_over_the_limits` | pass |
| R2 | probe check 1 | `ok` |
| R3 | probe check 2 | `ok` |
| R4 | probe check 3 | `ok` |
| R5 | probe check 4; `tests/unit/test_web_layout.py::test_create_app_only_registers_one_line_routes` within G1; `git diff e92eadd -- tests/unit/test_web_layout.py` | `ok`; pass; exactly correction 1's replacement |
| R6 | probe check 5 | `ok` |
| R7 | `test_pyproject_turns_the_rules_on_at_the_limits`; `git diff e92eadd -- pyproject.toml tests/unit/test_lint_rules.py` | pass; exactly the two texts under the spec's "Design" |
| R8 | G1, G2 | as given |
| R9 | G5, G6, G7; searches 7 and 8; `git diff e92eadd -- tests` shows only the Scope's test edits and the given test; `.venv/bin/python .claude/skills/phase-architect/code_map.py conductor.config` and the same for `conductor.evals.report` and `conductor.web.app`, on the build and at e92eadd | as given; silent; the same public names and signatures |

For R9's public names, run `code_map.py` for each of the three modules on the build and on a clone at e92eadd, and compare. A new public name, or a changed signature, is a finding. For `scripts/check.py`, compare its top-level public `def` lines by reading the diff.

Read each refactor:
- the checks run in today's order;
- every message is still a module constant or the same f-string;
- new helpers are private (`_`-named) and live in the same module;
- in the test, the seven `assert` lines are unchanged and still follow the two `read_state` calls;
- no behaviour was "fixed" along the way.

## 3. Probe

The probe is the given file `docs/verification/probe-09x.py` (G4). Its oracle is each module as it was at e92eadd, loaded from `git show` under another module name. Each check gives the old and new code the same inputs and compares the `repr` of the result, the exception type and message, or the printed output:
1. `get_settings` on 2000 environments, each the valid base with zero to three settings changed (Ollama host, model, timeouts, decided-by, demo, web port, MCP entries, data folder);
2. `compare_lines` on 2000 report pairs, each a base report with zero to three changes to either side (model, digests, templates, case files, case numbers, added, removed or reordered cases);
3. `scripts/check.py` `main` on 12 argument lists, 6 run-code scripts, coverage with and without a gap, and a JUnit report with and without a failure (288 runs). It compares the return or exit code, the commands run (temporary folders masked) and everything printed;
4. `create_app`'s route table: type of guard, its hosts, the disabled docs, and each route's path, methods, name, signature and whether it is async;
5. the refactored test's `assert` statements against e92eadd's, then the test itself, run as a subprocess;
6. the given test, run as a subprocess.

Checks 1 to 3 have a reach floor (distinct answers on the old side), so a probe that stopped reaching a branch fails. When a check fails, it prints up to three cases with the old and the new answer.

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
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/config.py src/conductor/evals/report.py src/conductor/web/app.py tests/integration/test_run_status_cases.py
git grep --untracked -n -E 'noqa: *[A-Z0-9, ]*(C901|PLR09)' -- src tests scripts .claude
```

## 5. Spot checks

Make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09x`, then `rsync -a --delete src tests scripts <scratch>/spot09x/`, copy `pyproject.toml` over, and link `.venv`. The probe needs `git show e92eadd`, which the clone has. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=<scratch>/spot09x/src`. Before the next row, restore the copy the same way.

The coder chose the refactors' shape, so the exact text of rows S2 to S6 is not known in advance. Each row names the behaviour to change. Find the one place in the coder's code that decides it, and change only that.

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | append a function `_extra(n: int) -> int` with six `if n == k: return k` lines and a final `return 7` (`src/conductor/config.py`) | `.venv/bin/python -m pytest 'tests/unit/test_complexity_rules.py::test_no_function_is_over_the_limits[config]' --no-cov -q` | `1 passed` | fails, `PLR0911` (7 > 6) |
| S2 | the model timeout is refused above 3599 instead of 3600 (`src/conductor/config.py`) | `.venv/bin/python docs/verification/probe-09x.py` | `FAILURES 0` | check 1 (`get_settings`) `FAIL`, `FAILURES 1` |
| S3 | the model line compares the names after `.strip()` (`src/conductor/evals/report.py`) | `.venv/bin/python docs/verification/probe-09x.py` | `FAILURES 0` | check 2 (`compare_lines`) `FAIL`, `FAILURES 1` |
| S4 | a step that did not run shows `skipped` instead of `not run` in the summary (`scripts/check.py`) | `.venv/bin/python docs/verification/probe-09x.py` | `FAILURES 0` | check 3 (`main`) `FAIL`, `FAILURES 1` |
| S5 | the edit form's path becomes `/approvals/{approval_id}/change` (`src/conductor/web/app.py`) | `.venv/bin/python docs/verification/probe-09x.py` | `FAILURES 0` | check 4 (routes) `FAIL`, `FAILURES 1` |
| S6 | replace `assert closed == [1, 1]` with `assert len(closed) == 2` (`tests/integration/test_run_status_cases.py`) | `.venv/bin/python docs/verification/probe-09x.py` | `FAILURES 0` | check 5 (assertions) `FAIL`, `FAILURES 1` |
| S7 | `max-complexity = 11` in `[tool.ruff.lint.mccabe]` (`pyproject.toml`) | `.venv/bin/python -m pytest tests/unit/test_complexity_rules.py::test_pyproject_turns_the_rules_on_at_the_limits --no-cov -q` | `1 passed` | fails, `max-complexity` 11 |

Notes for tracing:
- S1: Ruff counts seven `return` statements in `_extra`. The other functions in the file are under the limits, so this is the one finding.
- S2: the environments include `CONDUCTOR_MODEL_TIMEOUT=3600`, which today is accepted and is now refused.
- S3: one model variant is `m:1 ` with a trailing space; today it gives `changed: model`, and the changed code gives no model line.
- S4: the runs that fail at the first step leave three steps not run, and the summary prints them.
- S5: the eighth of the ten routes has the path `/approvals/{approval_id}/edit` at e92eadd.
- S6: the assertions are compared as text, so any change to one of them shows.
- S7: the test pins the whole `[tool.ruff.lint]` table, so `11` differs from `10`. `tests/unit/test_lint_rules.py::test_the_rule_selection_is_exact` fails the same way.

The architect ran S1 and S7 on today's code. S1 there gave two findings, because today's `get_settings` is also over. S7 there failed on the whole table, because today's `pyproject.toml` has no rules yet. It ran S2 to S6 as the same one-line edits of today's code, and each gave its "Broken" result. A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Any shape of refactor (a table of checks, private helpers, `match`), as long as the order of checks and every answer stay the same.
- A private constant that holds a check table.
- Module-level private wrapper classes in the test, or a private helper that makes them.
- A short docstring on a new helper.
- A deleted private helper that the refactor left unused.

## 7. Out of scope

Each must be absent:
- A refactor of the architect's tools or of the 9w files.
- Route helpers other than `_add_pages` and `_add_forms`, or routes registered out of today's order.
- Any rule beyond the four, or a different limit.
- Any change to `.claude/` or a given file, or a test edit outside the three Scope rows.
- A new module, a new public name, or a changed signature, message or exception type.
- A behaviour change, even one that looks like a fix.
- A new `noqa` or `pragma: no cover`.

## 8. Verdict

Write `docs/reviews/phase-09x-complexity-rules.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9x`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9x` must print `Reports OK.`
