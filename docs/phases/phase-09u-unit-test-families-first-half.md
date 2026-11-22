# Phase 9u: Unit test families by behaviour, first half

## Goal

This is the third of four slices that fold the test files named for when they were added back into files named for what they cover (9q did the CLI families, 9t the web and integration ones). It moves the first fifteen of the 31 `tests/unit` families, in alphabetical order from `test_answer_more.py` to `test_mcp_runner_more.py`, and changes no test. 9v moves the other sixteen.

| Today | After |
|---|---|
| `tests/unit/test_answer_more.py` | merged into `tests/unit/test_answer.py` |
| `tests/unit/test_decisions_more.py` | merged into `tests/unit/test_decisions.py` |
| `tests/unit/test_diagnostics_more.py` | merged into `tests/unit/test_diagnostics.py` |
| `tests/unit/test_finance_catalog_more.py` | merged into `tests/unit/test_finance_catalog.py` |
| `tests/unit/test_finance_proposals_more.py` | merged into `tests/unit/test_finance_proposals.py` |
| `tests/unit/test_mcp_declarations_more.py` | merged into `tests/unit/test_mcp_declarations.py` |
| `tests/unit/test_mcp_runner_more.py` | merged into `tests/unit/test_mcp_runner.py` |
| `tests/unit/test_contracts_more.py` | renamed `tests/unit/test_contracts_edge_cases.py` |
| `tests/unit/test_decide_more.py` | renamed `tests/unit/test_decide_failures.py` |
| `tests/unit/test_dollars_more.py` | renamed `tests/unit/test_dollars_and_days.py` |
| `tests/unit/test_eval_more.py` | renamed `tests/unit/test_eval_case_runs.py` |
| `tests/unit/test_eval_more_reports.py` | renamed `tests/unit/test_eval_report_history.py` |
| `tests/unit/test_finance_more.py` | renamed `tests/unit/test_finance_arguments.py` |
| `tests/unit/test_graph_split_more.py` | renamed `tests/unit/test_graph_step_failures.py` |
| `tests/unit/test_groundwork_more.py` | renamed `tests/unit/test_groundwork_limits.py` |

Decided with the owner (2026-11-21, for all four slices; see Phase 9q):
- A suffixed file merges into its module's `test_<module>.py`. One with no base file is renamed to the behaviour it covers.
- When its autouse fixtures or `pytestmark` differ from the base file's, it is renamed instead of merged, so no test gains a fixture.
- Every test function's code stays AST-identical, with the same name and parameter ids. A module-level name defined in both parts is kept once when its code is the same apart from a docstring. When its code differs, it is renamed in the moved part only, where it is used.
- The collected count, the section counts and coverage are unchanged. `tests/unit/test_suite_layout.py` refuses a name that says when a file was added, apart from its `PENDING` list.

Decided with the owner (2026-11-21, for this phase):
- A file merges only into the file with its own stem (`test_<stem>_more.py` into `test_<stem>.py`). `test_eval_more.py` covers `conductor.evals.run`, whose tests are in `test_eval_run.py`, but it is renamed, not merged there.

Decided by the architect, within those answers:
- The fifteen files are the alphabetical first half of the 31 left in `PENDING`. None is imported by another test file. The eight new names are fixed above (the layout test pins them).
- `test_decide_more.py` lacks the base's autouse `fixed`, so it is renamed. `test_contracts_more.py`, `test_dollars_more.py`, `test_eval_more.py`, `test_eval_more_reports.py`, `test_finance_more.py`, `test_graph_split_more.py` and `test_groundwork_more.py` have no file with their stem, so they are renamed.
- In the seven merges, the names to keep once and to rename are:

  | Merge | Keep once (same code) | Rename in the moved part |
  |---|---|---|
  | `test_answer.py` | `RUN`, `DECISION`, `MODEL`, `fixed` | `answer` |
  | `test_decisions.py` | `AT`, `REGISTRY`, `NOTE`, `ID` | the fixture `db` |
  | `test_diagnostics.py` | none | none |
  | `test_finance_catalog.py` | none | none |
  | `test_finance_proposals.py` | `REASON` | none |
  | `test_mcp_declarations.py` | the names the moved part imports from `tests.unit.test_mcp_declarations` (drop that import) | none |
  | `test_mcp_runner.py` | none | none |

  The coder chooses the new names (for example `answer_two`). In `test_mcp_runner.py` the moved helper `_spend` defines its own `Query` and `Rows` classes inside it. They shadow the base's module-level `Query` and `Rows` and stay as they are.
- The given layout test is edited from Phase 9t's: the fifteen files leave `PENDING` (16 remain), and their fifteen targets join `MOVED`. The sixteen earlier targets stay, so their moves stay guarded.
- The probe is 9t's with this phase's `MOVES` and base, and one fix: a class or function defined inside a test or helper is local to it. Without the fix the canonical form resolved `_spend`'s inner `Query` to the base file's `Query` after the merge.

## Read first

- The given files below, in full: they are the contract.
- The fifteen old files and the seven base files the probe's `MOVES` table lists, in full.
- `tests/sections.toml` and `docs/testing.md` rule 9.

## Starting state

Phase 9t is built and verified, and everything is committed at d42c3d8: 1566 tests. N is `1540`: the suite without `tests/unit/test_suite_layout.py`, whose 26 tests this phase replaces with the edited file's 41. **Sections: scripts 30, cli 122, core 1414.** No production code changes.

## Scope

| Path | What |
|---|---|
| `tests/unit/test_answer.py`, `tests/unit/test_decisions.py`, `tests/unit/test_diagnostics.py`, `tests/unit/test_finance_catalog.py`, `tests/unit/test_finance_proposals.py`, `tests/unit/test_mcp_declarations.py`, `tests/unit/test_mcp_runner.py` | each gains the tests of its `_more` file |
| `tests/unit/test_answer_more.py`, `tests/unit/test_decisions_more.py`, `tests/unit/test_diagnostics_more.py`, `tests/unit/test_finance_catalog_more.py`, `tests/unit/test_finance_proposals_more.py`, `tests/unit/test_mcp_declarations_more.py`, `tests/unit/test_mcp_runner_more.py` | deleted |
| the eight renames in the table above | `git mv`, content unchanged |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- The sixteen unit families still in `PENDING` (9v), and every file 9q and 9t moved.
- Merging into a file with another stem, such as `test_eval_run.py` or `test_contracts_base.py`.
- Renaming, re-wording or re-ordering a test, changing a parameter list or id, or sharing a fixture through `conftest.py` or `tests/support.py`.
- Editing a renamed file's content, including the `# noqa: F401` that `test_graph_split_more.py` already has.
- Any change to `src/`, `scripts/`, `pyproject.toml`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the seven merges

For each merge in the table:
1. Append the suffixed file's module-level code after the base file's, without its imports.
2. Merge its imports into the base file's import block. `ruff check --fix` sorts them.
3. Delete the moved part's copy of each "keep once" name. Rename each "rename" name in the moved part, and its uses there.
4. `git rm` the suffixed file.

Keep the moved tests in their original order, after the base file's tests.

### Part 2: the eight renames

`git mv` each file to its new name. Change nothing inside.

## Requirements

### Part 1: where the tests are

- **R1.** No test file outside the layout test's `PENDING` list has a name that says when it was added.
- **R2.** Each of the 31 target files (the sixteen of 9q and 9t, and this phase's fifteen) holds exactly the test functions listed for it in the layout test.
- **R3.** The eight renamed files are byte-identical to the files they replace (`git diff -M --stat` shows each as a rename with no changes).

### Part 2: what the tests do

- **R4.** Every test function of the 22 old files (fifteen suffixed, seven base) is AST-identical to its twin, and every module-level name it uses resolves to a definition with the same code (probe check 1).
- **R5.** Every moved test runs under the same autouse fixtures and `pytestmark` as before (probe check 2).
- **R6.** The suite collects the same node ids as at d42c3d8, with only the moved files' paths changed, apart from the layout test (probe check 3). The collected count is exactly N + the given count.
- **R7.** Section counts: `scripts` 30, `cli` 122, `core` 1429. Every moved file stays in `core`.
- **R8.** Only the Scope paths change. There is no new `noqa`, `pragma: no cover`, `skip` or `xfail` in a merged file.

## Given files

Committed with this spec. Do not change them; if a given test fails, the moves are wrong. Before your change, 16 of the given tests fail and 25 pass. The 25 are the sixteen earlier targets and the naming rule's nine cases, which hold today.

| File | What it is |
|---|---|
| `tests/unit/test_suite_layout.py` | R1, R2: only `PENDING` files are suffixed, the 31 target files and their test functions, and the naming rule's cases (41 tests from 3 functions) |
| `docs/verification/probe-09u.py` | the probe, run by its path in Acceptance |

Given test count: **41**.

## Tests to write

None. This phase adds no behaviour. R3 to R8 are checked by the probe, the protected diffs and the searches.

## Rules for this phase

- A move changes no test. If a moved test fails after the move, the move is wrong: undo it and look for the name it now resolves to.
- When a probe check prints `FAIL`, the lines above it name each test, file or count it rejected.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Facts

Checked on 2026-11-21 with the project's Python 3.12, outside the repository:
- Comparing the 31 pending files by canonical form against the file with their stem gave the merge and rename split and the name table above. No moved part imports a name the base defines or imports differently, and no moved test shares a name with a base definition.
- `git grep -n -E 'from tests\.(e2e|integration|unit)\.' -- tests` shows no importer of the fifteen files. `test_mcp_declarations_more.py` imports from its own base, and `test_graph_split_more.py` from `tests.integration.test_supervisor_step_runs`, which does not move.
- The oracle counts 108 test functions in the 22 old files, the same as the layout test lists for the fifteen targets.
- A scratch copy with the fifteen moves done by script (keep-once names dropped, clashing names renamed) gave all three probe checks `ok`, `1581 tests collected`, and 233 passed in the fifteen target files and the layout test. The first run there found the inner-class fault described above, now fixed in the probe.
- The only `noqa`, `skip`, `xfail` or `importorskip` in the fifteen files today is the `# noqa: F401` in `test_graph_split_more.py`.
- On today's tree the probe prints `FAIL` for all three checks and reaches `FAILURES 3`.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9u` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against d42c3d8 (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1581 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1429`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1581 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `41 passed` |
| `.venv/bin/python docs/verification/probe-09u.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09u-unit-test-families-first-half.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09u.py` | no output |
| `git diff d42c3d8 --stat -- src scripts tests pyproject.toml ':!tests/unit/test_answer.py' ':!tests/unit/test_answer_more.py' ':!tests/unit/test_decisions.py' ':!tests/unit/test_decisions_more.py' ':!tests/unit/test_diagnostics.py' ':!tests/unit/test_diagnostics_more.py' ':!tests/unit/test_finance_catalog.py' ':!tests/unit/test_finance_catalog_more.py' ':!tests/unit/test_finance_proposals.py' ':!tests/unit/test_finance_proposals_more.py' ':!tests/unit/test_mcp_declarations.py' ':!tests/unit/test_mcp_declarations_more.py' ':!tests/unit/test_mcp_runner.py' ':!tests/unit/test_mcp_runner_more.py' ':!tests/unit/test_contracts_more.py' ':!tests/unit/test_contracts_edge_cases.py' ':!tests/unit/test_decide_more.py' ':!tests/unit/test_decide_failures.py' ':!tests/unit/test_dollars_more.py' ':!tests/unit/test_dollars_and_days.py' ':!tests/unit/test_eval_more.py' ':!tests/unit/test_eval_case_runs.py' ':!tests/unit/test_eval_more_reports.py' ':!tests/unit/test_eval_report_history.py' ':!tests/unit/test_finance_more.py' ':!tests/unit/test_finance_arguments.py' ':!tests/unit/test_graph_split_more.py' ':!tests/unit/test_graph_step_failures.py' ':!tests/unit/test_groundwork_more.py' ':!tests/unit/test_groundwork_limits.py' ':!tests/unit/test_suite_layout.py'` | no output |
| `git diff -M d42c3d8 --stat -- tests/unit/test_contracts_more.py tests/unit/test_contracts_edge_cases.py tests/unit/test_decide_more.py tests/unit/test_decide_failures.py tests/unit/test_dollars_more.py tests/unit/test_dollars_and_days.py tests/unit/test_eval_more.py tests/unit/test_eval_case_runs.py tests/unit/test_eval_more_reports.py tests/unit/test_eval_report_history.py tests/unit/test_finance_more.py tests/unit/test_finance_arguments.py tests/unit/test_graph_split_more.py tests/unit/test_graph_step_failures.py tests/unit/test_groundwork_more.py tests/unit/test_groundwork_limits.py` | eight `=>` lines with `0` changes, and `8 files changed, 0 insertions(+), 0 deletions(-)` |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9u: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9u` (after writing progress) | `Reports OK.` |

The rename row needs the renames staged (`git mv` stages them) or committed, because `git diff` does not see untracked files.

### Searches

Each prints nothing (git grep exit 1 is no match). The last covers the merged files; the renamed ones are byte-identical by the rename row.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/unit/test_answer.py tests/unit/test_decisions.py tests/unit/test_diagnostics.py tests/unit/test_finance_catalog.py tests/unit/test_finance_proposals.py tests/unit/test_mcp_declarations.py tests/unit/test_mcp_runner.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Unit test families by behaviour, first half`, with `--tests-before 1566 --given 41` (the layout test's 26 tests are counted in 1566 and replaced by its 41).
