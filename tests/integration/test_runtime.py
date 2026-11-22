import itertools
import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, domains, ids
from conductor.config import SettingsError, get_settings
from conductor.contracts import Contract
from conductor.decisions import decide_approval
from conductor.domains import demo
from conductor.events import EventKind
from conductor.graph.supervisor import RunError, RunState, StepFailed
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.registry import Action, Domain
from conductor.runtime import (
    DEMO_SUMMARY,
    DemoRunner,
    NoRunner,
    Runtime,
    ask,
    open_runtime,
    resume,
    state,
)
from conductor.store import Store

START = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
NOW = [START]
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
REPLY = '{"reply": "Done."}'
OTHER = "9" * 32


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    NOW[0] = START
    monkeypatch.setattr(clock, "now", lambda: NOW[0])
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def scripted(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies])


def approve(runtime: Runtime, approval_id: str) -> None:
    decide_approval(
        runtime.store,
        runtime.registry,
        approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert (settings.demo, settings.demo_on) == ("false", False)
    assert settings.checkpoints_path == tmp_path / "data" / "checkpoints.db"
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    assert get_settings().demo_on is True


@pytest.mark.parametrize("value", ["yes", "True"])
def test_the_demo_setting_is_true_or_false(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == "CONDUCTOR_DEMO: must be true or false"


def test_without_the_demo_setting_no_domain_is_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", ())
    with open_runtime(get_settings(), model=scripted()) as runtime:
        assert runtime.registry.names == ()
        found = ask(runtime, "demo: echo hi")
        assert found.status == "waiting" and found.escalation_id is not None
        assert runtime.store.escalation(found.escalation_id).escalation.detail == (
            "no domains are registered"
        )


@pytest.mark.usefixtures("demo_on")
def test_a_run_survives_a_restart_in_private_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with open_runtime(get_settings(), model=scripted(("plan", NOTE_PLAN))) as first:
        assert first.registry.names == ("demo",)
        waiting = ask(first, "demo: note Milk")
        assert waiting.status == "waiting" and waiting.approval_id is not None
        assert {p.name: mode(p) for p in data.iterdir() if p.name.startswith("checkpoints")} == {
            name: 0o600 for name in ("checkpoints.db", "checkpoints.db-shm", "checkpoints.db-wal")
        }
        approve(first, waiting.approval_id)
    with open_runtime(get_settings(), model=scripted(("answer", REPLY))) as second:
        assert second.holder != first.holder
        assert state(second, waiting.run_id) == waiting
        step = resume(second, waiting.run_id)
        assert step.status == "waiting" and step.approval_id != waiting.approval_id
        approve(second, step.approval_id)
        assert resume(second, waiting.run_id) == RunState(
            run_id=waiting.run_id, status="done", reply="Done."
        )
    assert mode(data / "checkpoints.db") == 0o600


@pytest.mark.parametrize(
    ("action", "args", "output"),
    [
        ("echo", demo.EchoArgs(text="hi"), {"text": "hi"}),
        ("note", demo.NoteArgs(title="Milk"), {"note_id": "1".rjust(32, "0")}),
        ("delegate", demo.DelegateArgs(task="tidy"), {"summary": DEMO_SUMMARY}),
    ],
)
def test_the_demo_runner(action: str, args: object, output: dict) -> None:
    found = DemoRunner().run(next(a for a in demo.DOMAIN.actions if a.name == action), args)
    assert found == output
    assert DEMO_SUMMARY == "the demo agent does no work"


@pytest.mark.usefixtures("demo_on")
def test_a_busy_run_is_refused() -> None:
    with open_runtime(get_settings(), model=scripted(("plan", NOTE_PLAN))) as runtime:
        waiting = ask(runtime, "demo: note Milk")
        approve(runtime, waiting.approval_id)
        runtime.store.acquire(waiting.run_id, OTHER)
        with pytest.raises(RunError) as raised:
            resume(runtime, waiting.run_id)
        assert str(raised.value) == f"run {waiting.run_id} is busy"
        assert state(runtime, waiting.run_id) == waiting


@pytest.mark.usefixtures("demo_on")
def test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewals: list[tuple[str, str]] = []
    real = Store.renew

    def spy(self: Store, thread_id: str, holder: str):
        renewals.append((thread_id, holder))
        return real(self, thread_id, holder)

    monkeypatch.setattr(Store, "renew", spy)
    model = scripted(("plan", ECHO_PLAN), ("answer", REPLY))
    with open_runtime(get_settings(), model=model) as runtime:
        done = ask(runtime, "demo: say hi")
        assert done.status == "done"
        assert renewals == [(done.run_id, runtime.holder)] * 3
        runtime.store.acquire(done.run_id, OTHER)


@pytest.mark.usefixtures("demo_on")
def test_a_run_that_raises_releases_its_lease_and_stops() -> None:
    with open_runtime(get_settings(), model=scripted()) as runtime:
        with pytest.raises(Exception, match="no scripted reply left for plan"):
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        stopped = state(runtime, run.run_id)
        assert stopped == RunState(run_id=run.run_id, status="stopped", stopped_at="plan")
        runtime.store.acquire(run.run_id, OTHER)
        runtime.store.release(run.run_id, OTHER)
        with pytest.raises(Exception, match="no scripted reply left for plan"):
            resume(runtime, run.run_id)
        assert state(runtime, run.run_id) == stopped
        runtime.store.acquire(run.run_id, OTHER)


class StealingModel(ScriptedModel):
    """Answers like ScriptedModel, then calls `steal` (set by the test) after each chat."""

    steal = None

    def chat(self, request):
        reply = super().chat(request)
        if self.steal is not None:
            self.steal()
        return reply


@pytest.mark.usefixtures("demo_on")
def test_a_lost_lease_stops_the_run_before_its_step_runs() -> None:
    model = StealingModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))])
    with open_runtime(get_settings(), model=model) as runtime:

        def steal() -> None:
            NOW[0] = START + timedelta(seconds=601)
            [run] = runtime.log.runs()
            runtime.store.acquire(run.run_id, OTHER)

        model.steal = steal
        with pytest.raises(RunError) as raised:
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        assert str(raised.value) == f"run {run.run_id} lost its lease"
        assert EventKind.TOOL_RESULT not in [e.kind for e in runtime.log.read(run.run_id)]
        assert state(runtime, run.run_id) == RunState(
            run_id=run.run_id, status="stopped", stopped_at="run_step"
        )


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
