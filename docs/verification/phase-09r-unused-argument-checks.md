# Verify Phase 9r: Unused-argument checks

Spec: `docs/phases/phase-09r-unused-argument-checks.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09r-unused-argument-checks.md`.

## First: establish that the coder ran

- No `## Phase 9r: ` entry in `docs/progress.md` and no Scope path changed since 6b26679: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09r-unused-argument-checks.md docs/verification/phase-09r-unused-argument-checks.md tests/unit/test_lint_rules.py docs/verification/probe-09r.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff $(git log -1 --format=%h -- docs/phases/phase-09r-unused-argument-checks.md)` plus untracked files. G5 to G8 use the spec's commit and 6b26679, so they hold either way.

The coder:
- added `"ARG"` to the Ruff selection;
- fixed the nine source findings as the spec's Part 2 table gives;
- fixed the test findings by the spec's six rules, with no change of behaviour.

## 1. Gates

N is `1597`. Given count: 17. `.venv/bin/python scripts/accept.py --phase 9r --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1614 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1462`, each 0 failed |
| G2 | `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1614 tests collected` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_lint_rules.py --no-cov -q` | `17 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09r.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09r-unused-argument-checks.md) --stat -- tests/unit/test_lint_rules.py docs/verification/probe-09r.py` | no output |
| G6 | `git diff 6b26679 --stat -- src scripts .claude tests/conftest.py tests/support.py tests/sections.toml ':!src/conductor/cli/approvals.py' ':!src/conductor/cli/escalations.py' ':!src/conductor/cli/main.py' ':!src/conductor/graph/nodes.py' ':!src/conductor/runtime.py' ':!.claude/skills/phase-architect/history.md'` | no output |
| G7 | `git diff 6b26679 --stat -- src` | last line `5 files changed, 8 insertions(+), 8 deletions(-)` |
| G8 | `git diff 6b26679 --stat -- pyproject.toml` | `1 file changed, 1 insertion(+), 1 deletion(-)` |
| G9 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G10 | `grep -c '^## Phase 9r: ' docs/progress.md` | `1` |
| G11 | `.venv/bin/python scripts/check_reports.py --phase 9r` | `Reports OK.` |

G1 runs `ruff check .` with the new selection, so it also covers R2.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_rule_selection_is_exact`; G8 | pass; as given |
| R2 | G1; probe check 3 | as given; `ok` |
| R3 | probe checks 1 and 2 | `ok` |
| R4 | `test_every_noqa_in_the_tree_stands_where_it_may`, `test_where_a_noqa_may_stand` (15 cases) | pass |
| R5 | G7; read `git diff 6b26679 -- src` against the spec's Part 2 table; search 7 | as given; the same nine repairs; silent |
| R6 | G1, G2 | as given |
| R7 | G5, G6, G9; search 8 | as given; silent |

Then read every `noqa: ARG` line, which is `git grep -n 'noqa: ARG' -- tests`. The architect's scripted repair had 37: 32 in `tests/fake_finances_server.py`, `time` in `db` in `tests/unit/test_store.py`, and four keyword names. For each line outside `tests/fake_finances_server.py`, name the rule (3, 4 or 5) it rests on. For rule 5, also name the keyword-only marker or the call that passes the name by keyword. The given test accepts any name that `src/` passes by keyword somewhere, such as `run_id` or `settings`, so it cannot tell that a positional-only use was not renamed. Such a line, where rule 6 fits, is a finding against R4. Spot check it in a scratch copy: rename the parameter `_name` and run its file's tests. If they pass, rule 6 applied.

## 3. Probe

The probe is the given file `docs/verification/probe-09r.py` (G4). Its oracle is the tree at 6b26679, unpacked with `git archive`. It reduces each Python file under `src`, `tests`, `scripts` and `.claude` to its syntax tree, on both sides, after these normalisations from the spec's repair rules:
- an ordinary function's, method's or lambda's parameters lose one leading `_`;
- a test function or fixture is reduced to the sorted set of fixtures it requests, counting `@pytest.mark.usefixtures` names and leaving out `tmp_path` and `monkeypatch`;
- `wait_escalation` in `src/conductor/graph/nodes.py` loses `config`;
- an imported name nothing reads any more is dropped.

It checks:
1. the same Python files exist on both sides, apart from the given test;
2. every changed file has the same normalised tree on both sides;
3. `ruff check --select ARG .` reports nothing.

Comments are not in the tree, so check 2 ignores every `noqa`; the given test judges where they stand. The oracle checks itself on 18 known cases (its `assert` lines) before it reads the tree.

Before handover the architect ran the probe on today's tree: checks 1 and 2 printed `ok` (nothing has changed yet), check 3 printed `FAIL` (230 findings), and the run reached `FAILURES 1`. On a scratch copy repaired by script under the spec's rules, all three printed `ok`. When a check fails, the lines above it name each file or count it rejected.

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
git grep --untracked -n -E 'noqa: *[A-Z0-9, ]*ARG|pragma: no cover' -- src
git grep --untracked -n -E 'pytest\.mark\.(skip|xfail)|importorskip' -- tests
```

## 5. Spot checks

Make each change by hand in a scratch copy of the reviewed bytes. Make the copy with `git clone -q . <scratch>/spot09r`, then `rsync -a --delete src tests pyproject.toml <scratch>/spot09r/`, and link `.venv`. Run from the copy's root with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=<scratch>/spot09r/src`. The copy's commit must be the build's base, so the probe's `git archive 6b26679` works there. Before the next row, restore the copy with the same `rsync`. Each change is the shape of an edit; copy the exact old text from the coder's file (one match).

| # | Change (file) | Run | Correct | Broken |
|---|---|---|---|---|
| S1 | replace `"UP", "ARG"]` with `"UP"]` (`pyproject.toml`) | `.venv/bin/python -m pytest tests/unit/test_lint_rules.py::test_the_rule_selection_is_exact --no-cov -q` | `1 passed` | fails, the selection lacks `'ARG'` |
| S2 | replace the `# noqa: ARG001` on the `time` parameter of `db` with `# noqa` (`tests/unit/test_store.py`) | `.venv/bin/python -m pytest tests/unit/test_lint_rules.py::test_every_noqa_in_the_tree_stands_where_it_may --no-cov -q` | `1 passed` | fails, `tests/unit/test_store.py` |
| S3 | replace `def wait_escalation(state: State) -> Command:` with `def wait_escalation(state: State) -> Command:  # noqa: ARG001` (`src/conductor/graph/nodes.py`) | `.venv/bin/python -m pytest tests/unit/test_lint_rules.py::test_every_noqa_in_the_tree_stands_where_it_may --no-cov -q` | `1 passed` | fails, `src/conductor/graph/nodes.py` |
| S4 | append `, E501` to the `# noqa: ARG001` on the `count` parameter of `month_over_month` (`tests/fake_finances_server.py`) | `.venv/bin/python -m pytest tests/unit/test_lint_rules.py::test_every_noqa_in_the_tree_stands_where_it_may --no-cov -q` | `1 passed` | fails, `tests/fake_finances_server.py` |
| S5 | in `ask`'s `work` closure, replace `_settings: Settings` with `_: Settings` (`src/conductor/cli/main.py`) | `.venv/bin/python docs/verification/probe-09r.py` | `FAILURES 0` | check 2 `FAIL`, `src/conductor/cli/main.py`, `FAILURES 1` |
| S6 | replace `def wait_escalation(state: State) -> Command:` with `def wait_escalation(state: State, config: RunnableConfig) -> Command:` (`src/conductor/graph/nodes.py`) | `.venv/bin/python docs/verification/probe-09r.py` | `FAILURES 0` | check 3 `FAIL`, `1 unused-argument findings`, `FAILURES 1` |

Notes for tracing:
- S1: the given test compares the whole `[tool.ruff]` table, so the shorter `select` list differs.
- S2: a bare `noqa` hides every rule on its line, so the tree check reports it whatever the line holds.
- S3: `wait_escalation` now has no unused parameter, so the `noqa` hides no contract name.
- S4: a contract line's `noqa` may list only `ARG` codes.
- S5: `_` is a name Ruff accepts as unused, but the spec's rule 6 asks for `_settings`. The probe strips one leading `_`, and `_` stays `_`, so the parameter differs from `settings`.
- S6: the normalisation drops `config` from `wait_escalation` on both sides, so check 2 stays `ok`. Only Ruff sees the unused parameter again.

The architect ran all six rows on the scratch copy repaired by script, and each gave its "Broken" result. A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a check that cannot see the change (say which in "For the architect").

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- One `@pytest.mark.usefixtures("a", "b")` mark or one mark per fixture, above or below the other marks.
- `ruff format` rewrapping a signature, as long as each `noqa` stays on a line with a contract name.
- `# noqa: ARG001` or `# noqa: ARG002` as Ruff names the finding.
- An extra keyword-name `noqa` the architect's script did not need, when the coder shows the call that passes the name by keyword.

## 7. Out of scope

Each must be absent:
- `per-file-ignores`, `extend-ignore`, `ignore`, a `flake8-unused-arguments` table, a changed `dummy-variable-rgx`, a new `extend-exclude`, or any rule beyond `ARG`.
- A deleted parameter outside rule 1 and `wait_escalation`, a rename other than `_` plus the old name, or an argument used only to silence Ruff.
- A changed test body, test name or parameter set, or a renamed fake MCP tool parameter.
- Any change to `scripts/`, `.claude/`, `tests/conftest.py`, `tests/support.py`, `tests/sections.toml`, a given file, `AGENTS.md` or the design docs.

## 8. Verdict

Write `docs/reviews/phase-09r-unused-argument-checks.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9r`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9r` must print `Reports OK.`
