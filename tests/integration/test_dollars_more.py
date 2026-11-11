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


def test_a_spending_run_keeps_cents_in_the_log_and_sends_dollars() -> None:
    model = ScriptedModel(
        [
            ScriptedReply(
                "plan",
                ModelReply(content=json.dumps({"steps": [{"action": "get_spending", "args": {}}]})),
            ),
            ScriptedReply("answer", ModelReply(content='{"reply": "Spent 42.10."}')),
        ]
    )
    with open_runtime(get_settings(), model=model) as runtime:
        done = ask(runtime, "finance: how much did we spend")
        events = runtime.log.read(done.run_id)
    assert done.status == "done"
    answer = model.requests[1]
    assert answer.point == "answer"
    assert '"spent_dollars": "42.10"' in answer.user
    assert "_cents" not in answer.user
    results = [event.payload for event in events if event.kind == EventKind.TOOL_RESULT]
    assert results[0]["output"]["lines"][0]["spent_cents"] == 4210
