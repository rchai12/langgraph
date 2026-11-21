# Phase 9k: Smaller graph and structured failures

## Goal

`graph/supervisor.py` holds the run functions, the step runner contract, the ten node factories and the code that runs a step, in 463 lines of one critical module. This phase moves the step code into a new `graph/steps.py` and the nodes into a new `graph/nodes.py`, so the supervisor keeps only the graph's wiring and the start, resume and state functions. The interrupt and replay boundaries do not move: every node keeps its name, its edges and its first-line behaviour. The one new behaviour is in the record of a failed step: today its event says only `"error": "tool_error"`, and the runner's cause (`timeout`, `closed` and the rest) survives only inside the escalation's text. After this phase the event also names the cause, the action's effect, and whether a side effect may already have happened.

Decided with the owner (2026-11-20):
- **Which failures leave the outcome unknown.** For a `propose`, `write` or `implement` step, the outcome is unknown for every failure that can happen after the request reached the server: `timeout`, `closed`, `no_result`, `too_large`, a result that does not fit the action, and a failure with no code. It is known not done only for `no_command`, `start_failed` and `tool_error` (the server answered with an error). A `read` step's outcome is never unknown.
- **Where it shows.** Only in the event. The `run_step` ERROR event gains `code`, `effect` and `unknown_outcome`. The escalation, its `detail` text, its `problems`, the CLI and the web page are unchanged.
- **How the supervisor splits.** Two new modules: `graph/steps.py` (the failure codes, the runner contract and running one step) and `graph/nodes.py` (`Services`, `State`, the helpers and the ten nodes). Both are critical modules.

Decided by the architect, within those answers:
- `steps.py` is the bottom of the three: it imports nothing from `conductor.graph`. `nodes.py` imports `steps` and `graph.status`, never `supervisor`. `supervisor.py` imports both. No import cycle.
- A result that does not fit the action records the code `invalid_result` (`INVALID_RESULT`). It is not added to `FAILURE_CODES`: a runner cannot raise it, so `StepFailed(code="invalid_result")` still keeps no code.
- Every name a test or module imports from the supervisor today still imports from it and is the same object: `FAILURE_CODES`, `FailureCode`, `STEP_FAILED_DETAIL`, `RESULT_DETAIL`, `StepFailed`, `StepRunner`, `Services`, `State`, and the names re-exported from `graph.status`.
- The node that runs a step still parses edited args and still builds the results list; `steps.run_step` runs, logs and parses one step and returns its outcome or its escalation.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/graph/supervisor.py` (all of it), `src/conductor/graph/status.py` (`NODES`), and `src/conductor/runtime.py` (where each `StepFailed` code is raised).
- `docs/architecture.md`, "Supervisor graph": a resumed node runs again from its first line, so requests and escalations are created in their own nodes and the waiting nodes only read before `interrupt`.
- `tests/integration/test_supervisor_more.py` and `tests/integration/test_mcp_steps.py`: their helpers are imported by the given integration file.

## Starting state

Phase 9j is built and verified, and everything is committed: N is `1346`. **Sections: core.** `graph/nodes.py` and `graph/steps.py` do not exist. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/graph/steps.py` | new: failure codes, the runner contract, `failure_fields`, `run_step` (Part 1) |
| `src/conductor/graph/nodes.py` | new: `Services`, `State`, the helpers, the ten nodes and `build_nodes` (Part 2) |
| `src/conductor/graph/supervisor.py` | keeps the wiring and the run functions, re-exports the moved names (Part 3) |
| `scripts/critical_modules.txt` | two new lines, `graph/nodes.py` and `graph/steps.py` |
| `tests/unit/test_graph_split_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files, including the one edited existing test, are already committed; they are not in the Scope and never change.

## Out of scope

- Any change to the escalation's kind, detail, problems or retry node, to a node's name, edges or order of effects, to an interrupt value, to `NODES`, or to the CLI and web output.
- Passing the attempt number to `policy.step_request` or retrying an implementation (Phase 10), and any automatic retry of an unknown write.
- An idempotency key, a deduplication rule, or a new escalation kind for an unknown outcome.
- Giving `NoRunner` a code, or any change to `runtime.py`, `graph/status.py`, `policy.py`, `plancheck.py`, `store.py`, `decisions.py`, `events.py` or `mcp_client/`.
- Removing the `cast` calls in `run_state`, or other clean-ups in the supervisor's run functions.
- Any change to a given file, `AGENTS.md`, the design docs or another existing test.

## Dependencies

None new.

## Design

### Part 1: `graph/steps.py`

Moved from the supervisor unchanged: `FAILURE_CODES`, `FailureCode`, `STEP_FAILED_DETAIL`, `RESULT_DETAIL`, `StepFailed`, `StepRunner`. New:

```python
INVALID_RESULT = "invalid_result"
NOT_DONE_CODES = ("no_command", "start_failed", "tool_error")

def failure_fields(effect: Effect, code: str | None) -> dict[str, JsonValue]: ...

def run_step(
    step: CheckedStep,
    domain: str,
    args: Contract,
    *,
    runner: StepRunner,
    log: EventLog,
    run_id: str,
) -> StepOutcome | Escalation: ...
```

- `failure_fields(effect, code)` returns `{"code": code, "effect": effect, "unknown_outcome": effect != "read" and code not in NOT_DONE_CODES}`.
- `run_step` does what today's `run_step` node does from its TOOL_CALL event on, with `full_name = f"{domain}.{step.action.name}"`:
  1. logs TOOL_CALL `{"step": step.number, "action": full_name, "args": <args dumped as JSON>}` with node `run_step`;
  2. calls `runner.run(step.action, args)`. On `StepFailed` the reason is `STEP_FAILED_DETAIL`, followed by ` (<code>)` when the error has a code, and the code is the error's code (or `None`);
  3. parses the output with `step.action.result`. On `ValidationError` the reason is `RESULT_DETAIL`, the problems are `problems_from(error)`, and the code is `INVALID_RESULT`;
  4. on a failure, logs ERROR with node `run_step` and the payload `{"step": step.number, "error": "tool_error", **failure_fields(step.action.effect, code), "problems": [{"loc": ..., "code": ...}, ...]}`, and returns `Escalation(kind="tool_error", detail=f"step {step.number} {full_name}: {reason}", run_id=run_id, problems=problems)`;
  5. otherwise logs TOOL_RESULT `{"step": step.number, "output": <parsed result dumped as JSON>}` and returns `StepOutcome(step=step.number, action=full_name, output=<the same dump>)`.

The error's text is never logged or shown, as today.

### Part 2: `graph/nodes.py`

Moved from the supervisor unchanged: `Services`, `State`, the helpers (`_run_id`, `_dump`, `_load`, `_checked`, `_escalate`, `_queue`) and the ten node factories. `_tool_error` is gone: its work is in `steps.run_step`. New:

```python
def build_nodes(services: Services) -> dict[str, Callable[..., object]]: ...
```

`build_nodes` returns the ten built nodes keyed by name, in `NODES` order. The `run_step` node chooses the args (the approved step's, or the edited ones parsed with `action.args`), calls `steps.run_step(step, domain, args, runner=services.runner, log=services.log, run_id=run_id)`, and then either escalates with `_escalate(found, "ask_step")` or appends `_dump(found)` to the results and moves to the next step, as today.

### Part 3: `graph/supervisor.py`

`build_graph` adds each node from `build_nodes(services)` and the two edges `START → route` and `finish → END`, and compiles. The supervisor keeps `RECURSION_LIMIT`, `RESUMABLE_STOPS`, `build_graph`, `start_run`, `can_resume`, `resume_run`, `run_state`, `_config` and `_invoke`, with their bodies unchanged. It re-exports, with one `# noqa: F401` import per source module as it does for `graph.status` today, every moved name listed in the architect's decisions, so each is the same object as in its new home.

After this, `supervisor.py` defines no node and calls no `interrupt(`, and no module outside `steps.py` builds the `"error": "tool_error"` payload (searches in Acceptance).

## Facts

Checked on 2026-11-20 with the project's Python 3.12.16 and langgraph 1.2.20, on today's code:
- The compiled graph's `nodes` are the ten names plus `__start__`; the given test compares them without `__start__`.
- Names other modules import from the supervisor: `RunError`, `RunState`, `can_resume`, `Services`, `StepFailed`, `build_graph`, `resume_run`, `run_state`, `start_run` (`cli/main.py`, `runtime.py`, `web/app.py`, `web/jobs.py`). Tests also import `FAILURE_CODES`, `RESULT_DETAIL`, `RESUMABLE_STOPS` and `NODES` from it. No test patches a node or helper; only the 9h probe patches `supervisor.run_state` and `supervisor._invoke`, which stay.
- The only existing test that pins the `run_step` ERROR payload is `tests/integration/test_supervisor_more.py::test_a_rejected_step_logs_the_request_the_error_and_the_finish`. Its expected tuple gains the three fields; that edit is a given file.
- The probe, run on today's code with the three new fields left out of its expected payloads, prints `ok` for its 120 random runs: today's details, approvals, retries and results already match its oracle, so only the new fields fail before this phase.
- `runtime.McpRunner` raises `StepFailed` with `no_command`, `start_failed`, `timeout` or `closed` from the MCP client, and `tool_error`, `no_result` or `too_large` itself; `NoRunner` raises it with no code.

## Requirements

### Part 1: `graph/steps.py`

- **R1.** `FAILURE_CODES`, `STEP_FAILED_DETAIL`, `RESULT_DETAIL`, `StepFailed` and `StepRunner` live in `steps.py` and are the same objects as the supervisor's names. `INVALID_RESULT` is `"invalid_result"` and `NOT_DONE_CODES` is `("no_command", "start_failed", "tool_error")`.
- **R2.** `failure_fields` gives `unknown_outcome` true exactly for an effect that is not `read` and a code not in `NOT_DONE_CODES` (including `None` and `invalid_result`).
- **R3.** `run_step` logs TOOL_CALL, then TOOL_RESULT, and returns the `StepOutcome` for a result that fits.
- **R4.** For a `StepFailed` or a result that does not fit, `run_step` logs one ERROR event with the payload of Part 1 and returns the escalation with today's kind, detail and problems. The error's text is never in the log.

### Part 2: `graph/nodes.py`

- **R5.** `nodes.py` holds `Services`, `State` and the ten nodes; `build_nodes` returns them in `NODES` order, and the supervisor's `Services` and `State` are the same objects.
- **R6.** The `run_step` node runs every step through `steps.run_step`, with the edited args when the step was approved with edits.

### Part 3: the graph

- **R7.** `build_graph` builds its nodes with `build_nodes`; the compiled graph has the same ten nodes, and every run (approvals, retries, results, the answer and the finish) behaves as before.
- **R8.** A failed step's ERROR event names its cause, effect and unknown outcome in every run, including a real MCP server that stops mid-step, and an earlier step's result stays in the log.

### Part 4: the rules

- **R9.** `steps.py` imports nothing from `conductor.graph`, and `nodes.py` does not import the supervisor. Both are listed in `scripts/critical_modules.txt`. Only the Scope's paths change; given files and existing tests stay byte-identical.
- **R10.** `graph/nodes.py`, `graph/steps.py` and `graph/supervisor.py` are covered 100% (lines and branches), and the critical-module gate passes.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `test_graph_steps.py` fails to collect (`steps.StepFailed` does not exist), the three tests of `test_graph_nodes.py` fail with `AttributeError` (no `nodes.Services`, no `nodes.build_nodes`), and the 9 integration tests fail on the missing `code`, `effect` and `unknown_outcome` keys after their detail assertions pass. With names-only stubs every test fails except `test_the_compiled_graph_has_the_same_nodes`, a guard: today's graph already has the ten nodes, and it must keep them.

| File | What it is |
|---|---|
| `tests/unit/test_graph_steps.py` | R1 to R4: the codes, the moved names, the unknown-outcome table and one step's events (21 tests from 4 functions) |
| `tests/unit/test_graph_nodes.py` | R5, R7: the nodes in order, the kept names and the compiled graph (3 tests from 3 functions) |
| `tests/integration/test_step_failure_events.py` | R7, R8: the event fields through the graph, an earlier step's result, a real server that stops (8 tests from 4 functions) |
| `docs/verification/probe-09k.py` | the probe, run by its path in Acceptance |

Given test count: **32**.

One existing test is edited, and the edit is committed with these files: in `tests/integration/test_supervisor_more.py`, `test_a_rejected_step_logs_the_request_the_error_and_the_finish` expects the three new fields (`"code": None, "effect": "read", "unknown_outcome": False`) in its ERROR payload. It is protected like a given file.

## Tests to write

In `tests/unit/test_graph_split_more.py` (section `core`):
- R6 is pinned by the existing `tests/integration/test_supervisor.py::test_an_edit_runs_the_edited_arguments`; no new test is needed unless coverage asks for one.
- R8: after a write fails with `timeout` and the escalation is answered `retry`, the run waits for a new step approval before the runner is called again: the runner has run once when that approval is pending.
- R2: `failure_fields` for `propose` with `no_result`, and for `read` with `tool_error`.
- R10: any branch of `graph/nodes.py`, `graph/steps.py` or `graph/supervisor.py` the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- Side effects need approval: no path may run a `propose`, `write` or `implement` step without its own approval. The nodes keep today's order: `ask_step` creates the request, `wait_approval` only reads before `interrupt`.
- Messages are constant text plus identifiers. A runner's error text is never logged or shown.
- No automatic retry of a failed step.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9k` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1378 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/graph/nodes.py,*/conductor/graph/steps.py,*/conductor/graph/supervisor.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_graph_steps.py tests/unit/test_graph_nodes.py tests/integration/test_step_failure_events.py --no-cov -q` | `32 passed` |
| `.venv/bin/python docs/verification/probe-09k.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_graph_steps.py tests/unit/test_graph_nodes.py tests/integration/test_step_failure_events.py tests/integration/test_supervisor_more.py docs/verification/probe-09k.py src/conductor/runtime.py src/conductor/graph/status.py src/conductor/policy.py src/conductor/plancheck.py src/conductor/store.py src/conductor/decisions.py src/conductor/events.py src/conductor/mcp_client` | no output |
| `git diff 19d3e3d --stat -- tests ':!tests/unit/test_graph_steps.py' ':!tests/unit/test_graph_nodes.py' ':!tests/integration/test_step_failure_events.py' ':!tests/integration/test_supervisor_more.py' ':!tests/unit/test_graph_split_more.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9k: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9k` (after writing progress) | `Reports OK.` |

The second diff row compares against 19d3e3d (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/graph/nodes.py src/conductor/graph/steps.py
git grep --untracked -n -E 'interrupt\(|def _(route|plan|ask_plan|ask_step|wait_approval|run_step|answer|record_escalation|wait_escalation|finish)\(' -- src/conductor/graph/supervisor.py
git grep --untracked -n -E '"error": "tool_error"' -- src ':!src/conductor/graph/steps.py'
git grep --untracked -n -E '^(FAILURE_CODES|STEP_FAILED_DETAIL|RESULT_DETAIL) =|^class (StepFailed|StepRunner|Services|State)[(:]' -- src ':!src/conductor/graph/steps.py' ':!src/conductor/graph/nodes.py'
git grep --untracked -n -E '^(from|import) conductor\.graph|^from conductor import .*graph' -- src/conductor/graph/steps.py
git grep --untracked -n -E 'conductor\.graph\.supervisor|from conductor\.graph import .*supervisor' -- src/conductor/graph/nodes.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Smaller graph and structured failures`, with `--tests-before 1346 --given 32`.
