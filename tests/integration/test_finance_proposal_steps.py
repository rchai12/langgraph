import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.events import EventKind
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.policy import DecisionRefused
from conductor.runtime import Runtime, ask, open_runtime, resume

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"
PROPOSAL = {"transaction_id": 101, "category": "Groceries", "reason": "Corner Grocer sells food"}
READ_STEP = {"action": "list_uncategorized", "args": {}}
PROPOSE_STEP = {"action": "propose_category", "args": PROPOSAL}
REPLY = '{"reply": "Proposed."}'


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def scripted(*steps: dict, answer: bool = True) -> ScriptedModel:
    replies = [ScriptedReply("plan", ModelReply(content=json.dumps({"steps": list(steps)})))]
    if answer:
        replies.append(ScriptedReply("answer", ModelReply(content=REPLY)))
    return ScriptedModel(replies)


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


def kinds(runtime: Runtime, run_id: str) -> list[str]:
    return [event.kind for event in runtime.log.read(run_id)]


def payloads(runtime: Runtime, run_id: str, kind: EventKind) -> list[dict]:
    return [event.payload for event in runtime.log.read(run_id) if event.kind == kind]


def test_a_proposal_waits_for_both_approvals_and_then_runs() -> None:
    model = scripted(READ_STEP, PROPOSE_STEP)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        plan = runtime.store.approval(first.approval_id).request
        assert (first.status, plan.stage) == ("waiting", "plan")
        assert [(step.action, step.effect) for step in plan.steps] == [
            ("finance.list_uncategorized", "read"),
            ("finance.propose_category", "propose"),
        ]
        assert EventKind.TOOL_CALL not in kinds(runtime, first.run_id)
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        step = runtime.store.approval(second.approval_id).request
        assert (second.status, step.stage) == ("waiting", "step")
        assert [(item.number, item.action, item.args) for item in step.steps] == [
            (2, "finance.propose_category", PROPOSAL)
        ]
        assert [call["step"] for call in payloads(runtime, first.run_id, EventKind.TOOL_CALL)] == [
            1
        ]
        decide(runtime, second.approval_id, "approve")
        done = resume(runtime, first.run_id)
        results = payloads(runtime, first.run_id, EventKind.TOOL_RESULT)
    assert done == RunState(run_id=first.run_id, status="done", reply="Proposed.")
    assert [request.point for request in model.requests] == ["plan", "answer"]
    proposal = results[1]["output"]["proposal"]
    assert (results[1]["step"], proposal["kind"], proposal["transaction_id"]) == (
        2,
        "category",
        101,
    )


def test_a_rejected_proposal_never_reaches_the_server() -> None:
    model = scripted(PROPOSE_STEP, answer=False)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        decide(runtime, second.approval_id, "reject", note="Not groceries")
        ended = resume(runtime, first.run_id)
        found = kinds(runtime, first.run_id)
    assert (ended.status, ended.note) == ("rejected", "Not groceries")
    assert EventKind.TOOL_CALL not in found
    assert [request.point for request in model.requests] == ["plan"]


def test_an_edited_proposal_sends_the_edited_arguments() -> None:
    edited = {"transaction_id": 102, "category": "Dining", "reason": "A cafe"}
    model = scripted(PROPOSE_STEP)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        decide(runtime, second.approval_id, "edit", edited_args=edited)
        done = resume(runtime, first.run_id)
        calls = payloads(runtime, first.run_id, EventKind.TOOL_CALL)
        results = payloads(runtime, first.run_id, EventKind.TOOL_RESULT)
    assert done.status == "done"
    assert [call["args"] for call in calls] == [edited]
    proposal = results[0]["output"]["proposal"]
    assert (proposal["transaction_id"], proposal["category"], proposal["reason"]) == (
        102,
        "Dining",
        "A cafe",
    )


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        ({"reason": "two\nlines"}, "reason"),
        ({"transaction_id": 0}, "transaction_id"),
        ({"category": "x" * 101}, "category"),
    ],
    ids=["reason-two-lines", "id-0", "category-101"],
)
def test_an_edit_past_a_bound_is_refused_and_the_request_stays_open(change: dict, loc: str) -> None:
    model = scripted(PROPOSE_STEP, answer=False)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        with pytest.raises(DecisionRefused) as refused:
            decide(runtime, second.approval_id, "edit", edited_args={**PROPOSAL, **change})
        stored = runtime.store.approval(second.approval_id)
    assert (refused.value.code, [problem.loc for problem in refused.value.problems]) == (
        "invalid_edit",
        [loc],
    )
    assert stored.decision is None
