"""Probe for Phase 9p: several event logs on one run never repeat a seq, read only new lines,
and refuse a damaged file exactly where the oracle says.

The oracle is a table of what each log has seen: the file is a list of lines, and each log knows
how many of them it has read or written. An append takes the next seq and parses only the lines
the log has not seen. Damage is added from outside (a bad line, an unfinished line, a line rewritten
in place, the file cut short), and the oracle says which logs must refuse and with which message.
Run from the repository root with .venv/bin/python docs/verification/probe-09p.py. The last line is
FAILURES <n>.
"""

import os
import random
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from conductor import clock, events
from conductor.events import EventKind, EventLog, EventLogCorrupt

failures = 0
rng = random.Random(16)
RUN = "0123456789abcdef0123456789abcdef"
SCHEDULES = 300
DAMAGED = 200


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def section(label: str, body: Callable[[], bool]) -> None:
    try:
        ok = body()
    except Exception as error:  # noqa: BLE001
        print(f"     {label}: raised {type(error).__name__}")
        ok = False
    check(label, ok)


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
clock.now = lambda: datetime(2026, 10, 25, 21, 30, tzinfo=UTC)

parsed = [0]
real_parse = events._parse_line


def counting(run_id: str, number: int, raw: bytes):
    parsed[0] += 1
    return real_parse(run_id, number, raw)


events._parse_line = counting


def line(seq: int) -> bytes:
    return (
        '{"at":"2026-10-25T21:30:00.000000Z","kind":"node_started","node":"route","payload":{},'
        f'"run_id":"{RUN}","seq":{seq}}}\n'
    ).encode()


class Model:
    """The file as a number of good lines, and how many of them each log has seen."""

    def __init__(self, logs: int) -> None:
        self.lines = 0
        self.seen = [0] * logs

    def append(self, which: int) -> tuple[int, int]:
        """The seq this log's append gets and how many lines it parses."""
        new = self.lines - self.seen[which]
        self.lines += 1
        self.seen[which] = self.lines
        return self.lines, new


# The oracle on known cases.
known = Model(2)
assert known.append(0) == (1, 0) and known.append(1) == (2, 1) and known.append(0) == (3, 1)
assert known.append(0) == (4, 0) and known.seen == [4, 2]
assert line(2).endswith(b'"seq":2}\n')


def appended(log: EventLog) -> tuple[int, int]:
    parsed[0] = 0
    seq = log.append(RUN, EventKind.NODE_STARTED, node="route").seq
    return seq, parsed[0]


def play(folder: Path, model: Model, logs: list[EventLog], steps: int) -> tuple[bool, bool]:
    seqs_ok = counts_ok = True
    for _ in range(steps):
        which = rng.randrange(len(logs))
        want_seq, want_parsed = model.append(which)
        got_seq, got_parsed = appended(logs[which])
        seqs_ok &= got_seq == want_seq
        counts_ok &= got_parsed == want_parsed
    return seqs_ok, counts_ok


def whole(folder: Path, count: int) -> bool:
    return [event.seq for event in EventLog(folder).read(RUN)] == list(range(1, count + 1))


results = {"seqs": True, "counts": True, "read": True, "done": False}


def schedules() -> None:
    for _ in range(SCHEDULES):
        folder = Path(tempfile.mkdtemp())
        logs = [EventLog(folder) for _ in range(rng.randint(2, 4))]
        model = Model(len(logs))
        seqs_ok, counts_ok = play(folder, model, logs, rng.randint(1, 40))
        results["seqs"] &= seqs_ok
        results["counts"] &= counts_ok
        results["read"] &= whole(folder, model.lines)
    results["done"] = True


def run_schedules() -> bool:
    schedules()
    return results["seqs"] and results["read"]


reach = {"bad": 0, "unfinished": 0, "rewritten": 0, "cut": 0, "refused": 0, "continued": 0}


def damage(path: Path, model: Model, kind: str) -> Callable[[int], tuple]:
    """Damage the file and return the oracle for the next append by a log."""
    first = len(model.seen)
    if kind == "bad":
        with path.open("ab") as handle:
            handle.write(b"{not json\n")
        number = model.lines + 1
        return lambda which: ("refused", f"line {number} is not a valid event")
    if kind == "unfinished":
        with path.open("ab") as handle:
            handle.write(line(model.lines + 1).removesuffix(b"\n"))
        number = model.lines + 1
        return lambda which: ("refused", f"line {number} is not finished")
    if kind == "rewritten":
        number = rng.randint(1, model.lines)
        pieces = path.read_bytes().splitlines(keepends=True)
        pieces[number - 1] = b"x" + pieces[number - 1][1:]
        path.write_bytes(b"".join(pieces))

        def rewritten(which: int) -> tuple:
            seen = model.seen[which] if which < first else 0
            if seen >= number:
                return ("continued", model.lines + 1)
            return ("refused", f"line {number} is not a valid event")

        return rewritten
    kept = rng.randint(0, model.lines - 1)
    pieces = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(pieces[:kept]))

    def cut(which: int) -> tuple:
        seen = model.seen[which] if which < first else 0
        if seen > kept:
            return ("refused", "is shorter than when it was last read")
        return ("continued", kept + 1)

    return cut


def run_damaged() -> bool:
    agree = True
    for _ in range(DAMAGED):
        folder = Path(tempfile.mkdtemp())
        path = folder / f"{RUN}.jsonl"
        logs = [EventLog(folder) for _ in range(rng.randint(2, 3))]
        model = Model(len(logs))
        play(folder, model, logs, rng.randint(2, 12))
        kind = rng.choice(["bad", "unfinished", "rewritten", "cut"])
        reach[kind] += 1
        oracle = damage(path, model, kind)
        logs.append(EventLog(folder))
        order = list(range(len(logs)))
        rng.shuffle(order)
        if kind in ("cut", "rewritten"):
            order = order[:1]
        for which in order:
            want = oracle(which)
            before = path.read_bytes()
            try:
                got = ("continued", logs[which].append(RUN, EventKind.NODE_STARTED).seq)
            except EventLogCorrupt as error:
                got = ("refused", str(error).removeprefix(f"{RUN}.jsonl "))
                agree &= path.read_bytes() == before
            reach[want[0]] += 1
            agree &= got == want
    assert min(reach.values()) >= 20, reach
    return agree


section(f"{SCHEDULES} schedules of 2 to 4 logs: every append gets the next seq", run_schedules)
section(
    "every append parses only the lines its own log has not seen",
    lambda: results["done"] and results["counts"],
)
section(
    f"{DAMAGED} damaged files: each append refuses or continues as the oracle says", run_damaged
)
print(f"     reach {reach}")

print(f"FAILURES {failures}")
