# Verify Phase 9q: CLI test families by behaviour

**Correction 1 (2026-11-21).** The probe expected 56 moved tests; the seven old files hold 47 (the base files of `test_cli_doctor_private` and `test_cli_tool_check` do not move). The probe now expects 47 and names each test without a twin, or the count, when a check fails. The coder stopped correctly on the old count. The coder's first-pass build was checked against the corrected probe: all three checks `ok`. Judge the build as usual; a stop on the old count is not a finding.

Spec: `docs/phases/phase-09q-cli-test-families.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09q-cli-test-families.md`.

## First: establish that the coder ran

- No `## Phase 9q: ` entry in `docs/progress.md` and no Scope path changed since 3983234: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09q-cli-test-families.md docs/verification/phase-09q-cli-test-families.md tests/unit/test_suite_layout.py docs/verification/probe-09q.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff -M $(git log -1 --format=%h -- docs/phases/phase-09q-cli-test-families.md)` plus untracked files. G5 to G7 use the spec's commit and 3983234, so they hold either way.

The coder:
- merged `test_cli_approvals_more.py` and `test_cli_ask_more.py` into their base files;
- renamed the three other CLI `_more` files to behaviour names with `git mv`;
- changed no test.

## 1. Gates

N is `1540`. Given count: 15. `.venv/bin/python scripts/accept.py --phase 9q --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1555 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1403`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1555 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `15 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09q.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09q-cli-test-families.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09q.py` | no output |
| G6 | `git diff 3983234 --stat -- src scripts tests pyproject.toml ':!tests/e2e/test_cli_approvals.py' ':!tests/e2e/test_cli_approvals_more.py' ':!tests/e2e/test_cli_ask.py' ':!tests/e2e/test_cli_ask_more.py' ':!tests/e2e/test_cli_doctor_private_more.py' ':!tests/e2e/test_cli_doctor_not_writable.py' ':!tests/e2e/test_cli_tool_check_more.py' ':!tests/e2e/test_cli_tool_check_commands.py' ':!tests/e2e/test_cli_groups_more.py' ':!tests/e2e/test_cli_decide_without_asking.py' ':!tests/unit/test_suite_layout.py'` | no output |
| G7 | `git diff -M 3983234 --stat -- tests/e2e/test_cli_doctor_private_more.py tests/e2e/test_cli_doctor_not_writable.py tests/e2e/test_cli_tool_check_more.py tests/e2e/test_cli_tool_check_commands.py tests/e2e/test_cli_groups_more.py tests/e2e/test_cli_decide_without_asking.py` | three `=>` lines with `0` changes, and `3 files changed, 0 insertions(+), 0 deletions(-)` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G9 | `grep -c '^## Phase 9q: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9q` | `Reports OK.` |

If G7 shows a renamed file as deleted and added rather than `=>`, the rename is not staged. Stage it in your scratch copy (`git add -A tests/e2e`) and rerun the row there before judging. Content that differs is a finding against R3.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_only_the_pending_files_are_named_for_when_they_were_added` | pass |
| R2 | `test_moved_tests_live_in_their_new_file` (5 cases) | pass |
| R3 | G7 | as given |
| R4 | probe check 1 | `ok` |
| R5 | probe check 2 | `ok` |
| R6 | probe check 3; G2 | `ok`; as given |
| R7 | G1's `Sections:` rows | as given |
| R8 | G5, G6, G8; search 7 | as given; silent |

Read the two merged files against the spec's Part 1:
- the moved tests come after the base file's tests, in their original order;
- each name defined in both parts was either kept once (same code) or renamed in the moved part only;
- the imports are one sorted block.

Note in the review each name that was renamed or dropped.

## 3. Probe

The probe is the given file `docs/verification/probe-09q.py` (G4). Its oracle is the test tree at 3983234, read with `git show` and `git archive`. Each test function is reduced to a canonical form:
- its code;
- with every module-level name it uses replaced by the canonical form of that name's definition (with its docstring and its own name left out);
- with every imported name replaced by what it imports;
- with a fixture parameter treated the same way.

It checks:
- the 47 test functions of the seven old files have twins of the same name and canonical form in their new files, and each new file is in the same section as the old one;
- the autouse fixtures and `pytestmark` of each old file have the same canonical forms in its new file;
- the suite at 3983234 and today collect the same node ids, with the old paths mapped to the new ones and the given layout tests left out.

Before handover the architect ran it on today's tree. All three checks printed `FAIL` (the new files do not exist yet), and the run reached `FAILURES 3`. The canonical form gave the same result for all 908 test functions of the unchanged tree at 3983234 and in the working tree.

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
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/e2e/test_cli_approvals.py tests/e2e/test_cli_ask.py tests/e2e/test_cli_doctor_not_writable.py tests/e2e/test_cli_tool_check_commands.py tests/e2e/test_cli_decide_without_asking.py
```

## 5. Spot checks

This phase changes test files only, and `scripts/spot_check.py` edits files under `src/`. So make each change by hand in a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09q`, then copy in the uncommitted Scope files, stage them with `git add -A`, and link `.venv`). Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1`, then restore the file with `git checkout -- <file>`. Each change is the shape of an edit; copy the exact old text from the coder's file (one match).

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | replace `def test_show_json_includes_an_answer(` with `def check_show_json_includes_an_answer(` (`tests/e2e/test_cli_approvals.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_cli_approvals]' --no-cov -q` | `1 passed` | fails, `test_show_json_includes_an_answer` missing |
| S2 | replace `def test_cancel_decides_without_asking(` with `def check_cancel_decides_without_asking(` (`tests/e2e/test_cli_decide_without_asking.py`) | `.venv/bin/python -m pytest 'tests/unit/test_suite_layout.py::test_moved_tests_live_in_their_new_file[test_cli_decide_without_asking]' --no-cov -q` | `1 passed` | fails, `test_cancel_decides_without_asking` missing |
| S3 | replace `"y" * 2001` with `"y" * 2002` (`tests/e2e/test_cli_ask.py`) | `.venv/bin/python docs/verification/probe-09q.py` | `FAILURES 0` | check 1 `FAIL`, `FAILURES 1` |
| S4 | replace the first `@pytest.fixture(autouse=True)` with `@pytest.fixture` (`tests/e2e/test_cli_tool_check_commands.py`) | `.venv/bin/python docs/verification/probe-09q.py` | `FAILURES 0` | check 2 `FAIL`, `FAILURES 1` |

Notes for tracing:
- S1, S2: the renamed function is no longer collected as a test, so the file's set of `test_` functions lacks one name.
- S3: the literal sits in `test_a_request_of_2001_characters_is_refused`, a moved test, so its canonical form differs. The node ids and the autouse set do not change, so checks 2 and 3 stay `ok`.
- S4: the fixture keeps its code but is no longer autouse, so the file's autouse set loses it. The CLI tests in that file may also fail at G1; that is not the point of this row.

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Renamed helpers, constants and fixtures in the moved part named however the coder chose, as long as the probe passes.
- The moved part's code after the base file's code with or without a separating comment.
- `ruff format` rewrapping a merged import block.

## 7. Out of scope

Each must be absent:
- Any change to another test family, `conftest.py`, `tests/support.py` or `tests/sections.toml`.
- A renamed, re-ordered or re-worded test, or a changed parameter list or id.
- An edit inside a renamed file.
- Any change to `src/`, `scripts/`, `pyproject.toml`, a given file, `AGENTS.md` or the design docs.

## 8. Verdict

Write `docs/reviews/phase-09q-cli-test-families.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9q`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9q` must print `Reports OK.`
