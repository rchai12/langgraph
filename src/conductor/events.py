import fcntl
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from conductor import clock, private, times
from conductor.contracts.base import UTC_MESSAGE, is_id, is_utc

RUN_ID_MESSAGE = "run id must be 32 lowercase hexadecimal characters"

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    MODEL_REQUEST = "model_request"
    MODEL_REPLY = "model_reply"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    ESCALATED = "escalated"
    ERROR = "error"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    seq: int = Field(ge=1)
    at: datetime
    kind: EventKind
    node: str | None
    payload: dict[str, JsonValue]

    @field_validator("at")
    @classmethod
    def _at_is_utc(cls, value: datetime) -> datetime:
        if not is_utc(value):
            raise ValueError(UTC_MESSAGE)
        return value


class EventLogCorrupt(Exception):
    pass


class RunNotFound(Exception):
    pass


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    started_at: datetime
    events: int


def check_run_id(run_id: str) -> str:
    if not is_id(run_id):
        raise ValueError(RUN_ID_MESSAGE)
    return run_id


def _json_shape(value: object) -> None:
    """Reject values JSON cannot store. NaN and infinity stay for the line writer to refuse."""
    if isinstance(value, dict):
        for item in value.values():
            _json_shape(item)
        return
    if isinstance(value, list):
        for item in value:
            _json_shape(item)
        return
    if value is None or isinstance(value, str | int | float):
        return
    raise ValueError("event is not valid")


def _event_line(event: Event) -> str:
    data = {
        "at": times.stored(event.at),
        "kind": event.kind.value,
        "node": event.node,
        "payload": event.payload,
        "run_id": event.run_id,
        "seq": event.seq,
    }
    try:
        body = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("event is not valid") from error
    return f"{body}\n"


class EventLog:
    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._seen: dict[str, tuple[int, int]] = {}

    def append(
        self,
        run_id: str,
        kind: EventKind,
        *,
        node: str | None = None,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        run_id = check_run_id(run_id)
        draft = _event(run_id, 1, kind, node, payload)
        _event_line(draft)  # a refused event must not create the file
        path = self._folder / f"{run_id}.jsonl"
        descriptor = private.open_file(path, os.O_RDWR | os.O_APPEND)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            size, last = self._discover(run_id, descriptor)
            event = draft.model_copy(update={"seq": last + 1})
            raw = _event_line(event).encode("utf-8")
            os.write(descriptor, raw)
            os.fsync(descriptor)
            self._seen[run_id] = (size + len(raw), event.seq)
        finally:
            os.close(descriptor)
        return event

    def read(self, run_id: str) -> list[Event]:
        run_id = check_run_id(run_id)
        path = self._folder / f"{run_id}.jsonl"
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except FileNotFoundError:
            raise RunNotFound(f"no run {run_id}") from None
        with os.fdopen(descriptor, "rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            data = handle.read()
        pieces = data.split(b"\n")
        if pieces[-1] == b"":
            del pieces[-1]
        return [_parse_line(run_id, number, piece) for number, piece in enumerate(pieces, start=1)]

    def runs(self) -> list[RunSummary]:
        if not self._folder.is_dir():
            return []
        found: list[RunSummary] = []
        for path in self._folder.iterdir():
            if not (path.name.endswith(".jsonl") and is_id(path.name.removesuffix(".jsonl"))):
                continue
            run_id = path.name.removesuffix(".jsonl")
            events = self.read(run_id)
            found.append(RunSummary(run_id, events[0].at, len(events)))
        found.sort(key=lambda summary: summary.run_id)
        found.sort(key=lambda summary: summary.started_at, reverse=True)
        return found

    def _discover(self, run_id: str, descriptor: int) -> tuple[int, int]:
        """The file's size and last seq, parsing only the bytes this log has not seen."""
        seen_size, last = self._seen.get(run_id, (0, 0))
        size = os.fstat(descriptor).st_size
        if size < seen_size:
            raise EventLogCorrupt(f"{run_id}.jsonl is shorter than when it was last read")
        if size > seen_size:
            pieces = os.pread(descriptor, size - seen_size, seen_size).split(b"\n")
            tail = pieces.pop()
            for piece in pieces:
                last = _parse_line(run_id, last + 1, piece).seq
            if tail != b"":
                raise EventLogCorrupt(f"{run_id}.jsonl line {last + 1} is not finished")
        self._seen[run_id] = (size, last)
        return size, last


def _event(
    run_id: str,
    seq: int,
    kind: EventKind,
    node: str | None,
    payload: Mapping[str, JsonValue] | None,
) -> Event:
    stored: dict[str, JsonValue] = {} if payload is None else dict(payload)
    _json_shape(stored)
    try:
        return Event(run_id=run_id, seq=seq, at=clock.now(), kind=kind, node=node, payload=stored)
    except ValidationError as error:
        raise ValueError("event is not valid") from error


def _parse_line(run_id: str, number: int, raw: bytes) -> Event:
    try:
        event = Event.model_validate_json(raw, strict=True)
    except (UnicodeDecodeError, ValidationError, ValueError):
        raise EventLogCorrupt(f"{run_id}.jsonl line {number} is not a valid event") from None
    if event.run_id != run_id:
        raise EventLogCorrupt(f"{run_id}.jsonl line {number} belongs to another run")
    if event.seq != number:
        raise EventLogCorrupt(
            f"{run_id}.jsonl line {number} has seq {event.seq}, expected {number}"
        )
    return event
