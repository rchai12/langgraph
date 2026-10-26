import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import clock
from conductor.events import (
    RUN_ID_MESSAGE,
    Event,
    EventKind,
    EventLog,
    EventLogCorrupt,
    RunNotFound,
    RunSummary,
    check_run_id,
)
from tests.support import fixed_times

RUN_A = "0123456789abcdef0123456789abcdef"
RUN_B = "fedcba9876543210fedcba9876543210"
RUN_C = "00000000000000000000000000000001"

LINE_1 = (
    '{"at":"2026-10-25T21:30:00.000000Z","kind":"run_started","node":null,'
    '"payload":{"b":[1,2.5,null,true],"request":"plan my week"},'
    '"run_id":"0123456789abcdef0123456789abcdef","seq":1}'
)
LINE_2 = (
    '{"at":"2026-10-25T21:30:01.250000Z","kind":"node_started","node":"route","payload":{},'
    '"run_id":"0123456789abcdef0123456789abcdef","seq":2}'
)


def write_two(folder: Path, monkeypatch: pytest.MonkeyPatch) -> list[Event]:
    fixed_times(monkeypatch, "2026-10-25T21:30:00+00:00", "2026-10-25T21:30:01.250+00:00")
    log = EventLog(folder)
    return [
        log.append(
            RUN_A,
            EventKind.RUN_STARTED,
            payload={"request": "plan my week", "b": [1, 2.5, None, True]},
        ),
        log.append(RUN_A, EventKind.NODE_STARTED, node="route"),
    ]


def test_the_kinds() -> None:
    assert [kind.value for kind in EventKind] == [
        "run_started",
        "run_finished",
        "node_started",
        "node_finished",
        "model_request",
        "model_reply",
        "tool_call",
        "tool_result",
        "approval_requested",
        "approval_decided",
        "escalated",
        "error",
    ]


def test_each_event_is_one_line_with_sorted_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = write_two(tmp_path / "runs", monkeypatch)
    text = (tmp_path / "runs" / f"{RUN_A}.jsonl").read_text(encoding="utf-8")
    assert text == f"{LINE_1}\n{LINE_2}\n"
    assert [(event.seq, event.kind, event.node) for event in events] == [
        (1, EventKind.RUN_STARTED, None),
        (2, EventKind.NODE_STARTED, "route"),
    ]
    assert events[1].at == datetime(2026, 10, 25, 21, 30, 1, 250000, tzinfo=UTC)
    assert events[1].payload == {}


def test_reading_returns_what_was_written(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events = write_two(tmp_path / "runs", monkeypatch)
    assert EventLog(tmp_path / "runs").read(RUN_A) == events


def test_text_is_written_as_utf8_not_escaped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(monkeypatch, "2026-10-25T21:30:00+00:00")
    EventLog(tmp_path).append(RUN_A, EventKind.MODEL_REPLY, payload={"text": "café ☕"})
    assert '"payload":{"text":"café ☕"}' in (tmp_path / f"{RUN_A}.jsonl").read_text("utf-8")


def test_a_new_log_on_the_same_folder_continues_the_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_two(tmp_path, monkeypatch)
    fixed_times(monkeypatch, "2026-10-25T21:31:00+00:00", "2026-10-25T21:31:01+00:00")
    log = EventLog(tmp_path)
    assert log.append(RUN_A, EventKind.RUN_FINISHED).seq == 3
    assert log.append(RUN_B, EventKind.RUN_STARTED).seq == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == [f"{RUN_A}.jsonl", f"{RUN_B}.jsonl"]


def test_only_the_owner_can_read_the_folder_and_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_two(tmp_path / "data" / "runs", monkeypatch)
    assert (tmp_path / "data" / "runs").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "data" / "runs" / f"{RUN_A}.jsonl").stat().st_mode & 0o777 == 0o600


def test_each_append_is_synced_to_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    synced: list[int] = []
    monkeypatch.setattr(os, "fsync", lambda descriptor: synced.append(descriptor))
    write_two(tmp_path, monkeypatch)
    assert len(synced) == 2


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "0123456789ABCDEF0123456789ABCDEF",
        "0123456789abcdef0123456789abcde",
        "../../../../../../tmp/elsewhere0",
        "0123456789abcdef0123456789abcdef\n",
    ],
)
def test_a_run_id_that_is_not_32_lowercase_hex_is_refused(tmp_path: Path, run_id: str) -> None:
    log = EventLog(tmp_path / "runs")
    with pytest.raises(ValueError) as raised:
        log.append(run_id, EventKind.RUN_STARTED)
    assert str(raised.value) == RUN_ID_MESSAGE
    with pytest.raises(ValueError) as raised:
        log.read(run_id)
    assert str(raised.value) == RUN_ID_MESSAGE
    assert not (tmp_path / "runs").exists()


def test_a_good_run_id_is_returned_as_it_is() -> None:
    assert RUN_ID_MESSAGE == "run id must be 32 lowercase hexadecimal characters"
    assert check_run_id(RUN_A) == RUN_A


@pytest.mark.parametrize("value", [{1, 2}, float("nan"), float("inf"), b"raw"])
def test_a_payload_that_is_not_json_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object
) -> None:
    fixed_times(monkeypatch, *[f"2026-10-25T21:30:0{second}+00:00" for second in range(3)])
    log = EventLog(tmp_path)
    log.append(RUN_A, EventKind.RUN_STARTED)
    before = (tmp_path / f"{RUN_A}.jsonl").read_bytes()
    with pytest.raises(ValueError):
        log.append(RUN_A, EventKind.TOOL_RESULT, payload={"value": value})
    assert (tmp_path / f"{RUN_A}.jsonl").read_bytes() == before
    assert log.append(RUN_A, EventKind.RUN_FINISHED).seq == 2


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 10, 25, 21, 30),
        datetime(2026, 10, 25, 23, 30, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_a_time_that_is_not_utc_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, moment: datetime
) -> None:
    monkeypatch.setattr(clock, "now", lambda: moment)
    with pytest.raises(ValueError):
        EventLog(tmp_path).append(RUN_A, EventKind.RUN_STARTED)
    assert not (tmp_path / f"{RUN_A}.jsonl").exists()


@pytest.mark.parametrize(
    ("after_line_1", "message"),
    [
        (b"{not json\n", "line 2 is not a valid event"),
        (b'{"at":"2026-10-25T21:3', "line 2 is not a valid event"),
        (b"\n" + LINE_2.encode() + b"\n", "line 2 is not a valid event"),
        (b"\xff\xfe\n", "line 2 is not a valid event"),
        (LINE_2.replace('"seq":2', '"seq":2,"extra":1').encode(), "line 2 is not a valid event"),
        (LINE_2.replace("node_started", "launched").encode(), "line 2 is not a valid event"),
        (
            LINE_2.replace("21:30:01.250000Z", "21:30:01+02:00").encode(),
            "line 2 is not a valid event",
        ),
        (LINE_2.replace('"seq":2', '"seq":"2"').encode(), "line 2 is not a valid event"),
        (
            LINE_2.replace('"2026-10-25T21:30:01.250000Z"', "1792963801.25").encode(),
            "line 2 is not a valid event",
        ),
        (LINE_2.replace(RUN_A, RUN_B).encode(), "line 2 belongs to another run"),
        (LINE_2.replace('"seq":2', '"seq":3').encode(), "line 2 has seq 3, expected 2"),
    ],
)
def test_a_damaged_log_is_refused_with_its_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, after_line_1: bytes, message: str
) -> None:
    damaged = LINE_1.encode() + b"\n" + after_line_1
    (tmp_path / f"{RUN_A}.jsonl").write_bytes(damaged)
    log = EventLog(tmp_path)
    with pytest.raises(EventLogCorrupt) as raised:
        log.read(RUN_A)
    assert str(raised.value) == f"{RUN_A}.jsonl {message}"
    fixed_times(monkeypatch, "2026-10-25T21:40:00+00:00")
    with pytest.raises(EventLogCorrupt):
        log.append(RUN_A, EventKind.RUN_FINISHED)
    assert (tmp_path / f"{RUN_A}.jsonl").read_bytes() == damaged


def test_reading_a_run_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(RunNotFound) as raised:
        EventLog(tmp_path).read(RUN_A)
    assert str(raised.value) == f"no run {RUN_A}"


def test_runs_newest_first_then_by_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixed_times(
        monkeypatch,
        "2026-10-25T21:30:00+00:00",
        "2026-10-25T21:31:00.500+00:00",
        "2026-10-25T21:32:00+00:00",
        "2026-10-25T21:30:00+00:00",
    )
    log = EventLog(tmp_path)
    log.append(RUN_A, EventKind.RUN_STARTED)
    log.append(RUN_B, EventKind.RUN_STARTED)
    log.append(RUN_A, EventKind.RUN_FINISHED)
    log.append(RUN_C, EventKind.RUN_STARTED)
    (tmp_path / "notes.txt").write_text("not a run", encoding="utf-8")
    (tmp_path / "README.jsonl").write_text("not a run either", encoding="utf-8")
    assert log.runs() == [
        RunSummary(RUN_B, datetime(2026, 10, 25, 21, 31, 0, 500000, tzinfo=UTC), 1),
        RunSummary(RUN_C, datetime(2026, 10, 25, 21, 30, tzinfo=UTC), 1),
        RunSummary(RUN_A, datetime(2026, 10, 25, 21, 30, tzinfo=UTC), 2),
    ]


def test_runs_of_a_folder_not_made_yet(tmp_path: Path) -> None:
    assert EventLog(tmp_path / "runs").runs() == []
    assert not (tmp_path / "runs").exists()
