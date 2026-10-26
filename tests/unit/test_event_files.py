import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor.events import EventKind, EventLog
from tests.support import fixed_times

RUN_A = "0123456789abcdef0123456789abcdef"
LINE_1 = (
    '{"at":"2026-10-25T21:30:00.000000Z","kind":"run_started","node":null,'
    '"payload":{"b":[1,2.5,null,true],"request":"plan my week"},'
    '"run_id":"0123456789abcdef0123456789abcdef","seq":1}'
)


def test_an_existing_folder_keeps_its_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / "runs"
    folder.mkdir()
    os.chmod(folder, 0o755)
    fixed_times(monkeypatch, "2026-10-25T21:30:00+00:00")
    EventLog(folder).append(RUN_A, EventKind.RUN_STARTED)
    assert folder.stat().st_mode & 0o777 == 0o755
    assert (folder / f"{RUN_A}.jsonl").stat().st_mode & 0o777 == 0o600
    events = EventLog(folder).read(RUN_A)
    assert [(event.seq, event.kind) for event in events] == [(1, EventKind.RUN_STARTED)]


def test_a_valid_last_line_without_a_newline_is_read(tmp_path: Path) -> None:
    (tmp_path / f"{RUN_A}.jsonl").write_bytes(LINE_1.encode())
    events = EventLog(tmp_path).read(RUN_A)
    assert len(events) == 1
    assert events[0].run_id == RUN_A
    assert events[0].seq == 1
    assert events[0].kind is EventKind.RUN_STARTED
    assert events[0].node is None
    assert events[0].at == datetime(2026, 10, 25, 21, 30, tzinfo=UTC)
    assert events[0].payload == {"request": "plan my week", "b": [1, 2.5, None, True]}
