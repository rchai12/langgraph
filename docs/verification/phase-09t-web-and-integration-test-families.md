# Verify Phase 9t: Web and integration test families by behaviour

**Correction 1 (2026-11-21).** Three errors were the architect's, and the coder stopped correctly on them:
- `test_supervisor_more.py` had two importers outside the move, so with the owner it is now renamed `test_supervisor_step_runs.py` rather than merged. `test_step_failure_events.py` and `test_graph_split_more.py` change only the module path in one import line, and `test_supervisor.py` does not change.
- The probe now resolves names imported from another test module, on the same side, and checks the importers' tests too (`MOVED_TESTS` 78).
- Check 3 now leaves the layout test out of b1b529e's ids as well as today's.

The given layout test lists `test_supervisor_step_runs` in place of `test_supervisor`, still with 26 tests. The architect checked the corrected probe on a copy of the coder's first pass with the rename applied: all three checks `ok`. Spot rows S3 to S5 below were run there. Judge the build as usual; the stop is not a finding.

Spec: `docs/phases/phase-09t-web-and-integration-test-families.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09t-web-and-integration-test-families.md`.

## First: establish that the coder ran

- No `## Phase 9t: ` entry in `docs/progress.md` and no Scope path changed since b1b529e: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09t-web-and-integration-test-families.md docs/verification/phase-09t-web-and-integration-test-families.md tests/unit/test_suite_layout.py docs/verification/probe-09t.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff -M $(git log -1 --format=%h -- docs/phases/phase-09t-web-and-integration-test-families.md)` plus untracked files. G5 to G7 use the spec's commit and b1b529e, so they hold either way.

The coder:
- merged three `_more` files into their base files (`test_web_resume`, `test_mcp_client`, `test_runtime`);
- renamed eight others to behaviour names with `git mv`;
- changed the module path in the import line of `test_step_failure_events.py` and `test_graph_split_more.py`;
- changed no test.

## 1. Gates

N is `1540` (the suite without the layout test). Given count: 26. `.venv/bin/python scripts/accept.py --phase 9t --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1566 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1414`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1566 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `26 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09t.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09t-web-and-integration-test-families.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09t.py` | no output |
| G6 | `git diff b1b529e --stat -- src scripts tests pyproject.toml ':!tests/e2e/test_web_resume.py' ':!tests/e2e/test_web_resume_more.py' ':!tests/integration/test_mcp_client.py' ':!tests/integration/test_mcp_client_more.py' ':!tests/integration/test_runtime.py' ':!tests/integration/test_runtime_more.py' ':!tests/integration/test_supervisor_more.py' ':!tests/integration/test_supervisor_step_runs.py' ':!tests/integration/test_step_failure_events.py' ':!tests/unit/test_graph_split_more.py' ':!tests/e2e/test_web_decide_more.py' ':!tests/e2e/test_web_decide_forms.py' ':!tests/e2e/test_web_pages_more.py' ':!tests/e2e/test_web_page_safety.py' ':!tests/integration/test_mcp_steps_more.py' ':!tests/integration/test_mcp_step_runners.py' ':!tests/integration/test_resume_evidence_more.py' ':!tests/integration/test_resume_failed_note.py' ':!tests/integration/test_dollars_more.py' ':!tests/integration/test_dollars_spending_run.py' ':!tests/integration/test_finance_more.py' ':!tests/integration/test_finance_prefixed_request.py' ':!tests/integration/test_finance_proposals_more.py' ':!tests/integration/test_finance_proposal_approvals.py' ':!tests/unit/test_suite_layout.py'` | no output |
| G7 | `git diff -M b1b529e --stat -- tests/e2e/test_web_decide_more.py tests/e2e/test_web_decide_forms.py tests/e2e/test_web_pages_more.py tests/e2e/test_web_page_safety.py tests/integration/test_mcp_steps_more.py tests/integration/test_mcp_step_runners.py tests/integration/test_resume_evidence_more.py tests/integration/test_resume_failed_note.py tests/integration/test_dollars_more.py tests/integration/test_dollars_spending_run.py tests/integration/test_finance_more.py tests/integration/test_finance_prefixed_request.py tests/integration/test_finance_proposals_more.py tests/integration/test_finance_proposal_approvals.py tests/integration/test_supervisor_more.py tests/integration/test_supervisor_step_runs.py` | eight `=>` lines with `0` changes, and `8 files changed, 0 insertions(+), 0 deletions(-)` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G9 | `grep -c '^## Phase 9t: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9t` | `Reports OK.` |

If G7 shows a renamed file as deleted and added rather than `=>`, the rename is not staged. Stage it in your scratch copy (`git add -A tests`) and rerun the row there before judging. Content that differs is a finding against R3.

The progress entry's `Tests:` line reads `1555 -> 1566 (given 26)`: the layout test's 15 tests are counted in 1555 and replaced by 26.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_only_the_pending_files_are_named_for_when_they_were_added` | pass |
| R2 | `test_moved_tests_live_in_their_new_file` (16 cases) | pass |
| R3 | G7 | as given |
| R4 | probe check 1 | `ok` |
| R5 | probe check 2 | `ok` |
| R6 | probe check 3; G2 | `ok`; as given |
| R7 | G1's `Sections:` rows | as given |
| R8 | G5, G6, G8; search 7 | as given; silent |

Read the three merged files against the spec's Part 1 and its name table:
- the moved tests come after the base file's tests, in their original order;
- each "keep once" name appears once, and each "rename" name was renamed in the moved part only;
- the imports are one sorted block.

Note in the review the new name the coder gave each renamed name. In `test_mcp_client.py` the fixture `fake` may be kept once or renamed (the coder's first pass named it `fake_moved`); both are correct.

Run `git diff b1b529e -- tests/integration/test_step_failure_events.py tests/unit/test_graph_split_more.py`: each shows one changed line, `test_supervisor_more` to `test_supervisor_step_runs`. Anything else there is a finding against R8.

## 3. Probe

The probe is the given file `docs/verification/probe-09t.py` (G4). It is Phase 9q's probe with this phase's `MOVES` table and base, and two fixes from correction 1. Its oracle is the test tree at b1b529e, read with `git show` and `git archive`. Each test function is reduced to a canonical form:
- its code;
- with every module-level name it uses replaced by the canonical form of that name's definition (with its docstring and its own name left out);
- with every imported name replaced by what it imports, except that a name imported from another test module (`tests.…`) resolves to that module's definition, old modules read at b1b529e and new ones from today's tree;
- with a fixture parameter treated the same way.

It checks:
- the 78 test functions of the fourteen old files and the two importers have twins of the same name and canonical form in their new files, and each new file is in the same section as the old one;
- the autouse fixtures and `pytestmark` of each old file have the same canonical forms in its new file;
- the suite at b1b529e and today collect the same node ids, with the old paths mapped to the new ones and the layout test left out.

The 78 was counted by the oracle over the old files, not by hand. Before the correction's handover the architect ran the probe on the coder's first pass, which has no supervisor rename: all three checks printed `FAIL` and the run reached `FAILURES 3`. With the rename and the two import lines added in a copy, all three printed `ok`. When a check fails, the lines above it name each test, file or count it rejected.

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
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/e2e/test_web_resume.py tests/integration/test_mcp_client.py tests/integration/test_runtime.py tests/integration/test_supervisor_step_runs.py tests/e2e/test_web_decide_forms.py tests/e2e/test_web_page_safety.py tests/integration/test_mcp_step_runners.py tests/integration/test_resume_failed_note.py tests/integration/test_dollars_spending_run.py tests/integration/test_finance_prefixed_request.py tests/integration/test_finance_proposal_approvals.py
```

## 5. Spot checks

This phase changes test files only, and `scripts/spot_check.py` edits files under `src/`. So make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09t`, then `rsync -a --delete tests/ <scratch>/spot09t/tests/`, stage it with `git add -A tests`, and link `.venv`. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1`. Before the next row, restore the copy with the same `rsync`, not `git checkout`: the copy's commit predates the moves. Each change is the shape of an edit; copy the exact old text from the coder's file (one match).

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | replace `def test_an_answered_escalation_shows_the_button_and_an_open_one_does_not(` with `def check_an_answered_escalation_shows_the_button_and_an_open_one_does_not(` (`tests/e2e/test_web_resume.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_web_resume]' --no-cov -q` | `1 passed` | fails, `test_an_answered_escalation_shows_the_button_and_an_open_one_does_not` missing |
| S2 | replace `def test_a_rejected_plan_calls_no_tool(` with `def check_a_rejected_plan_calls_no_tool(` (`tests/integration/test_finance_proposal_approvals.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_finance_proposal_approvals]' --no-cov -q` | `1 passed` | fails, `test_a_rejected_plan_calls_no_tool` missing |
| S3 | replace `"demo: sweep the floor"` with `"demo: sweep the floors"` (`tests/integration/test_supervisor_step_runs.py`) | `.venv/bin/python docs/verification/probe-09t.py` | `FAILURES 0` | check 1 `FAIL`, `FAILURES 1` |
| S4 | replace `@pytest.fixture(autouse=True)` with `@pytest.fixture` (`tests/integration/test_mcp_step_runners.py`, its one autouse fixture) | `.venv/bin/python docs/verification/probe-09t.py` | `FAILURES 0` | check 2 `FAIL`, `FAILURES 1` |
| S5 | replace `from tests.integration.test_supervisor_step_runs import (` with `from tests.integration.test_supervisor import (` (`tests/unit/test_graph_split_more.py`) | `.venv/bin/python docs/verification/probe-09t.py` | `FAILURES 0` | checks 1 and 3 `FAIL`, `test_a_retried_write_waits_for_a_new_step_approval` has no twin, `FAILURES 2` |

Notes for tracing:
- S1, S2: the renamed function is no longer collected as a test, so the file's set of `test_` functions lacks one name.
- S3: the string sits in `test_a_delegate_step_asks_and_a_mixed_plan_runs_the_read_first`, a moved test, so its canonical form differs. The node ids and the autouse set do not change, so checks 2 and 3 stay `ok`.
- S4: the `lab` fixture keeps its code but is no longer autouse, so the file's autouse set loses it. Tests that need it may also fail at G1; that is not the point of this row.
- S5: `test_supervisor.py` defines a different `World` and no `Runner`, so the importer's names resolve to other code (check 1), and the file no longer imports, so its tests are not collected (check 3).

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- The names the coder gave the renamed names in the moved part, as long as the probe passes.
- The moved part's code after the base file's code with or without a separating comment.
- `ruff format` rewrapping a merged import block.

## 7. Out of scope

Each must be absent:
- Any change to a unit family, the CLI files 9q moved, `conftest.py`, `tests/support.py` or `tests/sections.toml`.
- A renamed, re-ordered or re-worded test, or a changed parameter list or id.
- An edit inside a renamed file.
- Any change to `src/`, `scripts/`, `pyproject.toml`, a given file, `AGENTS.md` or the design docs.

## 8. Verdict

Write `docs/reviews/phase-09t-web-and-integration-test-families.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9t`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9t` must print `Reports OK.`
