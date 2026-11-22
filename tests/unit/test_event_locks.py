import fcntl
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, events
from conductor.events import EventKind, EventLog

RUN = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
MOMENT = datetime(2026, 10, 25, 21, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: MOMENT)


def add(log: EventLog, run: str = RUN) -> int:
    return log.append(run, EventKind.NODE_STARTED, node="route").seq


def test_a_failed_write_releases_the_file_and_keeps_the_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = EventLog(tmp_path)
    assert add(log) == 1
    real = os.write

    def failing(_descriptor: int, _data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(os, "write", failing)
    with pytest.raises(OSError):
        add(log)
    monkeypatch.setattr(os, "write", real)
    descriptor = os.open(tmp_path / f"{RUN}.jsonl", os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)
    assert add(log) == 2


def test_the_first_append_parses_every_line_and_the_second_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = EventLog(tmp_path)
    for _ in range(500):
        add(writer)
    calls: list[int] = []
    real = events._parse_line

    def counting(run_id: str, number: int, raw: bytes) -> events.Event:
        calls.append(number)
        return real(run_id, number, raw)

    monkeypatch.setattr(events, "_parse_line", counting)
    fresh = EventLog(tmp_path)
    assert add(fresh) == 501
    assert len(calls) == 500
    calls.clear()
    assert add(fresh) == 502
    assert calls == []


def test_two_runs_are_kept_apart(tmp_path: Path) -> None:
    mine = EventLog(tmp_path)
    assert (add(mine), add(mine, OTHER)) == (1, 1)
    other = EventLog(tmp_path)
    add(other)
    add(other)
    assert add(mine, OTHER) == 2
    assert add(mine) == 4
