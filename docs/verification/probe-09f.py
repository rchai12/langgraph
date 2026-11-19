"""Probe for Phase 9f: the background resumer's retention bound and bounded shutdown.

Run from the repository root with .venv/bin/python docs/verification/probe-09f.py.
The last line is FAILURES <n>. It replaces runtime.open_runtime and runtime.resume
with fakes, so no model, server or saved run is involved.
"""

import os
import random
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

failures = 0
rng = random.Random(9)


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
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables: written from the spec, never read from the code.
CAP = 100
STOPPING = "the server is stopping"
FIXED = "the resume failed"


def busy(run: str) -> str:
    return f"run {run} is busy"


class Oracle:
    """Failure messages, oldest first. A start forgets the run's message; a failure re-adds it."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.kept: dict[str, str] = {}
        self.dropped = 0

    def outcome(self, run: str, message: str | None) -> None:
        self.kept.pop(run, None)
        if message is not None:
            self.kept[run] = message
            while len(self.kept) > self.cap:
                del self.kept[next(iter(self.kept))]
                self.dropped += 1


def name(number: int) -> str:
    return f"{number:032x}"


# The oracle on known cases.
_known = Oracle(2)
for _run, _message in [("a", "x"), ("b", "y"), ("c", "z"), ("b", "w"), ("c", None)]:
    _known.outcome(_run, _message)
assert _known.kept == {"b": "w"}
_known.outcome("d", "v")
_known.outcome("e", "u")
assert list(_known.kept) == ["d", "e"] and _known.dropped == 2


class Boom(Exception):
    pass


class Script:
    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()
        self.calls = 0

    def resume(self, opened: object, run: str) -> None:
        self.calls += 1
        self.entered.release()
        outcome = self.outcomes.get(run, "ok")
        if outcome.startswith("wait"):
            self.release.wait(10)
        if outcome.endswith("fail"):
            raise _run_error(busy(run))
        if outcome == "boom":
            raise Boom("a detail that must not be shown")


def _run_error(message: str) -> Exception:
    from conductor.graph.supervisor import RunError

    return RunError(message)


def fresh() -> tuple[object, Script]:
    from conductor import runtime
    from conductor.config import get_settings
    from conductor.web.jobs import Resumer

    script = Script()

    @contextmanager
    def fake_open(settings: object) -> Iterator[object]:
        yield object()

    runtime.open_runtime = fake_open
    runtime.resume = script.resume
    return Resumer(get_settings()), script


def finish(resumer, script: Script, run: str, outcome: str) -> None:
    script.outcomes[run] = outcome
    resumer.start(run)
    resumer.join(run, timeout=10)


def hold(resumer, script: Script, run: str, outcome: str = "wait") -> bool:
    script.outcomes[run] = outcome
    resumer.start(run)
    return script.entered.acquire(timeout=10)


def check_random_steps() -> bool:
    resumer, script = fresh()
    oracle = Oracle(CAP)
    agree = True
    runs = [name(number) for number in range(150)]
    for _ in range(600):
        run = rng.choice(runs)
        outcome = rng.choice(["ok", "fail", "fail", "boom"])
        finish(resumer, script, run, outcome)
        oracle.outcome(run, {"ok": None, "fail": busy(run), "boom": FIXED}[outcome])
        agree &= resumer.error(run) == oracle.kept.get(run)
    agree &= all(resumer.error(run) == oracle.kept.get(run) for run in runs)
    agree &= resumer.retained() == (0, len(oracle.kept))
    return agree and script.calls == 600 and len(oracle.kept) == CAP and oracle.dropped > 0


def check_close_is_one_bound() -> bool:
    resumer, script = fresh()
    runs = [name(number) for number in (4, 3, 2, 1)]
    reached = all(hold(resumer, script, run) for run in runs)
    began = time.monotonic()
    left = resumer.close(timeout=1.0)
    spent = time.monotonic() - began
    script.release.set()
    return reached and left == tuple(sorted(runs)) and 0.9 <= spent < 2.5


def check_a_job_outliving_close() -> bool:
    resumer, script = fresh()
    run = name(7)
    reached = hold(resumer, script, run, "waitfail")
    left = resumer.close(timeout=0.05)
    script.release.set()
    resumer.join(run, timeout=10)
    return (
        reached
        and left == (run,)
        and (resumer.running(run), resumer.error(run)) == (False, busy(run))
        and resumer.retained() == (0, 1)
    )


def check_refused_starts_are_capped() -> bool:
    resumer, script = fresh()
    for number in range(CAP):
        finish(resumer, script, name(number), "fail")
    resumer.close(timeout=0.05)
    resumer.start(name(0))
    resumer.start(name(CAP))
    return (
        script.calls == CAP
        and resumer.retained() == (0, CAP)
        and (resumer.error(name(0)), resumer.error(name(CAP))) == (STOPPING, STOPPING)
        and resumer.error(name(1)) is None
        and resumer.error(name(2)) == busy(name(2))
    )


def check_concurrent_failures() -> bool:
    resumer, script = fresh()
    runs = [name(200 + number) for number in range(30)]
    for run in runs:
        script.outcomes[run] = "fail"
    gate = threading.Barrier(len(runs))

    def start(run: str) -> None:
        gate.wait(10)
        resumer.start(run)

    starters = [threading.Thread(target=start, args=(run,)) for run in runs]
    for starter in starters:
        starter.start()
    for starter in starters:
        starter.join(10)
    for run in runs:
        resumer.join(run, timeout=10)
    return resumer.retained() == (0, len(runs)) and all(
        resumer.error(run) == busy(run) for run in runs
    )


section("600 random resumes keep exactly the newest 100 failures", check_random_steps)
section("close waits once for all running jobs, not once per job", check_close_is_one_bound)
section("a job still running at close records its outcome later", check_a_job_outliving_close)
section("a start refused after close counts against the bound", check_refused_starts_are_capped)
section("30 concurrent failures are all kept", check_concurrent_failures)

print(f"FAILURES {failures}")
