# Verify Phase 5c: the supervisor graph

Spec: `docs/phases/phase-05c-supervisor-graph.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 5c` on your own report.

The coder added `langgraph` to the dependencies and installed it, created `conductor.graph` (the tracing guard) and `conductor.graph.supervisor` (critical), copied `tests/integration/test_supervisor.py` (14 tests), and wrote `tests/integration/test_supervisor_more.py` and `tests/unit/test_graph_guard.py`.

## 1. Gates

N is `500`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 514 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary (a LangGraph `Deserializing unregistered type` warning is a finding); 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `graph/supervisor.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/graph/*.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/integration/test_supervisor.py --no-cov -W error` | exactly `14 passed` |
| `.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph'))"` | `1.2.20` or a later `1.2.x` |
| `.venv/bin/python scripts/check_reports.py --phase 5c` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/contracts src/conductor/policy.py src/conductor/store.py src/conductor/decisions.py src/conductor/routing src/conductor/planning src/conductor/plancheck.py src/conductor/events.py src/conductor/llm tests/unit tests/e2e tests/support.py` | no output |
| `git diff HEAD -- pyproject.toml` | exactly one added line, `"langgraph>=1.2.20,<1.3",` |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/graph/supervisor.py | grep -v -E "^[^:]+:[0-9]+:from conductor(\.contracts|\.contracts\.approvals|\.events|\.llm\.model|\.planning\.plan|\.planning\.answer|\.registry|\.routing\.route|\.store|\.graph)? import "`
2. `git grep --untracked -n -E "get_settings|clock\.|ids\.|OllamaModel|urllib|decide\(|from conductor\.plancheck import|langchain" -- src/conductor/graph`
3. `git grep --untracked -n -E "langgraph|langsmith" -- src | grep -v "^src/conductor/graph/"`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given file equals the spec's block; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_tracing_is_off_inside_a_run`; the coder's guard tests; probe "with tracing asked for by the environment, a run opens no connection"; read `conductor/graph/__init__.py` | pass; ok; the variables set before any `langgraph` import |
| R2 | `test_the_nodes`, `test_the_checkpoint_holds_only_json`; read `build_graph` against the node table | pass; every edge as the table says |
| R3 | `test_a_read_only_request_runs_to_its_answer`, `test_an_escalation_waits_and_retry_runs_the_node_again`, `test_cancel_ends_the_run`; the coder's plan and answer retry tests | pass |
| R4 | `test_a_write_step_waits_for_the_plan_and_then_for_itself`; the coder's implement and mixed-plan tests | pass |
| R5 | `test_resume_needs_a_recorded_decision`; the coder's no-duplicates test; read both `wait_*` nodes: nothing but reads before `interrupt` | pass; the same |
| R6 | `test_an_edit_runs_the_edited_arguments`, `test_a_result_that_does_not_fit_escalates`, `test_eight_read_steps_run_in_one_go`; probe "no propose, write, or implement step ran without its own decided approval" | pass; ok |
| R7 | `test_a_failed_step_escalates_and_retry_asks_for_its_approval_again`; the coder's retry tests | pass |
| R8 | `test_runs_are_checked`, `test_a_rejection_ends_the_run_with_its_note`; the coder's run-state tests | pass |
| R9 | the payload checks in the given tests; the coder's payload test; probe "every run ends done, rejected, or cancelled, once" | pass; ok |
| R10 | searches 1 to 3 | no output |
| R11 | the coder's `SYNTHETIC-SECRET` test; read every `RunError(` and `Escalation(` in the graph | pass; constant texts plus ids and action names |
| R12 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It plays 300 random runs of one to four demo steps with random decisions (approve, edit, reject), random step failures, and random retries and cancels, with a runner that checks, at every call of a step that is not `read`, that the newest decided approval of the run is that step's own and allows exactly the arguments it is given. Its last check runs one request in a subprocess with LangSmith tracing asked for by the environment and a socket spy. Its bookkeeping checks itself on a known request before it starts; a stop at one of its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 5c. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from conductor import plancheck, policy
from conductor.contracts import Plan, Route, Step
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import Services, StepFailed, build_graph, resume_run, start_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from conductor.store import Store
from langgraph.checkpoint.memory import InMemorySaver

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(23)
REGISTRY = Registry((demo.DOMAIN,))
EFFECT = {action.name: action.effect for action in demo.DOMAIN.actions}
ARGS = {
    "echo": {"text": "hi"},
    "note": {"title": "Milk"},
    "delegate": {"task": "tidy up"},
}
OUTPUT = {"echo": {"text": "hi"}, "note": {"note_id": "e" * 32}, "delegate": {"summary": "ok"}}


def approved_step(store: Store, run_id: str, action: str) -> dict | None:
    """The arguments the newest decided step approval of this run allows, or None."""
    found = None
    for approval_id in decided[run_id]:
        stored = store.approval(approval_id)
        if stored.request.stage != "step" or stored.decision is None:
            continue
        if stored.decision.verdict == "reject":
            found = None
            continue
        step = stored.request.steps[0]
        if step.action == f"demo.{action}":
            found = stored.decision.edited_args if stored.decision.verdict == "edit" else step.args
    return found


class SpyRunner:
    def __init__(self, store: Store, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self.calls: list[str] = []
        self.violations = 0
        self.used: set[str] = set()

    def run(self, action, args):
        self.calls.append(action.name)
        if EFFECT[action.name] != "read":
            allowed = approved_step(self.store, self.run_id, action.name)
            newest = decided[self.run_id][-1] if decided[self.run_id] else None
            if allowed is None or newest in self.used:
                self.violations += 1
            elif json.loads(json.dumps(args.model_dump(mode="json"))) != json.loads(
                json.dumps(action.args.model_validate(allowed).model_dump(mode="json"))
            ):
                self.violations += 1
            self.used.add(newest)
        if rng.random() < 0.2:
            raise StepFailed()
        return OUTPUT[action.name]


decided: dict[str, list[str]] = {}

# The probe's own bookkeeping checks itself on a known case first.
_store = Store(Path(tempfile.mkdtemp()) / "conductor.db")
_checked = plancheck.check_plan(
    Plan(steps=(Step(action="demo.note", args={"title": "Milk"}),)),
    Route(domain="demo", decided_by="rule", rule_id="demo.prefix"),
    REGISTRY,
)
_request = policy.step_request("demo", _checked[0], run_id="c" * 32)
_store.add_request(_request)
decided["c" * 32] = [_request.approval_id]
assert approved_step(_store, "c" * 32, "note") is None
decide_approval(
    _store, REGISTRY, _request.approval_id, "approve", channel="terminal", decided_by="owner"
)
assert approved_step(_store, "c" * 32, "note") == {"title": "Milk", "body": "", "tags": []}
assert approved_step(_store, "c" * 32, "echo") is None

ok = True
outcomes = {"done": 0, "rejected": 0, "cancelled": 0}
violations = 0
json_only = True
one_pending = True
for scenario in range(300):
    folder = Path(tempfile.mkdtemp())
    store = Store(folder / "conductor.db")
    log = EventLog(folder / "runs")
    run_id = f"{scenario + 1:032x}"
    decided[run_id] = []
    actions = [rng.choice(["echo", "note", "delegate"]) for _ in range(rng.randint(1, 4))]
    plan = json.dumps({"steps": [{"action": a, "args": ARGS[a]} for a in actions]})
    model = ScriptedModel(
        [
            ScriptedReply("plan", ModelReply(content=plan)),
            ScriptedReply("answer", ModelReply(content='{"reply": "Done."}')),
        ]
    )
    runner = SpyRunner(store, run_id)
    graph = build_graph(
        Services(
            registry=REGISTRY,
            store=store,
            log=log,
            model=model,
            model_name="m",
            runner=runner,
        ),
        InMemorySaver(),
    )
    state = start_run(graph, "demo: do the things", run_id=run_id)
    for _ in range(200):
        values = graph.get_state({"configurable": {"thread_id": run_id}}).values
        json_only &= json.loads(json.dumps(values)) == values
        one_pending &= len(store.pending()) <= 1
        if state.status != "waiting":
            break
        if state.approval_id is not None:
            request = store.approval(state.approval_id).request
            roll = rng.random()
            if roll < 0.1:
                verdict, extra = "reject", {}
            elif roll < 0.25 and request.stage == "step" and request.steps[0].action == "demo.note":
                verdict, extra = "edit", {"edited_args": {"title": f"T{scenario}"}}
            else:
                verdict, extra = "approve", {}
            decide_approval(
                store,
                REGISTRY,
                state.approval_id,
                verdict,
                channel="terminal",
                decided_by="owner",
                **extra,
            )
            decided[run_id].append(state.approval_id)
        else:
            answer = "cancel" if rng.random() < 0.2 else "retry"
            answer_escalation(
                store, state.escalation_id, answer, channel="terminal", decided_by="owner"
            )
        state = resume_run(graph, store, run_id)
    ok &= state.status in outcomes
    outcomes[state.status] = outcomes.get(state.status, 0) + 1
    violations += runner.violations
    finished = [e for e in log.read(run_id) if e.kind == EventKind.RUN_FINISHED]
    ok &= [e.payload for e in finished] == [{"status": state.status}]
check(f"every run ends done, rejected, or cancelled, once ({outcomes})", ok)
check("no propose, write, or implement step ran without its own decided approval", violations == 0)
check("the checkpoint holds only JSON at every pause", json_only)
check("at most one approval is pending at a time", one_pending)

# Tracing stays off even when the environment asks for it.
code = """
import socket, time
attempts = []
def spy(self, address):
    attempts.append(address)
    raise OSError("blocked")
socket.socket.connect = spy
import tempfile
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from conductor.domains import demo
from conductor.events import EventLog
from conductor.graph.supervisor import Services, build_graph, start_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from conductor.store import Store
class Runner:
    def run(self, action, args):
        return {"text": "hi"}
folder = Path(tempfile.mkdtemp())
model = ScriptedModel([
    ScriptedReply("plan", ModelReply(content='{"steps": [{"action": "echo", "args": {"text": "hi"}}]}')),
    ScriptedReply("answer", ModelReply(content='{"reply": "Done."}')),
])
graph = build_graph(Services(registry=Registry((demo.DOMAIN,)), store=Store(folder / "c.db"),
    log=EventLog(folder), model=model, model_name="m", runner=Runner()), InMemorySaver())
print(start_run(graph, "demo: say hi", run_id="a" * 32).status)
time.sleep(3)
print(len(attempts))
"""
environment = dict(os.environ)
environment.update(
    LANGSMITH_TRACING="true",
    LANGCHAIN_TRACING_V2="true",
    LANGSMITH_API_KEY="lsv2_synthetic",
    LANGSMITH_ENDPOINT="http://127.0.0.1:9",
)
done = subprocess.run(
    [sys.executable, "-c", code], capture_output=True, text=True, env=environment, check=False
)
check(
    "with tracing asked for by the environment, a run opens no connection",
    done.stdout.split() == ["done", "0"],
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run actually printed; if it differs from the "Broken" column but the test still fails, that is not a finding (note it for the architect).

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the step request built in `wait_approval` instead of `ask_step` | `test_a_write_step_waits_for_the_plan_and_then_for_itself` | one step request | a new request on every resume |
| 2 | the decision taken from the resume value, not the store (`wait_approval`) | `test_resume_needs_a_recorded_decision` | `is not decided yet` | the run goes on |
| 3 | `run_step` uses the checked step's arguments even after an edit | `test_an_edit_runs_the_edited_arguments` | `Bread` | `Milk` |
| 4 | a retry after a step failure goes to `run_step` | `test_a_failed_step_escalates_and_retry_asks_for_its_approval_again` | a new approval | the step runs again at once |
| 5 | the result not parsed by the action's result contract (`run_step`) | `test_a_result_that_does_not_fit_escalates` | `tool_error` | `done` |
| 6 | the `tracing_context` left out of `start_run` | `test_tracing_is_off_inside_a_run` | `[False]` | `[True]` |
| 7 | `resume_run` without its unknown-thread check | `test_runs_are_checked` | `no run ...` | a new run from `START` |
| 8 | `RECURSION_LIMIT` left at LangGraph's default | `test_eight_read_steps_run_in_one_go` | `done` | `GraphRecursionError` |
| 9 | a contract kept in the state instead of its JSON (`plan` node) | `test_the_checkpoint_holds_only_json` | equal | not JSON |

Reasonable variations that are correct: private helpers for building the checked steps and for the escalation; the edges written with `add_conditional_edges` and path maps, or with `Command(goto=...)` returned from nodes; `RunState` built from the snapshot in one helper; `Services` with `slots=True`.

## 6. Project rules

- Searches 1 to 3.
- The runner is called for a step that is not `read` only after `policy.apply_decision` approved that step's own request (read the code path from `wait_approval` to `run_step`).
- No node that calls `interrupt` writes to the store or the log, or reads `clock` or `ids` (through any function), before the `interrupt` returns.
- No test or probe opens a connection; tracing is off in every run.

## 7. Out of scope

Each must be absent: `checkpoints.db` or `SqliteSaver`, leases, `conductor ask` or `conductor resume`, MCP, real agents, more than one run per thread, undoing steps, replanning, `NODE_STARTED`/`NODE_FINISHED` events, new event or escalation kinds, changes to contracts, `policy`, `store`, `decisions`, routing, or planning, streaming, async, parallel steps.

## 8. Progress log

The entry exists, headed `## Phase 5c: the supervisor graph (...)`, with `Tests: 500 -> <passed> (given 14)`, and each deviation it lists is real and justified.
