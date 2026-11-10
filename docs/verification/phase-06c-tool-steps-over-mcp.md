# Verify Phase 6c: tool steps over MCP

Spec: `docs/phases/phase-06c-tool-steps-over-mcp.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 6c` on your own report.

The coder added `FAILURE_CODES` and `StepFailed`'s code to `conductor.graph.supervisor`, `MAX_RESULT_BYTES`, `McpRunner`, and `DomainRunner` to `conductor.runtime`, copied two test files (17 tests), and wrote two of their own.

## 1. Gates

N is `641`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 658 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed |
| `.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/supervisor.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_mcp_runner.py tests/integration/test_mcp_steps.py --no-cov` | exactly `17 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 6c` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/registry.py src/conductor/contracts src/conductor/cli src/conductor/domains tests/unit/test_tool_check.py tests/integration/test_supervisor.py tests/integration/test_supervisor_more.py tests/integration/test_runtime.py tests/integration/test_resume_stopped.py tests/mcp_fake_server.py tests/support.py` | no output |
| `git diff HEAD -- src/conductor/graph/supervisor.py` | only `FAILURE_CODES`, `FailureCode`, `StepFailed`'s `__init__` and `code`, and the detail with the code in `run_step` |
| `pgrep -f mcp_fake_server` (after the whole check) | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) mcp|^(from|import) anyio" -- src | grep -v "^src/conductor/mcp_client/"`
2. `git grep --untracked -n -E "call_tool" -- src | grep -v -E "^src/conductor/(mcp_client/client|runtime)\.py:"`
3. `git grep --untracked -n -E "\.content\b|\.text\b|print\(|logging" -- src/conductor/runtime.py`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_failure_codes`; the coder's `nonsense` and detail tests; the 5c tests still pass unchanged | pass |
| R2 | `test_a_call_with_the_declared_server_and_the_arguments_as_json`, `test_a_read_step_runs_over_mcp`; the coder's two-server test | pass |
| R3 | `test_each_failure_has_its_code` (6 cases), `test_a_tool_error_escalates_with_its_code`, `test_a_step_that_takes_too_long_escalates_as_timeout`, `test_a_server_that_stops_escalates_as_closed_and_retry_asks_again`; the coder's secret and `__cause__` tests; probe "1000 tool outcomes map ..." | pass; ok |
| R4 | `test_fields_the_contract_does_not_name_are_dropped`, `test_a_result_over_256_kb_fails` (2 cases); the coder's unknown-keys test | pass |
| R5 | `test_the_domain_runner_sends_each_action_to_its_runner`, `test_without_the_demo_setting_demo_actions_do_not_run`; the coder's two-runner test; `tests/integration/test_resume_stopped.py` still passes | pass |
| R6 | the coder's start-line test; probe "real runs end done or at the first failing step"; read `McpRunner`: called only through the runner `run_step` uses | pass; ok; the same |
| R7 | searches 1 and 2 | no output |
| R8 | the coverage gate | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It plays 1000 random tool outcomes into `McpRunner` against its own reading of the rules (which checks itself on known cases first), then runs eight random plans of `echo` and `fail` steps through the real graph and the fake server. A stop at its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 6c. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import shlex
import sys
import tempfile
from pathlib import Path

from conductor import domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.decisions import decide_approval
from conductor.events import EventKind
from conductor.graph.supervisor import StepFailed
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.mcp_client.client import McpUnavailable, ToolOutcome
from conductor.registry import Action, Domain, McpServer, Registry
from conductor.runtime import MAX_RESULT_BYTES, McpRunner, ask, open_runtime, resume

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(67)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "data")


class Args(Contract):
    q: str


class Res(Contract):
    a: str
    b: int = 0


ACTION = Action("look", "Look.", "tool", "look", "read", Args, Res, "srv")
REGISTRY = Registry((Domain("d", "A domain.", (ACTION,), servers=(McpServer("srv"),)),))


def expected(outcome) -> tuple[str, object]:
    """The probe's own reading of the runner's rules."""
    if isinstance(outcome, McpUnavailable):
        return "fail", outcome.code
    if outcome.is_error:
        return "fail", "tool_error"
    if outcome.structured is None:
        return "fail", "no_result"
    if len(json.dumps(outcome.structured, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
        return "fail", "too_large"
    return "ok", {k: v for k, v in outcome.structured.items() if k in ("a", "b")}


assert expected(ToolOutcome(True, None)) == ("fail", "tool_error")
assert expected(ToolOutcome(False, {"a": "x", "z": 1})) == ("ok", {"a": "x"})
assert expected(McpUnavailable("srv", "timeout")) == ("fail", "timeout")

# 1. every outcome maps as the rules say
agree = True
for _ in range(1000):
    roll = rng.random()
    if roll < 0.15:
        outcome = McpUnavailable(
            "srv", rng.choice(["no_command", "start_failed", "timeout", "closed"])
        )
    elif roll < 0.3:
        outcome = ToolOutcome(True, None)
    elif roll < 0.4:
        outcome = ToolOutcome(False, None)
    else:
        structured = {
            k: "v" for k in rng.sample(["a", "b", "c", "SYNTHETIC-SECRET"], rng.randint(0, 4))
        }
        if rng.random() < 0.1:
            structured["pad"] = "x" * (MAX_RESULT_BYTES + rng.randint(-40, 40))
        outcome = ToolOutcome(False, structured)

    class Client:
        def call_tool(self, name, arguments, outcome=outcome):
            if isinstance(outcome, McpUnavailable):
                raise outcome
            return outcome

    runner = McpRunner(REGISTRY, get_settings(), connect=lambda s, st: Client())
    try:
        got = ("ok", runner.run(ACTION, Args(q="x")))
    except StepFailed as error:
        got = ("fail", error.code)
    agree &= got == expected(outcome)
check("1000 tool outcomes map to results and codes as the rules say", agree)

# 2. through the real graph and the real fake server
FAKE = Path("tests/mcp_fake_server.py").resolve()
os.environ["CONDUCTOR_MCP__FAKE"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


ECHO = Action("echo", "Echo.", "tool", "echo", "read", Text, Text, "fake")
FAIL = Action("fail", "Fail.", "tool", "fail", "write", Reason, Text, "fake")
domains.DOMAINS = (Domain("lab", "Lab.", (ECHO, FAIL), servers=(McpServer("fake"),)),)
ok_runs = True
seen = {"done": 0, "tool_error": 0}
for i in range(8):
    steps = [rng.choice(["echo", "fail"]) for _ in range(rng.randint(1, 3))]
    plan = {
        "steps": [
            {
                "action": s,
                "args": {"text": f"t{i}"} if s == "echo" else {"reason": "SYNTHETIC-SECRET"},
            }
            for s in steps
        ]
    }
    replies = [ScriptedReply("plan", ModelReply(content=json.dumps(plan)))]
    replies.append(ScriptedReply("answer", ModelReply(content='{"reply": "Done."}')))
    with open_runtime(get_settings(), model=ScriptedModel(replies)) as runtime:
        state = ask(runtime, "lab: go")
        while state.status == "waiting" and state.approval_id is not None:
            decide_approval(
                runtime.store,
                runtime.registry,
                state.approval_id,
                "approve",
                channel="terminal",
                decided_by="owner",
            )
            state = resume(runtime, state.run_id)
        events = runtime.log.read(state.run_id)
        results = [e.payload["output"] for e in events if e.kind == EventKind.TOOL_RESULT]
        first_fail = steps.index("fail") if "fail" in steps else None
        if first_fail is None:
            ok_runs &= state.status == "done" and results == [{"text": f"t{i}"}] * len(steps)
            seen["done"] += 1
        else:
            stored = runtime.store.escalation(state.escalation_id).escalation
            ok_runs &= stored.detail == (
                f"step {first_fail + 1} lab.fail: the step failed (tool_error)"
            )
            ok_runs &= len(results) == first_fail
            errors = [e.payload for e in events if e.kind == EventKind.ERROR]
            ok_runs &= "SYNTHETIC-SECRET" not in json.dumps(errors) + stored.model_dump_json()
            seen["tool_error"] += 1
check(f"real runs end done or at the first failing step, with its code ({seen})", ok_runs)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the code left out of the detail (`run_step`) | `test_a_tool_error_escalates_with_its_code` | `... the step failed (tool_error)` | `... the step failed` |
| 2 | the size measured after the unknown keys are dropped (`McpRunner.run`) | `test_a_result_over_256_kb_fails`, `extra=1` (its `pad` key is not a field of `Rows`) | `too_large` | returns `{"rows": []}` |
| 3 | `>=` instead of `>` in the size check | `test_a_result_over_256_kb_fails`, `extra=0` | returns `{"rows": []}` | `too_large` |
| 4 | the structured result returned whole (no keys dropped) | `test_fields_the_contract_does_not_name_are_dropped` | without `total_cents` | with `total_cents` |
| 5 | `McpUnavailable` turned into `StepFailed()` with no code | `test_each_failure_has_its_code`, `no_command` | `no_command` | `None` |
| 6 | demo actions sent to the demo runner whatever the setting (`DomainRunner`) | `test_without_the_demo_setting_demo_actions_do_not_run` | `StepFailed` | returns `{"text": "hi"}` |
| 7 | `open_runtime` keeps choosing `DemoRunner` or `NoRunner` by the setting | `test_a_read_step_runs_over_mcp` (demo off) | `done` | `waiting` at a `tool_error` escalation |

Reasonable variations that are correct: the server found through a dictionary built once in `McpRunner.__init__`; `DomainRunner` building its `McpRunner` once; the field filter as a dict comprehension over `action.result.model_fields`; the code check in `StepFailed.__init__` as a membership test on `FAILURE_CODES`.

## 6. Project rules

- Searches 1 to 3.
- A `propose` or `write` tool is called only through `run_step`, after its step approval.
- No tool text, argument, or result appears in a `StepFailed`, a message, or an escalation.
- No test or probe opens a network connection; servers are child processes over stdio, and none is left running.

## 7. Out of scope

Each must be absent: agent actions running, retries, reused server processes, parallel calls, nested field dropping, coercion, changes to the client, the tool check, the registry, contracts, the CLI, the `ERROR` payload, or the demo runner's outputs.

## 8. Progress log

The entry exists, headed `## Phase 6c: tool steps over MCP (...)`, with `Tests: 641 -> <passed> (given 17)`, and each deviation it lists is real and justified.
