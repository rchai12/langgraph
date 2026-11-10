import json

import pytest
from pydantic import Field

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.graph.supervisor import FAILURE_CODES, StepFailed
from conductor.mcp_client.client import McpUnavailable, ToolOutcome
from conductor.registry import Action, Domain, McpServer, Registry
from conductor.runtime import (
    DEMO_SUMMARY,
    MAX_RESULT_BYTES,
    DomainRunner,
    McpRunner,
)


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

    def connect(server: McpServer, settings):
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
    runner = DomainRunner(registry, get_settings(), connect=lambda server, settings: client)
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
