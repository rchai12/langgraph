# Phase 9x: Complexity refactors and rules

## Corrections

**2026-11-22, correction 1 (a spec error, not the coder's).** The coder stopped, correctly, on R1 for `create_app`. `tests/unit/test_web_layout.py::test_create_app_only_registers_one_line_routes` (Phase 9n) requires all ten one-line route functions to be nested directly in `create_app`. Ruff adds 1 for each nested function, so `create_app` cannot get under `C901` 10 while that test stands. The architect had not searched the tests for one that pins `create_app`'s shape.

Decided with the owner (2026-11-22): the ten routes move into two private helpers in `src/conductor/web/app.py`, and the 9n test is edited to count them there. The test keeps its intent: ten one-line `return` routes and no `try`.
- `_add_pages(api: FastAPI, ctx: Context) -> None` registers the four `GET` pages (`/`, `/approvals/{approval_id}`, `/escalations/{escalation_id}`, `/runs/{run_id}`), as nested one-line route functions, in today's order and with today's names.
- `_add_forms(api: FastAPI, ctx: Context) -> None` registers the six `POST` forms (`resume`, `approve`, `reject`, `edit`, `retry`, `cancel`) the same way, in today's order.
- `create_app` builds the context (your private `_context` helper may stay), creates `FastAPI`, calls `_add_pages(api, ctx)` and then `_add_forms(api, ctx)`, and returns the `HostGuard`. Routes register in today's order, which probe check 4 compares.
- In `tests/unit/test_web_layout.py`, replace the whole function

```python
def test_create_app_only_registers_one_line_routes() -> None:
    body = top_functions("app")["create_app"].body
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    routes = [node for node in body if isinstance(node, kinds)]
    assert len(routes) == 10
    assert [len(route.body) for route in routes] == [1] * 10
    assert {type(route.body[0]).__name__ for route in routes} == {"Return"}
    assert [
        node for node in ast.walk(top_functions("app")["create_app"]) if isinstance(node, ast.Try)
    ] == []
```

with exactly

```python
def test_create_app_only_registers_one_line_routes() -> None:
    found = top_functions("app")
    registrars = [found[name] for name in ("create_app", "_add_pages", "_add_forms")]
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    routes = [node for function in registrars for node in function.body if isinstance(node, kinds)]
    assert [len(route.body) for route in routes] == [1] * 10
    assert {type(route.body[0]).__name__ for route in routes} == {"Return"}
    tries = [node for function in registrars for node in ast.walk(function)]
    assert [node for node in tries if isinstance(node, ast.Try)] == []
```

The test count does not change, so N (`1619`), the given count, the collected count (`1626`) and the section counts stay as they are. `tests/unit/test_web_layout.py` joins the Scope and the protected-diff exclusions, and so does the architect's own `.claude/skills/phase-architect/SKILL.md`, edited with this correction.

Checked on a copy of your uncommitted first pass, with the routes moved into the two helpers and the test edited: `_add_pages` has complexity 5, `_add_forms` 7, and `create_app` is under the limit. `ruff check .` passes. `tests/unit/test_web_layout.py`, the web tests and the given test give `172 passed`. The probe ends at `FAILURES 0`. On your first pass as it stands, the edited test fails with `KeyError: '_add_pages'`.

Live again: every Acceptance row. Keep your first pass. Move the routes, make the test edit, and run Acceptance. Then rewrite your 9x progress entry with `scripts/progress.py` (it replaces the entry), removing the `Stopped:` item and the `create_app` deviation.

## Goal

The last five functions over the complexity limits are brought under them, and none of them answers any differently. Then Ruff's complexity rules go on in `pyproject.toml` at explicit limits, so `scripts/check.py`'s lint step refuses any function over them from now on.

| Function | Today | Over |
|---|---|---|
| `config.get_settings` | complexity 15, 14 branches | C901, PLR0912 |
| `evals.report.compare_lines` | complexity 14, 13 branches | C901, PLR0912 |
| `web.app.create_app` | complexity 11 | C901 |
| `scripts/check.py` `main` | complexity 15, 15 branches | C901, PLR0912 |
| `tests/integration/test_run_status_cases.py::test_the_read_begins_before_both_selects_and_closes` | complexity 11 | C901 |

The limits are `C901` 10 (McCabe complexity), `PLR0911` 6 returns, `PLR0912` 12 branches and `PLR0915` 50 statements.

Decided with the owner (2026-11-22, for Phase 9r):
- **Complexity joins the gates at Ruff's defaults:** `C901` at 10, and `PLR0911`, `PLR0912` and `PLR0915` at 6, 12 and 50. Argument-count rules stay out.

Decided with the owner (2026-11-22, for Phase 9w):
- **Two slices.** 9w did the six guard-chain functions. 9x does the five functions above, and then adds the rules to `pyproject.toml`.
- **The architect refactors the three functions in its own tools** (`.claude/skills/phase-architect/phase_tools.py`) with this spec. That refactor is committed with this spec. The coder never edits `.claude/`.

Decided by the architect, within those answers:
- The limits are written out in `pyproject.toml` (`[tool.ruff.lint.mccabe]` and `[tool.ruff.lint.pylint]`), not left to Ruff's defaults, so a Ruff upgrade cannot move them. The exact text is under "Design".
- The coder chooses the shape of each refactor, for example a table of checks walked in order, or a private helper per part. The probe judges only behaviour, and the given test only the limits.
- Every public name, signature, message constant and message text stays as it is. New private helpers (`_`-named) are allowed in the same module, and nowhere else. A private helper left unused by a refactor may be deleted.
- The checks keep their order. Where two problems are found, they are joined in today's order, so each input gets the same `Settings`, exception, lines or printed output as before.
- The refactored test keeps its name, and its seven `assert` statements stay word for word. Its wrapper classes may move to module level as private classes (`_Cursor`, `_Connection`), or into a helper.
- `tests/unit/test_lint_rules.py::test_the_rule_selection_is_exact` pins the whole `[tool.ruff]` table, so it gets the one edit given under "Design".
- The 9w given test `tests/unit/test_complexity_limits.py` stays as it is. The new given test covers the whole tree.

## Read first

- The given files below, in full: they are the contract.
- The five functions, and the private helpers they call: `validation_problems` in `config.py`; `_moved`, `_differs`, `_shown` in `evals/report.py`; `home`, `approval_page`, `escalation_page`, `run_page`, `post_resume`, `post_approval`, `post_escalation` and `Context` in `web/app.py`; `steps`, `_run_one_section`, `_critical_coverage`, `_print_table`, `_show_tail`, `_quiet_dir`, `_log_name` in `scripts/check.py`.
- `tests/unit/test_config*.py`, `tests/unit/test_eval*.py`, `tests/unit/test_web*.py`, `tests/unit/test_check_script*.py`, and `tests/integration/test_run_status_cases.py`.
- `docs/testing.md` ("Critical modules"): `config.py` and `web/app.py` are on the list.

## Starting state

Phase 9w is built and verified, and everything is committed at e92eadd: N is `1619`. **Sections: scripts 30, cli 122, core 1467.** No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/config.py` | `get_settings` refactored (Part 1) |
| `src/conductor/evals/report.py` | `compare_lines` refactored (Part 1) |
| `src/conductor/web/app.py` | `create_app` refactored (Part 1) |
| `scripts/check.py` | `main` refactored (Part 1) |
| `tests/integration/test_run_status_cases.py` | `test_the_read_begins_before_both_selects_and_closes` refactored (Part 1) |
| `pyproject.toml` | the rules and the limits (Part 2) |
| `tests/unit/test_lint_rules.py` | the expected table in `test_the_rule_selection_is_exact` (Part 2) |
| `tests/unit/test_web_layout.py` | `test_create_app_only_registers_one_line_routes` counts the routes in `create_app`, `_add_pages` and `_add_forms` (correction 1) |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- The architect's tools and the 9w files: they are already under the limits.
- Any other rule: no `PLR0913`, `PLR0917` or other new selection.
- A new module, a new public name, or a changed signature, message or exception type.
- A `noqa` or `pragma: no cover` added anywhere.
- Fixing anything the probe shows as odd but unchanged. Behaviour stays as it is, even where it looks wrong.
- New tests, or edits to tests other than the three Scope rows. The existing tests must pass unchanged.
- Any change to `.claude/`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the five refactors

- `get_settings` builds `Settings`, turns a `ValidationError` or the environment's `SettingsError` into one `SettingsError`, then collects problems in this order: Ollama host, model, model timeout, decided-by, demo, MCP timeout, web port, then each MCP key in sorted order (its name, then its command line). One way under the limits is a private check per setting, or a table of (label, message, test) rows.
- `compare_lines` emits the model line, the digest line, the template lines, the case-file lines, the moved lines for shared cases in the current report's order, then the added and the removed cases, or `["no change"]`. One way is a private helper per kind of line.
- `create_app` builds the `Context`, then registers ten routes. Each nested route function adds to the function's complexity. The routes move into `_add_pages` and `_add_forms` (correction 1).
- `main` in `scripts/check.py` parses the arguments, runs one section, checks `--first` names, runs the steps until one fails, then prints the summary. One way is a private helper for the `--first` check, one for the step loop, and one for the summary.
- The test wraps `sqlite3.connect` to record each SQL statement and each close. Its two wrapper classes are what push it over.

### Part 2: the rules

In `pyproject.toml`, replace the `[tool.ruff.lint]` table with exactly:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ARG", "C901", "PLR0911", "PLR0912", "PLR0915"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-returns = 6
max-branches = 12
max-statements = 50
```

In `tests/unit/test_lint_rules.py`, replace the line `"lint": {"select": ["E", "F", "I", "B", "UP", "ARG"]},` in `test_the_rule_selection_is_exact` with:

```python
        "lint": {
            "select": ["E", "F", "I", "B", "UP", "ARG", "C901", "PLR0911", "PLR0912", "PLR0915"],
            "mccabe": {"max-complexity": 10},
            "pylint": {"max-returns": 6, "max-branches": 12, "max-statements": 50},
        },
```

Do Part 2 last. With the rules on, `.venv/bin/python -m ruff check .` lists whatever is still over.

## Facts

Checked on 2026-11-22 with the project's Python 3.12 and Ruff 0.17.2, outside the repository:
- `ruff check --select C901,PLR0911,PLR0912,PLR0915` with the limits above reports exactly the eight findings in the five functions above. The architect's three (`missing_imports`, `lint`, `main` in `phase_tools.py`) are refactored in this spec's commit, and the tools give the same answers as before.
- With the `pyproject.toml` text above, a plain `ruff check .` reports the same findings as the explicit flags. `docs/` stays excluded, so probes are not checked.
- The probe loads each module as it was at e92eadd under another name and compares answers. On today's code its five comparisons print `ok`, and its last check (the given test) prints `FAIL`, so the run reaches `FAILURES 1`.
- Reach on today's code: 89 distinct `get_settings` answers over 2000 environments, 72 distinct `compare_lines` line shapes over 2000 report pairs, 23 distinct `main` endings over 288 runs, 10 routes, and 7 assertions in the test. The probe's floors are 60, 20, 15, 10 routes and 7 assertions.
- Five one-line mutations of today's code each turned exactly their own comparison to `FAIL`: the model timeout's limit 3600 made 3599, the model compared after `strip()`, `not run` made `skipped` in the summary, the edit route's path changed, and `assert closed == [1, 1]` made `assert len(closed) == 2`.

## Requirements

### Part 1: the limits

- **R1.** No function in the five Scope source files is over `C901` 10, `PLR0911` 6, `PLR0912` 12 or `PLR0915` 50, and nothing in the tree is (the given test).

### Part 2: the same answers

- **R2.** `get_settings` gives the same `Settings` or `SettingsError` as at e92eadd for every probe environment (probe check 1).
- **R3.** `compare_lines` gives the same lines as at e92eadd for every probe report pair (probe check 2).
- **R4.** `scripts/check.py` `main` returns, exits, runs and prints the same as at e92eadd for every probe argument list and run outcome (probe check 3).
- **R5.** `create_app` registers the same routes, with the same paths, methods, names and signatures, behind the same host guard (probe check 4).
- **R6.** The refactored test keeps its name and its seven assertions word for word, and passes (probe check 5).

### Part 3: the rules

- **R7.** `pyproject.toml` turns `C901`, `PLR0911`, `PLR0912` and `PLR0915` on at the limits, in the exact text under "Design", and `test_the_rule_selection_is_exact` pins it (the given test; `tests/unit/test_lint_rules.py`).
- **R8.** The suite collects N + 7 tests and every one passes. Sections: `scripts 30`, `cli 122`, `core 1474`. Every line and branch of `config.py` and `web/app.py` stays covered.
- **R9.** Only the Scope's paths change; given files stay byte-identical. No public name is added or removed. No `noqa` names a complexity rule anywhere, and there is no `noqa` or `pragma: no cover` in the four Scope files that have none today (all but `scripts/check.py`, whose `__main__` line keeps its pragma).

## Given files

Committed with this spec. Do not change them; if a given test fails, the work is not finished. Before your change, all 7 given tests fail: each named file has a function over the limits, the tree has them, and `pyproject.toml` does not turn the rules on.

| File | What it is |
|---|---|
| `tests/unit/test_complexity_rules.py` | R1, R7: no finding in each of the five files, none in the tree, and the exact `[tool.ruff.lint]` table (7 tests from 3 functions) |
| `docs/verification/probe-09x.py` | the probe, run by its path in Acceptance |

Given test count: **7**.

## Tests to write

None. This phase changes no behaviour. R2 to R9 are checked by the probe, the existing tests, the coverage gate, the protected diffs and the searches.

## Rules for this phase

- A refactor changes no answer. If an existing test or a probe comparison fails, the refactor is wrong. Find the input from the lines the probe prints, and keep today's order of checks.
- When a probe check prints `FAIL`, the lines above it give up to three cases with the old and the new answer.
- Only the three test edits in the Scope. The refactored test's assertions stay word for word.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9x` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against e92eadd (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1626 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1474`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1626 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_complexity_rules.py --no-cov -q` | `7 passed` |
| `.venv/bin/python docs/verification/probe-09x.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09x-complexity-rules.md) --stat -- tests/unit/test_complexity_rules.py docs/verification/probe-09x.py` | no output |
| `git diff e92eadd --stat -- src scripts tests pyproject.toml .claude ':!src/conductor/config.py' ':!src/conductor/evals/report.py' ':!src/conductor/web/app.py' ':!scripts/check.py' ':!tests/integration/test_run_status_cases.py' ':!tests/unit/test_lint_rules.py' ':!tests/unit/test_web_layout.py' ':!pyproject.toml' ':!tests/unit/test_complexity_rules.py' ':!.claude/skills/phase-architect/history.md' ':!.claude/skills/phase-architect/phase_tools.py' ':!.claude/skills/phase-architect/SKILL.md'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9x: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9x` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Complexity refactors and rules`, with `--tests-before 1619 --given 7`.
