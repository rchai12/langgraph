# Verify Phase 9k: Smaller graph and structured failures

Spec: `docs/phases/phase-09k-smaller-graph-and-structured-failures.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09k-smaller-graph-and-structured-failures.md`.

## First: establish that the coder ran

- No `## Phase 9k: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09k-smaller-graph-and-structured-failures.md docs/verification/phase-09k-smaller-graph-and-structured-failures.md tests/unit/test_graph_steps.py tests/unit/test_graph_nodes.py tests/integration/test_step_failure_events.py docs/verification/probe-09k.py` must succeed: the gates judge against a committed baseline.

The coder:
- wrote `src/conductor/graph/steps.py` (the moved `FAILURE_CODES`, `FailureCode`, `STEP_FAILED_DETAIL`, `RESULT_DETAIL`, `StepFailed`, `StepRunner`; new `INVALID_RESULT`, `NOT_DONE_CODES`, `failure_fields`, `run_step`);
- wrote `src/conductor/graph/nodes.py` (the moved `Services`, `State`, helpers and ten node factories; new `build_nodes`);
- reduced `src/conductor/graph/supervisor.py` to the wiring and the run functions, with re-exports, and listed both new modules in `scripts/critical_modules.txt`.

## 1. Gates

N is `1346`. Given count: 32. `.venv/bin/python scripts/accept.py --phase 9k --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1378 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/graph/nodes.py,*/conductor/graph/steps.py,*/conductor/graph/supervisor.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_graph_steps.py tests/unit/test_graph_nodes.py tests/integration/test_step_failure_events.py --no-cov -q` | `32 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09k.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_graph_steps.py tests/unit/test_graph_nodes.py tests/integration/test_step_failure_events.py tests/integration/test_supervisor_more.py docs/verification/probe-09k.py src/conductor/runtime.py src/conductor/graph/status.py src/conductor/policy.py src/conductor/plancheck.py src/conductor/store.py src/conductor/decisions.py src/conductor/events.py src/conductor/mcp_client` | no output |
| G6 | `git diff 19d3e3d --stat -- tests ':!tests/unit/test_graph_steps.py' ':!tests/unit/test_graph_nodes.py' ':!tests/integration/test_step_failure_events.py' ':!tests/integration/test_supervisor_more.py' ':!tests/unit/test_graph_split_more.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9k: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9k` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_codes_and_the_old_names`; search 10 | pass; silent |
| R2 | `test_which_failures_leave_the_outcome_unknown` (16 cases); probe check 1; the coder's `failure_fields` test | pass; `ok` |
| R3 | `test_a_step_that_runs_returns_its_outcome` | pass |
| R4 | `test_a_failed_step_escalates_and_records_its_cause` (3 cases); search 9; read `steps.run_step`: no `str(error)`, no error text in a payload | pass; silent; the text is never used |
| R5 | `test_build_nodes_makes_every_node_in_order`, `test_the_supervisor_keeps_its_names`; probe check 2 | pass; `ok` |
| R6 | `tests/integration/test_supervisor.py::test_an_edit_runs_the_edited_arguments` (in G1); read the `run_step` node | pass; it passes the parsed edited args to `steps.run_step` |
| R7 | `test_the_compiled_graph_has_the_same_nodes`; probe check 3; the supervisor and approval tests (in G1); search 8; read `ask_step` and `wait_approval` in `nodes.py` against `git show 19d3e3d:src/conductor/graph/supervisor.py` | pass; `ok`; silent; each node's body is unchanged apart from the `run_step` node |
| R8 | the 8 tests of `test_step_failure_events.py`; the edited `test_a_rejected_step_logs_the_request_the_error_and_the_finish`; the coder's retry test | pass |
| R9 | searches 7, 11 and 12; read `scripts/critical_modules.txt`; G5, G6, G7 | silent; both modules listed; as given |
| R10 | G1 (the critical gate), G2 | as given |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09k.py` (G4). It checks:
- all 36 pairs of the four effects and the nine codes (the seven runner codes, `invalid_result` and `None`): `failure_fields` matches the probe's own table;
- `build_nodes` returns the ten node names in order, every node's function is defined in `conductor.graph.nodes`, and the supervisor holds no name of a node;
- 120 random runs of 1 to 3 demo steps (echo, note, delegate), each approved, where the runner fails once at a random step with a random code, a result that does not fit, or no code, or never fails (at least 5 runs). Each escalation is answered `retry`. The probe checks the ERROR event payloads, the escalation details, the order of runner calls, the number of approvals (one plan approval when any step is not a read, and one approval per run of a step that is not a read, including the retry), one TOOL_RESULT per step, a finished run, and that the runner's error text is not in the log. At least 25 runs reach an unknown outcome and 25 a known one.

Before handover the architect ran it on the predecessor with the three new fields left out of its expected payloads: the run check printed `ok`. So a run check that fails on the build points at a changed detail, approval, retry or result, or at the new fields.

A stop at its own `assert` lines, before any check prints, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

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

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09k`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09k`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | drop `effect != "read" and` (`failure_fields`) | `tests/unit/test_graph_steps.py::test_which_failures_leave_the_outcome_unknown[read-timeout-False]` | `False` | `True` |
| S2 | `code not in NOT_DONE_CODES` becomes `code is not None and code not in NOT_DONE_CODES` (`failure_fields`) | `tests/unit/test_graph_steps.py::test_which_failures_leave_the_outcome_unknown[write-None-True]` | `True` | `False` |
| S3 | `effect != "read"` becomes `effect == "write"` (`failure_fields`) | `tests/unit/test_graph_steps.py::test_which_failures_leave_the_outcome_unknown[propose-closed-True]` | `True` | `False` |
| S4 | a result that does not fit records the code `None` instead of `INVALID_RESULT` (`run_step`) | `tests/unit/test_graph_steps.py::test_a_failed_step_escalates_and_records_its_cause[write-bad-result]` | `'invalid_result'` | `None` |
| S5 | drop the ` ({code})` suffix from the reason (`run_step`) | `tests/unit/test_graph_steps.py::test_a_failed_step_escalates_and_records_its_cause[write-timeout]` | `'step 2 demo.note: the step failed (timeout)'` | `'step 2 demo.note: the step failed'` |
| S6 | `build_nodes` leaves out `answer` | `tests/unit/test_graph_nodes.py::test_build_nodes_makes_every_node_in_order` | 10 names | 9 names |
| S7 | the supervisor defines its own `class StepFailed(Exception)` instead of re-exporting it | `tests/unit/test_graph_steps.py::test_the_codes_and_the_old_names` | `[True] * 5` | one `False` |

Notes for tracing. S1: `"timeout"` is not in `NOT_DONE_CODES`, so without the effect test a read becomes unknown. S2: a failure with no code is unknown for a write; the change makes it known. S3: `propose` is a side effect too. S4: the escalation still matches (its detail is `RESULT_DETAIL` and its problems are the parse's), so the first assertion to fail is the payload's `code`. S5: the escalation is compared first, so the detail is what fails. S7: the moved-names list compares by identity; a second class with the same name is a different object (search 10 also matches). Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- `steps.py` keeping its own private JSON dump helper, or `nodes.py` importing one from `steps.py`.
- `build_nodes` building the dict with a loop or a literal, as long as the order is `NODES`.
- `run_step` choosing its code and reason in one helper or inline.
- The supervisor's re-exports as one import per source module or several.
- Extra behaviour tests in `tests/unit/test_graph_split_more.py`.

## 7. Out of scope

Each must be absent:
- Any changed escalation kind, detail, problems or retry node; any changed node name, edge, interrupt value or order of effects; any change to the CLI or web output.
- Passing the attempt number to the policy, retrying an implementation, or any automatic retry.
- An idempotency key, deduplication, or a new escalation kind.
- Any change to `runtime.py`, `graph/status.py`, `policy.py`, `plancheck.py`, `store.py`, `decisions.py`, `events.py` or `mcp_client/`, including a code for `NoRunner`.
- Removing the `cast` calls in `run_state` or other supervisor clean-ups.
- Any change to a given file, `AGENTS.md`, the design docs or another existing test.

## 8. Verdict

Write `docs/reviews/phase-09k-smaller-graph-and-structured-failures.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9k`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9k` must print `Reports OK.`
