from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.events import EventLog
from conductor.graph.supervisor import (
    RESULT_DETAIL,
    Services,
    StepFailed,
    build_graph,
    start_run,
)
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.mcp_client.client import McpUnavailable, ToolOutcome
from conductor.registry import Action, Domain, McpServer, Registry
from conductor.runtime import McpRunner
from conductor.store import Store

ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'


class Text(Contract):
    text: str


class One(Contract):
    value: str


def test_an_unknown_code_is_dropped_and_the_detail_names_a_real_one(tmp_path: Path) -> None:
    assert StepFailed(code="nonsense").code is None  # type: ignore[arg-type]
    coded = _detail(tmp_path / "coded", StepFailed(code="no_result"))
    bare = _detail(tmp_path / "bare", StepFailed())
    assert coded == "step 1 demo.echo: the step failed (no_result)"
    assert bare == "step 1 demo.echo: the step failed"


def test_each_action_calls_its_own_server_once() -> None:
    east = McpServer("east", env=("EAST_HOME",))
    west = McpServer("west")
    alpha = Action("alpha", "Alpha.", "tool", "do", "read", One, One, "east")
    beta = Action("beta", "Beta.", "tool", "do", "read", One, One, "west")
    registry = Registry(
        (
            Domain("one", "One.", (alpha,), servers=(east,)),
            Domain("two", "Two.", (beta,), servers=(west,)),
        )
    )
    seen: list[McpServer] = []
    calls: list[tuple[str, str]] = []

    class Client:
        def __init__(self, name: str) -> None:
            self.name = name

        def call_tool(self, name: str, arguments: dict) -> ToolOutcome:
            calls.append((self.name, name))
            return ToolOutcome(False, {"value": arguments["value"]})

    def connect(server: McpServer, settings: object) -> Client:
        seen.append(server)
        return Client(server.name)

    runner = McpRunner(registry, get_settings(), connect=connect)
    assert runner.run(alpha, One(value="a")) == {"value": "a"}
    assert runner.run(beta, One(value="b")) == {"value": "b"}
    assert seen == [east, west]
    assert calls == [("east", "do"), ("west", "do")]


def test_a_failure_carries_no_secret_and_no_cause() -> None:
    secret = "SYNTHETIC-SECRET"
    errored = _spend(ToolOutcome(True, {"reason": secret}))
    with_cause = _spend(McpUnavailable("ledger", "timeout"))
    for raised in (errored, with_cause):
        assert secret not in str(raised.value)
        assert all(secret not in str(arg) for arg in raised.value.args)
        assert raised.value.__cause__ is None
    assert (errored.value.code, with_cause.value.code) == ("tool_error", "timeout")


def test_unknown_keys_only_give_nothing_and_the_graph_refuses_it(tmp_path: Path) -> None:
    echo = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
    registry = Registry((Domain("lab", "Lab.", (echo,), servers=(McpServer("fake"),)),))

    class Client:
        def call_tool(self, name: str, arguments: dict) -> ToolOutcome:
            return ToolOutcome(False, {"extra": "x"})

    runner = McpRunner(registry, get_settings(), connect=lambda server, settings: Client())
    assert runner.run(echo, Text(text="hi")) == {}
    state = _start(tmp_path, registry, runner)
    stored = Store(tmp_path / "conductor.db").escalation(state.escalation_id)
    assert stored.escalation.detail == f"step 1 lab.echo: {RESULT_DETAIL}"


class _Raiser:
    def __init__(self, error: StepFailed) -> None:
        self.error = error

    def run(self, action: Action, args: Contract) -> dict:
        raise self.error


def _detail(folder: Path, error: StepFailed) -> str:
    from conductor.domains import demo

    state = _start(folder, Registry((demo.DOMAIN,)), _Raiser(error))
    return Store(folder / "conductor.db").escalation(state.escalation_id).escalation.detail


def _start(folder: Path, registry: Registry, runner: object):
    store = Store(folder / "conductor.db")
    graph = build_graph(
        Services(
            registry=registry,
            store=store,
            log=EventLog(folder / "runs"),
            model=ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))]),
            model_name="test-model:1b",
            runner=runner,  # type: ignore[arg-type]
        ),
        InMemorySaver(),
    )
    request = "lab: go" if registry.names == ("lab",) else "demo: hi"
    return start_run(graph, request, run_id="f" * 32)


def _spend(outcome: ToolOutcome | McpUnavailable):
    import pytest

    from conductor.contracts import Contract as Base

    class Query(Base):
        month: str

    class Rows(Base):
        rows: list[str] = []

    action = Action("spend", "Spending.", "tool", "get_spending", "read", Query, Rows, "ledger")
    registry = Registry((Domain("finance", "Money.", (action,), servers=(McpServer("ledger"),)),))

    class Client:
        def call_tool(self, name: str, arguments: dict) -> ToolOutcome:
            if isinstance(outcome, McpUnavailable):
                raise outcome
            return outcome

    runner = McpRunner(registry, get_settings(), connect=lambda server, settings: Client())
    with pytest.raises(StepFailed) as raised:
        runner.run(action, Query(month="2026-10"))
    return raised
