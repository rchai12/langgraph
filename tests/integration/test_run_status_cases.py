import copy
import itertools
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.status import RunState, RunStateUnavailable, checkpoint_state
from conductor.graph.supervisor import (
    RunError,
    Services,
    build_graph,
    resume_run,
    start_run,
)
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.registry import Registry
from conductor.runtime import DemoRunner
from conductor.store import LeaseHeld, Store

RUN = "a" * 32
NOTE = '{"steps":[{"action":"note","args":{"title":"Milk"}}]}'
ECHO = '{"steps":[{"action":"echo","args":{"text":"hi"}}]}'
EMPTY = '{"steps":[]}'
REPLY = '{"reply":"Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def scripted(*rows: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(point, ModelReply(content=text)) for point, text in rows])


class RecordingSaver(InMemorySaver):
    def __init__(self) -> None:
        super().__init__()
        self.pending: list[RunState] = []
        self.checkpoints: list[RunState] = []

    def put_writes(self, config: dict, writes: list, task_id: str, task_path: str = "") -> None:
        super().put_writes(config, writes, task_id, task_path)
        self.pending.append(self._state(config))

    def put(self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict) -> dict:
        saved = super().put(config, checkpoint, metadata, new_versions)
        self.checkpoints.append(self._state(config))
        return saved

    def _state(self, config: dict) -> RunState:
        thread = config["configurable"]["thread_id"]
        found = self.get_tuple({"configurable": {"thread_id": thread, "checkpoint_ns": ""}})
        before = copy.deepcopy(found)
        state = checkpoint_state(found, thread)
        assert found == before
        return state


def graph_for(folder: Path, model: ScriptedModel) -> tuple[object, Store, EventLog, RecordingSaver]:
    saver = RecordingSaver()
    log = EventLog(folder / "runs")
    store = Store(folder / "conductor.db")
    graph = build_graph(
        Services(Registry((demo.DOMAIN,)), store, log, model, "test-model", DemoRunner()),
        saver,
    )
    return graph, store, log, saver


def test_echo_node_outputs_stop_then_finish_done(tmp_path: Path) -> None:
    graph, _, log, saver = graph_for(tmp_path, scripted(("plan", ECHO), ("answer", REPLY)))
    done = start_run(graph, "demo: say hi", run_id=RUN, log=log)
    assert done == RunState(RUN, "done", reply="Done.")
    assert [(state.status, state.stopped_at, state.reply) for state in saver.pending] == [
        ("stopped", "route", None),
        ("stopped", "plan", None),
        ("stopped", "ask_plan", None),
        ("stopped", "ask_step", None),
        ("stopped", "run_step", None),
        ("stopped", "ask_step", None),
        ("stopped", "answer", None),
        ("stopped", "finish", None),
        ("done", None, "Done."),
    ]
    assert saver.checkpoints[-1] == RunState(RUN, "done", reply="Done.")


def test_plan_and_step_approvals_and_a_superseded_interrupt(tmp_path: Path) -> None:
    graph, store, log, saver = graph_for(tmp_path, scripted(("plan", NOTE)))
    waiting = start_run(graph, "demo: note Milk", run_id=RUN, log=log)
    assert waiting == RunState(RUN, "waiting", approval_id="00000000000000000000000000000002")
    assert saver.pending[-1] == waiting
    decide_approval(
        store,
        Registry((demo.DOMAIN,)),
        waiting.approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )
    saver.pending.clear()
    step = resume_run(graph, store, RUN)
    assert step == RunState(RUN, "waiting", approval_id="00000000000000000000000000000003")
    assert saver.pending[1] == RunState(RUN, "stopped", stopped_at="ask_step")


def test_an_escalation_stops_through_record_and_then_waits(tmp_path: Path) -> None:
    graph, _, log, saver = graph_for(tmp_path, scripted(("plan", EMPTY)))
    escalated = start_run(graph, "demo: do something", run_id=RUN, log=log)
    assert escalated == RunState(RUN, "waiting", escalation_id="00000000000000000000000000000002")
    assert "record_escalation" in [state.stopped_at for state in saver.pending]
    assert saver.pending[-1] == escalated


def test_rejection_and_cancellation_are_terminal(tmp_path: Path) -> None:
    graph, store, log, _ = graph_for(tmp_path / "reject", scripted(("plan", NOTE)))
    waiting = start_run(graph, "demo: note Milk", run_id=RUN, log=log)
    decide_approval(
        store,
        Registry((demo.DOMAIN,)),
        waiting.approval_id,
        "reject",
        channel="terminal",
        decided_by="owner",
        note="not today",
    )
    assert resume_run(graph, store, RUN) == RunState(RUN, "rejected", note="not today")

    graph, store, log, _ = graph_for(tmp_path / "cancel", scripted(("plan", EMPTY)))
    waiting = start_run(graph, "demo: do something", run_id=RUN, log=log)
    answer_escalation(
        store, waiting.escalation_id, "cancel", channel="terminal", decided_by="owner"
    )
    assert resume_run(graph, store, RUN) == RunState(RUN, "cancelled")


def test_a_stopped_plan_and_route_are_literal(tmp_path: Path) -> None:
    graph, _, log, saver = graph_for(tmp_path, scripted())
    with pytest.raises(ScriptError):
        start_run(graph, "demo: say hi", run_id=RUN, log=log)
    assert saver.pending[-1] == RunState(RUN, "stopped", stopped_at="plan")
    assert "route" in [state.stopped_at for state in saver.pending]


def test_a_bad_start_adds_no_run_and_ask_records_the_start_first() -> None:
    settings = get_settings()
    model = scripted(("plan", ECHO), ("answer", REPLY))
    with runtime.open_runtime(settings, model=model) as opened:
        with pytest.raises(ValueError):
            start_run(opened.graph, "   ", run_id="f" * 32, log=opened.log)
        assert opened.log.runs() == []
        done = runtime.ask(opened, "demo: say hi")
        with pytest.raises(RunError):
            start_run(opened.graph, "demo: say hi", run_id=done.run_id, log=opened.log)
        events = opened.log.read(done.run_id)
    assert events[0].kind is EventKind.RUN_STARTED
    assert [event.kind for event in events].count(EventKind.RUN_STARTED) == 1


def test_resume_of_a_malformed_run_does_not_look_up_or_invoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
        opened.graph.checkpointer.conn.execute("UPDATE checkpoints SET checkpoint = ?", (b"nope",))
        opened.graph.checkpointer.conn.commit()

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("resume inspected a decision or invoked the graph")

        monkeypatch.setattr(opened.store, "approval", forbidden)
        monkeypatch.setattr(opened.store, "escalation", forbidden)
        monkeypatch.setattr(opened.graph, "invoke", forbidden)
        with pytest.raises(RunStateUnavailable) as raised:
            runtime.resume(opened, waiting.run_id)
    assert str(raised.value) == f"run {waiting.run_id} state is not available"


def test_a_leased_run_can_be_read_without_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
        opened.store.acquire(waiting.run_id, "e" * 32)
        with pytest.raises(LeaseHeld):
            opened.store.acquire(waiting.run_id, "f" * 32)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the read invoked, leased, logged, or minted an id")

    acquire = Store.acquire
    monkeypatch.setattr(ids, "new_id", forbidden)
    monkeypatch.setattr(runtime, "open_runtime", forbidden)
    monkeypatch.setattr(Store, "acquire", forbidden)
    monkeypatch.setattr(Store, "renew", forbidden)
    monkeypatch.setattr(EventLog, "append", forbidden)
    assert runtime.read_state(settings, waiting.run_id) == waiting
    with pytest.raises(LeaseHeld):
        acquire(Store(settings.db_path), waiting.run_id, "f" * 32)


def test_a_path_with_reserved_characters_reads_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "odd dir#hash?question"))
    settings = get_settings()
    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
    before = settings.checkpoints_path.read_bytes()
    assert runtime.read_state(settings, waiting.run_id) == waiting
    assert settings.checkpoints_path.read_bytes() == before
    with pytest.raises(RunError) as raised:
        runtime.read_state(settings, "f" * 32)
    assert str(raised.value) == f"no run {'f' * 32}"
    assert settings.checkpoints_path.read_bytes() == before


def test_a_corrupt_blob_and_failed_reads_are_unavailable() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
    connection = sqlite3.connect(settings.checkpoints_path)
    connection.execute(
        "UPDATE checkpoints SET metadata = ? WHERE thread_id = ?",
        (b"not-json", waiting.run_id),
    )
    connection.commit()
    connection.close()
    with pytest.raises(RunStateUnavailable) as raised:
        runtime.read_state(settings, waiting.run_id)
    assert str(raised.value) == f"run {waiting.run_id} state is not available"

    settings.data_dir.mkdir(exist_ok=True)
    settings.checkpoints_path.write_bytes(b"not a sqlite database")
    with pytest.raises(RunStateUnavailable):
        runtime.read_state(settings, waiting.run_id)


def test_the_read_begins_before_both_selects_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    model = scripted(("plan", ECHO), ("answer", REPLY))
    with runtime.open_runtime(settings, model=model) as opened:
        done = runtime.ask(opened, "demo: say hi")
    schema_before = _schema(settings.checkpoints_path)
    calls: list[str] = []
    closed: list[int] = []
    real_connect = sqlite3.connect

    class Cursor:
        def __init__(self, inner: sqlite3.Cursor) -> None:
            self.inner = inner

        def execute(self, sql: str, parameters: object = ()) -> object:
            calls.append(sql)
            return self.inner.execute(sql, parameters)

        def __iter__(self) -> object:
            return iter(self.inner)

        def __getattr__(self, name: str) -> object:
            return getattr(self.inner, name)

    class Connection:
        def __init__(self, inner: sqlite3.Connection) -> None:
            self.inner = inner

        def execute(self, sql: str, parameters: object = ()) -> object:
            calls.append(sql)
            return self.inner.execute(sql, parameters)

        def cursor(self) -> Cursor:
            return Cursor(self.inner.cursor())

        def close(self) -> None:
            closed.append(1)
            self.inner.close()

        def __getattr__(self, name: str) -> object:
            return getattr(self.inner, name)

    def connect(*args: object, **kwargs: object) -> Connection:
        return Connection(real_connect(*args, **kwargs))

    monkeypatch.setattr(sqlite3, "connect", connect)
    assert runtime.read_state(settings, done.run_id) == done
    assert runtime.read_state(settings, done.run_id) == done
    assert closed == [1, 1]
    assert calls[0] == "BEGIN"
    selects = [sql for sql in calls if sql.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 4
    assert all("checkpoints" in sql or "writes" in sql for sql in selects)
    assert _schema(settings.checkpoints_path) == schema_before


def test_a_live_wal_is_read_without_a_schema_change() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
        before = _schema(settings.checkpoints_path)
        assert (settings.checkpoints_path.parent / "checkpoints.db-wal").exists()
        assert runtime.read_state(settings, waiting.run_id) == waiting
        assert _schema(settings.checkpoints_path) == before


def test_opening_a_directory_is_unavailable() -> None:
    settings = get_settings()
    settings.data_dir.mkdir()
    settings.checkpoints_path.mkdir()
    with pytest.raises(RunStateUnavailable) as raised:
        runtime.read_state(settings, "f" * 32)
    assert str(raised.value) == f"run {'f' * 32} state is not available"


def test_open_and_close_failures_stay_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.data_dir.mkdir()
    settings.checkpoints_path.write_bytes(b"")
    with pytest.raises(RunStateUnavailable) as raised:
        runtime.read_state(settings, "f" * 32)
    assert str(raised.value) == f"run {'f' * 32} state is not available"

    with runtime.open_runtime(settings, model=scripted(("plan", NOTE))) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")

    real_connect = sqlite3.connect

    class Connection:
        def __init__(self, inner: sqlite3.Connection) -> None:
            self.inner = inner

        def close(self) -> None:
            self.inner.close()
            raise sqlite3.OperationalError("close failed")

        def __getattr__(self, name: str) -> object:
            return getattr(self.inner, name)

    def connect(*args: object, **kwargs: object) -> Connection:
        return Connection(real_connect(*args, **kwargs))

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(RunStateUnavailable):
        runtime.read_state(settings, waiting.run_id)

    with pytest.raises(RunError) as missing:
        runtime.read_state(settings, "f" * 32)
    assert str(missing.value) == f"no run {'f' * 32}"


def _schema(path: Path) -> tuple:
    connection = sqlite3.connect(path)
    try:
        master = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()
        return (master, version)
    finally:
        connection.close()
