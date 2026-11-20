import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph

from conductor import domains, ids, private
from conductor.config import Settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.events import EventKind, EventLog, JsonValue, check_run_id
from conductor.graph.status import RunStateUnavailable, checkpoint_state
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
from conductor.mcp_client.check import ToolCheckFailed, check_registry
from conductor.mcp_client.client import McpClient, McpUnavailable, client_for
from conductor.registry import Action, McpServer, Registry
from conductor.store import LeaseHeld, LeaseLost, Store

DEMO_SUMMARY = "the demo agent does no work"
MAX_RESULT_BYTES = 256 * 1024
RESUME_FAILED = "resume_failed"


class DemoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        if action.name == "echo":
            return {"text": args.model_dump()["text"]}
        if action.name == "note":
            return {"note_id": ids.new_id()}
        return {"summary": DEMO_SUMMARY}


class NoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        raise StepFailed()


class McpRunner:
    def __init__(
        self,
        registry: Registry,
        settings: Settings,
        *,
        connect: Callable[[McpServer, Settings], McpClient] = client_for,
    ) -> None:
        self._settings = settings
        self._connect = connect
        servers: dict[str, McpServer] = {}
        for name in registry.names:
            for server in registry.domain(name).servers:
                servers[server.name] = server
        self._servers = servers

    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        server = self._servers[action.server]  # type: ignore[index]
        try:
            outcome = self._connect(server, self._settings).call_tool(
                action.target, args.model_dump(mode="json")
            )
        except McpUnavailable as error:
            raise StepFailed(code=error.code) from None
        if outcome.is_error:
            raise StepFailed(code="tool_error")
        structured = outcome.structured
        if structured is None:
            raise StepFailed(code="no_result")
        encoded = json.dumps(structured, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            raise StepFailed(code="too_large")
        return {
            key: value for key, value in structured.items() if key in action.result.model_fields
        }


class DomainRunner:
    def __init__(
        self,
        registry: Registry,
        settings: Settings,
        *,
        connect: Callable[[McpServer, Settings], McpClient] = client_for,
    ) -> None:
        self._settings = settings
        self._mcp = McpRunner(registry, settings, connect=connect)
        self._demo = DemoRunner()
        self._none = NoRunner()

    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        if action.server is not None:
            return self._mcp.run(action, args)
        if self._settings.demo_on and action in demo.DOMAIN.actions:
            return self._demo.run(action, args)
        return self._none.run(action, args)


@dataclass
class _Focus:
    run_id: str = ""


@dataclass
class _Checked:
    done: bool = False


@dataclass(frozen=True)
class Runtime:
    graph: CompiledStateGraph
    store: Store
    log: EventLog
    registry: Registry
    holder: str
    focus: _Focus
    settings: Settings
    checked: _Checked


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
    def __init__(self, runner: DomainRunner, store: Store, holder: str, focus: _Focus) -> None:
        self._runner = runner
        self._store = store
        self._holder = holder
        self._focus = focus

    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]:
        self._store.renew(self._focus.run_id, self._holder)
        return self._runner.run(action, args)


@contextmanager
def open_runtime(settings: Settings, *, model: Model | None = None) -> Iterator[Runtime]:
    private.ensure_file(settings.checkpoints_path)
    connection = sqlite3.connect(settings.checkpoints_path, check_same_thread=False)
    try:
        saver = SqliteSaver(connection)
        store = Store(settings.db_path)
        log = EventLog(settings.runs_dir)
        registry = Registry(domains.registered(settings))
        runner = DomainRunner(registry, settings)
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
        yield Runtime(graph, store, log, registry, holder, focus, settings, _Checked())
    finally:
        connection.close()


def check_tools(runtime: Runtime) -> None:
    if runtime.checked.done:
        return
    problems = check_registry(runtime.registry, runtime.settings)
    if problems:
        raise ToolCheckFailed(problems)
    runtime.checked.done = True


def ask(runtime: Runtime, request: str) -> RunState:
    check_tools(runtime)
    run_id = ids.new_id()
    runtime.store.acquire(run_id, runtime.holder)
    return _call(
        runtime, run_id, lambda: start_run(runtime.graph, request, run_id=run_id, log=runtime.log)
    )


def resume(runtime: Runtime, run_id: str) -> RunState:
    check_tools(runtime)
    try:
        runtime.store.acquire(run_id, runtime.holder)
    except LeaseHeld:
        raise RunError(f"run {run_id} is busy") from None
    return _call(runtime, run_id, lambda: _resume(runtime, run_id))


def state(runtime: Runtime, run_id: str) -> RunState:
    return run_state(runtime.graph, run_id)


def read_state(settings: Settings, run_id: str) -> RunState:
    check_run_id(run_id)
    path = settings.checkpoints_path
    if not path.exists():
        raise RunError(f"no run {run_id}")
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    except Exception:
        raise RunStateUnavailable(f"run {run_id} state is not available") from None
    outcome: RunState | BaseException
    try:
        try:
            connection.execute("BEGIN")
            saver = SqliteSaver(connection)
            saver.is_setup = True
            try:
                saved = saver.get_tuple(
                    {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
                )
            except Exception:
                raise RunStateUnavailable(f"run {run_id} state is not available") from None
            outcome = checkpoint_state(saved, run_id)
        except Exception as error:
            outcome = error
    finally:
        try:
            connection.close()
        except Exception:
            if not isinstance(outcome, Exception):
                outcome = RunStateUnavailable(f"run {run_id} state is not available")
    if isinstance(outcome, Exception):
        raise outcome
    return outcome


def _resume(runtime: Runtime, run_id: str) -> RunState:
    try:
        return resume_run(runtime.graph, runtime.store, run_id)
    except Exception as error:
        if not isinstance(error, (RunError, LeaseLost)):
            try:
                runtime.log.append(
                    run_id,
                    EventKind.ERROR,
                    payload={"error": RESUME_FAILED, "type": type(error).__name__},
                )
            except Exception:
                pass
        raise


def _call(runtime: Runtime, run_id: str, call: Callable[[], RunState]) -> RunState:
    runtime.focus.run_id = run_id
    try:
        try:
            return call()
        finally:
            runtime.store.release(run_id, runtime.holder)
    except LeaseLost:
        raise RunError(f"run {run_id} lost its lease") from None
