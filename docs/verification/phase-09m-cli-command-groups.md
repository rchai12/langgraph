# Verify Phase 9m: CLI command groups

Spec: `docs/phases/phase-09m-cli-command-groups.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09m-cli-command-groups.md`.

## First: establish that the coder ran

- No `## Phase 9m: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09m-cli-command-groups.md docs/verification/phase-09m-cli-command-groups.md tests/unit/test_cli_layout.py docs/verification/probe-09m.py` must succeed, and `git diff a9c5485 -- tests/e2e/test_cli_web_shutdown.py` must show only the committed edit (`main` to `web` on three lines). The gates judge against a committed baseline.

The coder:
- split `src/conductor/cli/main.py` into `common.py`, `runs.py`, `approvals.py`, `escalations.py`, `evals.py` and `web.py`, leaving `doctor`, `ask`, `resume` and the wiring in `main.py`;
- folded the confirm-record-resume steps into `common.decide_then_resume`, used by the five decision commands;
- wrote `tests/e2e/test_cli_groups_more.py`.

## 1. Gates

N is `1404`. Given count: 32. `.venv/bin/python scripts/accept.py --phase 9m --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli` | last line `All checks passed.`; at least 1436 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/cli/*' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_cli_layout.py --no-cov -q` | `32 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09m.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_cli_layout.py docs/verification/probe-09m.py tests/e2e/test_cli_web_shutdown.py tests/support.py pyproject.toml src/conductor/runtime.py src/conductor/decisions.py src/conductor/views.py src/conductor/policy.py src/conductor/store.py src/conductor/web` | no output |
| G6 | `git diff a9c5485 --stat -- tests ':!tests/unit/test_cli_layout.py' ':!tests/e2e/test_cli_web_shutdown.py' ':!tests/e2e/test_cli_groups_more.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9m: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9m` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_cli_package_holds_one_module_per_group`; `pyproject.toml` entry point (G5) | pass; unchanged |
| R2 | `test_each_command_lives_in_its_group_module_with_todays_options` (16 cases); probe check 1 | pass; `ok` |
| R3 | `test_commands_and_groups_are_listed_in_todays_order`; probe check 2 | pass; `ok` |
| R4 | `test_each_module_imports_only_common_from_the_cli` (6 cases), `test_main_wires_every_group_module`; search 12 | pass; silent |
| R5 | `test_common_holds_the_shared_plumbing` | pass |
| R6 | the six `decide_then_resume` tests in `test_cli_layout.py` | pass |
| R7 | searches 8 to 10; read each decision command against the spec's Part 2 table; the coder's reject and cancel test | silent; prompt, preview and line as the table gives; pass |
| R8 | probe checks 2 and 3; `tests/e2e/test_cli_*.py` (in G1) | `ok`; pass |
| R9 | `tests/e2e/test_cli_web_shutdown.py` and the other CLI tests (in G1); search 12; the coder's `--args '[1]'` test | pass; silent; pass |
| R10 | G2, G5, G6, G7; search 7 | as given; silent |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09m.py` (G4). Its oracle is the predecessor's `cli/main.py`, read from commit a9c5485 with `git show` and loaded as a separate module. Each session runs on the old app and then the new one, each in a fresh data directory with the same fixed clock, ids, scripted model replies, fake `uvicorn.run` and port. It checks:
- the layout: `web`, `runs show`, `eval run`, `approvals edit` and `escalations retry` are defined in their group modules;
- every `--help` text (root, the four groups, all 16 commands) is as before;
- 19 forced sessions, one for each decision path, and 300 random ones agree. A random session is a start (empty, a pending plan, a pending step, an open escalation), then one to three base commands, each with at most one change: a wrong id, a dropped word, `--json`, `--no-resume`, bad `--args`, a `n` answer or an unknown flag. For every step, the exit code, standard output, standard error and any uncaught exception type must agree, and so must the stored approvals, escalations, runs and events, which the old app reads back. The probe also requires that recorded decisions, refused confirmations, errors, usage errors, edited approvals and retries were each reached at least 5 times.

Before handover the architect ran it on today's code. The layout check printed `FAIL`, and the other two printed `ok`, because both sides were the same file. When `Nothing recorded.` lost its full stop in a scratch copy, the session check printed `FAIL`. So a help or session failure on the build points at a changed command line.

A stop at its own `assert` lines, or a `git show` failure, is the probe's fault (or a missing commit). Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/cli
git grep --untracked -n -E 'decide_approval\(' -- src/conductor/cli ':!src/conductor/cli/approvals.py'
git grep --untracked -n -E 'answer_escalation\(' -- src/conductor/cli ':!src/conductor/cli/escalations.py'
git grep --untracked -n -E 'confirm\(' -- src/conductor/cli ':!src/conductor/cli/common.py'
git grep --untracked -n -E 'uvicorn|socket' -- src/conductor/cli ':!src/conductor/cli/web.py'
git grep --untracked -n -E '^from \.|import \*|from conductor\.runtime import|from uvicorn import|from conductor\.evals\.run import' -- src/conductor/cli
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09m`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match). Then run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09m`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (module) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | in `decide_then_resume`, echo `line` before calling `record()` (`common.py`) | `tests/unit/test_cli_layout.py::test_a_refused_decision_prints_no_line_and_does_not_resume` | out `''` | out `'Rejected a2.\n'` |
| S2 | `typer.confirm(prompt, default=False)` becomes `default=True` (`common.py`) | `tests/unit/test_cli_layout.py::test_a_refused_confirmation_records_nothing` | `{'default': False}` | `{'default': True}` |
| S3 | swap the `runs` and `eval` `add_typer` lines (`main.py`) | `tests/unit/test_cli_layout.py::test_commands_and_groups_are_listed_in_todays_order` | root `..., 'runs', 'eval', ...` | root `..., 'eval', 'runs', ...` |
| S4 | add `from conductor.cli import approvals` under the imports (`escalations.py`) | `tests/unit/test_cli_layout.py::test_each_module_imports_only_common_from_the_cli[escalations]` | `{'conductor.cli.common'}` | `'conductor.cli.approvals'` extra |
| S5 | in `decide_then_resume`, drop the echo of the preview (`common.py`) | `tests/unit/test_cli_layout.py::test_an_accepted_confirmation_records_then_resumes` | out starts `approval a1  plan  pending` | out starts `Approved a1.` |

Notes for tracing:
- S1: `record` raises `Refused`, so `pytest.raises` still passes; the captured output is the first assertion that fails.
- S2: the fake `confirm` still refuses (the list holds `"refuse"`), so the output matches; `seen` is the first assertion that fails.
- S3: `get_command` lists the root's commands, then its groups, in registration order.
- S4: the import is unused at run time; only the layer rule sees it.
- S5: the fake `confirm` prints nothing, so the preview is the only text before the line.

Spot rows that make the same change in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside a group module (such as a module's own `_when`), and imports of several common names in one statement or several.
- `decide_then_resume` written with an early return or a nested condition, as long as the order in the spec holds.
- A command's `record` written as a nested function or a `functools.partial`.
- Extra behaviour tests in `tests/e2e/test_cli_groups_more.py`.

## 7. Out of scope

Each must be absent:
- Any changed command name, help text, argument, option, default, prompt, preview, message, exit code, output or order.
- A decision, check, retry or default added to the CLI, or a decision moved out of `conductor.decisions` or the policy.
- New commands or options, completion, `--version`, `rich` formatting, or help-changing docstrings.
- Any change to `runtime`, `decisions`, `views`, `web`, `store`, `policy` or `pyproject.toml`.
- Code shared between `conductor.cli` and `conductor.web`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09m-cli-command-groups.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9m`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9m` must print `Reports OK.`
