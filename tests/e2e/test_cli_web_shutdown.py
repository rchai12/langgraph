import socket

import pytest
import uvicorn

from conductor.cli import main
from conductor.config import Settings
from tests.support import run

LEFT = ("1" * 32, "2" * 32)


class Served:
    """Stands in for the resumer, the page and the server that `conductor web` starts."""

    def __init__(self) -> None:
        self.resumers: list[object] = []
        self.handed: list[object] = []
        self.left: tuple[str, ...] = ()
        self.interrupt = False


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Served:
    chosen = Served()

    class FakeResumer:
        def __init__(self, settings: Settings) -> None:
            self.closes: list[tuple[tuple, dict]] = []
            chosen.resumers.append(self)

        def close(self, *args: object, **kwargs: object) -> tuple[str, ...]:
            self.closes.append((args, kwargs))
            return chosen.left

    def fake_create_app(settings: Settings, *, resumer: object = None) -> str:
        chosen.handed.append(resumer)
        return "the page"

    def fake_run(app: object, **options: object) -> None:
        if chosen.interrupt:
            raise KeyboardInterrupt

    monkeypatch.setattr(main, "Resumer", FakeResumer)
    monkeypatch.setattr(main, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    return chosen


@pytest.fixture
def port(monkeypatch: pytest.MonkeyPatch) -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    chosen = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(chosen))
    return chosen


def test_the_page_gets_one_resumer_that_is_closed(served: Served, port: int) -> None:
    result = run("web")
    assert (result.exit_code, result.stdout, result.stderr) == (
        0,
        f"Serving on http://127.0.0.1:{port}/\n",
        "",
    )
    [resumer] = served.resumers
    assert served.handed == [resumer]
    assert resumer.closes == [((), {})]


@pytest.mark.parametrize(("interrupt", "code"), [(False, 0), (True, 130)])
def test_runs_left_running_are_named_on_the_way_out(
    served: Served, port: int, interrupt: bool, code: int
) -> None:
    served.left = LEFT
    served.interrupt = interrupt
    result = run("web")
    assert (result.exit_code, result.stderr) == (
        code,
        f"the resume did not finish before shutdown: run {LEFT[0]}\n"
        f"the resume did not finish before shutdown: run {LEFT[1]}\n",
    )
    [resumer] = served.resumers
    assert resumer.closes == [((), {})]


def test_a_taken_port_starts_no_resumer(served: Served, monkeypatch: pytest.MonkeyPatch) -> None:
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(taken.getsockname()[1]))
    try:
        result = run("web")
    finally:
        taken.close()
    assert result.exit_code == 1
    assert (served.resumers, served.handed) == ([], [])
