# Phase 9v: Unit test families by behaviour, second half

## Goal

This is the last of four slices that fold the test files named for when they were added back into files named for what they cover (9q did the CLI families, 9t the web and integration ones, 9u the first half of the unit ones). It moves the sixteen `tests/unit` families left, from `test_ollama_more.py` to `test_web_jobs_lifecycle_more.py`, and changes no test. Afterwards no test file is named for when it was added, and the layout test's `PENDING` list is empty.

| Today | After |
|---|---|
| `tests/unit/test_ollama_more.py` | merged into `tests/unit/test_ollama.py` |
| `tests/unit/test_plan_more.py` | merged into `tests/unit/test_plan.py` |
| `tests/unit/test_points_more.py` | merged into `tests/unit/test_points.py` |
| `tests/unit/test_private_more.py` | merged into `tests/unit/test_private.py` |
| `tests/unit/test_registry_more.py` | merged into `tests/unit/test_registry.py` |
| `tests/unit/test_reports_more.py` | merged into `tests/unit/test_reports.py` |
| `tests/unit/test_reports_phase_more.py` | merged into `tests/unit/test_reports_phase.py` |
| `tests/unit/test_route_more.py` | merged into `tests/unit/test_route.py` |
| `tests/unit/test_rules_more.py` | merged into `tests/unit/test_rules.py` |
| `tests/unit/test_store_more.py` | merged into `tests/unit/test_store.py` |
| `tests/unit/test_tags_more.py` | merged into `tests/unit/test_tags.py` |
| `tests/unit/test_tool_check_more.py` | merged into `tests/unit/test_tool_check.py` |
| `tests/unit/test_web_jobs_lifecycle_more.py` | merged into `tests/unit/test_web_jobs_lifecycle.py` |
| `tests/unit/test_policy_more.py` | renamed `tests/unit/test_policy_decision_checks.py` |
| `tests/unit/test_shared_rules_more.py` | renamed `tests/unit/test_shared_rules.py` |
| `tests/unit/test_web_handlers_more.py` | renamed `tests/unit/test_web_handlers.py` |

Decided with the owner (2026-11-21, for all four slices; see Phase 9q):
- A suffixed file merges into its module's `test_<module>.py`. One with no base file is renamed to the behaviour it covers.
- When its autouse fixtures or `pytestmark` differ from the base file's, it is renamed instead of merged, so no test gains a fixture.
- Every test function's code stays AST-identical, with the same name and parameter ids. A module-level name defined in both parts is kept once when its code is the same apart from a docstring. When its code differs, it is renamed in the moved part only, where it is used.
- The collected count, the section counts and coverage are unchanged. `tests/unit/test_suite_layout.py` refuses a name that says when a file was added, apart from its `PENDING` list.
- A file merges only into the file with its own stem (decided for 9u).

Decided with the owner (2026-11-21, for this phase):
- From this phase on, the layout test's `MOVED` table says which test functions each of its 47 files must still hold, not all it holds. A moved test that disappears still fails. A later phase may add tests to these files, as `docs/phase-conventions.md` tells the coder to.

Decided by the architect, within those answers:
- The three new names are fixed above (the layout test pins them). `test_shared_rules_more.py` and `test_web_handlers_more.py` have no file with their stem, so they take it: no `test_shared_rules.py` or `test_web_handlers.py` exists. `test_policy_more.py` lacks the base's autouse `fixed`, so it is renamed.
- In the thirteen merges, the names to keep once and to rename are:

  | Merge | Keep once (same code) | Rename in the moved part |
  |---|---|---|
  | `test_ollama.py` | `PLAIN`, `GOOD`, `unavailable` | `request` |
  | `test_plan.py` | `RUN`, `DECISION`, `MODEL`, `DEMO`, `BY_RULE`, `fixed` | none |
  | `test_points.py` | none | none |
  | `test_private.py` | `mode` | none |
  | `test_registry.py` | `PingArgs`, `PingResult` | none |
  | `test_reports.py` | `write` | `PASS_REVIEW`, `ENTRY_1` |
  | `test_reports_phase.py` | none | `ENTRY` |
  | `test_route.py` | `RUN`, `DECISION`, `MODEL`, `PingArgs`, `PingResult`, `PING`, `LAB`, `NoModel`, `fixed` | none |
  | `test_rules.py` | `PingArgs`, `PingResult`, `PING`, `LAB`, `BOTH` | none |
  | `test_store.py` | `START`, `RUN`, `THREAD`, `NOTE`, `ESCALATION`, `ME`, `Clock`, `time`, `decision` | `request`, `answer` |
  | `test_tags.py` | none | none |
  | `test_tool_check.py` | none | `OPEN_OUTPUT` |
  | `test_web_jobs_lifecycle.py` | `run_id` | `Script`, `script` |

  The coder chooses the new names (9u used a `_moved` suffix). A rename changes only the uses of the module-level name. A parameter, attribute or keyword with the same spelling stays: in `test_ollama_more.py`, `_Raises.open(self, request, timeout)` keeps its `request`.
- `test_store.py` defines `ME, OTHER = "e" * 32, "f" * 32` in one line, and the moved part has `ME = "e" * 32`. The value is the same, so the moved part's line is dropped and the base's tuple stays.
- The given layout test is edited from Phase 9u's: the sixteen files leave `PENDING`, which ends empty, their sixteen targets join `MOVED`, and the `MOVED` check becomes "holds at least" for all 47 targets.
- The probe is 9u's with this phase's `MOVES` and base, and one fix: each name of a module-level tuple assignment is a definition of its own. Without it, a merge that adds `ME = …` beside the base's `ME, OTHER = …` changed what the base tests' `ME` resolved to.

## Read first

- The given files below, in full: they are the contract.
- The sixteen old files and the thirteen base files the probe's `MOVES` table lists, in full.
- `tests/sections.toml` and `docs/testing.md` rule 9.

## Starting state

Phase 9u is built and verified, and everything is committed at 8b34f08: 1581 tests. N is `1540`: the suite without `tests/unit/test_suite_layout.py`, whose 41 tests this phase replaces with the edited file's 57. **Sections: scripts 30, cli 122, core 1429.** No production code changes.

## Scope

| Path | What |
|---|---|
| `tests/unit/test_ollama.py`, `tests/unit/test_plan.py`, `tests/unit/test_points.py`, `tests/unit/test_private.py`, `tests/unit/test_registry.py`, `tests/unit/test_reports.py`, `tests/unit/test_reports_phase.py`, `tests/unit/test_route.py`, `tests/unit/test_rules.py`, `tests/unit/test_store.py`, `tests/unit/test_tags.py`, `tests/unit/test_tool_check.py`, `tests/unit/test_web_jobs_lifecycle.py` | each gains the tests of its `_more` file |
| `tests/unit/test_ollama_more.py`, `tests/unit/test_plan_more.py`, `tests/unit/test_points_more.py`, `tests/unit/test_private_more.py`, `tests/unit/test_registry_more.py`, `tests/unit/test_reports_more.py`, `tests/unit/test_reports_phase_more.py`, `tests/unit/test_route_more.py`, `tests/unit/test_rules_more.py`, `tests/unit/test_store_more.py`, `tests/unit/test_tags_more.py`, `tests/unit/test_tool_check_more.py`, `tests/unit/test_web_jobs_lifecycle_more.py` | deleted |
| the three renames in the table above | `git mv`, content unchanged |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- Every file 9q, 9t and 9u moved.
- Merging into a file with another stem.
- Renaming, re-wording or re-ordering a test, changing a parameter list or id, or sharing a fixture through `conftest.py` or `tests/support.py`.
- Editing a renamed file's content.
- Adding a test. The layout test now allows it, but probe check 3 refuses it in this phase.
- Any change to `src/`, `scripts/`, `pyproject.toml`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the thirteen merges

For each merge in the table:
1. Append the suffixed file's module-level code after the base file's, without its imports.
2. Merge its imports into the base file's import block. `ruff check --fix` sorts them.
3. Delete the moved part's copy of each "keep once" name. Rename each "rename" name in the moved part, and its uses there.
4. `git rm` the suffixed file.

Keep the moved tests in their original order, after the base file's tests.

### Part 2: the three renames

`git mv` each file to its new name. Change nothing inside.

## Requirements

### Part 1: where the tests are

- **R1.** No test file has a name that says when it was added (the layout test's `PENDING` list is empty).
- **R2.** Each of the 47 target files (the 31 of 9q, 9t and 9u, and this phase's sixteen) holds at least the test functions listed for it in the layout test.
- **R3.** The three renamed files are byte-identical to the files they replace (`git diff -M --stat` shows each as a rename with no changes).

### Part 2: what the tests do

- **R4.** Every test function of the 29 old files (sixteen suffixed, thirteen base) is AST-identical to its twin, and every module-level name it uses resolves to a definition with the same code (probe check 1).
- **R5.** Every moved test runs under the same autouse fixtures and `pytestmark` as before (probe check 2).
- **R6.** The suite collects the same node ids as at 8b34f08, with only the moved files' paths changed, apart from the layout test (probe check 3). The collected count is exactly N + the given count.
- **R7.** Section counts: `scripts` 30, `cli` 122, `core` 1445. Every moved file stays in `core`.
- **R8.** Only the Scope paths change. There is no new `noqa`, `pragma: no cover`, `skip` or `xfail` in a moved file.

## Given files

Committed with this spec. Do not change them; if a given test fails, the moves are wrong. Before your change, 17 of the given tests fail and 40 pass. The 40 are the 31 earlier targets and the naming rule's nine cases, which hold today.

| File | What it is |
|---|---|
| `tests/unit/test_suite_layout.py` | R1, R2: no suffixed file is left, the 47 target files hold at least their listed test functions, and the naming rule's cases (57 tests from 3 functions) |
| `docs/verification/probe-09v.py` | the probe, run by its path in Acceptance |

Given test count: **57**.

## Tests to write

None. This phase adds no behaviour. R3 to R8 are checked by the probe, the protected diffs and the searches.

## Rules for this phase

- A move changes no test. If a moved test fails after the move, the move is wrong: undo it and look for the name it now resolves to.
- When a probe check prints `FAIL`, the lines above it name each test, file or count it rejected.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Facts

Checked on 2026-11-21 with the project's Python 3.12, outside the repository:
- Comparing the sixteen files by canonical form against the file with their stem gave the merge and rename split and the name table above. No moved part imports a name the base defines or imports differently, and no moved test shares a name with a base definition.
- `git grep -n -E 'from tests\.(e2e|integration|unit)\.' -- tests` shows no importer of the sixteen files. `test_shared_rules_more.py` imports from `test_checkpoint_status_cases` and `test_eval_cases`, which do not move.
- The oracle counts 213 test functions in the 29 old files, the same as the layout test lists for the sixteen targets.
- A scratch copy with the sixteen moves done by script gave all three probe checks `ok`, `1597 tests collected`, and 367 passed in the sixteen target files and the layout test. Its first run found the tuple-assignment fault described above, now fixed in the probe.
- `ECHO, NOTE, DELEGATE = demo.DOMAIN.actions` in `test_policy.py` and `test_policy_more.py` is the only other module-level tuple assignment in these files. Its names resolve by index.
- None of the 29 files has a `noqa`, `skip`, `xfail` or `importorskip` today.
- On today's tree the probe prints `FAIL` for all three checks and reaches `FAILURES 3`.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9v` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against 8b34f08 (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1597 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1445`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1597 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `57 passed` |
| `.venv/bin/python docs/verification/probe-09v.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09v-unit-test-families-second-half.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09v.py` | no output |
| `git diff 8b34f08 --stat -- src scripts tests pyproject.toml ':!tests/unit/test_ollama.py' ':!tests/unit/test_ollama_more.py' ':!tests/unit/test_plan.py' ':!tests/unit/test_plan_more.py' ':!tests/unit/test_points.py' ':!tests/unit/test_points_more.py' ':!tests/unit/test_private.py' ':!tests/unit/test_private_more.py' ':!tests/unit/test_registry.py' ':!tests/unit/test_registry_more.py' ':!tests/unit/test_reports.py' ':!tests/unit/test_reports_more.py' ':!tests/unit/test_reports_phase.py' ':!tests/unit/test_reports_phase_more.py' ':!tests/unit/test_route.py' ':!tests/unit/test_route_more.py' ':!tests/unit/test_rules.py' ':!tests/unit/test_rules_more.py' ':!tests/unit/test_store.py' ':!tests/unit/test_store_more.py' ':!tests/unit/test_tags.py' ':!tests/unit/test_tags_more.py' ':!tests/unit/test_tool_check.py' ':!tests/unit/test_tool_check_more.py' ':!tests/unit/test_web_jobs_lifecycle.py' ':!tests/unit/test_web_jobs_lifecycle_more.py' ':!tests/unit/test_policy_more.py' ':!tests/unit/test_policy_decision_checks.py' ':!tests/unit/test_shared_rules_more.py' ':!tests/unit/test_shared_rules.py' ':!tests/unit/test_web_handlers_more.py' ':!tests/unit/test_web_handlers.py' ':!tests/unit/test_suite_layout.py'` | no output |
| `git diff -M 8b34f08 --stat -- tests/unit/test_policy_more.py tests/unit/test_policy_decision_checks.py tests/unit/test_shared_rules_more.py tests/unit/test_shared_rules.py tests/unit/test_web_handlers_more.py tests/unit/test_web_handlers.py` | three `=>` lines with `0` changes, and `3 files changed, 0 insertions(+), 0 deletions(-)` |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9v: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9v` (after writing progress) | `Reports OK.` |

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
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/unit/test_ollama.py tests/unit/test_plan.py tests/unit/test_points.py tests/unit/test_private.py tests/unit/test_registry.py tests/unit/test_reports.py tests/unit/test_reports_phase.py tests/unit/test_route.py tests/unit/test_rules.py tests/unit/test_store.py tests/unit/test_tags.py tests/unit/test_tool_check.py tests/unit/test_web_jobs_lifecycle.py tests/unit/test_policy_decision_checks.py tests/unit/test_shared_rules.py tests/unit/test_web_handlers.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Unit test families by behaviour, second half`, with `--tests-before 1581 --given 57` (the layout test's 41 tests are counted in 1581 and replaced by its 57).
