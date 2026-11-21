# Phase 9q: CLI test families by behaviour

## Goal

`docs/testing.md` says a module's tests live in `test_<module>.py`. The tree has 47 test files named for when they were added (`test_store_more.py`, `test_eval_more_reports.py`), so the tests for one behaviour are spread over files whose names say nothing about it. This phase is the first of four slices that fold them back. It moves the five CLI families in `tests/e2e/` and changes no test.

| Today | After |
|---|---|
| `tests/e2e/test_cli_approvals_more.py` | merged into `tests/e2e/test_cli_approvals.py` |
| `tests/e2e/test_cli_ask_more.py` | merged into `tests/e2e/test_cli_ask.py` |
| `tests/e2e/test_cli_doctor_private_more.py` | renamed `tests/e2e/test_cli_doctor_not_writable.py` |
| `tests/e2e/test_cli_tool_check_more.py` | renamed `tests/e2e/test_cli_tool_check_commands.py` |
| `tests/e2e/test_cli_groups_more.py` | renamed `tests/e2e/test_cli_decide_without_asking.py` |

Decided with the owner (2026-11-21):
- **Slices.** First the naming rule and a layout test, with the CLI families (this phase). Then 9t takes the web e2e and integration families, 9u half of unit, and 9v the rest. Each slice deletes its own files from the layout test's `PENDING` list.
- **Target.** A suffixed file merges into its module's `test_<module>.py`. A suffixed file with no base file is renamed to the behaviour it covers.
- **Different autouse.** When the suffixed file's autouse fixtures or `pytestmark` differ from the base file's, it is renamed to a behaviour name instead of merged, so no test gains a fixture. `test_cli_doctor_private_more.py` lacks the base file's `python_3_12_13`. `test_cli_tool_check_more.py` has `python_3_12_13` where its base has `fake_server`.
- **Preservation.** Every test function's code is AST-identical, with the same name and parameter ids. Helpers, constants and fixtures that are identical apart from a docstring are kept once, as the base file has them. One that clashes with different code is renamed in the moved part only, where it is used. The collected count, the section counts and coverage are unchanged.
- **Future rule.** Given tests go in a new behaviour-named file. The coder adds to an existing module file or to another behaviour-named file. The layout test refuses a name that says when a file was added. The architect has already updated `docs/testing.md`, `docs/phase-conventions.md` and the architect templates to say so.

Decided by the architect, within those answers:
- The three new names are fixed above (the given layout test pins them).
- `test_cli_groups_more.py` has no base file. Its autouse fixture `fixed` differs from `test_cli_approvals.py`, which has none, so it is renamed, not merged into approvals.
- In `test_cli_ask.py` the two `replies` fixtures differ only by the base's docstring: keep the base's. The four other shared names are identical: keep one.
- In `test_cli_approvals.py`, `NOTE` and the `db` fixture differ between the parts: keep the base's and rename the moved part's (for example `NOTE_ONE` and `fresh_db`), changing only the moved tests that use them. A renamed fixture changes the moved tests' parameter names. The probe resolves every name to its definition, so that is allowed.
- A name that says when a file was added matches `_(more|extra|again)(_|$)` or `_(phase_?)?\d+[a-z]?$` in its stem. `test_reports_phase.py` and `test_check_reports_phase.py` are about the `--phase` option and do not match.

## Read first

- The given files below, in full: they are the contract.
- The seven CLI files in the table's left column and the two base files, in full.
- `tests/sections.toml` and `docs/testing.md` rule 9.

## Starting state

Phase 9p is built and verified, and everything is committed at 3983234: N is `1540`. **Sections: scripts 30, cli 122, core 1388.** No production code changes in this phase.

## Scope

| Path | What |
|---|---|
| `tests/e2e/test_cli_approvals.py` | gains the tests of `test_cli_approvals_more.py` |
| `tests/e2e/test_cli_ask.py` | gains the tests of `test_cli_ask_more.py` |
| `tests/e2e/test_cli_approvals_more.py`, `tests/e2e/test_cli_ask_more.py` | deleted |
| `tests/e2e/test_cli_doctor_private_more.py` → `tests/e2e/test_cli_doctor_not_writable.py` | renamed with `git mv`, content unchanged |
| `tests/e2e/test_cli_tool_check_more.py` → `tests/e2e/test_cli_tool_check_commands.py` | renamed with `git mv`, content unchanged |
| `tests/e2e/test_cli_groups_more.py` → `tests/e2e/test_cli_decide_without_asking.py` | renamed with `git mv`, content unchanged |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- Any other test family, including `test_web_*_more.py` (9t) and every integration and unit family (9t to 9v).
- Renaming, re-wording or re-ordering a test, changing a parameter list or id, or sharing a fixture through `conftest.py` or `tests/support.py`.
- Editing a renamed file's content. The three renames are pure moves.
- Any change to `src/`, `scripts/`, `pyproject.toml`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the two merges

For `test_cli_approvals.py` and `test_cli_ask.py`:
1. Append the suffixed file's module-level code after the base file's, without its imports.
2. Merge its imports into the base file's import block. `ruff check --fix` sorts them.
3. For each module-level name defined in both parts:
   - same code, apart from a docstring: delete the moved part's copy;
   - different code: rename the moved part's copy, and its uses in the moved part only.
4. `git rm` the suffixed file.

Keep the moved tests in their original order, after the base file's tests.

### Part 2: the three renames

`git mv` each file to its new name. Change nothing inside.

## Requirements

### Part 1: where the tests are

- **R1.** No test file outside the layout test's `PENDING` list has a name that says when it was added.
- **R2.** Each of the five target files holds exactly the test functions listed for it in the layout test.
- **R3.** The three renamed files are byte-identical to the files they replace (`git diff -M --stat` shows each as a 100% rename).

### Part 2: what the tests do

- **R4.** Every moved test function is AST-identical to its original. Every module-level name it uses resolves to a definition with the same code, whatever that definition is now called (probe check 1).
- **R5.** Every moved test runs under the same autouse fixtures and `pytestmark` as before (probe check 2).
- **R6.** The suite collects the same node ids as at 3983234, with only the moved files' paths changed, plus the given layout tests (probe check 3). The collected count is exactly N + the given count.
- **R7.** Section counts: `scripts` 30, `cli` 122, `core` 1388 + the given count. Every moved file stays in `cli`.
- **R8.** Only the Scope paths change. There is no new `noqa`, `pragma: no cover`, `skip` or `xfail` in a moved file.

## Given files

Committed with this spec. Do not change them; if a given test fails, the moves are wrong. Before your change, 6 of the given tests fail and 9 pass. The 9 are the naming rule's own cases, which hold whatever the tree looks like.

| File | What it is |
|---|---|
| `tests/unit/test_suite_layout.py` | R1, R2: only `PENDING` files are suffixed, the five target files and their test functions, and the naming rule's cases (15 tests from 3 functions) |
| `docs/verification/probe-09q.py` | the probe, run by its path in Acceptance |

Given test count: **15**.

## Tests to write

None. This phase adds no behaviour. R3 to R8 are checked by the probe, the protected diffs and the searches.

## Rules for this phase

- A move changes no test. If a moved test fails after the move, the move is wrong: undo it and look for the name it now resolves to.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged apart from where they live.

## Facts

Checked on 2026-11-21 with the project's Python 3.12, outside the repository:
- `git archive 3983234 tests pyproject.toml`, unpacked in a temporary folder, collects there with `pytest --collect-only --no-cov -p no:cacheprovider` (`--import-mode=importlib` comes from `pyproject.toml`). It gives the same node ids as today's tree.
- The probe's canonical form gives the same result for all 908 test functions of today's tree at 3983234 and in the working tree. Its own known cases show that a renamed helper or fixture with the same code matches, and a changed constant or argument does not.
- No moved file has a `noqa`, `skip`, `xfail` or `importorskip` today. No test name is defined in both parts of a merged family.
- On today's tree the probe printed `FAIL` for all three checks and reached `FAILURES 3`.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9q` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against 3983234 (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1555 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1403`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1555 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `15 passed` |
| `.venv/bin/python docs/verification/probe-09q.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09q-cli-test-families.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09q.py` | no output |
| `git diff 3983234 --stat -- src scripts tests pyproject.toml ':!tests/e2e/test_cli_approvals.py' ':!tests/e2e/test_cli_approvals_more.py' ':!tests/e2e/test_cli_ask.py' ':!tests/e2e/test_cli_ask_more.py' ':!tests/e2e/test_cli_doctor_private_more.py' ':!tests/e2e/test_cli_doctor_not_writable.py' ':!tests/e2e/test_cli_tool_check_more.py' ':!tests/e2e/test_cli_tool_check_commands.py' ':!tests/e2e/test_cli_groups_more.py' ':!tests/e2e/test_cli_decide_without_asking.py' ':!tests/unit/test_suite_layout.py'` | no output |
| `git diff -M 3983234 --stat -- tests/e2e/test_cli_doctor_private_more.py tests/e2e/test_cli_doctor_not_writable.py tests/e2e/test_cli_tool_check_more.py tests/e2e/test_cli_tool_check_commands.py tests/e2e/test_cli_groups_more.py tests/e2e/test_cli_decide_without_asking.py` | three `=>` lines with `0` changes, and `3 files changed, 0 insertions(+), 0 deletions(-)` |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9q: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9q` (after writing progress) | `Reports OK.` |

The rename row needs the renames staged (`git mv` stages them) or committed, because `git diff` does not see untracked files.

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/e2e/test_cli_approvals.py tests/e2e/test_cli_ask.py tests/e2e/test_cli_doctor_not_writable.py tests/e2e/test_cli_tool_check_commands.py tests/e2e/test_cli_decide_without_asking.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `CLI test families by behaviour`, with `--tests-before 1540 --given 15`.
