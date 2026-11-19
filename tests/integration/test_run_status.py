import itertools
from datetime import UTC, datetime

import pytest

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import answer_escalation, decide_approval
from conductor.graph.supervisor import RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError

NOTE = '{"steps":[{"action":"note","args":{"title":"Milk"}}]}'
ECHO = '{"steps":[{"action":"echo","args":{"text":"hi"}}]}'
REPLY = '{"reply":"Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def model(*rows: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(point, ModelReply(content=text)) for point, text in rows])


def forbid_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("status read constructed execution services")

    for name in (
        "open_runtime",
        "build_graph",
        "OllamaModel",
        "Store",
        "EventLog",
        "Registry",
        "DomainRunner",
    ):
        monkeypatch.setattr(runtime, name, forbidden)
    monkeypatch.setattr(ids, "new_id", forbidden)


def test_waiting_status_uses_only_checkpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
        expected = runtime.ask(opened, "demo: note Milk")
        opened.store.acquire(expected.run_id, "e" * 32)
    before = settings.checkpoints_path.read_bytes()
    forbid_execution(monkeypatch)
    for _ in range(12):
        assert runtime.read_state(settings, expected.run_id) == expected
    assert settings.checkpoints_path.read_bytes() == before


@pytest.mark.parametrize("terminal", ["done", "rejected", "cancelled"])
def test_terminal_status_survives_closed_runtime(terminal: str) -> None:
    settings = get_settings()
    if terminal == "done":
        with runtime.open_runtime(
            settings, model=model(("plan", ECHO), ("answer", REPLY))
        ) as opened:
            expected = runtime.ask(opened, "demo: say hi")
    elif terminal == "rejected":
        with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
            waiting = runtime.ask(opened, "demo: note Milk")
            decide_approval(
                opened.store,
                opened.registry,
                waiting.approval_id,
                "reject",
                channel="terminal",
                decided_by="owner",
                note="not today",
            )
            expected = runtime.resume(opened, waiting.run_id)
    else:
        with runtime.open_runtime(settings, model=model(("plan", '{"steps":[]}'))) as opened:
            waiting = runtime.ask(opened, "demo: do something")
            answer_escalation(
                opened.store,
                waiting.escalation_id,
                "cancel",
                channel="terminal",
                decided_by="owner",
            )
            expected = runtime.resume(opened, waiting.run_id)
    assert runtime.read_state(settings, expected.run_id) == expected
    assert expected.status == terminal


def test_missing_database_creates_nothing() -> None:
    settings = get_settings()
    with pytest.raises(RunError, match="^no run " + "f" * 32 + "$"):
        runtime.read_state(settings, "f" * 32)
    assert not settings.data_dir.exists()


def test_missing_run_leaves_existing_database_unchanged() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
        runtime.ask(opened, "demo: note Milk")
    before = settings.checkpoints_path.read_bytes()
    with pytest.raises(RunError, match="^no run " + "f" * 32 + "$"):
        runtime.read_state(settings, "f" * 32)
    assert settings.checkpoints_path.read_bytes() == before


def test_stopped_status_matches_the_execution_reader() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model()) as opened:
        with pytest.raises(ScriptError):
            runtime.ask(opened, "demo: say hi")
        [run] = opened.log.runs()
        expected = runtime.state(opened, run.run_id)
    assert expected == RunState(run.run_id, "stopped", stopped_at="plan")
    assert runtime.read_state(settings, run.run_id) == expected


@pytest.mark.parametrize("contents", [b"not a sqlite database", b""])
def test_unreadable_checkpoint_database_is_safely_refused(contents: bytes) -> None:
    settings = get_settings()
    settings.data_dir.mkdir()
    settings.checkpoints_path.write_bytes(contents)
    with pytest.raises(RunError) as raised:
        runtime.read_state(settings, "f" * 32)
    assert type(raised.value).__name__ == "RunStateUnavailable"
    assert str(raised.value) == f"run {'f' * 32} state is not available"
    assert settings.checkpoints_path.read_bytes() == contents
