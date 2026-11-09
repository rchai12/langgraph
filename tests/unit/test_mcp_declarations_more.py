from dataclasses import replace

import pytest

from conductor.config import SettingsError, get_settings
from conductor.domains import demo
from conductor.registry import McpServer, Registry, RegistryError
from tests.unit.test_mcp_declarations import BALANCES, FINANCE


def test_a_long_environment_name_is_refused_before_an_action() -> None:
    long_name = "A" * 65
    domain = replace(
        FINANCE,
        servers=(McpServer("Ledger", env=(long_name,)),),
        actions=(replace(BALANCES, name="9bad"),),
    )
    with pytest.raises(RegistryError) as raised:
        Registry((domain,))
    assert str(raised.value) == "server finance.Ledger: not a valid name"
    refused = replace(FINANCE, servers=(McpServer("ledger", env=(long_name,)),))
    with pytest.raises(RegistryError) as raised:
        Registry((refused,))
    assert str(raised.value) == "server finance.ledger: environment name 1 is not valid"


def test_a_domain_without_servers_keeps_tool_actions() -> None:
    registry = Registry((demo.DOMAIN,))
    assert registry.names == ("demo",)
    assert demo.DOMAIN.servers == ()
    tools = [action for action in demo.DOMAIN.actions if action.kind == "tool"]
    assert tools
    assert all(action.server is None for action in tools)


def test_bad_server_names_follow_the_timeout_in_sorted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "601")
    monkeypatch.setenv("CONDUCTOR_MCP__9LEDGER", "ledger")
    monkeypatch.setenv("CONDUCTOR_MCP__" + "A" * 33, "ledger")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == (
        "CONDUCTOR_MCP_TIMEOUT: must be whole seconds from 1 to 600; "
        "CONDUCTOR_MCP__9LEDGER: not a server name; "
        f"CONDUCTOR_MCP__{'A' * 33}: not a server name"
    )


def test_a_quoted_command_keeps_a_path_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP__LEDGER", "'/opt/my ledger/run' --stdio")
    settings = get_settings()
    assert settings.mcp_command("ledger") == ("/opt/my ledger/run", "--stdio")
