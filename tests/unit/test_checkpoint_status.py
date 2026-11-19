import copy
from importlib import import_module

import pytest
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.types import Interrupt

RUN = "a" * 32
APPROVAL = "b" * 32
ESCALATION = "c" * 32


def saved(values: dict, writes: list | None = None, version: int = 4) -> CheckpointTuple:
    return CheckpointTuple(
        {"configurable": {"thread_id": RUN}},
        {"v": version, "channel_values": values, "pending_sends": []},
        {},
        pending_writes=writes or [],
    )


def api():
    return import_module("conductor.graph.status")


@pytest.mark.parametrize("field", ["approval_id", "escalation_id"])
def test_valid_interrupt_is_waiting(field: str) -> None:
    module = api()
    value = APPROVAL if field == "approval_id" else ESCALATION
    node = "wait_approval" if field == "approval_id" else "wait_escalation"
    record = saved(
        {f"branch:to:{node}": None}, [("task", "__interrupt__", [Interrupt({field: value})])]
    )
    before = copy.deepcopy(record)
    assert module.checkpoint_state(record, RUN) == module.RunState(RUN, "waiting", **{field: value})
    assert record == before


def test_completed_pending_writes_override_an_old_interrupt() -> None:
    module = api()
    record = saved(
        {"branch:to:wait_approval": None},
        [
            ("task", "__interrupt__", [Interrupt({"approval_id": APPROVAL})]),
            ("task", "pending", None),
            ("task", "branch:to:ask_step", None),
        ],
    )
    assert module.checkpoint_state(record, RUN) == module.RunState(
        RUN, "stopped", stopped_at="ask_step"
    )


def test_finish_pending_no_writes_is_terminal() -> None:
    module = api()
    record = saved(
        {"branch:to:finish": None, "status": "done", "reply": "Done."},
        [("task", "__no_writes__", None)],
    )
    assert module.checkpoint_state(record, RUN) == module.RunState(RUN, "done", reply="Done.")


@pytest.mark.parametrize(
    "record",
    [
        saved({"status": "SYNTHETIC-SECRET"}),
        saved({"status": "done", "reply": 5}),
        saved({"status": "rejected", "note": ["SYNTHETIC-SECRET"]}),
        saved({"branch:to:wait_approval": None}, [("t", "__interrupt__", [Interrupt({})])]),
        saved(
            {"branch:to:wait_approval": None},
            [
                (
                    "t",
                    "__interrupt__",
                    [Interrupt({"approval_id": APPROVAL, "escalation_id": ESCALATION})],
                )
            ],
        ),
        saved(
            {"branch:to:wait_approval": None},
            [("t", "__interrupt__", [Interrupt({"approval_id": "B" * 32})])],
        ),
        saved({"branch:to:plan": None, "branch:to:answer": None}),
        saved({"status": "done", "reply": "Done."}, version=99),
        saved({"branch:to:plan": None}, [("t", "__pregel_tasks", "SYNTHETIC-SECRET")]),
        saved({"branch:to:plan": None}, [("t1", "status", "done"), ("t2", "status", "cancelled")]),
    ],
    ids=[
        "status",
        "reply",
        "note",
        "missing-id",
        "two-ids",
        "invalid-id",
        "parallel",
        "version",
        "task-send",
        "two-tasks",
    ],
)
def test_malformed_state_is_safely_refused(record: CheckpointTuple) -> None:
    module = api()
    with pytest.raises(module.RunStateUnavailable) as raised:
        module.checkpoint_state(record, RUN)
    assert str(raised.value) == f"run {RUN} state is not available"
    assert "SYNTHETIC-SECRET" not in str(raised.value)
