import re
from dataclasses import dataclass
from typing import Literal, cast

from langgraph.checkpoint.base import CheckpointTuple
from langgraph.types import Interrupt

from conductor.events import check_run_id

NODES = (
    "route",
    "plan",
    "ask_plan",
    "ask_step",
    "wait_approval",
    "run_step",
    "answer",
    "record_escalation",
    "wait_escalation",
    "finish",
)
RunStatus = Literal["waiting", "done", "rejected", "cancelled", "stopped"]
_NULL_TASK = "00000000-0000-0000-0000-000000000000"
_BOOKKEEPING = frozenset({"__scheduled__", "__resume__"})
_RESERVED = frozenset({"__interrupt__", "__error__", "__no_writes__", *_BOOKKEEPING})
_FIELDS = frozenset(
    {
        "request",
        "routed",
        "route",
        "plan",
        "step",
        "args",
        "results",
        "pending",
        "escalation",
        "escalation_id",
        "retry_node",
        "status",
        "reply",
        "note",
    }
)
_NODES = frozenset((*NODES, "__start__"))
_TERMINAL = frozenset({"done", "rejected", "cancelled"})
_HEX = re.compile(r"^[0-9a-f]{32}$")
_MISSING = object()


class RunError(Exception):
    pass


class RunStateUnavailable(RunError):
    pass


@dataclass(frozen=True)
class RunState:
    run_id: str
    status: RunStatus
    approval_id: str | None = None
    escalation_id: str | None = None
    reply: str | None = None
    note: str = ""
    stopped_at: str | None = None


def checkpoint_state(saved: CheckpointTuple | None, run_id: str) -> RunState:
    check_run_id(run_id)
    if saved is None:
        raise RunError(f"no run {run_id}")
    return _project(saved, run_id)


def _unavailable(run_id: str) -> RunStateUnavailable:
    return RunStateUnavailable(f"run {run_id} state is not available")


def _project(saved: CheckpointTuple, run_id: str) -> RunState:
    checkpoint = saved.checkpoint
    if type(checkpoint) is not dict:
        raise _unavailable(run_id)
    version = checkpoint.get("v", _MISSING)
    if type(version) is not int or version != 4:
        raise _unavailable(run_id)
    values = checkpoint.get("channel_values", _MISSING)
    if type(values) is not dict:
        raise _unavailable(run_id)
    sends = checkpoint.get("pending_sends", [])
    if sends is None:
        sends = []
    if type(sends) is not list or len(sends) > 0:
        raise _unavailable(run_id)
    rows = _rows(saved.pending_writes, run_id)
    live = _live(values, run_id)
    task = _task(rows, run_id)
    if task is not None and _completes(task, run_id):
        return _completed(values, task, run_id)
    interrupts = [value for _, channel, value in rows if channel == "__interrupt__"]
    if interrupts:
        return _waiting(interrupts, live, run_id)
    if live is not None:
        return RunState(run_id, "stopped", stopped_at=live)
    return _terminal(values, run_id)


def _rows(writes: object, run_id: str) -> list[tuple[str, str, object]]:
    if writes is None:
        return []
    if type(writes) is not list:
        raise _unavailable(run_id)
    rows: list[tuple[str, str, object]] = []
    for row in writes:
        if type(row) is not tuple or len(row) != 3:
            raise _unavailable(run_id)
        task_id, channel, value = row
        if type(task_id) is not str or type(channel) is not str:
            raise _unavailable(run_id)
        if channel == "__pregel_tasks" or (channel.startswith("__") and channel not in _RESERVED):
            raise _unavailable(run_id)
        if task_id == _NULL_TASK or channel in _BOOKKEEPING:
            continue
        rows.append((task_id, channel, value))
    return rows


def _live(values: dict[object, object], run_id: str) -> str | None:
    found: list[str] = []
    for key in values:
        if type(key) is not str:
            raise _unavailable(run_id)
        if key == "__start__":
            found.append("__start__")
        elif key.startswith("branch:to:"):
            node = key.removeprefix("branch:to:")
            if node not in _NODES:
                raise _unavailable(run_id)
            found.append(node)
    if len(found) > 1:
        raise _unavailable(run_id)
    if not found:
        return None
    return found[0]


def _task(rows: list[tuple[str, str, object]], run_id: str) -> list[tuple[str, object]] | None:
    names = {task_id for task_id, _, _ in rows}
    if len(names) > 1:
        raise _unavailable(run_id)
    if not names:
        return None
    task_id = next(iter(names))
    return [(channel, value) for found, channel, value in rows if found == task_id]


def _completes(task: list[tuple[str, object]], run_id: str) -> bool:
    completed = False
    for channel, _ in task:
        if channel == "__no_writes__" or channel in _FIELDS or channel.startswith("branch:to:"):
            node = channel.removeprefix("branch:to:")
            if channel.startswith("branch:to:") and node not in _NODES:
                raise _unavailable(run_id)
            completed = True
        elif channel not in {"__interrupt__", "__error__"}:
            raise _unavailable(run_id)
    return completed


def _completed(
    values: dict[object, object], task: list[tuple[str, object]], run_id: str
) -> RunState:
    overlay: dict[str, object] = {}
    nxt: list[str] = []
    for channel, value in task:
        if channel.startswith("branch:to:"):
            nxt.append(channel.removeprefix("branch:to:"))
        elif channel in _FIELDS:
            overlay[channel] = value
    if len(nxt) > 1:
        raise _unavailable(run_id)
    if len(nxt) == 1:
        return RunState(run_id, "stopped", stopped_at=nxt[0])
    merged = {key: item for key, item in values.items() if type(key) is str}
    merged.update(overlay)
    return _terminal(merged, run_id)


def _waiting(interrupts: list[object], live: str | None, run_id: str) -> RunState:
    if len(interrupts) != 1:
        raise _unavailable(run_id)
    container = interrupts[0]
    if (type(container) is not list and type(container) is not tuple) or len(container) != 1:
        raise _unavailable(run_id)
    item = container[0]
    if not isinstance(item, Interrupt) or type(item.value) is not dict or len(item.value) != 1:
        raise _unavailable(run_id)
    key, value = next(iter(item.value.items()))
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise _unavailable(run_id)
    if key == "approval_id" and live == "wait_approval":
        return RunState(run_id, "waiting", approval_id=value)
    if key == "escalation_id" and live == "wait_escalation":
        return RunState(run_id, "waiting", escalation_id=value)
    raise _unavailable(run_id)


def _terminal(values: dict[object, object], run_id: str) -> RunState:
    status = values.get("status", _MISSING)
    reply = _reply(values, run_id)
    if status == "done" and reply is None:
        raise _unavailable(run_id)
    if type(status) is not str or status not in _TERMINAL:
        raise _unavailable(run_id)
    return RunState(run_id, cast(RunStatus, status), reply=reply, note=_note(values, run_id))


def _reply(values: dict[object, object], run_id: str) -> str | None:
    if "reply" not in values or values["reply"] is None:
        return None
    reply = values["reply"]
    if type(reply) is str and reply.strip() != "" and len(reply) <= 2000:
        return reply
    raise _unavailable(run_id)


def _note(values: dict[object, object], run_id: str) -> str:
    if "note" not in values or values["note"] is None:
        return ""
    note = values["note"]
    if type(note) is str:
        return note
    raise _unavailable(run_id)
