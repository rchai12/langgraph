import fcntl
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.events import EventKind, EventLog, EventLogCorrupt

RUN = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
MOMENT = datetime(2026, 10, 25, 21, 30, tzinfo=UTC)
LINE_2 = (
    '{"at":"2026-10-25T21:30:00.000000Z","kind":"node_started","node":"route","payload":{},'
    f'"run_id":"{RUN}","seq":2}}'
)
BLOCKED = 0.3


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: MOMENT)


def file_of(folder: Path) -> Path:
    return folder / f"{RUN}.jsonl"


def seqs(folder: Path) -> list[int]:
    return [event.seq for event in EventLog(folder).read(RUN)]


def started(folder: Path, count: int = 1) -> EventLog:
    log = EventLog(folder)
    for _ in range(count):
        log.append(RUN, EventKind.NODE_STARTED, node="route")
    return log


def while_locked(folder: Path, mode: int, work: Callable[[], object]) -> tuple[bool, object]:
    """Hold a lock of this mode on the run's file, start work in a thread, then release it.

    Returns whether the work was still waiting while the lock was held, and its result.
    """
    found: list[object] = []
    descriptor = os.open(file_of(folder), os.O_RDONLY)
    try:
        fcntl.flock(descriptor, mode)
        thread = threading.Thread(target=lambda: found.append(work()))
        thread.start()
        thread.join(BLOCKED)
        waiting = thread.is_alive()
    finally:
        os.close(descriptor)
    thread.join(10)
    assert not thread.is_alive()
    return waiting, found[0]


def free(folder: Path) -> bool:
    descriptor = os.open(file_of(folder), os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(descriptor)
    return True


def test_two_logs_on_one_run_take_turns_without_repeating_a_seq(tmp_path: Path) -> None:
    first, second = EventLog(tmp_path), EventLog(tmp_path)
    order = [first, second, first, first, second, second, first]
    returned = [log.append(RUN, EventKind.NODE_STARTED).seq for log in order]
    assert (returned, seqs(tmp_path)) == ([1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 7])


def test_threads_with_their_own_logs_never_repeat_a_seq(tmp_path: Path) -> None:
    barrier = threading.Barrier(6)
    returned: list[int] = []

    def work() -> None:
        log = EventLog(tmp_path)
        barrier.wait()
        for _ in range(20):
            returned.append(log.append(RUN, EventKind.NODE_STARTED).seq)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert (sorted(returned), seqs(tmp_path)) == (list(range(1, 121)), list(range(1, 121)))


@pytest.mark.parametrize("mode", [fcntl.LOCK_EX, fcntl.LOCK_SH], ids=["writer", "reader"])
def test_an_append_waits_for_the_file(tmp_path: Path, mode: int) -> None:
    log = started(tmp_path)
    waiting, seq = while_locked(tmp_path, mode, lambda: log.append(RUN, EventKind.RUN_FINISHED).seq)
    assert (waiting, seq, seqs(tmp_path)) == (True, 2, [1, 2])


def test_a_read_waits_for_an_append_in_progress(tmp_path: Path) -> None:
    started(tmp_path)
    waiting, found = while_locked(tmp_path, fcntl.LOCK_EX, lambda: EventLog(tmp_path).read(RUN))
    assert (waiting, [event.seq for event in found]) == (True, [1])


def test_readers_do_not_wait_for_each_other(tmp_path: Path) -> None:
    started(tmp_path)
    waiting, found = while_locked(tmp_path, fcntl.LOCK_SH, lambda: EventLog(tmp_path).read(RUN))
    assert (waiting, [event.seq for event in found]) == (False, [1])


def test_a_refused_payload_releases_the_file(tmp_path: Path) -> None:
    log = started(tmp_path)
    with pytest.raises(ValueError):
        log.append(RUN, EventKind.TOOL_RESULT, payload={"value": float("nan")})
    assert (free(tmp_path), seqs(tmp_path)) == (True, [1])


def test_a_corrupt_file_releases_the_file(tmp_path: Path) -> None:
    file_of(tmp_path).write_bytes(b"{not json\n")
    with pytest.raises(EventLogCorrupt):
        EventLog(tmp_path).append(RUN, EventKind.NODE_STARTED)
    assert (free(tmp_path), file_of(tmp_path).read_bytes()) == (True, b"{not json\n")


def test_a_log_reads_only_the_lines_it_has_not_seen(tmp_path: Path) -> None:
    mine = started(tmp_path, 2)
    started(tmp_path)
    data = file_of(tmp_path).read_bytes()
    file_of(tmp_path).write_bytes(b"x" + data[1:])
    assert mine.append(RUN, EventKind.RUN_FINISHED).seq == 4
    with pytest.raises(EventLogCorrupt) as raised:
        EventLog(tmp_path).append(RUN, EventKind.RUN_FINISHED)
    assert str(raised.value) == f"{RUN}.jsonl line 1 is not a valid event"


@pytest.mark.parametrize(
    ("added", "message"),
    [
        (b"{not json\n", "line 2 is not a valid event"),
        (LINE_2.replace(RUN, OTHER).encode() + b"\n", "line 2 belongs to another run"),
        (LINE_2.replace('"seq":2', '"seq":3').encode() + b"\n", "line 2 has seq 3, expected 2"),
        (LINE_2.encode(), "line 2 is not finished"),
        (LINE_2.encode() + b"\n{not", "line 3 is not finished"),
    ],
    ids=["not json", "other run", "wrong seq", "unfinished", "unfinished after good"],
)
def test_lines_another_writer_added_are_checked(tmp_path: Path, added: bytes, message: str) -> None:
    log = started(tmp_path)
    with file_of(tmp_path).open("ab") as handle:
        handle.write(added)
    before = file_of(tmp_path).read_bytes()
    with pytest.raises(EventLogCorrupt) as raised:
        log.append(RUN, EventKind.RUN_FINISHED)
    assert (str(raised.value), file_of(tmp_path).read_bytes()) == (f"{RUN}.jsonl {message}", before)


def test_a_file_that_shrank_is_corrupt(tmp_path: Path) -> None:
    log = started(tmp_path, 3)
    kept = b"".join(file_of(tmp_path).read_bytes().splitlines(keepends=True)[:2])
    file_of(tmp_path).write_bytes(kept)
    with pytest.raises(EventLogCorrupt) as raised:
        log.append(RUN, EventKind.RUN_FINISHED)
    assert (str(raised.value), file_of(tmp_path).read_bytes()) == (
        f"{RUN}.jsonl is shorter than when it was last read",
        kept,
    )
    assert EventLog(tmp_path).append(RUN, EventKind.RUN_FINISHED).seq == 3


def test_an_unfinished_last_line_is_refused_by_a_new_log(tmp_path: Path) -> None:
    started(tmp_path)
    data = file_of(tmp_path).read_bytes().removesuffix(b"\n")
    file_of(tmp_path).write_bytes(data)
    with pytest.raises(EventLogCorrupt) as raised:
        EventLog(tmp_path).append(RUN, EventKind.RUN_FINISHED)
    assert (str(raised.value), file_of(tmp_path).read_bytes()) == (
        f"{RUN}.jsonl line 1 is not finished",
        data,
    )


def test_an_existing_empty_file_starts_at_one(tmp_path: Path) -> None:
    file_of(tmp_path).write_bytes(b"")
    assert EventLog(tmp_path).append(RUN, EventKind.RUN_STARTED).seq == 1
