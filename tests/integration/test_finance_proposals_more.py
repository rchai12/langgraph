import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.events import EventKind
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import Runtime, ask, open_runtime, resume

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"
NOTE = "Review the streaming subscriptions in December."
PROPOSAL = {"transaction_id": 101, "category": "Groceries", "reason": "Corner Grocer sells food"}


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def scripted(*steps: dict) -> ScriptedModel:
    return ScriptedModel(
        [
            ScriptedReply("plan", ModelReply(content=json.dumps({"steps": list(steps)}))),
            ScriptedReply("answer", ModelReply(content='{"reply": "Done."}')),
        ]
    )


def decide(runtime: Runtime, approval_id: str, verdict: str, **more: object) -> None:
    decide_approval(
        runtime.store,
        runtime.registry,
        approval_id,
        verdict,
        channel="terminal",
        decided_by="owner",
        **more,
    )


def kinds(runtime: Runtime, run_id: str) -> list:
    return [event.kind for event in runtime.log.read(run_id)]


def test_advice_waits_for_both_approvals_and_keeps_its_text() -> None:
    model = scripted({"action": "log_advice", "args": {"text": NOTE}})
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: keep a note about the subscriptions")
        assert first.status == "waiting"
        assert runtime.store.approval(first.approval_id).request.stage == "plan"
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        assert second.status == "waiting"
        assert runtime.store.approval(second.approval_id).request.stage == "step"
        decide(runtime, second.approval_id, "approve")
        done = resume(runtime, first.run_id)
        results = [
            event.payload
            for event in runtime.log.read(first.run_id)
            if event.kind == EventKind.TOOL_RESULT
        ]
    assert done.status == "done"
    assert results[0]["output"]["advice"]["text"] == NOTE


def test_a_rejected_plan_calls_no_tool() -> None:
    model = scripted(
        {"action": "get_balances", "args": {}},
        {"action": "propose_category", "args": PROPOSAL},
    )
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "reject", note="Not now")
        ended = resume(runtime, first.run_id)
        found = kinds(runtime, first.run_id)
    assert ended.status == "rejected"
    assert EventKind.TOOL_CALL not in found
