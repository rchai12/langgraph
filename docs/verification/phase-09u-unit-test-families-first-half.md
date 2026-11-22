# Verify Phase 9u: Unit test families by behaviour, first half

Spec: `docs/phases/phase-09u-unit-test-families-first-half.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09u-unit-test-families-first-half.md`.

## First: establish that the coder ran

- No `## Phase 9u: ` entry in `docs/progress.md` and no Scope path changed since d42c3d8: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09u-unit-test-families-first-half.md docs/verification/phase-09u-unit-test-families-first-half.md tests/unit/test_suite_layout.py docs/verification/probe-09u.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff -M $(git log -1 --format=%h -- docs/phases/phase-09u-unit-test-families-first-half.md)` plus untracked files. G5 to G7 use the spec's commit and d42c3d8, so they hold either way.

The coder:
- merged seven `_more` files into their base files (`test_answer`, `test_decisions`, `test_diagnostics`, `test_finance_catalog`, `test_finance_proposals`, `test_mcp_declarations`, `test_mcp_runner`);
- renamed eight others to behaviour names with `git mv`;
- changed no test.

## 1. Gates

N is `1540` (the suite without the layout test). Given count: 41. `.venv/bin/python scripts/accept.py --phase 9u --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1581 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1429`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1581 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `41 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09u.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09u-unit-test-families-first-half.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09u.py` | no output |
| G6 | `git diff d42c3d8 --stat -- src scripts tests pyproject.toml ':!tests/unit/test_answer.py' ':!tests/unit/test_answer_more.py' ':!tests/unit/test_decisions.py' ':!tests/unit/test_decisions_more.py' ':!tests/unit/test_diagnostics.py' ':!tests/unit/test_diagnostics_more.py' ':!tests/unit/test_finance_catalog.py' ':!tests/unit/test_finance_catalog_more.py' ':!tests/unit/test_finance_proposals.py' ':!tests/unit/test_finance_proposals_more.py' ':!tests/unit/test_mcp_declarations.py' ':!tests/unit/test_mcp_declarations_more.py' ':!tests/unit/test_mcp_runner.py' ':!tests/unit/test_mcp_runner_more.py' ':!tests/unit/test_contracts_more.py' ':!tests/unit/test_contracts_edge_cases.py' ':!tests/unit/test_decide_more.py' ':!tests/unit/test_decide_failures.py' ':!tests/unit/test_dollars_more.py' ':!tests/unit/test_dollars_and_days.py' ':!tests/unit/test_eval_more.py' ':!tests/unit/test_eval_case_runs.py' ':!tests/unit/test_eval_more_reports.py' ':!tests/unit/test_eval_report_history.py' ':!tests/unit/test_finance_more.py' ':!tests/unit/test_finance_arguments.py' ':!tests/unit/test_graph_split_more.py' ':!tests/unit/test_graph_step_failures.py' ':!tests/unit/test_groundwork_more.py' ':!tests/unit/test_groundwork_limits.py' ':!tests/unit/test_suite_layout.py'` | no output |
| G7 | `git diff -M d42c3d8 --stat -- tests/unit/test_contracts_more.py tests/unit/test_contracts_edge_cases.py tests/unit/test_decide_more.py tests/unit/test_decide_failures.py tests/unit/test_dollars_more.py tests/unit/test_dollars_and_days.py tests/unit/test_eval_more.py tests/unit/test_eval_case_runs.py tests/unit/test_eval_more_reports.py tests/unit/test_eval_report_history.py tests/unit/test_finance_more.py tests/unit/test_finance_arguments.py tests/unit/test_graph_split_more.py tests/unit/test_graph_step_failures.py tests/unit/test_groundwork_more.py tests/unit/test_groundwork_limits.py` | eight `=>` lines with `0` changes, and `8 files changed, 0 insertions(+), 0 deletions(-)` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G9 | `grep -c '^## Phase 9u: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9u` | `Reports OK.` |

If G7 shows a renamed file as deleted and added rather than `=>`, the rename is not staged. Stage it in your scratch copy (`git add -A tests`) and rerun the row there before judging. Content that differs is a finding against R3.

The progress entry's `Tests:` line reads `1566 -> 1581 (given 41)`: the layout test's 26 tests are counted in 1566 and replaced by 41.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_only_the_pending_files_are_named_for_when_they_were_added` | pass |
| R2 | `test_moved_tests_live_in_their_new_file` (31 cases) | pass |
| R3 | G7 | as given |
| R4 | probe check 1 | `ok` |
| R5 | probe check 2 | `ok` |
| R6 | probe check 3; G2 | `ok`; as given |
| R7 | G1's `Sections:` rows | as given |
| R8 | G5, G6, G8; search 7 | as given; silent |

Read the seven merged files against the spec's Part 1 and its name table:
- the moved tests come after the base file's tests, in their original order;
- each "keep once" name appears once, and each "rename" name was renamed in the moved part only;
- in `test_mcp_runner.py`, the `Query` and `Rows` classes inside `_spend` are still there, unrenamed;
- the imports are one sorted block, and `test_mcp_declarations.py` no longer imports from itself.

Note in the review the new name the coder gave each renamed name.

## 3. Probe

The probe is the given file `docs/verification/probe-09u.py` (G4). It is Phase 9t's probe with this phase's `MOVES` table and base, and one fix: a class or function defined inside a function is local to it. Its oracle is the test tree at d42c3d8, read with `git show` and `git archive`. Each test function is reduced to a canonical form:
- its code;
- with every module-level name it uses replaced by the canonical form of that name's definition (with its docstring and its own name left out);
- with every imported name replaced by what it imports, except that a name imported from another test module (`tests.…`) resolves to that module's definition, old modules read at d42c3d8 and new ones from today's tree;
- with a fixture parameter treated the same way.

It checks:
- the 108 test functions of the 22 old files have twins of the same name and canonical form in their new files, and each new file is in the same section as the old one;
- the autouse fixtures and `pytestmark` of each old file have the same canonical forms in its new file;
- the suite at d42c3d8 and today collect the same node ids, with the old paths mapped to the new ones and the layout test left out on both sides.

The 108 was counted by the oracle over the old files, not by hand. Before handover the architect ran the probe on today's tree: all three checks printed `FAIL` (the new files do not exist yet), and the run reached `FAILURES 3`. On a scratch copy with the moves done by script, all three printed `ok`. When a check fails, the lines above it name each test, file or count it rejected.

A stop at its own `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names. The last covers the merged files only: the renamed files are byte-identical by G7, and `test_graph_step_failures.py` keeps the `# noqa: F401` it had as `test_graph_split_more.py`.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/unit/test_answer.py tests/unit/test_decisions.py tests/unit/test_diagnostics.py tests/unit/test_finance_catalog.py tests/unit/test_finance_proposals.py tests/unit/test_mcp_declarations.py tests/unit/test_mcp_runner.py
```

## 5. Spot checks

This phase changes test files only, and `scripts/spot_check.py` edits files under `src/`. So make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09u`, then `rsync -a --delete tests/ <scratch>/spot09u/tests/`, stage it with `git add -A tests`, and link `.venv`. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1`. Before the next row, restore the copy with the same `rsync`, not `git checkout`: the copy's commit predates the moves. Each change is the shape of an edit; copy the exact old text from the coder's file (one match).

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | replace `def test_a_failure_carries_no_secret_and_no_cause(` with `def check_a_failure_carries_no_secret_and_no_cause(` (`tests/unit/test_mcp_runner.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_mcp_runner]' --no-cov -q` | `1 passed` | fails, `test_a_failure_carries_no_secret_and_no_cause` missing |
| S2 | replace `def test_a_late_offset_just_after_midnight_is_the_local_day(` with `def check_a_late_offset_just_after_midnight_is_the_local_day(` (`tests/unit/test_groundwork_limits.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_groundwork_limits]' --no-cov -q` | `1 passed` | fails, `test_a_late_offset_just_after_midnight_is_the_local_day` missing |
| S3 | replace `== ("tool_error", "timeout")` with `== ("tool_error", "timeouts")` (`tests/unit/test_mcp_runner.py`) | `.venv/bin/python docs/verification/probe-09u.py` | `FAILURES 0` | check 1 `FAIL`, `FAILURES 1` |
| S4 | replace `@pytest.fixture(autouse=True)` with `@pytest.fixture` (`tests/unit/test_answer.py`, its one autouse fixture) | `.venv/bin/python docs/verification/probe-09u.py` | `FAILURES 0` | check 2 `FAIL`, `FAILURES 1` |

Notes for tracing:
- S1, S2: the renamed function is no longer collected as a test, so the file's set of `test_` functions lacks one name.
- S3: the tuple sits in `test_a_failure_carries_no_secret_and_no_cause`, a moved test, so its canonical form differs. The node ids and the autouse set do not change, so checks 2 and 3 stay `ok`.
- S4: `fixed` keeps its code but is no longer autouse, so the merged file's autouse set loses it, unlike both old files. Tests that need it may also fail at G1; that is not the point of this row.

The architect ran all four rows on the scratch copy with the moves done by script, and each gave its "Broken" result. A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- The names the coder gave the renamed names in the moved part, as long as the probe passes.
- The moved part's code after the base file's code with or without a separating comment.
- `ruff format` rewrapping a merged import block.

## 7. Out of scope

Each must be absent:
- Any change to the sixteen families still in `PENDING`, the files 9q and 9t moved, `conftest.py`, `tests/support.py` or `tests/sections.toml`.
- A merge into a file with another stem, such as `test_eval_run.py`.
- A renamed, re-ordered or re-worded test, or a changed parameter list or id.
- An edit inside a renamed file.
- Any change to `src/`, `scripts/`, `pyproject.toml`, a given file, `AGENTS.md` or the design docs.

## 8. Verdict

Write `docs/reviews/phase-09u-unit-test-families-first-half.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9u`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9u` must print `Reports OK.`
