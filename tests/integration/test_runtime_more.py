import itertools
import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, domains, ids
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.graph.supervisor import RunError, StepFailed
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.registry import Action, Domain
from conductor.runtime import DemoRunner, NoRunner, ask, open_runtime, resume, state

START = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
NOW = [START]
OTHER = "9" * 32
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
LAB = Domain(
    name="lab",
    description="A domain used only by this test.",
    actions=(
        Action(
            "ping",
            "Answer a ping.",
            "tool",
            "ping",
            "read",
            demo.EchoArgs,
            demo.EchoResult,
        ),
    ),
)


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    NOW[0] = START
    monkeypatch.setattr(clock, "now", lambda: NOW[0])
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def reply(point: str, content: str) -> ScriptedReply:
    return ScriptedReply(point, ModelReply(content=content))


def leases(path: Path) -> list[tuple[str, str]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT thread_id, holder FROM leases").fetchall()
    finally:
        connection.close()


def test_private_files_are_kept_and_the_connection_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    previous = os.umask(0o022)
    try:
        model = ScriptedModel([reply("plan", NOTE_PLAN)])
        with open_runtime(get_settings(), model=model) as runtime:
            data = get_settings().data_dir
            database = data / "checkpoints.db"
            assert (mode(data), mode(database)) == (0o700, 0o600)
            waiting = ask(runtime, "demo: note Milk")
            connection = runtime.graph.checkpointer.conn
            inode = database.stat().st_ino
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        with open_runtime(get_settings(), model=ScriptedModel([])) as again:
            assert database.stat().st_ino == inode
            assert state(again, waiting.run_id) == waiting
        with pytest.raises(RuntimeError, match="boom"):
            with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
                connection = runtime.graph.checkpointer.conn
                raise RuntimeError("boom")
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
    finally:
        os.umask(previous)


def test_domains_and_the_runner_follow_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
        assert runtime.registry.names == ("lab",)
        with pytest.raises(ScriptError):
            ask(runtime, "lab: ping")
        [run] = runtime.log.runs()
        assert state(runtime, run.run_id).stopped_at == "plan"
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
        assert runtime.registry.names == ("lab", "demo")
    echo = next(item for item in demo.DOMAIN.actions if item.name == "echo")
    with pytest.raises(StepFailed):
        NoRunner().run(echo, demo.EchoArgs(text="hi"))
    with open_runtime(get_settings()) as runtime:
        found = ask(runtime, "Book a flight to Lisbon")
        stored = runtime.store.escalation(found.escalation_id).escalation
        assert stored.kind == "model_unavailable"
        assert stored.detail.startswith("model unavailable:")


def test_a_blank_request_and_an_unknown_run_leave_no_lease() -> None:
    with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
        with pytest.raises(ValueError):
            ask(runtime, "   ")
        assert leases(get_settings().db_path) == []
        missing = "a" * 32
        with pytest.raises(RunError) as raised:
            resume(runtime, missing)
        assert str(raised.value) == f"no run {missing}"
        assert leases(get_settings().db_path) == []


def test_a_lease_taken_during_the_step_stops_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    real = DemoRunner.run
    opened: dict[str, object] = {}

    def steal(self: DemoRunner, action: Action, args: Contract) -> dict[str, str]:
        output = real(self, action, args)
        NOW[0] = START + timedelta(seconds=601)
        runtime = opened["runtime"]
        [run] = runtime.log.runs()
        runtime.store.acquire(run.run_id, OTHER)
        return output

    monkeypatch.setattr(DemoRunner, "run", steal)
    with open_runtime(get_settings(), model=ScriptedModel([reply("plan", ECHO_PLAN)])) as runtime:
        opened["runtime"] = runtime
        with pytest.raises(RunError) as raised:
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        assert str(raised.value) == f"run {run.run_id} lost its lease"
        assert state(runtime, run.run_id).stopped_at == "answer"


def test_state_answers_while_another_holder_has_the_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    with open_runtime(get_settings(), model=ScriptedModel([reply("plan", NOTE_PLAN)])) as runtime:
        waiting = ask(runtime, "demo: note Milk")
        runtime.store.acquire(waiting.run_id, OTHER)
        assert state(runtime, waiting.run_id) == waiting


def test_a_classifier_error_stops_at_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
        with pytest.raises(ScriptError):
            ask(runtime, "Book a flight to Lisbon")
        [run] = runtime.log.runs()
        assert state(runtime, run.run_id).stopped_at == "route"


def test_run_errors_name_the_run_and_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
        held = "b" * 32
        runtime.store.acquire(held, OTHER)
        with pytest.raises(RunError) as busy:
            resume(runtime, held)
        assert str(busy.value) == f"run {held} is busy"
        with pytest.raises(ScriptError):
            ask(runtime, "Book a flight to Lisbon")
        [run] = runtime.log.runs()
        with pytest.raises(ScriptError):
            resume(runtime, run.run_id)
        assert state(runtime, run.run_id).stopped_at == "route"
