# Phase 6c: tool steps over MCP

## Corrections (2026-11-09, after the first verification)

The first attempt failed on a mistake in this spec, not in the code: `tests/integration/test_mcp_steps.py` called `model_dump_json()` on a `StoredEscalation`, a dataclass, instead of on the `Escalation` it holds. The corrected file below calls `.escalation.model_dump_json()`; nothing else changes. The code already written stays: replace the given file, then run Acceptance and write the progress entry.

## Goal

The last part of Phase 6: a tool action's step now runs on its MCP server.

- `McpRunner` (in `conductor.runtime`, critical) calls the action's tool with its validated arguments through the 6a client, keeps only the result fields the action's contract names, and turns every failure into a `StepFailed` **with a cause code**;
- `DomainRunner` sends each step to the right runner: an action with a server to `McpRunner`, a demo action (with `CONDUCTOR_DEMO`) to the demo runner, anything else to `NoRunner`;
- a failed step's escalation says why: `step 1 lab.fail: the step failed (timeout)`.

Decided with the owner (2026-11-09): the escalation names **a constant cause code**; a result keeps **only the fields its contract names** (top level); a result over **256 KB** fails the step (`too_large`). Earlier: one server process per call (6a); the graph validates the result strictly and a failed step escalates as `tool_error`, retry asking for the step's approval again (5c).

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 7), `docs/architecture.md` ("Run a step")
- `src/conductor/runtime.py` (5d, 6b), `src/conductor/graph/supervisor.py` (`StepFailed`, `run_step`), `src/conductor/mcp_client/client.py`, `tests/mcp_fake_server.py`, `tests/integration/test_resume_stopped.py` (it replaces `DemoRunner.run` on the class)

## Starting state

Phase 6b is built and verified, and everything is committed: N is `641`. **Sections: core.** No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/graph/supervisor.py` | `FAILURE_CODES`, `StepFailed`'s code, and the code in the step escalation's detail (Part 1) |
| `src/conductor/runtime.py` | `MAX_RESULT_BYTES`, `McpRunner`, `DomainRunner`, and `DomainRunner` in `open_runtime` (Part 2, critical) |
| `tests/unit/test_mcp_runner.py`, `tests/integration/test_mcp_steps.py` | given |
| `tests/unit/test_mcp_runner_more.py`, `tests/integration/test_mcp_steps_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Agent actions and the coder (Phase 10): they still go to `NoRunner`.
- Retrying a call, reusing a server process, calling tools in parallel, streaming or paging results.
- Dropping nested fields, renaming fields, or coercing values; a result is otherwise validated by the graph as in 5c.
- Changes to the client, the tool check, the registry, contracts, the CLI, the `ERROR` event's payload, or the demo runner's outputs.

## Dependencies

None new.

## Design

```python
# conductor/graph/supervisor.py: added and changed
FAILURE_CODES = ("tool_error", "no_command", "start_failed", "timeout", "closed", "no_result", "too_large")
FailureCode = Literal["tool_error", "no_command", "start_failed", "timeout", "closed", "no_result", "too_large"]

class StepFailed(Exception):
    """A runner raises it when a step could not be done; its text is never shown."""
    def __init__(self, *args: object, code: FailureCode | None = None) -> None: ...
    code: FailureCode | None            # None unless it is one of FAILURE_CODES
```

`code` is keyword-only, so the 5c tests' `StepFailed("hidden")` keeps `code` `None`; a `code` that is not in `FAILURE_CODES` is kept as `None`. In `run_step`, a `StepFailed` with a code gives the detail `step <n> <domain>.<action>: the step failed (<code>)`; without one, the 5c detail `step <n> <domain>.<action>: the step failed`. The `ERROR` event is unchanged.

```python
# conductor/runtime.py: added
MAX_RESULT_BYTES = 256 * 1024

class McpRunner:
    def __init__(self, registry: Registry, settings: Settings, *, connect: Callable[[McpServer, Settings], McpClient] = client_for) -> None: ...
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...

class DomainRunner:
    def __init__(self, registry: Registry, settings: Settings, *, connect: ... = client_for) -> None: ...
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...
```

`McpRunner.run`, in order:

1. the server is the `McpServer` named `action.server`, found among the registry's domains' servers;
2. `connect(server, settings).call_tool(action.target, args.model_dump(mode="json"))`;
3. `McpUnavailable` raises `StepFailed(code=<its code>)`, from `None`;
4. an outcome with `is_error` raises `StepFailed(code="tool_error")`; one with `structured` `None` raises `StepFailed(code="no_result")`;
5. when `len(json.dumps(structured, ensure_ascii=False).encode("utf-8"))` is over `MAX_RESULT_BYTES`, `StepFailed(code="too_large")`;
6. it returns the structured result without the top-level keys that are not fields of `action.result` (nested values are kept as they are).

`DomainRunner.run`: an action with a `server` goes to its `McpRunner`; an action of `demo.DOMAIN` (by identity, `action in demo.DOMAIN.actions`) goes to a `DemoRunner()` instance it holds, only when `settings.demo_on`; anything else to `NoRunner`, which raises `StepFailed()` with no code. It calls the chosen runner's `run` method, so a test that replaces `DemoRunner.run` on the class still reaches it.

`open_runtime` uses `DomainRunner(registry, settings)` as the runner it wraps with the lease (5d), in place of choosing `DemoRunner` or `NoRunner` by the setting. Nothing else in the runtime changes.

## Facts

- From 6a: a tool error is an outcome with `is_error`, whose text is never read; a server that cannot be reached is `McpUnavailable` with `no_command`, `start_failed`, `timeout`, or `closed`; a `str` tool result arrives as `{"result": ...}`; every `finances` tool returns an open object, so its fields are checked only here, per call, by the contract.
- A `timeout` or `closed` during a `propose` or `write` call means the outcome on the server is unknown: the tool may have acted. The retry of 5c asks for the step's approval again, and the escalation now says which it was, so the person can check first.
- `args.model_dump(mode="json")` includes defaults (`limit` 50 when not given), as the tool check of 6b compared.

## Requirements

### Part 1: the cause

- **R1.** `FAILURE_CODES`, `StepFailed`'s keyword-only `code`, and the escalation detail are as under Design; a step failing without a code keeps the 5c text exactly.

### Part 2: the runners (critical)

- **R2.** `McpRunner.run` does the Design's six steps in order, with one call per step and no retry.
- **R3.** Every failure is a `StepFailed` with the code the Design gives, raised `from None`; no tool text, argument, or result is put into it.
- **R4.** Only top-level keys that are not fields of the result contract are dropped; the size is measured before dropping.
- **R5.** `DomainRunner` sends each action as under Design, and `open_runtime` uses it under the lease.

### Part 3: the rules

- **R6.** Side effects stay behind approval: the runner is reached only from `run_step` (5c), so a `propose` or `write` tool is called only after its step approval; nothing in 6c calls a tool otherwise.
- **R7.** `runtime.py` imports `conductor.mcp_client.client` and `conductor.domains.demo` and nothing new besides; `mcp` is still imported only in `conductor/mcp_client/`.
- **R8.** `runtime.py` and `graph/supervisor.py` stay at 100% of lines and branches.

## Given tests

17 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong. The integration tests run the real graph and the real fake server (`tests/mcp_fake_server.py`) as a child process.

`tests/unit/test_mcp_runner.py` (13 tests)

```python
import json

import pytest
from pydantic import Field

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.graph.supervisor import FAILURE_CODES, StepFailed
from conductor.mcp_client.client import McpUnavailable, ToolOutcome
from conductor.registry import Action, Domain, McpServer, Registry
from conductor.runtime import (
    DEMO_SUMMARY,
    MAX_RESULT_BYTES,
    DomainRunner,
    McpRunner,
)


class Query(Contract):
    month: str
    limit: int = Field(default=50, ge=1, le=200)


class Rows(Contract):
    rows: list[dict[str, str]]


SPEND = Action("spend", "Spending.", "tool", "get_spending", "read", Query, Rows, "ledger")
LEDGER = McpServer("ledger", env=("LEDGER_HOME",))
FINANCE = Domain("finance", "Money.", (SPEND,), servers=(LEDGER,))
REGISTRY = Registry((FINANCE,))


class FakeClient:
    def __init__(self, outcome: ToolOutcome | McpUnavailable) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> ToolOutcome:
        self.calls.append((name, arguments))
        if isinstance(self.outcome, McpUnavailable):
            raise self.outcome
        return self.outcome


def runner_with(outcome: ToolOutcome | McpUnavailable):
    client = FakeClient(outcome)
    servers: list[McpServer] = []

    def connect(server: McpServer, settings):
        servers.append(server)
        return client

    return McpRunner(REGISTRY, get_settings(), connect=connect), client, servers


def failure(runner: McpRunner) -> str | None:
    with pytest.raises(StepFailed) as raised:
        runner.run(SPEND, Query(month="2026-10"))
    return raised.value.code


def test_the_failure_codes() -> None:
    assert FAILURE_CODES == (
        "tool_error",
        "no_command",
        "start_failed",
        "timeout",
        "closed",
        "no_result",
        "too_large",
    )
    assert (StepFailed().code, StepFailed(code="timeout").code) == (None, "timeout")
    assert StepFailed("SYNTHETIC-SECRET").code is None
    assert MAX_RESULT_BYTES == 256 * 1024


def test_a_call_with_the_declared_server_and_the_arguments_as_json() -> None:
    runner, client, servers = runner_with(ToolOutcome(False, {"rows": [{"merchant": "Grocer"}]}))
    assert runner.run(SPEND, Query(month="2026-10")) == {"rows": [{"merchant": "Grocer"}]}
    assert client.calls == [("get_spending", {"month": "2026-10", "limit": 50})]
    assert servers == [LEDGER]


def test_fields_the_contract_does_not_name_are_dropped() -> None:
    structured = {"rows": [{"merchant": "Grocer", "extra": "kept inside"}], "total_cents": 1200}
    runner, _, _ = runner_with(ToolOutcome(False, structured))
    assert runner.run(SPEND, Query(month="2026-10")) == {
        "rows": [{"merchant": "Grocer", "extra": "kept inside"}]
    }


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (ToolOutcome(True, None), "tool_error"),
        (McpUnavailable("ledger", "no_command"), "no_command"),
        (McpUnavailable("ledger", "start_failed"), "start_failed"),
        (McpUnavailable("ledger", "timeout"), "timeout"),
        (McpUnavailable("ledger", "closed"), "closed"),
        (ToolOutcome(False, None), "no_result"),
    ],
)
def test_each_failure_has_its_code(outcome, code: str) -> None:
    runner, _, _ = runner_with(outcome)
    assert failure(runner) == code


@pytest.mark.parametrize(("extra", "code"), [(0, None), (1, "too_large")])
def test_a_result_over_256_kb_fails(extra: int, code: str | None) -> None:
    padding = MAX_RESULT_BYTES - len(json.dumps({"rows": [], "pad": ""}).encode())
    structured = {"rows": [], "pad": "x" * (padding + extra)}
    assert len(json.dumps(structured, ensure_ascii=False).encode()) == MAX_RESULT_BYTES + extra
    runner, _, _ = runner_with(ToolOutcome(False, structured))
    if code is None:
        assert runner.run(SPEND, Query(month="2026-10")) == {"rows": []}
    else:
        assert failure(runner) == code


def test_the_domain_runner_sends_each_action_to_its_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    registry = Registry((FINANCE, demo.DOMAIN))
    client = FakeClient(ToolOutcome(False, {"rows": []}))
    runner = DomainRunner(registry, get_settings(), connect=lambda server, settings: client)
    assert runner.run(SPEND, Query(month="2026-10")) == {"rows": []}
    delegate = next(a for a in demo.DOMAIN.actions if a.name == "delegate")
    assert runner.run(delegate, demo.DelegateArgs(task="tidy")) == {"summary": DEMO_SUMMARY}
    advise = Action("advise", "Advise.", "agent", "advisor", "read", Query, Rows)
    with pytest.raises(StepFailed) as raised:
        runner.run(advise, Query(month="2026-10"))
    assert raised.value.code is None
    assert len(client.calls) == 1


def test_without_the_demo_setting_demo_actions_do_not_run() -> None:
    runner = DomainRunner(Registry((demo.DOMAIN,)), get_settings())
    echo = next(a for a in demo.DOMAIN.actions if a.name == "echo")
    with pytest.raises(StepFailed):
        runner.run(echo, demo.EchoArgs(text="hi"))
```

`tests/integration/test_mcp_steps.py` (4 tests)

```python
import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor import domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.decisions import answer_escalation, decide_approval
from conductor.events import EventKind
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Domain, McpServer
from conductor.runtime import Runtime, ask, open_runtime, resume

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"
REPLY = '{"reply": "Done."}'


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


class Wait(Contract):
    seconds: int
    pid_file: str


class Woke(Contract):
    result: str


ECHO = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
FAIL = Action("fail", "Fail on purpose.", "tool", "fail", "write", Reason, Text, "fake")
WAIT = Action("wait", "Wait a while.", "tool", "wait", "write", Wait, Woke, "fake")
STOP = Action("stop", "Stop the server.", "tool", "stop", "write", Contract, Woke, "fake")
LAB = Domain("lab", "Lab tools.", (ECHO, FAIL, WAIT, STOP), servers=(McpServer("fake"),))


@pytest.fixture(autouse=True)
def lab(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "2")
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))


def model(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies])


def plan(action: str, args: dict) -> str:
    return json.dumps({"steps": [{"action": action, "args": args}]})


def approve_all(runtime: Runtime, state: RunState) -> RunState:
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
    return state


def detail(runtime: Runtime, state: RunState) -> str:
    assert state.status == "waiting" and state.escalation_id is not None
    return runtime.store.escalation(state.escalation_id).escalation.detail


def test_a_read_step_runs_over_mcp(tmp_path: Path) -> None:
    replies = model(("plan", plan("echo", {"text": "hi"})), ("answer", REPLY))
    with open_runtime(get_settings(), model=replies) as runtime:
        done = ask(runtime, "lab: echo hi")
        assert done == RunState(run_id=done.run_id, status="done", reply="Done.")
        [result] = [e for e in runtime.log.read(done.run_id) if e.kind == EventKind.TOOL_RESULT]
        assert result.payload == {"step": 1, "output": {"text": "hi"}}
    assert "fake server started" in (tmp_path / "data" / "mcp" / "fake.log").read_text()


def test_a_tool_error_escalates_with_its_code() -> None:
    reason = {"reason": "SYNTHETIC-SECRET"}
    with open_runtime(get_settings(), model=model(("plan", plan("fail", reason)))) as runtime:
        failed = approve_all(runtime, ask(runtime, "lab: fail"))
        assert detail(runtime, failed) == "step 1 lab.fail: the step failed (tool_error)"
        assert (
            "SYNTHETIC-SECRET"
            not in runtime.store.escalation(failed.escalation_id).escalation.model_dump_json()
        )


def test_a_step_that_takes_too_long_escalates_as_timeout(tmp_path: Path) -> None:
    args = {"seconds": 30, "pid_file": str(tmp_path / "pid")}
    with open_runtime(get_settings(), model=model(("plan", plan("wait", args)))) as runtime:
        failed = approve_all(runtime, ask(runtime, "lab: wait"))
        assert detail(runtime, failed) == "step 1 lab.wait: the step failed (timeout)"


def test_a_server_that_stops_escalates_as_closed_and_retry_asks_again() -> None:
    with open_runtime(get_settings(), model=model(("plan", plan("stop", {})))) as runtime:
        failed = approve_all(runtime, ask(runtime, "lab: stop"))
        assert detail(runtime, failed) == "step 1 lab.stop: the step failed (closed)"
        answer_escalation(
            runtime.store, failed.escalation_id, "retry", channel="terminal", decided_by="owner"
        )
        again = resume(runtime, failed.run_id)
        assert again.status == "waiting" and again.approval_id is not None
        request = runtime.store.approval(again.approval_id).request
        assert (request.stage, request.steps[0].action) == ("step", "lab.stop")
```

## Tests to write

In `tests/unit/test_mcp_runner_more.py`, each with its deciding input:

- R1: `StepFailed(code="nonsense")` keeps `code` `None`; a graph test with a runner raising `StepFailed(code="no_result")` gets the detail with `(no_result)`, and one raising `StepFailed()` the 5c text.
- R2: two servers in two domains: an action reaches its own server's declaration; one call per `run`.
- R3: a tool error whose `structured` would contain `SYNTHETIC-SECRET` does not put it into the `StepFailed` (`str()` and `args`); `__cause__` is `None` after an `McpUnavailable`.
- R4: a result with only unknown keys gives `{}` (and the graph then refuses it as not fitting, `RESULT_DETAIL`).

In `tests/integration/test_mcp_steps_more.py`:

- R5: with `CONDUCTOR_DEMO` on and a lab domain, a demo `echo` step and a lab `echo` step each run on their own runner in one runtime (two runs); without the setting, the demo domain is not registered (as in 5d).
- R6: a `write` tool step starts no server for its call before its step approval: the fake server writes one start line to `data/mcp/fake.log` per process, so after `ask` (the tool check) and the plan approval the log has one start line, and after the step approval and its resume, two.

## Rules for this phase

- **Side effects need approval** (`AGENTS.md` rule 7): unchanged; a tool with a side effect runs only from `run_step`, after its approval.
- **Network**: only the servers' own stdio, through the 6a client.
- **Privacy**: a tool's error text is never read; results are logged only after the contract has kept its own fields.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 17 = 658 passed; `critical coverage` passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_mcp_runner.py tests/integration/test_mcp_steps.py --no-cov`, exactly `17 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/supervisor.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 6c`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) mcp|^(from|import) anyio" -- src | grep -v "^src/conductor/mcp_client/"`
  - `git grep --untracked -n -E "call_tool" -- src | grep -v -E "^src/conductor/(mcp_client/client|runtime)\.py:"`
  - `git grep --untracked -n -E "\.content\b|\.text\b|print\(|logging" -- src/conductor/runtime.py`
- `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/registry.py src/conductor/contracts src/conductor/cli src/conductor/domains tests/unit/test_tool_check.py tests/integration/test_supervisor.py tests/integration/test_supervisor_more.py tests/integration/test_runtime.py tests/integration/test_resume_stopped.py tests/mcp_fake_server.py tests/support.py` prints nothing (new files are untracked, so it does not show them).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 6c: tool steps over MCP (YYYY-MM-DD)`, with `Tests: 641 -> <passed> (given 17)`.
