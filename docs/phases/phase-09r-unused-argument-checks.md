# Phase 9r: Unused-argument checks

## Goal

Ruff checks for unused arguments from this phase on. The selection gains `ARG`, and each of today's 230 findings is fixed in a way that changes no behaviour. Afterwards `scripts/check.py` refuses a new unused argument. A `noqa` may hide one only where the name is a contract: an MCP tool's schema, a fixture pytest resolves by name, or a parameter some call passes by keyword. Complexity checks come next, in Phase 9w.

Decided with the owner (2026-11-22):
- **Unused arguments and complexity both join the gates, in two slices.** This phase adds `ARG`. Phase 9w adds `C901` at 10 and `PLR0911`, `PLR0912` and `PLR0915` at their defaults (6, 12, 50) and refactors the 13 functions over them. Argument-count rules (`PLR0913`, `PLR0917`) stay out: `decide()` and the MCP tool schemas fix those counts.
- **An unused argument that an interface requires is kept by name, never by exemption.** Rename it `_name` when nothing passes it by keyword. A fixture a test requests only for its setup moves into `@pytest.mark.usefixtures`. A per-line `# noqa: ARG00n` stands only where the name is a contract. No `per-file-ignores`, no file-level `# ruff: noqa`, and no setting that widens what Ruff treats as unused.

Decided by the architect, within those answers:
- The repair rules below are exact. The probe and the given test check them, so the coder has no other choice to make.
- Unused `tmp_path` and `monkeypatch` are dropped from tests and fixtures rather than kept as `usefixtures`. Neither does anything until it is used. An import that only their annotation used goes with them.
- `wait_escalation` in `src/conductor/graph/nodes.py` drops its `config` parameter. LangGraph passes `config` by that name only to a node that declares it, so `_config` would break the node. `interrupt()` reads its config from context, not from the parameter.
- `NoRunner.run` and the six CLI `work` closures rename their unused parameters with `_`. Every caller passes them by position: `runner.run(action, args)` in `src/conductor/graph/steps.py` and `src/conductor/runtime.py`, and `work(settings, …)` in `src/conductor/cli/common.py`.
- The given test also refuses a bare `# noqa` and a file-level `# ruff: noqa` anywhere. Neither exists today.

## Read first

- The given files below, in full: they are the contract.
- `pyproject.toml` (`[tool.ruff]`), `src/conductor/cli/common.py` (`with_store`, `with_runtime`), `src/conductor/runtime.py` (`NoRunner`), and `wait_escalation` in `src/conductor/graph/nodes.py`.
- `tests/fake_finances_server.py`: its `@server.tool` functions mirror the finances server's tool schemas, so their parameter names are the schema.
- `docs/testing.md` rule 9.

## Starting state

Phase 9v is built and verified, and everything is committed at 6b26679: N is `1597`. **Sections: scripts 30, cli 122, core 1445.** `.venv/bin/python -m ruff check --select ARG .` reports 230 findings: 9 in `src/`, 221 in `tests/`, none in `scripts/` or `.claude/`. No new dependency.

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | `"ARG"` joins `[tool.ruff.lint] select` (Part 1) |
| `src/conductor/cli/approvals.py`, `src/conductor/cli/escalations.py`, `src/conductor/cli/main.py`, `src/conductor/graph/nodes.py`, `src/conductor/runtime.py` | the nine source findings (Part 2) |
| every file under `tests/` with a finding (53 today) | the test findings (Part 3) |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- Phase 9w's complexity rules and refactors, and any other rule (`PLR0913`, `PLR0917`, `D`, `ANN`, `SIM`, …).
- `per-file-ignores`, `extend-ignore`, `ignore`, a `[tool.ruff.lint.flake8-unused-arguments]` table, a changed `dummy-variable-rgx`, or a new `extend-exclude`.
- Removing an unused parameter from a function other than a test or fixture (`tmp_path` and `monkeypatch` only) or `wait_escalation`. Changing a fake's arity changes what its callers may send.
- Renaming a parameter to anything but `_` plus its old name (not `_`, not `unused`).
- Using an argument to silence Ruff (`del limit`, `_ = limit`, an `assert`).
- Changing a test body, a test name, a parameter set, or a fake MCP tool's parameter names. Changing `with_store`, `with_runtime` or the `Runner` call shape.
- Any change to `scripts/`, `.claude/`, `tests/conftest.py`, `tests/support.py`, `tests/sections.toml`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new. Ruff 0.17.2 is installed.

## Design

### Part 1: the selection

`[tool.ruff.lint]` becomes `select = ["E", "F", "I", "B", "UP", "ARG"]`, and nothing else in `[tool.ruff]` changes. The given test pins the whole table.

### Part 2: the source findings

| Where | Finding | Repair |
|---|---|---|
| `cli/approvals.py`, two `work` closures | `settings` | `_settings` |
| `cli/escalations.py`, two `work` closures | `settings` | `_settings` |
| `cli/main.py`, `work` in `ask` and in `resume` | `settings` | `_settings` |
| `graph/nodes.py`, `wait_escalation` | `config` | delete the parameter |
| `runtime.py`, `NoRunner.run` | `action`, `args` | `_action`, `_args` |

### Part 3: the test findings

Take each finding from `.venv/bin/python -m ruff check --select ARG --output-format concise tests`. Apply the first rule that fits:

1. **A test function** (a module-level `test_…`, or one in a `Test…` class) or a **fixture** (`@pytest.fixture`), whose unused parameter is `tmp_path` or `monkeypatch`: delete the parameter. Delete an import only its annotation used.
2. **A test function** whose unused parameter is any other fixture (`db`, `replies`, `model`, `cases`, `port`, `time`, …): delete the parameter and name the fixture in `@pytest.mark.usefixtures(...)` on that test. Add it to the test's existing `usefixtures` mark if it has one.
3. **A fixture** whose unused parameter is another fixture it needs for its setup (`time` in `db` in `tests/unit/test_store.py`): keep the name and add `# noqa: ARG001` to that parameter's line.
4. **A `@server.tool` function** in `tests/fake_finances_server.py`: keep the name and add `# noqa: ARG001` to its line. Put one parameter on a line when `ruff format` allows, so each `noqa` covers only contract names.
5. **A keyword-only parameter**, or one that some call passes by keyword (`timeout` in a fake opener's `open`, which `src/conductor/llm/ollama.py` calls with `timeout=`): keep the name and add `# noqa: ARG001` or `# noqa: ARG002` to its line.
6. **Anything else**, whether a fake method, a nested fake, a lambda, `*args` or `**kwargs`: rename to `_` plus the name (`_run_id`, `_settings`, `*_args`, `**_kwargs`).

A `noqa` lists only `ARG` codes, and its line holds no unused parameter that rule 6 should have renamed. When a rename breaks a test with `unexpected keyword argument`, that call passes the name by keyword: undo the rename and use rule 5. Then run `ruff format` and `ruff check --fix` for the import order.

## Facts

Checked on 2026-11-22 with the project's Python 3.12 and Ruff 0.17.2, outside the repository:
- The 230 findings by kind: 152 renames (rule 6), 28 moves to `usefixtures` (rule 2), 13 deletions (rule 1), and 37 contract names kept with `noqa` (rules 3 to 5: 32 fake tool parameters, 1 fixture, 4 keyword names).
- A scratch copy repaired by script under these rules gave: `ruff check .` and `ruff format --check .` clean; all three probe checks `ok`; the given test `17 passed`; and the whole suite 1614 passed. One rename (`timeout` in `tests/unit/test_ollama.py`'s `_Raises.open`) broke a test by keyword and was moved to rule 5. Two `tmp_path` deletions left an unused `Path` import, removed by `ruff check --fix`.
- In that copy the diff touched 5 source files (8 lines) and 53 test files.
- `ruff format` rewraps a signature that a trailing `noqa` makes too long, which can move the comment onto a line with no unused parameter. The given test reports that line.
- Ruff does not report a parameter whose name starts with `_`, or `self` and `cls`.
- On today's tree the probe's third check prints `FAIL` (230 findings), and the run reaches `FAILURES 1`.

## Requirements

### Part 1: the rule

- **R1.** `[tool.ruff]` in `pyproject.toml` is exactly `line-length = 100`, `target-version = "py312"`, `extend-exclude = ["docs"]` and `[tool.ruff.lint] select = ["E", "F", "I", "B", "UP", "ARG"]`.
- **R2.** `.venv/bin/python -m ruff check .` passes, with no unused-argument finding anywhere.

### Part 2: the repairs

- **R3.** Every changed Python file differs from 6b26679 only by the repair rules above (probe check 2). The same Python files exist under `src`, `tests`, `scripts` and `.claude`, apart from the given test (probe check 1).
- **R4.** Every `noqa` that names an `ARG` code stands on a line whose unused parameters are all contract names (rules 3 to 5), and lists only `ARG` codes. There is no bare `# noqa` and no file-level `# ruff: noqa` (the given test).
- **R5.** The source repairs are exactly the Part 2 table. `src/` gains no `noqa`.

### Part 3: the rules

- **R6.** The suite collects N + 17 tests, and every one passes. Sections: `scripts 30`, `cli 122`, `core 1462`. Coverage stays at or above the threshold.
- **R7.** Only the Scope's paths change; given files stay byte-identical. No test is skipped or marked `xfail`.

## Given files

Committed with this spec. Do not change them; if a given test fails, the repairs are wrong. Before your change, 1 of the given tests fails (the selection lacks `ARG`) and 16 pass. The tree check and the noqa rule's 15 cases already hold today, because no `ARG` noqa exists yet.

| File | What it is |
|---|---|
| `tests/unit/test_lint_rules.py` | R1, R4: the exact Ruff table, where an `ARG` noqa may stand in the whole tree, and that rule's 15 cases (17 tests from 3 functions) |
| `docs/verification/probe-09r.py` | the probe, run by its path in Acceptance |

Given test count: **17**.

## Tests to write

None. This phase changes no behaviour. R2, R3 and R5 to R7 are checked by the probe, `scripts/check.py`, the protected diffs and the searches.

## Rules for this phase

- A repair changes no behaviour. If a test fails after a repair, the repair is wrong: undo it and apply the rule that fits (usually rule 5).
- When a probe check prints `FAIL`, the lines above it name each file or count it rejected.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9r` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against 6b26679 (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1614 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1462`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1614 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_lint_rules.py --no-cov -q` | `17 passed` |
| `.venv/bin/python docs/verification/probe-09r.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09r-unused-argument-checks.md) --stat -- tests/unit/test_lint_rules.py docs/verification/probe-09r.py` | no output |
| `git diff 6b26679 --stat -- src scripts .claude tests/conftest.py tests/support.py tests/sections.toml ':!src/conductor/cli/approvals.py' ':!src/conductor/cli/escalations.py' ':!src/conductor/cli/main.py' ':!src/conductor/graph/nodes.py' ':!src/conductor/runtime.py' ':!.claude/skills/phase-architect/history.md'` | no output |
| `git diff 6b26679 --stat -- src` | last line `5 files changed, 8 insertions(+), 8 deletions(-)` |
| `git diff 6b26679 --stat -- pyproject.toml` | `1 file changed, 1 insertion(+), 1 deletion(-)` |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9r: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9r` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'noqa: *[A-Z0-9, ]*ARG|pragma: no cover' -- src
git grep --untracked -n -E 'pytest\.mark\.(skip|xfail)|importorskip' -- tests
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Unused-argument checks`, with `--tests-before 1597 --given 17`.
