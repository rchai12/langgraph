from dataclasses import replace

import pytest

from conductor.config import SettingsError, get_settings
from conductor.contracts import Contract
from conductor.domains import demo
from conductor.registry import Action, Domain, McpServer, Registry, RegistryError


class Args(Contract):
    account: str


class Result(Contract):
    cents: int


BALANCES = Action(
    "balances", "Read the balances.", "tool", "get_balances", "read", Args, Result, "ledger"
)
FINANCE = Domain(
    "finance",
    "Household money.",
    (BALANCES,),
    servers=(McpServer("ledger", env=("LEDGER_HOME",)),),
)


def test_the_declarations() -> None:
    assert (BALANCES.server, FINANCE.servers[0].name, FINANCE.servers[0].env) == (
        "ledger",
        "ledger",
        ("LEDGER_HOME",),
    )
    assert McpServer("plain").env == ()
    assert demo.DOMAIN.servers == ()
    assert {action.server for action in demo.DOMAIN.actions} == {None}
    assert Registry((FINANCE, demo.DOMAIN)).names == ("finance", "demo")


@pytest.mark.parametrize(
    ("domains", "message"),
    [
        (
            (replace(FINANCE, servers=(McpServer("Ledger"),)),),
            "server finance.Ledger: not a valid name",
        ),
        (
            (replace(FINANCE, servers=(McpServer("ledger"), McpServer("ledger"))),),
            "server finance.ledger: declared twice",
        ),
        (
            (FINANCE, Domain("budget", "Budgets.", (BALANCES,), servers=(McpServer("ledger"),))),
            "server budget.ledger: also declared by finance",
        ),
        (
            (replace(FINANCE, servers=(McpServer("ledger", env=("ledger_home",)),)),),
            "server finance.ledger: environment name 1 is not valid",
        ),
        (
            (replace(FINANCE, servers=(McpServer("ledger", env=("HOME", "CONDUCTOR_MODEL")),)),),
            "server finance.ledger: environment name 2 is not valid",
        ),
        (
            (replace(FINANCE, actions=(replace(BALANCES, server="bank"),)),),
            "action finance.balances: no server bank in this domain",
        ),
        (
            (replace(FINANCE, actions=(replace(BALANCES, server=None),)),),
            "action finance.balances: a tool action of a domain with servers names one",
        ),
        (
            (
                replace(
                    FINANCE,
                    actions=(
                        BALANCES,
                        replace(BALANCES, name="advise", kind="agent", server="ledger"),
                    ),
                ),
            ),
            "action finance.advise: only a tool action names a server",
        ),
    ],
)
def test_server_declarations_are_checked(domains: tuple[Domain, ...], message: str) -> None:
    with pytest.raises(RegistryError) as raised:
        Registry(domains)
    assert str(raised.value) == message


def test_the_mcp_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert (settings.mcp, settings.mcp_timeout, settings.mcp_timeout_seconds) == ({}, "60", 60)
    monkeypatch.setenv("CONDUCTOR_MCP__LEDGER", "/opt/ledger/bin/ledger mcp serve")
    monkeypatch.setenv("CONDUCTOR_MCP__MAIL_BOX", "'/opt/mail box/run' --stdio")
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "600")
    settings = get_settings()
    assert settings.mcp == {
        "ledger": "/opt/ledger/bin/ledger mcp serve",
        "mail_box": "'/opt/mail box/run' --stdio",
    }
    assert settings.mcp_command("ledger") == ("/opt/ledger/bin/ledger", "mcp", "serve")
    assert settings.mcp_command("mail_box") == ("/opt/mail box/run", "--stdio")
    assert settings.mcp_command("bank") is None
    assert settings.mcp_timeout_seconds == 600


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (
            "CONDUCTOR_MCP_TIMEOUT",
            "0",
            "CONDUCTOR_MCP_TIMEOUT: must be whole seconds from 1 to 600",
        ),
        (
            "CONDUCTOR_MCP_TIMEOUT",
            "601",
            "CONDUCTOR_MCP_TIMEOUT: must be whole seconds from 1 to 600",
        ),
        ("CONDUCTOR_MCP__LEDGER", "   ", "CONDUCTOR_MCP__LEDGER: must be a command line"),
        ("CONDUCTOR_MCP__LEDGER", "'/opt/ledger", "CONDUCTOR_MCP__LEDGER: must be a command line"),
        ("CONDUCTOR_MCP", '{"ledger": 1}', "CONDUCTOR_MCP: must map server names to command lines"),
    ],
)
def test_bad_mcp_settings(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == message
    assert "1}" not in str(raised.value)
