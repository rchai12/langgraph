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
