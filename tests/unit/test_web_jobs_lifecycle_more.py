import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from conductor import runtime
from conductor.config import Settings, get_settings
from conductor.graph.supervisor import RunError
from conductor.mcp_client.check import CheckProblem, ToolCheckFailed
from conductor.web.jobs import STOPPING_MESSAGE, Resumer


def run_id(number: int) -> str:
    return f"{number:032x}"


class Script:
    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}
        self.calls: list[str] = []
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()

    def resume(self, opened: object, chosen: str) -> None:
        self.calls.append(chosen)
        self.entered.release()
        outcome = self.outcomes.get(chosen, "ok")
        if outcome == "wait":
            self.release.wait(10)
        elif outcome == "fail":
            raise RunError(f"run {chosen} is busy")
        elif outcome == "late":
            self.release.wait(10)
            raise RunError(f"run {chosen} is busy")
        elif outcome == "check":
            raise ToolCheckFailed((CheckProblem("ledger", "the balance tool is absent"),))


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


def test_a_tool_check_failure_is_kept_by_its_text(script: Script) -> None:
    script.outcomes[run_id(1)] = "check"
    resumer = Resumer(get_settings())
    resumer.start(run_id(1))
    resumer.join(run_id(1), timeout=10)
    assert resumer.error(run_id(1)) == "the tool check failed"
    assert resumer.retained() == (0, 1)
    assert "the balance tool is absent" not in str(resumer.error(run_id(1)))


def test_a_job_held_at_the_deadline_keeps_its_later_failure(script: Script) -> None:
    script.outcomes[run_id(1)] = "late"
    resumer = Resumer(get_settings())
    resumer.start(run_id(1))
    assert script.entered.acquire(timeout=10)
    assert resumer.close(timeout=0.05) == (run_id(1),)
    script.release.set()
    resumer.join(run_id(1), timeout=10)
    assert resumer.error(run_id(1)) == f"run {run_id(1)} is busy"
    assert resumer.retained() == (0, 1)


def test_a_start_after_close_replaces_the_old_failure(script: Script) -> None:
    script.outcomes[run_id(1)] = "fail"
    resumer = Resumer(get_settings())
    resumer.start(run_id(1))
    resumer.join(run_id(1), timeout=10)
    assert resumer.error(run_id(1)) == f"run {run_id(1)} is busy"
    assert resumer.close() == ()
    resumer.start(run_id(1))
    assert script.calls == [run_id(1)]
    assert resumer.error(run_id(1)) == STOPPING_MESSAGE
    assert resumer.retained() == (0, 1)
