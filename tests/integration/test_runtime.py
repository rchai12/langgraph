import itertools
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, domains, ids
from conductor.config import SettingsError, get_settings
from conductor.decisions import decide_approval
from conductor.domains import demo
from conductor.events import EventKind
from conductor.graph.supervisor import RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import DEMO_SUMMARY, DemoRunner, Runtime, ask, open_runtime, resume, state
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
def test_a_busy_run_is_refused(tmp_path: Path) -> None:
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
def test_a_run_that_raises_releases_its_lease_and_stops(tmp_path: Path) -> None:
    with open_runtime(get_settings(), model=scripted()) as runtime:
        with pytest.raises(Exception, match="no scripted reply left for plan"):
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        stopped = state(runtime, run.run_id)
        assert stopped == RunState(run_id=run.run_id, status="stopped", stopped_at="plan")
        runtime.store.acquire(run.run_id, OTHER)
        runtime.store.release(run.run_id, OTHER)
        with pytest.raises(RunError) as raised:
            resume(runtime, run.run_id)
        assert str(raised.value) == f"run {run.run_id} stopped at plan and cannot be resumed"


class StealingModel(ScriptedModel):
    """Answers like ScriptedModel, then calls `steal` (set by the test) after each chat."""

    steal = None

    def chat(self, request):
        reply = super().chat(request)
        if self.steal is not None:
            self.steal()
        return reply


@pytest.mark.usefixtures("demo_on")
def test_a_lost_lease_stops_the_run_before_its_step_runs(tmp_path: Path) -> None:
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
