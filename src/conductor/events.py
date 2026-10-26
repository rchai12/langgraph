import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from conductor import clock

RUN_ID_MESSAGE = "run id must be 32 lowercase hexadecimal characters"
_RUN_ID = re.compile(r"[0-9a-f]{32}")
_RUN_FILE = re.compile(r"[0-9a-f]{32}\.jsonl")

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
        if value.utcoffset() != timedelta(0):
            raise ValueError("time must be UTC")
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
    if _RUN_ID.fullmatch(run_id) is None:
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
        "at": event.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
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
        self._counts: dict[str, int] = {}

    def append(
        self,
        run_id: str,
        kind: EventKind,
        *,
        node: str | None = None,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        run_id = check_run_id(run_id)
        if run_id not in self._counts:
            self._counts[run_id] = self._count_on_disk(run_id)
        seq = self._counts[run_id] + 1
        event = _event(run_id, seq, kind, node, payload)
        line = _event_line(event)
        self._write_line(run_id, line)
        self._counts[run_id] = seq
        return event

    def read(self, run_id: str) -> list[Event]:
        run_id = check_run_id(run_id)
        path = self._folder / f"{run_id}.jsonl"
        if not path.is_file():
            raise RunNotFound(f"no run {run_id}")
        pieces = path.read_bytes().split(b"\n")
        if pieces[-1] == b"":
            del pieces[-1]
        return [_parse_line(run_id, number, piece) for number, piece in enumerate(pieces, start=1)]

    def runs(self) -> list[RunSummary]:
        if not self._folder.is_dir():
            return []
        found: list[RunSummary] = []
        for path in self._folder.iterdir():
            if _RUN_FILE.fullmatch(path.name) is None:
                continue
            run_id = path.name.removesuffix(".jsonl")
            events = self.read(run_id)
            found.append(RunSummary(run_id, events[0].at, len(events)))
        found.sort(key=lambda summary: summary.run_id)
        found.sort(key=lambda summary: summary.started_at, reverse=True)
        return found

    def _count_on_disk(self, run_id: str) -> int:
        path = self._folder / f"{run_id}.jsonl"
        if not path.is_file():
            return 0
        return len(self.read(run_id))

    def _write_line(self, run_id: str, line: str) -> None:
        if not self._folder.exists():
            self._folder.mkdir(parents=True, mode=0o700)
            self._folder.chmod(0o700)
        path = self._folder / f"{run_id}.jsonl"
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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
