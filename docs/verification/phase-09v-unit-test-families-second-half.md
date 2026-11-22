# Verify Phase 9v: Unit test families by behaviour, second half

Spec: `docs/phases/phase-09v-unit-test-families-second-half.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09v-unit-test-families-second-half.md`.

## First: establish that the coder ran

- No `## Phase 9v: ` entry in `docs/progress.md` and no Scope path changed since 8b34f08: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09v-unit-test-families-second-half.md docs/verification/phase-09v-unit-test-families-second-half.md tests/unit/test_suite_layout.py docs/verification/probe-09v.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff -M $(git log -1 --format=%h -- docs/phases/phase-09v-unit-test-families-second-half.md)` plus untracked files. G5 to G7 use the spec's commit and 8b34f08, so they hold either way.

The coder:
- merged thirteen `_more` files into their base files;
- renamed three others to behaviour names with `git mv`;
- changed no test.

## 1. Gates

N is `1540` (the suite without the layout test). Given count: 57. `.venv/bin/python scripts/accept.py --phase 9v --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1597 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1445`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1597 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `57 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09v.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09v-unit-test-families-second-half.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09v.py` | no output |
| G6 | `git diff 8b34f08 --stat -- src scripts tests pyproject.toml ':!tests/unit/test_ollama.py' ':!tests/unit/test_ollama_more.py' ':!tests/unit/test_plan.py' ':!tests/unit/test_plan_more.py' ':!tests/unit/test_points.py' ':!tests/unit/test_points_more.py' ':!tests/unit/test_private.py' ':!tests/unit/test_private_more.py' ':!tests/unit/test_registry.py' ':!tests/unit/test_registry_more.py' ':!tests/unit/test_reports.py' ':!tests/unit/test_reports_more.py' ':!tests/unit/test_reports_phase.py' ':!tests/unit/test_reports_phase_more.py' ':!tests/unit/test_route.py' ':!tests/unit/test_route_more.py' ':!tests/unit/test_rules.py' ':!tests/unit/test_rules_more.py' ':!tests/unit/test_store.py' ':!tests/unit/test_store_more.py' ':!tests/unit/test_tags.py' ':!tests/unit/test_tags_more.py' ':!tests/unit/test_tool_check.py' ':!tests/unit/test_tool_check_more.py' ':!tests/unit/test_web_jobs_lifecycle.py' ':!tests/unit/test_web_jobs_lifecycle_more.py' ':!tests/unit/test_policy_more.py' ':!tests/unit/test_policy_decision_checks.py' ':!tests/unit/test_shared_rules_more.py' ':!tests/unit/test_shared_rules.py' ':!tests/unit/test_web_handlers_more.py' ':!tests/unit/test_web_handlers.py' ':!tests/unit/test_suite_layout.py'` | no output |
| G7 | `git diff -M 8b34f08 --stat -- tests/unit/test_policy_more.py tests/unit/test_policy_decision_checks.py tests/unit/test_shared_rules_more.py tests/unit/test_shared_rules.py tests/unit/test_web_handlers_more.py tests/unit/test_web_handlers.py` | three `=>` lines with `0` changes, and `3 files changed, 0 insertions(+), 0 deletions(-)` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G9 | `grep -c '^## Phase 9v: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9v` | `Reports OK.` |

If G7 shows a renamed file as deleted and added rather than `=>`, the rename is not staged. Stage it in your scratch copy (`git add -A tests`) and rerun the row there before judging. Content that differs is a finding against R3.

The progress entry's `Tests:` line reads `1581 -> 1597 (given 57)`: the layout test's 41 tests are counted in 1581 and replaced by 57.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_only_the_pending_files_are_named_for_when_they_were_added` | pass |
| R2 | `test_moved_tests_live_in_their_new_file` (47 cases) | pass |
| R3 | G7 | as given |
| R4 | probe check 1 | `ok` |
| R5 | probe check 2 | `ok` |
| R6 | probe check 3; G2 | `ok`; as given |
| R7 | G1's `Sections:` rows | as given |
| R8 | G5, G6, G8; search 7 | as given; silent |

Read the thirteen merged files against the spec's Part 1 and its name table:
- the moved tests come after the base file's tests, in their original order;
- each "keep once" name appears once, and each "rename" name was renamed in the moved part only;
- in `test_ollama.py`, `_Raises.open` still takes a parameter named `request`;
- in `test_store.py`, `ME` is defined only by the base's `ME, OTHER = …` line;
- the imports are one sorted block.

Note in the review the new name the coder gave each renamed name.

## 3. Probe

The probe is the given file `docs/verification/probe-09v.py` (G4). It is Phase 9u's probe with this phase's `MOVES` table and base, and one fix: each name of a module-level tuple assignment is a definition of its own. Its oracle is the test tree at 8b34f08, read with `git show` and `git archive`. Each test function is reduced to a canonical form:
- its code;
- with every module-level name it uses replaced by the canonical form of that name's definition (with its docstring and its own name left out; `A, B = x, y` defines `A = x` and `B = y`);
- with every imported name replaced by what it imports, except that a name imported from another test module (`tests.…`) resolves to that module's definition, old modules read at 8b34f08 and new ones from today's tree;
- with a fixture parameter treated the same way, and a class or function defined inside a function left as its own.

It checks:
- the 213 test functions of the 29 old files have twins of the same name and canonical form in their new files, and each new file is in the same section as the old one;
- the autouse fixtures and `pytestmark` of each old file have the same canonical forms in its new file;
- the suite at 8b34f08 and today collect the same node ids, with the old paths mapped to the new ones and the layout test left out on both sides.

The 213 was counted by the oracle over the old files, not by hand. Before handover the architect ran the probe on today's tree: all three checks printed `FAIL` (the new files do not exist yet), and the run reached `FAILURES 3`. On a scratch copy with the moves done by script, all three printed `ok`. When a check fails, the lines above it name each test, file or count it rejected.

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
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/unit/test_ollama.py tests/unit/test_plan.py tests/unit/test_points.py tests/unit/test_private.py tests/unit/test_registry.py tests/unit/test_reports.py tests/unit/test_reports_phase.py tests/unit/test_route.py tests/unit/test_rules.py tests/unit/test_store.py tests/unit/test_tags.py tests/unit/test_tool_check.py tests/unit/test_web_jobs_lifecycle.py tests/unit/test_policy_decision_checks.py tests/unit/test_shared_rules.py tests/unit/test_web_handlers.py
```

## 5. Spot checks

This phase changes test files only, and `scripts/spot_check.py` edits files under `src/`. So make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09v`, then `rsync -a --delete tests/ <scratch>/spot09v/tests/`, stage it with `git add -A tests`, and link `.venv`. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1`. Before the next row, restore the copy with the same `rsync`, not `git checkout`: the copy's commit predates the moves. Each change is the shape of an edit; copy the exact old text from the coder's file (one match).

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | replace `def test_a_refused_decision_leaves_the_first_one(` with `def check_a_refused_decision_leaves_the_first_one(` (`tests/unit/test_store.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_store]' --no-cov -q` | `1 passed` | fails, `test_a_refused_decision_leaves_the_first_one` missing |
| S2 | replace `def test_a_second_approve_is_a_conflict_and_starts_nothing(` with `def check_a_second_approve_is_a_conflict_and_starts_nothing(` (`tests/unit/test_web_handlers.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_web_handlers]' --no-cov -q` | `1 passed` | fails, `test_a_second_approve_is_a_conflict_and_starts_nothing` missing |
| S3 | replace `(ConnectionResetError(), "unreachable")` with `(ConnectionResetError(), "unreachables")` (`tests/unit/test_ollama.py`) | `.venv/bin/python docs/verification/probe-09v.py` | `FAILURES 0` | check 1 `FAIL`, `test_opener_errors_keep_their_codes` has no twin, `FAILURES 1` |
| S4 | replace `@pytest.fixture(autouse=True)` with `@pytest.fixture` (`tests/unit/test_route.py`, its one autouse fixture) | `.venv/bin/python docs/verification/probe-09v.py` | `FAILURES 0` | check 2 `FAIL`, `FAILURES 1` |
| S5 | replace `ME, OTHER = "e" * 32, "f" * 32` with `ME, OTHER = "e" * 31, "f" * 32` (`tests/unit/test_store.py`) | `.venv/bin/python docs/verification/probe-09v.py` | `FAILURES 0` | check 1 `FAIL`, `test_lease_ids_are_checked` has no twin, `FAILURES 1` |
| S6 | append a function `test_added_later` that asserts `True` at the end of `tests/unit/test_tags.py` | `.venv/bin/python docs/verification/probe-09v.py` | `FAILURES 0` | check 3 `FAIL`, `test_added_later` collected today only, `FAILURES 1` |

Notes for tracing:
- S1, S2: the renamed function is no longer collected as a test, so the file lacks one listed name.
- S3: the tuple sits in `test_opener_errors_keep_their_codes`, a moved test, so its canonical form differs. Checks 2 and 3 stay `ok`.
- S4: `fixed` keeps its code but is no longer autouse, so the merged file's autouse set loses it, unlike both old files. Tests that need it may also fail at G1; that is not the point of this row.
- S5: the base tests and the moved tests that use `ME` now resolve to `"e" * 31`. It shows the probe reads the tuple's elements.
- S6: the layout test still passes on this change (`[test_tags]` gives `1 passed`): from this phase it allows added tests. Only probe check 3 refuses it, because this phase adds none.

The architect ran all six rows on the scratch copy with the moves done by script, and each gave its "Broken" result. A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- The names the coder gave the renamed names in the moved part, as long as the probe passes.
- The moved part's code after the base file's code with or without a separating comment.
- `ruff format` rewrapping a merged import block.

## 7. Out of scope

Each must be absent:
- Any change to the files 9q, 9t and 9u moved, `conftest.py`, `tests/support.py` or `tests/sections.toml`.
- A merge into a file with another stem.
- A renamed, re-ordered, re-worded or added test, or a changed parameter list or id.
- An edit inside a renamed file.
- Any change to `src/`, `scripts/`, `pyproject.toml`, a given file, `AGENTS.md` or the design docs.

## 8. Verdict

Write `docs/reviews/phase-09v-unit-test-families-second-half.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9v`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9v` must print `Reports OK.`
