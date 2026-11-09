import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph

from conductor import domains, ids
from conductor.config import Settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.events import EventLog, JsonValue
from conductor.graph.supervisor import (
    RunError,
    RunState,
    Services,
    StepFailed,
    build_graph,
    resume_run,
    run_state,
    start_run,
)
from conductor.llm.model import Model, ModelInfo, ModelReply
from conductor.llm.ollama import OllamaModel
from conductor.registry import Action, Registry
from conductor.store import LeaseHeld, LeaseLost, Store

DEMO_SUMMARY = "the demo agent does no work"


class DemoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        if action.name == "echo":
            return {"text": args.text}  # type: ignore[attr-defined]
        if action.name == "note":
            return {"note_id": ids.new_id()}
        return {"summary": DEMO_SUMMARY}


class NoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        raise StepFailed()


@dataclass
class _Focus:
    run_id: str = ""


@dataclass(frozen=True)
class Runtime:
    graph: CompiledStateGraph
    store: Store
    log: EventLog
    registry: Registry
    holder: str
    focus: _Focus


class _LeasedModel:
    def __init__(self, model: Model, store: Store, holder: str, focus: _Focus) -> None:
        self._model = model
        self._store = store
        self._holder = holder
        self._focus = focus

    def model_info(self, name: str) -> ModelInfo:
        return self._model.model_info(name)

    def chat(self, request: object) -> ModelReply:
        self._store.renew(self._focus.run_id, self._holder)
        return self._model.chat(request)


class _LeasedRunner:
    def __init__(
        self, runner: DemoRunner | NoRunner, store: Store, holder: str, focus: _Focus
    ) -> None:
        self._runner = runner
        self._store = store
        self._holder = holder
        self._focus = focus

    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        self._store.renew(self._focus.run_id, self._holder)
        return self._runner.run(action, args)


@contextmanager
def open_runtime(settings: Settings, *, model: Model | None = None) -> Iterator[Runtime]:
    folder = settings.data_dir
    if not folder.exists():
        folder.mkdir(parents=True, mode=0o700)
        folder.chmod(0o700)
    path = settings.checkpoints_path
    if not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        saver = SqliteSaver(connection)
        store = Store(settings.db_path)
        log = EventLog(settings.runs_dir)
        registered = domains.DOMAINS
        if settings.demo_on:
            registered = (*registered, demo.DOMAIN)
            runner: DemoRunner | NoRunner = DemoRunner()
        else:
            runner = NoRunner()
        registry = Registry(registered)
        chosen = model
        if chosen is None:
            chosen = OllamaModel(settings.ollama_host, timeout=settings.model_timeout_seconds)
        holder = ids.new_id()
        focus = _Focus()
        graph = build_graph(
            Services(
                registry=registry,
                store=store,
                log=log,
                model=_LeasedModel(chosen, store, holder, focus),
                model_name=settings.model,
                runner=_LeasedRunner(runner, store, holder, focus),
            ),
            saver,
        )
        yield Runtime(graph, store, log, registry, holder, focus)
    finally:
        connection.close()


def ask(runtime: Runtime, request: str) -> RunState:
    run_id = ids.new_id()
    runtime.store.acquire(run_id, runtime.holder)
    return _call(runtime, run_id, lambda: start_run(runtime.graph, request, run_id=run_id))


def resume(runtime: Runtime, run_id: str) -> RunState:
    try:
        runtime.store.acquire(run_id, runtime.holder)
    except LeaseHeld:
        raise RunError(f"run {run_id} is busy") from None
    return _call(runtime, run_id, lambda: resume_run(runtime.graph, runtime.store, run_id))


def state(runtime: Runtime, run_id: str) -> RunState:
    return run_state(runtime.graph, run_id)


def _call(runtime: Runtime, run_id: str, call: Callable[[], RunState]) -> RunState:
    runtime.focus.run_id = run_id
    try:
        try:
            return call()
        finally:
            runtime.store.release(run_id, runtime.holder)
    except LeaseLost:
        raise RunError(f"run {run_id} lost its lease") from None
