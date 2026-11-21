import os
import subprocess
import sys
from pathlib import Path

from conductor import events
from conductor.events import EventKind, EventLog

RUN = "0123456789abcdef0123456789abcdef"
CHILD = """
import sys
from pathlib import Path
from conductor.events import EventKind, EventLog
log = EventLog(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    log.append(sys.argv[3], EventKind.NODE_STARTED, node="child")
"""


def child(folder: Path, count: int) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(Path(events.__file__).parents[1])}
    command = [sys.executable, "-c", CHILD, str(folder), str(count), RUN]
    return subprocess.Popen(command, env=env)


def seqs(folder: Path) -> list[int]:
    return [event.seq for event in EventLog(folder).read(RUN)]


def test_an_append_after_another_process_wrote_continues_its_sequence(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    assert log.append(RUN, EventKind.RUN_STARTED).seq == 1
    assert child(tmp_path, 5).wait(60) == 0
    assert log.append(RUN, EventKind.RUN_FINISHED).seq == 7
    assert seqs(tmp_path) == [1, 2, 3, 4, 5, 6, 7]


def test_processes_appending_together_never_repeat_a_seq(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    log.append(RUN, EventKind.RUN_STARTED)
    children = [child(tmp_path, 15) for _ in range(3)]
    mine = [log.append(RUN, EventKind.NODE_STARTED).seq for _ in range(15)]
    assert [process.wait(60) for process in children] == [0, 0, 0]
    assert seqs(tmp_path) == list(range(1, 62))
    assert len(set(mine)) == 15
