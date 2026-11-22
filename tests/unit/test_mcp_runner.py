import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.events import EventLog
from conductor.graph.supervisor import (
    FAILURE_CODES,
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
from conductor.runtime import (
    DEMO_SUMMARY,
    MAX_RESULT_BYTES,
    DomainRunner,
    McpRunner,
)
from conductor.store import Store


class Query(Contract):
    month: str
    limit: int = Field(default=50, ge=1, le=200)


class Rows(Contract):
    rows: list[dict[str, str]]


SPEND = Action("spend", "Spending.", "tool", "get_spending", "read", Query, Rows, "ledger")
LEDGER = McpServer("ledger", env=("LEDGER_HOME",))
FINANCE = Domain("finance", "Money.", (SPEND,), servers=(LEDGER,))
REGISTRY = Registry((FINANCE,))


class FakeClient:
    def __init__(self, outcome: ToolOutcome | McpUnavailable) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> ToolOutcome:
        self.calls.append((name, arguments))
        if isinstance(self.outcome, McpUnavailable):
            raise self.outcome
        return self.outcome


def runner_with(outcome: ToolOutcome | McpUnavailable):
    client = FakeClient(outcome)
    servers: list[McpServer] = []

    def connect(server: McpServer, _settings):
        servers.append(server)
        return client

    return McpRunner(REGISTRY, get_settings(), connect=connect), client, servers


def failure(runner: McpRunner) -> str | None:
    with pytest.raises(StepFailed) as raised:
        runner.run(SPEND, Query(month="2026-10"))
    return raised.value.code


def test_the_failure_codes() -> None:
    assert FAILURE_CODES == (
        "tool_error",
        "no_command",
        "start_failed",
        "timeout",
        "closed",
        "no_result",
        "too_large",
    )
    assert (StepFailed().code, StepFailed(code="timeout").code) == (None, "timeout")
    assert StepFailed("SYNTHETIC-SECRET").code is None
    assert MAX_RESULT_BYTES == 256 * 1024


def test_a_call_with_the_declared_server_and_the_arguments_as_json() -> None:
    runner, client, servers = runner_with(ToolOutcome(False, {"rows": [{"merchant": "Grocer"}]}))
    assert runner.run(SPEND, Query(month="2026-10")) == {"rows": [{"merchant": "Grocer"}]}
    assert client.calls == [("get_spending", {"month": "2026-10", "limit": 50})]
    assert servers == [LEDGER]


def test_fields_the_contract_does_not_name_are_dropped() -> None:
    structured = {"rows": [{"merchant": "Grocer", "extra": "kept inside"}], "total_cents": 1200}
    runner, _, _ = runner_with(ToolOutcome(False, structured))
    assert runner.run(SPEND, Query(month="2026-10")) == {
        "rows": [{"merchant": "Grocer", "extra": "kept inside"}]
    }


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (ToolOutcome(True, None), "tool_error"),
        (McpUnavailable("ledger", "no_command"), "no_command"),
        (McpUnavailable("ledger", "start_failed"), "start_failed"),
        (McpUnavailable("ledger", "timeout"), "timeout"),
        (McpUnavailable("ledger", "closed"), "closed"),
        (ToolOutcome(False, None), "no_result"),
    ],
)
def test_each_failure_has_its_code(outcome, code: str) -> None:
    runner, _, _ = runner_with(outcome)
    assert failure(runner) == code


@pytest.mark.parametrize(("extra", "code"), [(0, None), (1, "too_large")])
def test_a_result_over_256_kb_fails(extra: int, code: str | None) -> None:
    padding = MAX_RESULT_BYTES - len(json.dumps({"rows": [], "pad": ""}).encode())
    structured = {"rows": [], "pad": "x" * (padding + extra)}
    assert len(json.dumps(structured, ensure_ascii=False).encode()) == MAX_RESULT_BYTES + extra
    runner, _, _ = runner_with(ToolOutcome(False, structured))
    if code is None:
        assert runner.run(SPEND, Query(month="2026-10")) == {"rows": []}
    else:
        assert failure(runner) == code


def test_the_domain_runner_sends_each_action_to_its_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    registry = Registry((FINANCE, demo.DOMAIN))
    client = FakeClient(ToolOutcome(False, {"rows": []}))
    runner = DomainRunner(registry, get_settings(), connect=lambda _server, _settings: client)
    assert runner.run(SPEND, Query(month="2026-10")) == {"rows": []}
    delegate = next(a for a in demo.DOMAIN.actions if a.name == "delegate")
    assert runner.run(delegate, demo.DelegateArgs(task="tidy")) == {"summary": DEMO_SUMMARY}
    advise = Action("advise", "Advise.", "agent", "advisor", "read", Query, Rows)
    with pytest.raises(StepFailed) as raised:
        runner.run(advise, Query(month="2026-10"))
    assert raised.value.code is None
    assert len(client.calls) == 1


def test_without_the_demo_setting_demo_actions_do_not_run() -> None:
    runner = DomainRunner(Registry((demo.DOMAIN,)), get_settings())
    echo = next(a for a in demo.DOMAIN.actions if a.name == "echo")
    with pytest.raises(StepFailed):
        runner.run(echo, demo.EchoArgs(text="hi"))


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

    def connect(server: McpServer, _settings: object) -> Client:
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
        def call_tool(self, _name: str, _arguments: dict) -> ToolOutcome:
            return ToolOutcome(False, {"extra": "x"})

    runner = McpRunner(registry, get_settings(), connect=lambda _server, _settings: Client())
    assert runner.run(echo, Text(text="hi")) == {}
    state = _start(tmp_path, registry, runner)
    stored = Store(tmp_path / "conductor.db").escalation(state.escalation_id)
    assert stored.escalation.detail == f"step 1 lab.echo: {RESULT_DETAIL}"


class _Raiser:
    def __init__(self, error: StepFailed) -> None:
        self.error = error

    def run(self, _action: Action, _args: Contract) -> dict:
        raise self.error


def _detail(folder: Path, error: StepFailed) -> str:
    from conductor.domains import demo

    state = _start(folder, Registry((demo.DOMAIN,)), _Raiser(error))
    return Store(folder / "conductor.db").escalation(state.escalation_id).escalation.detail


def _start(folder: Path, registry: Registry, runner: object):
    store = Store(folder / "conductor.db")
    log = EventLog(folder / "runs")
    graph = build_graph(
        Services(
            registry=registry,
            store=store,
            log=log,
            model=ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))]),
            model_name="test-model:1b",
            runner=runner,  # type: ignore[arg-type]
        ),
        InMemorySaver(),
    )
    request = "lab: go" if registry.names == ("lab",) else "demo: hi"
    return start_run(graph, request, run_id="f" * 32, log=log)


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
        def call_tool(self, _name: str, _arguments: dict) -> ToolOutcome:
            if isinstance(outcome, McpUnavailable):
                raise outcome
            return outcome

    runner = McpRunner(registry, get_settings(), connect=lambda _server, _settings: Client())
    with pytest.raises(StepFailed) as raised:
        runner.run(action, Query(month="2026-10"))
    return raised
