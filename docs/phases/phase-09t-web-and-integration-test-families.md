# Phase 9t: Web and integration test families by behaviour

## Goal

This is the second of four slices that fold the test files named for when they were added back into files named for what they cover (Phase 9q did the CLI families). It moves the three web families in `tests/e2e/` and the eight families in `tests/integration/`, and changes no test.

| Today | After |
|---|---|
| `tests/e2e/test_web_resume_more.py` | merged into `tests/e2e/test_web_resume.py` |
| `tests/integration/test_mcp_client_more.py` | merged into `tests/integration/test_mcp_client.py` |
| `tests/integration/test_runtime_more.py` | merged into `tests/integration/test_runtime.py` |
| `tests/integration/test_supervisor_more.py` | merged into `tests/integration/test_supervisor.py` |
| `tests/e2e/test_web_decide_more.py` | renamed `tests/e2e/test_web_decide_forms.py` |
| `tests/e2e/test_web_pages_more.py` | renamed `tests/e2e/test_web_page_safety.py` |
| `tests/integration/test_mcp_steps_more.py` | renamed `tests/integration/test_mcp_step_runners.py` |
| `tests/integration/test_resume_evidence_more.py` | renamed `tests/integration/test_resume_failed_note.py` |
| `tests/integration/test_dollars_more.py` | renamed `tests/integration/test_dollars_spending_run.py` |
| `tests/integration/test_finance_more.py` | renamed `tests/integration/test_finance_prefixed_request.py` |
| `tests/integration/test_finance_proposals_more.py` | renamed `tests/integration/test_finance_proposal_approvals.py` |

Decided with the owner (2026-11-21, for all four slices; see Phase 9q):
- A suffixed file merges into its module's `test_<module>.py`. One with no base file is renamed to the behaviour it covers.
- When its autouse fixtures or `pytestmark` differ from the base file's, it is renamed instead of merged, so no test gains a fixture.
- Every test function's code stays AST-identical, with the same name and parameter ids. A module-level name defined in both parts is kept once when its code is the same apart from a docstring. When its code differs, it is renamed in the moved part only, where it is used.
- The collected count, the section counts and coverage are unchanged. `tests/unit/test_suite_layout.py` refuses a name that says when a file was added, apart from its `PENDING` list.

Decided by the architect, within those answers:
- The seven new names are fixed above (the layout test pins them).
- "Differ" means after resolving names, as the probe does, not as text. `test_mcp_steps_more.py`'s autouse `lab` fixture reads exactly like the base file's, but it uses a `LAB` constant whose code differs. Merged, the moved tests would run under the base's `LAB`, so this family is renamed. `test_web_decide_more.py` lacks the base's `demo_on`. `test_web_pages_more.py` and `test_resume_evidence_more.py` differ in `fixed`.
- `test_dollars_more.py`, `test_finance_more.py` and `test_finance_proposals_more.py` have no base file, so they are renamed. They are not merged into `test_finance_steps.py` or `test_finance_proposal_steps.py`, which are other modules' behaviour files.
- In the four merges, the names to keep once and to rename are:

  | Merge | Keep once (same code) | Rename in the moved part |
  |---|---|---|
  | `test_web_resume.py` | `BASE`, `TOKEN`, `BUTTON`, `Still`, `fixed`, `client` | `Raising`, `post`, `failed_once` |
  | `test_mcp_client.py` | none | the fixture `fake` |
  | `test_runtime.py` | `START`, `NOW`, `OTHER`, `NOTE_PLAN`, `ECHO_PLAN`, `fixed`, `mode` | none |
  | `test_supervisor.py` | `ECHO_PLAN`, `NOTE_PLAN`, `REPLY`, `fixed` | `RUN`, `World` |

  The coder chooses the new names (for example `RUN_TWO`).
- The given layout test is edited from Phase 9q's: the eleven files leave `PENDING`, and their eleven targets join `MOVED`. 9q's five targets stay, so its moves stay guarded.

## Read first

- The given files below, in full: they are the contract.
- The fifteen old files the probe's `MOVES` table lists, in full.
- `tests/sections.toml` and `docs/testing.md` rule 9.

## Starting state

Phase 9q is built and verified, and everything is committed at b1b529e: 1555 tests. N is `1540`: the suite without `tests/unit/test_suite_layout.py`, whose 15 tests this phase replaces with the edited file's 26. **Sections: scripts 30, cli 122, core 1403.** No production code changes.

## Scope

| Path | What |
|---|---|
| `tests/e2e/test_web_resume.py`, `tests/integration/test_mcp_client.py`, `tests/integration/test_runtime.py`, `tests/integration/test_supervisor.py` | each gains the tests of its `_more` file |
| `tests/e2e/test_web_resume_more.py`, `tests/integration/test_mcp_client_more.py`, `tests/integration/test_runtime_more.py`, `tests/integration/test_supervisor_more.py` | deleted |
| the seven renames in the table above | `git mv`, content unchanged |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- Every unit family (9u, 9v), and the CLI files 9q moved.
- Renaming, re-wording or re-ordering a test, changing a parameter list or id, or sharing a fixture through `conftest.py` or `tests/support.py`.
- Editing a renamed file's content.
- Any change to `src/`, `scripts/`, `pyproject.toml`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the four merges

For each merge in the table:
1. Append the suffixed file's module-level code after the base file's, without its imports.
2. Merge its imports into the base file's import block. `ruff check --fix` sorts them.
3. Delete the moved part's copy of each "keep once" name. Rename each "rename" name in the moved part, and its uses there.
4. `git rm` the suffixed file.

Keep the moved tests in their original order, after the base file's tests.

### Part 2: the seven renames

`git mv` each file to its new name. Change nothing inside.

## Requirements

### Part 1: where the tests are

- **R1.** No test file outside the layout test's `PENDING` list has a name that says when it was added.
- **R2.** Each of the sixteen target files (9q's five and this phase's eleven) holds exactly the test functions listed for it in the layout test.
- **R3.** The seven renamed files are byte-identical to the files they replace (`git diff -M --stat` shows each as a rename with no changes).

### Part 2: what the tests do

- **R4.** Every test function of the fifteen old files is AST-identical to its twin, and every module-level name it uses resolves to a definition with the same code (probe check 1).
- **R5.** Every moved test runs under the same autouse fixtures and `pytestmark` as before (probe check 2).
- **R6.** The suite collects the same node ids as at b1b529e, with only the moved files' paths changed, apart from the layout test (probe check 3). The collected count is exactly N + the given count.
- **R7.** Section counts: `scripts` 30, `cli` 122, `core` 1414. Every moved file stays in `core`.
- **R8.** Only the Scope paths change. There is no new `noqa`, `pragma: no cover`, `skip` or `xfail` in a moved file.

## Given files

Committed with this spec. Do not change them; if a given test fails, the moves are wrong. Before your change, 12 of the given tests fail and 14 pass. The 14 are 9q's five targets and the naming rule's nine cases, which hold today.

| File | What it is |
|---|---|
| `tests/unit/test_suite_layout.py` | R1, R2: only `PENDING` files are suffixed, the sixteen target files and their test functions, and the naming rule's cases (26 tests from 3 functions) |
| `docs/verification/probe-09t.py` | the probe, run by its path in Acceptance |

Given test count: **26**.

## Tests to write

None. This phase adds no behaviour. R3 to R8 are checked by the probe, the protected diffs and the searches.

## Rules for this phase

- A move changes no test. If a moved test fails after the move, the move is wrong: undo it and look for the name it now resolves to.
- When a probe check prints `FAIL`, the lines above it name each test, file or count it rejected.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Facts

Checked on 2026-11-21 with the project's Python 3.12, outside the repository:
- Phase 9q's probe method held on its build: the canonical form found every moved test, and the reach count came out exactly.
- Comparing the fifteen old files by canonical form gave the merge and rename split and the name table above. A text comparison had called `test_mcp_steps`'s two `lab` fixtures the same.
- The oracle counts 86 test functions in the fifteen old files, the same as the layout test lists for the eleven targets.
- No moved file has a `noqa`, `skip`, `xfail` or `importorskip` today.
- On today's tree the probe printed `FAIL` for all three checks and reached `FAILURES 3`.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9t` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against b1b529e (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1566 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1414`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1566 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_suite_layout.py --no-cov -q` | `26 passed` |
| `.venv/bin/python docs/verification/probe-09t.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09t-web-and-integration-test-families.md) --stat -- tests/unit/test_suite_layout.py docs/verification/probe-09t.py` | no output |
| `git diff b1b529e --stat -- src scripts tests pyproject.toml ':!tests/e2e/test_web_resume.py' ':!tests/e2e/test_web_resume_more.py' ':!tests/integration/test_mcp_client.py' ':!tests/integration/test_mcp_client_more.py' ':!tests/integration/test_runtime.py' ':!tests/integration/test_runtime_more.py' ':!tests/integration/test_supervisor.py' ':!tests/integration/test_supervisor_more.py' ':!tests/e2e/test_web_decide_more.py' ':!tests/e2e/test_web_decide_forms.py' ':!tests/e2e/test_web_pages_more.py' ':!tests/e2e/test_web_page_safety.py' ':!tests/integration/test_mcp_steps_more.py' ':!tests/integration/test_mcp_step_runners.py' ':!tests/integration/test_resume_evidence_more.py' ':!tests/integration/test_resume_failed_note.py' ':!tests/integration/test_dollars_more.py' ':!tests/integration/test_dollars_spending_run.py' ':!tests/integration/test_finance_more.py' ':!tests/integration/test_finance_prefixed_request.py' ':!tests/integration/test_finance_proposals_more.py' ':!tests/integration/test_finance_proposal_approvals.py' ':!tests/unit/test_suite_layout.py'` | no output |
| `git diff -M b1b529e --stat -- tests/e2e/test_web_decide_more.py tests/e2e/test_web_decide_forms.py tests/e2e/test_web_pages_more.py tests/e2e/test_web_page_safety.py tests/integration/test_mcp_steps_more.py tests/integration/test_mcp_step_runners.py tests/integration/test_resume_evidence_more.py tests/integration/test_resume_failed_note.py tests/integration/test_dollars_more.py tests/integration/test_dollars_spending_run.py tests/integration/test_finance_more.py tests/integration/test_finance_prefixed_request.py tests/integration/test_finance_proposals_more.py tests/integration/test_finance_proposal_approvals.py` | seven `=>` lines with `0` changes, and `7 files changed, 0 insertions(+), 0 deletions(-)` |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9t: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9t` (after writing progress) | `Reports OK.` |

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
git grep --untracked -n -E 'noqa|pragma: no cover|pytest\.mark\.(skip|xfail)|importorskip' -- tests/e2e/test_web_resume.py tests/integration/test_mcp_client.py tests/integration/test_runtime.py tests/integration/test_supervisor.py tests/e2e/test_web_decide_forms.py tests/e2e/test_web_page_safety.py tests/integration/test_mcp_step_runners.py tests/integration/test_resume_failed_note.py tests/integration/test_dollars_spending_run.py tests/integration/test_finance_prefixed_request.py tests/integration/test_finance_proposal_approvals.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Web and integration test families by behaviour`, with `--tests-before 1555 --given 26` (the layout test's 15 tests are counted in 1555 and replaced by its 26).
