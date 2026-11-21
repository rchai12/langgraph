import itertools
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
import typer

from conductor import clock, ids, runtime
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run


def ID(n: int) -> str:
    return f"{n:032x}"


NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    queue: list[tuple[str, str]] = []
    real = runtime.open_runtime

    @contextmanager
    def scripted(settings, *, model=None):
        answers = [ScriptedReply(point, ModelReply(content=text)) for point, text in queue]
        queue.clear()
        with real(settings, model=ScriptedModel(answers)) as opened:
            yield opened

    monkeypatch.setattr(runtime, "open_runtime", scripted)
    return queue


def test_bad_edit_args_open_no_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime opened")

    monkeypatch.setattr(runtime, "open_runtime", refuse)
    result = run("approvals", "edit", "a" * 32, "--args", "[1]")
    assert (result.exit_code, result.stderr) == (1, "Error: --args must be a JSON object\n")


@pytest.fixture
def no_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    def asked(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("confirmation asked")

    monkeypatch.setattr(typer, "confirm", asked)


@pytest.mark.usefixtures("no_confirm")
def test_reject_decides_without_asking(
    replies: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    result = run("approvals", "reject", ID(4), "--note", "not now")
    assert (result.exit_code, result.stdout) == (
        0,
        f"Rejected {ID(4)}.\nrun {ID(2)}  rejected\nnote: not now\n",
    )


@pytest.mark.usefixtures("no_confirm")
def test_cancel_decides_without_asking() -> None:
    run("ask", "Say hi back to me")
    result = run("escalations", "cancel", ID(3))
    assert (result.exit_code, result.stdout) == (
        0,
        f"Cancelled {ID(3)}.\nrun {ID(2)}  cancelled\n",
    )
