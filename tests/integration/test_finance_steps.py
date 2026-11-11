import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.domains import finance
from conductor.events import EventKind
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.mcp_client.client import McpClient
from conductor.runtime import ask, open_runtime

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def test_the_fake_lists_the_real_read_tools() -> None:
    listed = McpClient(finance.SERVER, get_settings()).list_tools()
    found = {
        tool.name: {
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "read_only": tool.read_only,
        }
        for tool in listed
    }
    assert found == json.loads((TESTS / "finances_tools.json").read_text())


def test_a_finance_request_runs_its_reads_without_asking() -> None:
    steps = [
        {
            "action": "get_spending",
            "args": {"start": "2026-10-01", "end": "2026-10-31", "by": "merchant"},
        },
        {"action": "list_transactions", "args": {"merchant": "Corner Grocer", "limit": 5}},
    ]
    model = ScriptedModel(
        [
            ScriptedReply("plan", ModelReply(content=json.dumps({"steps": steps}))),
            ScriptedReply("answer", ModelReply(content='{"reply": "You spent $42.10."}')),
        ]
    )
    with open_runtime(get_settings(), model=model) as runtime:
        assert runtime.registry.names == ("finance",)
        done = ask(runtime, "What have we spent at Corner Grocer in October?")
        assert done == RunState(run_id=done.run_id, status="done", reply="You spent $42.10.")
        events = runtime.log.read(done.run_id)
    kinds = [event.kind for event in events]
    assert EventKind.APPROVAL_REQUESTED not in kinds
    results = [event.payload for event in events if event.kind == EventKind.TOOL_RESULT]
    assert [item["step"] for item in results] == [1, 2]
    assert results[0]["output"]["start"] == "2026-10-01"
    assert results[0]["output"]["by"] == "merchant"
    assert results[1]["output"]["transactions"][0]["merchant"] == "Corner Grocer"
    assert results[1]["output"]["next_offset"] is None
    assert [request.point for request in model.requests] == ["plan", "answer"]
    assert '"action": "finance.list_transactions"' in model.requests[1].user
