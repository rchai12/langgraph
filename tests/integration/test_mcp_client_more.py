import os
import threading
from pathlib import Path

import pytest
from mcp.shared.exceptions import MCPError

from conductor.config import get_settings
from conductor.mcp_client.client import McpUnavailable, client_for
from tests.integration.test_mcp_client import COMMAND, FAKE, FAKE_SERVER, mode


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
    return client_for(FAKE_SERVER, get_settings())


def test_two_calls_start_two_processes_and_a_thread_can_call(fake) -> None:
    fake.list_tools()
    fake.call_tool("echo", {"text": "one"})
    log = get_settings().data_dir / "mcp" / "fake.log"
    assert log.read_text().count("fake server started") == 2
    found: list[str] = []

    def work() -> None:
        outcome = fake.call_tool("echo", {"text": "from-thread"})
        found.append(outcome.structured["text"])

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert found == ["from-thread"]


def test_a_declared_variable_that_is_unset_stays_unset(
    fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FAKE_PASSED", raising=False)
    seen = fake.call_tool("env", {"name": "FAKE_PASSED"}).structured["result"]
    assert seen == "<unset>"


def test_an_existing_log_folder_keeps_its_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = tmp_path / "data" / "mcp"
    folder.mkdir(parents=True)
    folder.chmod(0o755)
    previous = os.umask(0o022)
    try:
        monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
        client_for(FAKE_SERVER, get_settings()).list_tools()
    finally:
        os.umask(previous)
    log = folder / "fake.log"
    assert (mode(folder), mode(log)) == (0o755, 0o600)


def test_a_string_result_is_structured(fake) -> None:
    outcome = fake.call_tool("env", {"name": "PATH"})
    assert outcome.is_error is False
    assert outcome.structured == {"result": os.environ["PATH"]}


def test_a_program_that_is_not_executable_fails_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", str(FAKE))
    with pytest.raises(McpUnavailable) as raised:
        client_for(FAKE_SERVER, get_settings()).list_tools()
    assert (raised.value.code, raised.value.__cause__) == ("start_failed", None)


def _leaves(error: BaseException) -> tuple[BaseException, ...]:
    if isinstance(error, BaseExceptionGroup):
        found: list[BaseException] = []
        for item in error.exceptions:
            found.extend(_leaves(item))
        return tuple(found)
    return (error,)


def test_an_unexpected_session_error_passes_through(fake, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(self: object) -> None:
        raise RuntimeError("session broke")

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", broken)
    with pytest.raises(ExceptionGroup) as grouped:
        fake.list_tools()
    assert any(isinstance(item, RuntimeError) for item in _leaves(grouped.value))


def test_a_bare_connection_error_is_closed(fake, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise MCPError(-32000, "Connection closed")

    monkeypatch.setattr("conductor.mcp_client.client.stdio_client", boom)
    with pytest.raises(McpUnavailable) as raised:
        fake.list_tools()
    assert (raised.value.code, raised.value.__cause__) == ("closed", None)
    assert "Connection closed" not in str(raised.value)


def test_a_closed_connection_and_a_mixed_group(fake, monkeypatch: pytest.MonkeyPatch) -> None:
    async def closed(self: object) -> None:
        raise MCPError(-32000, "Connection closed")

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", closed)
    with pytest.raises(McpUnavailable) as raised:
        fake.list_tools()
    assert (raised.value.code, raised.value.__cause__) == ("closed", None)

    async def mixed(self: object) -> None:
        raise ExceptionGroup("mixed", [MCPError(-32000, "Connection closed"), RuntimeError("nope")])

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", mixed)
    with pytest.raises(ExceptionGroup) as grouped:
        fake.list_tools()
    assert any(isinstance(item, RuntimeError) for item in _leaves(grouped.value))
