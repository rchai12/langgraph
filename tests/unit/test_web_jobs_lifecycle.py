import inspect
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from conductor import runtime
from conductor.config import Settings, get_settings
from conductor.graph.supervisor import RunError
from conductor.web import jobs
from conductor.web.jobs import Resumer


class Boom(Exception):
    pass


def run_id(number: int) -> str:
    return f"{number:032x}"


class Script:
    """What the fake `runtime.resume` does for each run: 'ok' (default), 'fail', 'boom', 'wait'."""

    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}
        self.calls: list[str] = []
        self.daemon: list[bool] = []
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()

    def resume(self, opened: object, run_id: str) -> None:
        self.calls.append(run_id)
        self.daemon.append(threading.current_thread().daemon)
        self.entered.release()
        outcome = self.outcomes.get(run_id, "ok")
        if outcome == "wait":
            self.release.wait(10)
        elif outcome == "fail":
            raise RunError(f"run {run_id} is busy")
        elif outcome == "boom":
            raise Boom("a detail that must not be shown")


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    chosen = Script()

    @contextmanager
    def fake_open(settings: Settings) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(runtime, "open_runtime", fake_open)
    monkeypatch.setattr(runtime, "resume", chosen.resume)
    yield chosen
    chosen.release.set()


def finish(resumer: Resumer, script: Script, number: int, outcome: str) -> None:
    script.outcomes[run_id(number)] = outcome
    resumer.start(run_id(number))
    resumer.join(run_id(number), timeout=10)


def hold(resumer: Resumer, script: Script, number: int) -> None:
    script.outcomes[run_id(number)] = "wait"
    resumer.start(run_id(number))
    assert script.entered.acquire(timeout=10)


def test_the_limits_and_messages() -> None:
    assert (
        jobs.MAX_FAILURES,
        jobs.SHUTDOWN_SECONDS,
        jobs.STOPPING_MESSAGE,
        jobs.UNFINISHED_MESSAGE,
    ) == (100, 10.0, "the server is stopping", "the resume did not finish before shutdown")
    assert inspect.signature(Resumer.close).parameters["timeout"].default == 10.0


def test_a_worker_is_a_daemon_thread(script: Script) -> None:
    resumer = Resumer(get_settings())
    finish(resumer, script, 1, "ok")
    assert script.daemon == [True]


def test_finished_resumes_are_forgotten(script: Script) -> None:
    resumer = Resumer(get_settings())
    for number in range(150):
        finish(resumer, script, number, "ok")
    assert resumer.retained() == (0, 0)
    assert (resumer.running(run_id(0)), resumer.error(run_id(0))) == (False, None)


@pytest.mark.parametrize(
    ("outcome", "message"),
    [("fail", f"run {run_id(1)} is busy"), ("boom", "the resume failed")],
)
def test_a_failure_is_kept(script: Script, outcome: str, message: str) -> None:
    resumer = Resumer(get_settings())
    finish(resumer, script, 1, outcome)
    assert (resumer.running(run_id(1)), resumer.error(run_id(1))) == (False, message)
    assert resumer.retained() == (0, 1)


def test_failures_are_capped_oldest_first(script: Script) -> None:
    resumer = Resumer(get_settings())
    for number in range(101):
        finish(resumer, script, number, "fail")
    assert resumer.retained() == (0, 100)
    assert [resumer.error(run_id(number)) is None for number in (0, 1, 100)] == [
        True,
        False,
        False,
    ]


def test_a_repeated_failure_is_the_newest(script: Script) -> None:
    resumer = Resumer(get_settings())
    for number in [*range(100), 0, 100]:
        finish(resumer, script, number, "fail")
    assert resumer.retained() == (0, 100)
    assert [resumer.error(run_id(number)) is None for number in (0, 1, 2)] == [
        False,
        True,
        False,
    ]


def test_starting_again_clears_the_last_failure(script: Script) -> None:
    resumer = Resumer(get_settings())
    finish(resumer, script, 1, "fail")
    hold(resumer, script, 1)
    assert (resumer.running(run_id(1)), resumer.error(run_id(1))) == (True, None)
    script.release.set()
    resumer.join(run_id(1), timeout=10)
    assert (resumer.running(run_id(1)), resumer.error(run_id(1))) == (False, None)
    assert resumer.retained() == (0, 0)


def test_an_active_run_is_not_started_twice(script: Script) -> None:
    resumer = Resumer(get_settings())
    hold(resumer, script, 1)
    resumer.start(run_id(1))
    assert (script.calls, resumer.retained()) == ([run_id(1)], (1, 0))
    script.release.set()
    resumer.join(run_id(1), timeout=10)
    assert (script.calls, resumer.retained()) == ([run_id(1)], (0, 0))


def test_a_running_job_is_never_dropped(script: Script) -> None:
    resumer = Resumer(get_settings())
    hold(resumer, script, 0)
    for number in range(1, 102):
        finish(resumer, script, number, "fail")
    assert (resumer.running(run_id(0)), resumer.retained()) == (True, (1, 100))
    script.release.set()
    resumer.join(run_id(0), timeout=10)
    assert (resumer.running(run_id(0)), resumer.retained()) == (False, (0, 100))


def test_close_waits_for_a_job_that_finishes(script: Script) -> None:
    resumer = Resumer(get_settings())
    hold(resumer, script, 1)
    timer = threading.Timer(0.2, script.release.set)
    timer.start()
    assert resumer.close(timeout=10) == ()
    assert (resumer.running(run_id(1)), resumer.retained()) == (False, (0, 0))
    timer.join()


def test_close_names_the_runs_still_running(script: Script) -> None:
    resumer = Resumer(get_settings())
    hold(resumer, script, 2)
    hold(resumer, script, 1)
    assert resumer.close(timeout=0.1) == (run_id(1), run_id(2))
    assert resumer.retained() == (2, 0)


def test_close_with_nothing_running_returns_at_once(script: Script) -> None:
    resumer = Resumer(get_settings())
    finish(resumer, script, 1, "ok")
    began = time.monotonic()
    assert resumer.close() == ()
    assert time.monotonic() - began < 5


def test_a_start_after_close_is_refused(script: Script) -> None:
    resumer = Resumer(get_settings())
    resumer.close(timeout=0.1)
    resumer.start(run_id(1))
    assert script.calls == []
    assert (resumer.running(run_id(1)), resumer.error(run_id(1))) == (
        False,
        "the server is stopping",
    )
    assert resumer.retained() == (0, 1)
