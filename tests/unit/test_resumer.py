import threading
from contextlib import contextmanager

from conductor import runtime
from conductor.config import get_settings
from conductor.graph.supervisor import RunError
from conductor.mcp_client.check import ToolCheckFailed
from conductor.web.jobs import Resumer

RUN = "a" * 32


@contextmanager
def _open(settings: object, *, model: object = None) -> object:
    yield None


def test_a_second_start_waits_and_the_thread_is_not_a_daemon(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[tuple[str, bool]] = []

    def resume(opened: object, run_id: str) -> None:
        calls.append((run_id, threading.current_thread().daemon))
        started.set()
        release.wait(5)

    monkeypatch.setattr(runtime, "open_runtime", _open)
    monkeypatch.setattr(runtime, "resume", resume)
    resumer = Resumer(get_settings())
    try:
        resumer.start(RUN)
        assert started.wait(5)
        resumer.start(RUN)
        assert calls == [(RUN, False)]
        assert resumer.running(RUN) is True
        assert resumer.running("b" * 32) is False
        assert resumer.error("b" * 32) is None
        resumer.join("b" * 32)
    finally:
        release.set()
        resumer.join(RUN, timeout=5)
    assert resumer.running(RUN) is False


def test_other_exceptions_are_kept_as_a_fixed_line_and_a_tool_check_is_its_text(
    monkeypatch,
) -> None:
    def boom(opened: object, run_id: str) -> None:
        raise RuntimeError("SYNTHETIC-SECRET")

    monkeypatch.setattr(runtime, "open_runtime", _open)
    monkeypatch.setattr(runtime, "resume", boom)
    resumer = Resumer(get_settings())
    resumer.start(RUN)
    resumer.join(RUN, timeout=5)
    assert resumer.error(RUN) == "the resume failed"
    assert "SYNTHETIC-SECRET" not in str(resumer.error(RUN))

    started = threading.Event()
    release = threading.Event()

    def checked(opened: object, run_id: str) -> None:
        started.set()
        release.wait(5)
        raise ToolCheckFailed(())

    monkeypatch.setattr(runtime, "resume", checked)
    try:
        resumer.start(RUN)
        assert started.wait(5)
        assert resumer.error(RUN) is None
    finally:
        release.set()
        resumer.join(RUN, timeout=5)
    assert resumer.error(RUN) == "the tool check failed"


def test_a_run_error_is_kept_and_the_next_start_clears_it(monkeypatch) -> None:
    def missing(opened: object, run_id: str) -> None:
        raise RunError(f"no run {run_id}")

    monkeypatch.setattr(runtime, "open_runtime", _open)
    monkeypatch.setattr(runtime, "resume", missing)
    resumer = Resumer(get_settings())
    resumer.start(RUN)
    resumer.join(RUN, timeout=5)
    assert resumer.error(RUN) == f"no run {RUN}"

    started = threading.Event()
    release = threading.Event()

    def wait(opened: object, run_id: str) -> None:
        started.set()
        release.wait(5)

    monkeypatch.setattr(runtime, "resume", wait)
    try:
        resumer.start(RUN)
        assert started.wait(5)
        assert resumer.error(RUN) is None
    finally:
        release.set()
        resumer.join(RUN, timeout=5)
