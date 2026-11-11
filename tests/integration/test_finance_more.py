import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.events import EventKind
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import ask, open_runtime

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def test_a_prefixed_balance_request_runs_to_done() -> None:
    model = ScriptedModel(
        [
            ScriptedReply(
                "plan",
                ModelReply(content=json.dumps({"steps": [{"action": "get_balances", "args": {}}]})),
            ),
            ScriptedReply("answer", ModelReply(content='{"reply": "Net worth is 1234.56."}')),
        ]
    )
    with open_runtime(get_settings(), model=model) as runtime:
        done = ask(runtime, "finance: what is the balance")
        events = runtime.log.read(done.run_id)
    assert done.status == "done"
    assert [request.point for request in model.requests] == ["plan", "answer"]
    assert EventKind.APPROVAL_REQUESTED not in [event.kind for event in events]
    results = [event.payload for event in events if event.kind == EventKind.TOOL_RESULT]
    assert results[0]["output"]["net_worth_cents"] == 123456
