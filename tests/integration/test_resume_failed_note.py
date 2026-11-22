import itertools
from datetime import UTC, datetime

import pytest

from conductor import clock, ids
from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import DemoRunner, ask, open_runtime, resume
from conductor.store import Store

NOTE = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
SECRET = "SYNTHETIC-SECRET"
START = datetime(2031, 3, 4, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: START)
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def test_a_failed_note_records_its_type_and_keeps_both_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with open_runtime(
        get_settings(), model=ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE))])
    ) as opened:
        plan = ask(opened, "demo: note Milk")
        decide_approval(
            opened.store,
            opened.registry,
            plan.approval_id,
            "approve",
            channel="terminal",
            decided_by="owner",
            note="",
        )
        step = resume(opened, plan.run_id)
        decide_approval(
            opened.store,
            opened.registry,
            step.approval_id,
            "approve",
            channel="terminal",
            decided_by="owner",
            note="",
        )

    def broken(_self: DemoRunner, _action: object, _args: object) -> dict:
        raise ValueError(SECRET)

    monkeypatch.setattr(DemoRunner, "run", broken)
    with open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        with pytest.raises(ValueError) as raised:
            resume(opened, plan.run_id)
    assert str(raised.value) == SECRET
    log = EventLog(get_settings().runs_dir)
    found = [
        event.payload
        for event in log.read(plan.run_id)
        if event.kind.value == "error" and event.node is None
    ]
    assert found == [{"error": "resume_failed", "type": "ValueError"}]
    path = get_settings().runs_dir / f"{plan.run_id}.jsonl"
    assert SECRET not in path.read_text(encoding="utf-8")
    store = Store(get_settings().db_path)
    assert store.approval(plan.approval_id).decision is not None
    assert store.approval(step.approval_id).decision is not None
