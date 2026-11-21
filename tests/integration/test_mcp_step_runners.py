import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor import domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.decisions import decide_approval
from conductor.events import EventKind
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Domain, McpServer
from conductor.runtime import ask, open_runtime, resume

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"
REPLY = '{"reply": "Done."}'


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


ECHO = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
FAIL = Action("fail", "Fail on purpose.", "tool", "fail", "write", Reason, Text, "fake")
LAB = Domain("lab", "Lab tools.", (ECHO, FAIL), servers=(McpServer("fake"),))


@pytest.fixture(autouse=True)
def lab(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "2")
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))


def test_demo_and_lab_echo_use_their_own_runners(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with open_runtime(get_settings()) as runtime:
        assert runtime.registry.names == ("lab",)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    replies = model(
        ("plan", plan("echo", {"text": "from-demo"})),
        ("answer", REPLY),
        ("plan", plan("echo", {"text": "from-lab"})),
        ("answer", REPLY),
    )
    log_path = tmp_path / "data" / "mcp" / "fake.log"
    with open_runtime(get_settings(), model=replies) as runtime:
        assert runtime.registry.names == ("lab", "demo")
        demo_done = ask(runtime, "echo please")
        assert demo_done.status == "done"
        assert _output(runtime, demo_done.run_id) == {"text": "from-demo"}
        assert log_path.read_text().count("fake server started") == 1
        lab_done = ask(runtime, "lab: echo please")
        assert lab_done.status == "done"
        assert _output(runtime, lab_done.run_id) == {"text": "from-lab"}
        assert log_path.read_text().count("fake server started") == 2


def test_a_write_call_starts_the_server_only_after_step_approval(tmp_path: Path) -> None:
    log_path = tmp_path / "data" / "mcp" / "fake.log"
    replies = model(("plan", plan("fail", {"reason": "because"})))
    with open_runtime(get_settings(), model=replies) as runtime:
        waiting = ask(runtime, "lab: fail")
        assert waiting.approval_id is not None
        _approve(runtime, waiting.approval_id)
        after_plan = resume(runtime, waiting.run_id)
        assert after_plan.status == "waiting" and after_plan.approval_id is not None
        assert log_path.read_text().count("fake server started") == 1
        _approve(runtime, after_plan.approval_id)
        resume(runtime, waiting.run_id)
        assert log_path.read_text().count("fake server started") == 2


def model(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel(
        [ScriptedReply(point, ModelReply(content=content)) for point, content in replies]
    )


def plan(action: str, args: dict) -> str:
    return json.dumps({"steps": [{"action": action, "args": args}]})


def _approve(runtime, approval_id: str) -> None:
    decide_approval(
        runtime.store,
        runtime.registry,
        approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )


def _output(runtime, run_id: str) -> dict:
    results = [event for event in runtime.log.read(run_id) if event.kind == EventKind.TOOL_RESULT]
    return results[-1].payload["output"]
