import copy

import pytest
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.types import Interrupt

from conductor.events import RUN_ID_MESSAGE
from conductor.graph.status import (
    RunError,
    RunState,
    RunStateUnavailable,
    checkpoint_state,
)
from conductor.graph.supervisor import run_state

RUN = "a" * 32
APPROVAL = "b" * 32
ESCALATION = "c" * 32
NULL = "00000000-0000-0000-0000-000000000000"


def record(values: dict, writes: list | None = None, version: object = 4) -> CheckpointTuple:
    return CheckpointTuple(
        {"configurable": {"thread_id": RUN}},
        {"v": version, "channel_values": values, "pending_sends": []},
        {},
        pending_writes=writes,
    )


def refused(saved: CheckpointTuple) -> None:
    before = copy.deepcopy(saved)
    with pytest.raises(RunStateUnavailable) as raised:
        checkpoint_state(saved, RUN)
    assert str(raised.value) == f"run {RUN} state is not available"
    assert saved == before
    assert "SYNTHETIC-SECRET" not in str(raised.value)


def test_a_missing_tuple_is_a_missing_run() -> None:
    with pytest.raises(RunError) as raised:
        checkpoint_state(None, RUN)
    assert str(raised.value) == f"no run {RUN}"


def test_an_invalid_run_id_is_refused_before_the_checkpoint() -> None:
    class Untouched:
        @property
        def checkpoint(self) -> dict:
            raise AssertionError("the checkpoint was examined")

    with pytest.raises(ValueError) as raised:
        checkpoint_state(Untouched(), "nope")  # type: ignore[arg-type]
    assert str(raised.value) == RUN_ID_MESSAGE


def test_null_task_bookkeeping_does_not_change_a_terminal_run() -> None:
    saved = record(
        {"status": "done", "reply": "Done.", "approval_id": APPROVAL},
        [
            (NULL, "__resume__", "SYNTHETIC-SECRET"),
            (NULL, "__scheduled__", "SYNTHETIC-SECRET"),
            ("task", "__scheduled__", "SYNTHETIC-SECRET"),
        ],
    )
    before = copy.deepcopy(saved)
    assert checkpoint_state(saved, RUN) == RunState(RUN, "done", reply="Done.")
    assert saved == before


def test_a_null_task_resume_does_not_decide_an_approval() -> None:
    saved = record(
        {"branch:to:wait_approval": None},
        [
            (NULL, "__resume__", APPROVAL),
            ("task", "__interrupt__", (Interrupt({"approval_id": APPROVAL}),)),
        ],
    )
    assert checkpoint_state(saved, RUN) == RunState(RUN, "waiting", approval_id=APPROVAL)


def test_pending_output_from_start_stops_at_route() -> None:
    saved = record(
        {"__start__": None},
        [("task", "request", "demo: say hi"), ("task", "branch:to:route", None)],
    )
    before = copy.deepcopy(saved)
    assert checkpoint_state(saved, RUN) == RunState(RUN, "stopped", stopped_at="route")
    assert saved == before


def test_an_error_stays_opaque_and_the_node_stays_stopped() -> None:
    error = RuntimeError("SYNTHETIC-SECRET")
    saved = record({"branch:to:plan": None}, [("task", "__error__", error)])
    assert checkpoint_state(saved, RUN) == RunState(RUN, "stopped", stopped_at="plan")
    assert saved.pending_writes is not None
    assert saved.pending_writes[0][2] is error


def test_absent_writes_and_sends_still_read_a_terminal_run() -> None:
    saved = CheckpointTuple(
        {"configurable": {"thread_id": RUN}},
        {
            "v": 4,
            "channel_values": {"status": "rejected", "note": None, "reply": None},
            "pending_sends": None,
        },
        {},
        pending_writes=None,
    )
    assert checkpoint_state(saved, RUN) == RunState(RUN, "rejected")


@pytest.mark.parametrize(
    "saved",
    [
        CheckpointTuple({"configurable": {}}, "SYNTHETIC-SECRET", {}, None, []),
        record({"status": "done", "reply": "Done."}, version=True),
        record({"status": "done", "reply": "Done."}, version="4"),
        record(["SYNTHETIC-SECRET"]),  # type: ignore[arg-type]
        CheckpointTuple(
            {"configurable": {}},
            {"v": 4, "channel_values": {"status": "done", "reply": "Done."}, "pending_sends": [1]},
            {},
            None,
            [],
        ),
        CheckpointTuple(
            {"configurable": {}},
            {
                "v": 4,
                "channel_values": {"status": "done", "reply": "Done."},
                "pending_sends": "SYNTHETIC-SECRET",
            },
            {},
            None,
            [],
        ),
        record({"status": "done", "reply": "Done."}, writes="SYNTHETIC-SECRET"),  # type: ignore[arg-type]
        record({"status": "done", "reply": "Done."}, writes=[["task", "status", "done"]]),
        record({"status": "done", "reply": "Done."}, writes=[("task", "status")]),
        record({"status": "done", "reply": "Done."}, writes=[(1, "status", "done")]),
        record({"status": "done", "reply": "Done."}, writes=[("task", 1, "done")]),
        record({"branch:to:sideways": None}),
        record({1: None, "status": "done", "reply": "Done."}),
        record({"__start__": None, "branch:to:route": None}),
        record(
            {"branch:to:plan": None},
            [("task", "branch:to:ask_step", None), ("task", "branch:to:answer", None)],
        ),
        record({"branch:to:plan": None}, [("task", "branch:to:sideways", None)]),
        record({"branch:to:plan": None}, [("task", "secret", "SYNTHETIC-SECRET")]),
        record({"branch:to:plan": None}, [("task", "__input__", "SYNTHETIC-SECRET")]),
        record(
            {"branch:to:wait_approval": None},
            [
                ("task", "__interrupt__", [Interrupt({"approval_id": APPROVAL})]),
                ("task", "__interrupt__", [Interrupt({"approval_id": APPROVAL})]),
            ],
        ),
        record(
            {"branch:to:wait_approval": None},
            [("task", "__interrupt__", [])],
        ),
        record(
            {"branch:to:wait_approval": None},
            [("task", "__interrupt__", Interrupt({"approval_id": APPROVAL}))],
        ),
        record(
            {"branch:to:wait_approval": None},
            [("task", "__interrupt__", [Interrupt(["SYNTHETIC-SECRET"])])],
        ),
        record(
            {"branch:to:wait_escalation": None},
            [("task", "__interrupt__", [Interrupt({"approval_id": APPROVAL})])],
        ),
        record(
            {"branch:to:wait_approval": None},
            [("task", "__interrupt__", [Interrupt({"approval_id": "g" * 32})])],
        ),
        record(
            {"branch:to:wait_approval": None},
            [("task", "__interrupt__", [Interrupt({"approval_id": 4210})])],
        ),
        record({"status": "done"}),
        record({"status": "done", "reply": None}),
        record({"status": "done", "reply": ""}),
        record({"status": "done", "reply": "   "}),
        record({"status": "done", "reply": "x" * 2001}),
        record({"status": "done", "reply": False}),
        record({"status": True, "reply": "Done."}),
        record({"status": "rejected", "note": False}),
    ],
)
def test_one_bad_field_is_refused(saved: CheckpointTuple) -> None:
    refused(saved)


def test_a_long_reply_at_the_bound_is_kept_and_references_are_cleared() -> None:
    reply = "x" * 2000
    saved = record(
        {
            "status": "cancelled",
            "reply": reply,
            "note": "kept",
            "approval_id": APPROVAL,
            "escalation_id": ESCALATION,
            "stopped_at": "plan",
        }
    )
    assert checkpoint_state(saved, RUN) == RunState(RUN, "cancelled", reply=reply, note="kept")


class _Broken:
    def get_tuple(self, config: dict) -> CheckpointTuple:
        raise RuntimeError("SYNTHETIC-SECRET")


class _Graph:
    checkpointer = _Broken()


def test_a_checkpoint_read_failure_is_a_safe_unavailable_state() -> None:
    with pytest.raises(RunStateUnavailable) as raised:
        run_state(_Graph(), RUN)  # type: ignore[arg-type]
    assert str(raised.value) == f"run {RUN} state is not available"
    assert "SYNTHETIC-SECRET" not in str(raised.value)


def test_a_bad_run_id_never_reads_the_checkpointer() -> None:
    with pytest.raises(ValueError) as raised:
        run_state(_Graph(), "nope")  # type: ignore[arg-type]
    assert str(raised.value) == RUN_ID_MESSAGE
