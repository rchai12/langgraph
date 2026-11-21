# Phase 9m: CLI command groups

## Goal

`src/conductor/cli/main.py` is 515 lines: the root commands, the `runs`, `approvals`, `escalations` and `eval` groups, the `web` command and every helper they share. Each decision command repeats the same steps: confirm, record, print, resume. This phase splits the module into one module per command group plus one module of shared plumbing. The confirm-record-resume sequence becomes one shared helper, `decide_then_resume`. No command name, argument, option, default, prompt, message, exit code or output changes. The decisions stay in `conductor.decisions` and the policy behind it.

Decided with the owner (2026-11-20):
- **Layout.** There is one module per command group: `runs.py`, `approvals.py`, `escalations.py`, `evals.py` and `web.py`, beside a `main.py` that keeps `doctor`, `ask` and `resume` and wires the groups together.
- **Sharing.** The plumbing the groups share lives in `common.py`: settings, error reporting, opening a store or a runtime, output, the run-state text, and the confirm-record-resume sequence. Each decision command keeps its own `decide_approval` or `answer_escalation` call, its prompt, its preview and its message.
- **The web command.** `web` moves to `web.py`. The one existing test that patches names in `main`, `tests/e2e/test_cli_web_shutdown.py`, is edited to patch them in `conductor.cli.web` (the edit is committed with this spec).

Decided by the architect, within those answers:
- `common.py` imports nothing from `conductor.cli`. The group modules import only `conductor.cli.common` from the CLI, never each other. `main.py` imports all six. So no import cycle is possible.
- The entry point stays `conductor.cli.main:app`, and `from conductor.cli.main import app` keeps working for every test and helper that uses it.
- The private helpers `_allow`, `_stopped` and `_recorded` become the one public `decide_then_resume`. `_bail`, `_settings`, `_CAUGHT`, `_report`, `_run`, `_session`, `_dump`, `_state_text` and `_emit` become public names in `common.py`. Helpers used by one group move into that group's module and stay private: `_approval_json`, `_json_object` and `_args` go to `approvals.py`, `_escalation_json` to `escalations.py`, `_case_files` to `evals.py`. `_when` becomes `times.display` at each use, or a private helper in each module that needs it.
- Commands keep their function names. The `web` command's function is `serve` in `web.py`, so it does not shadow the module name.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/cli/main.py` (all of it).
- `tests/e2e/test_cli_ask.py`, `tests/e2e/test_cli_approvals.py`, `tests/e2e/test_cli_escalations.py` and `tests/e2e/test_cli_web_shutdown.py`: they pin the commands' whole output and must keep passing. The last of these carries the one edit described under "Given files".
- `docs/architecture.md` ("Repository layout") only where this phase changes it.

## Starting state

Phase 9l is built and verified, and everything is committed: N is `1404`. **Sections: cli, core.** `conductor.cli` holds only `__init__.py` and `main.py`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/cli/main.py` | reduced to `app`, `doctor`, `ask`, `resume` and the wiring (Part 1) |
| `src/conductor/cli/common.py` | new: the shared plumbing and `decide_then_resume` (Parts 1 and 2) |
| `src/conductor/cli/runs.py` | new: `app`, `runs list`, `runs show` (Part 1) |
| `src/conductor/cli/approvals.py` | new: `app` and the five approval commands (Part 1) |
| `src/conductor/cli/escalations.py` | new: `app` and the four escalation commands (Part 1) |
| `src/conductor/cli/evals.py` | new: `app` and `eval run` (Part 1) |
| `src/conductor/cli/web.py` | new: `serve`, the `web` command (Part 1) |
| `tests/e2e/test_cli_groups_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files and the edit to `tests/e2e/test_cli_web_shutdown.py` are already committed; they are not in the Scope and never change.

## Out of scope

- Any change to a command's name, help text, argument, option, default, prompt, preview, message, exit code, output or order.
- Moving decisions out of `conductor.decisions`, `conductor.policy` or the store, or adding a check, a retry or a default to a command.
- New commands or options, shell completion, a `--version` option, `rich` formatting, or docstrings that change the help text.
- Changes to `conductor.runtime`, `conductor.decisions`, `conductor.views`, `conductor.web`, `conductor.store`, `conductor.policy` or `pyproject.toml`.
- Sharing code between `conductor.cli` and `conductor.web`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: the modules

```
src/conductor/cli/
    __init__.py      unchanged
    main.py          app; doctor, ask, resume; registers the groups and web
    common.py        CAUGHT, bail, load_settings, report, with_store, with_runtime,
                     dump, state_text, emit, decide_then_resume
    runs.py          app; list_runs, show
    approvals.py     app; list_approvals, show_approval, approve, reject, edit
    escalations.py   app; list_escalations, show_escalation, retry, cancel
    evals.py         app; eval_run
    web.py           serve
```

Each of `runs.py`, `approvals.py`, `escalations.py` and `evals.py` defines `app = typer.Typer(no_args_is_help=True, add_completion=False)` and registers its commands on it with today's names (`@app.command("list")` and so on), in today's order. `main.py` defines its `app` the same way, defines `doctor`, `ask` and `resume` in that order, and then wires:

```python
app.add_typer(runs.app, name="runs")
app.add_typer(evals.app, name="eval")
app.add_typer(approvals.app, name="approvals")
app.add_typer(escalations.app, name="escalations")
app.command("web")(web.serve)
```

`web` is registered after `resume`, because Typer lists a group's commands in the order they were registered. Each command's parameters (names, `Annotated` options, defaults) are copied unchanged.

The shared names in `common.py` are today's helpers renamed. Their bodies are unchanged:

| Today in `main.py` | In `common.py` |
|---|---|
| `_CAUGHT` | `CAUGHT` |
| `_bail(message)` | `bail(message: str) -> NoReturn` |
| `_settings()` | `load_settings() -> Settings` |
| `_report(error)` | `report(error: BaseException) -> NoReturn` |
| `_run(work)` | `with_store(work: Callable[[Settings, Store], None]) -> None` |
| `_session(work)` | `with_runtime(work: Callable[[Settings, runtime.Runtime], None]) -> None` |
| `_dump(value)` | `dump(value: object) -> None` |
| `_state_text(opened, found)` | `state_text(opened: runtime.Runtime, found: RunState) -> str` |
| `_emit(opened, found, json_output)` | `emit(opened: runtime.Runtime, found: RunState, json_output: bool) -> None` |

Names tests patch are reached through their modules at call time, as today:
- `runtime.open_runtime`, `runtime.ask` and `runtime.resume` are called as `runtime.X` after `from conductor import runtime`.
- `evals_run.model_for` is called the same way, after `from conductor.evals import run as evals_run`.
- `domains.registered` is called as `domains.registered`.
- `uvicorn.run` is called after `import uvicorn`.
- `web.py` imports `Resumer` and `create_app` by name and calls them as module globals. The edited web test patches `conductor.cli.web.Resumer` and `conductor.cli.web.create_app`.

`approvals edit` still parses `--args` with `_json_object` before it opens the runtime, so a bad `--args` opens nothing.

### Part 2: `decide_then_resume`

```python
def decide_then_resume(
    opened: runtime.Runtime,
    run_id: str,
    record: Callable[[], object],
    line: str,
    *,
    no_resume: bool,
    confirm: tuple[str, str] | None = None,
    yes: bool = False,
) -> None:
```

`confirm` is `(prompt, preview)`. In order:
1. If `confirm` is given and `yes` is false: echo `preview`, then call `typer.confirm(prompt, default=False)`. If it returns false, echo `Nothing recorded.` and return.
2. Call `record()`. If it raises, the exception propagates: no line is printed and nothing resumes.
3. Echo `line`.
4. Unless `no_resume`: `emit(opened, runtime.resume(opened, run_id), False)`.

Each decision command looks up its approval or escalation, builds its `record` from its own `decide_approval` or `answer_escalation` call, and calls `decide_then_resume`:

| Command | `confirm` | `line` |
|---|---|---|
| `approvals approve` | `("Approve?", the request lines)` | `Approved <id>.` |
| `approvals reject` | none | `Rejected <id>.` |
| `approvals edit` | `("Approve with these arguments?", the request lines + "\nedited args: <args>")` | `Approved <id> with edited arguments.` |
| `escalations retry` | `("Retry?", the escalation lines)` | `Retry recorded for <id>.` |
| `escalations cancel` | none | `Cancelled <id>.` |

`typer.confirm` is called only in `common.py`, `decide_approval` only in `approvals.py`, and `answer_escalation` only in `escalations.py`. The Acceptance searches check this.

## Facts

Checked on 2026-11-20 with typer 0.27.3 and click 8.5.0, on today's code:
- `typer.main.get_command(app)` lists a group's own commands first, then its sub-groups, each in registration order. Today the root lists `doctor, ask, resume, web, runs, eval, approvals, escalations`.
- A command's click `callback` is the decorated function itself, so `callback.__module__` names the module that defines it. Today all 16 commands report `conductor.cli.main`.
- Outside `tests/e2e/test_cli_web_shutdown.py`, tests reach the CLI only through `app` and patch only module attributes (`runtime.open_runtime`, `runtime.resume`, `runtime.read_state`, `evals_run.model_for`, `domains.DOMAINS`, `uvicorn.run`, `clock.now`, `ids.new_id`, `diagnostics.python_version`). Moving code keeps them working while those names are called through their modules.
- The probe loads the predecessor's `cli/main.py` from commit a9c5485 with `git show`. It replays 19 forced and 300 random sessions on that module and on the code under test. Each session runs in a fresh data directory with a fixed clock and fixed ids, a scripted model, a fake `uvicorn.run` and a free or taken local port. On today's code, its help and session checks print `ok`, because the two copies are the same file, and its layout check fails. When `Nothing recorded.` lost its full stop in a scratch copy, the session check failed.

## Requirements

### Part 1: the modules

- **R1.** `conductor.cli` holds `__init__.py`, `approvals.py`, `common.py`, `escalations.py`, `evals.py`, `main.py`, `runs.py` and `web.py`. The entry point is still `conductor.cli.main:app`.
- **R2.** Each of the 16 commands is defined in its group's module (`doctor`, `ask` and `resume` in `main`; `web` in `web`; `eval run` in `evals`), with today's arguments, options, defaults and required flags.
- **R3.** The root and each group list their commands in today's order.
- **R4.** `common.py` imports nothing from `conductor.cli`. `runs.py`, `approvals.py`, `escalations.py`, `evals.py` and `web.py` import only `conductor.cli.common` from it. `main.py` imports all six, and its only top-level functions are `doctor`, `ask` and `resume`.
- **R5.** `common.py`'s public functions are exactly `bail`, `load_settings`, `report`, `with_store`, `with_runtime`, `dump`, `state_text`, `emit` and `decide_then_resume`, and it defines `CAUGHT`.

### Part 2: the shared decision sequence

- **R6.** `decide_then_resume` confirms (unless `yes` or no `confirm`), records, prints the line and resumes (unless `no_resume`), in that order. A refused confirmation prints `Nothing recorded.` and records nothing. A `record()` that raises prints nothing and resumes nothing.
- **R7.** Each decision command uses `decide_then_resume` with the prompt, preview and line in the Part 2 table. `decide_approval` is called only in `approvals.py`, `answer_escalation` only in `escalations.py`, and `typer.confirm` only in `common.py`.

### Part 3: the same command line

- **R8.** For every command line, the exit code, standard output, standard error and resulting stored state are as before, and every `--help` text is as before.
- **R9.** The names tests patch are still reached through their modules. The existing CLI tests pass unchanged, and so does the edited web shutdown test.

### Part 4: the rules

- **R10.** Only the Scope's paths change. Given files and existing tests stay byte-identical. There is no `noqa` or `pragma: no cover` in `conductor.cli`, and the package is 100% covered (lines and branches).

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `test_cli_layout.py` fails to import (`cannot import name 'common'`). With empty stub modules and the names `CAUGHT` and `decide_then_resume` stubbed, 26 tests fail and 6 pass. The 6 are the file list, the command order, the `doctor`, `ask` and `resume` cases, and the `common` import case. They are guards: they already hold, and they must keep holding.

| File | What it is |
|---|---|
| `tests/unit/test_cli_layout.py` | R1 to R6: the files, the command order, each command's module and options, the import layers, the shared names and `decide_then_resume` (32 tests from 12 functions) |
| `docs/verification/probe-09m.py` | the probe, run by its path in Acceptance |

Given test count: **32**.

One existing test is edited with this spec and committed with it. In `tests/e2e/test_cli_web_shutdown.py`, `from conductor.cli import main` becomes `from conductor.cli import web`, and its two `monkeypatch.setattr(main, ...)` lines patch `web` instead. Before your change, that file fails to import (`cannot import name 'web'`).

## Tests to write

In `tests/e2e/test_cli_groups_more.py` (section `cli`):
- R9: `approvals edit <id> --args '[1]'`, with `runtime.open_runtime` patched to raise if called, exits 1 with standard error `Error: --args must be a JSON object\n` and never opens a runtime.
- R7: `approvals reject <id>` and `escalations cancel <id>` never ask for confirmation. With `typer.confirm` patched to raise, a pending demo approval and an open escalation are each decided, and the run's state is printed.
- R10: any branch of `conductor.cli` that the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- `cli` stays thin: it parses, calls `conductor.decisions` and the runtime, and prints. No rule, check or default moves into it.
- A decision is recorded only after the confirmation, or with `--yes`. A `propose`, `write` or `implement` action still waits for its approval.
- Error messages stay constant text plus identifiers, exactly as today.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9m` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli` | last line `All checks passed.`; at least 1436 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/cli/*' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_cli_layout.py --no-cov -q` | `32 passed` |
| `.venv/bin/python docs/verification/probe-09m.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_cli_layout.py docs/verification/probe-09m.py tests/e2e/test_cli_web_shutdown.py tests/support.py pyproject.toml src/conductor/runtime.py src/conductor/decisions.py src/conductor/views.py src/conductor/policy.py src/conductor/store.py src/conductor/web` | no output |
| `git diff a9c5485 --stat -- tests ':!tests/unit/test_cli_layout.py' ':!tests/e2e/test_cli_web_shutdown.py' ':!tests/e2e/test_cli_groups_more.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9m: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9m` (after writing progress) | `Reports OK.` |

The second diff row compares against a9c5485 (the commit before this spec). It excludes the given test, the edited web test (guarded by the first diff row) and the coder's test file, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match). The first is the standing network search. Its exclusion moves from `cli/main.py` to `cli/web.py`, where the port check's `socket` now lives.

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `CLI command groups`, with `--tests-before 1404 --given 32`.
