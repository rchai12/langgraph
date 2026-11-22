import importlib.metadata
import importlib.util
import os
import shlex
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from mcp.shared.exceptions import MCPError

from conductor.config import get_settings
from conductor.mcp_client.client import (
    McpUnavailable,
    ToolInfo,
    ToolOutcome,
    client_for,
)
from conductor.registry import McpServer

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"
COMMAND = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
FAKE_SERVER = McpServer("fake", env=("FAKE_PASSED",))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
    return client_for(FAKE_SERVER, get_settings())


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_tools_of_a_server(fake) -> None:
    tools = {tool.name: tool for tool in fake.list_tools()}
    assert sorted(tools) == ["echo", "env", "fail", "stop", "wait"]
    assert tools["echo"] == ToolInfo(
        name="echo",
        input_schema={
            "type": "object",
            "properties": {"text": {"title": "Text", "type": "string"}},
            "required": ["text"],
            "title": "echoArguments",
        },
        output_schema={
            "properties": {"text": {"title": "Text", "type": "string"}},
            "required": ["text"],
            "title": "Echoed",
            "type": "object",
        },
        read_only=True,
    )
    assert (tools["fail"].read_only, tools["stop"].read_only) == (None, None)


def test_a_call_and_a_failed_call(fake) -> None:
    assert fake.call_tool("echo", {"text": "hi"}) == ToolOutcome(
        is_error=False, structured={"text": "hi"}
    )
    failed = fake.call_tool("fail", {"reason": "SYNTHETIC-SECRET"})
    assert failed == ToolOutcome(is_error=True, structured=None)
    assert "SYNTHETIC-SECRET" not in repr(failed)
    assert fake.call_tool("echo", {"text": 5}) == ToolOutcome(is_error=True, structured=None)
    assert fake.call_tool("nope", {}) == ToolOutcome(is_error=True, structured=None)


def test_the_server_sees_only_safe_and_declared_variables(
    fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_PASSED", "yes")
    monkeypatch.setenv("FAKE_NOT_DECLARED", "no")
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", "owner")

    def seen(name: str) -> str:
        return fake.call_tool("env", {"name": name}).structured["result"]

    assert [
        seen(name) for name in ("FAKE_PASSED", "FAKE_NOT_DECLARED", "CONDUCTOR_DECIDED_BY")
    ] == [
        "yes",
        "<unset>",
        "<unset>",
    ]
    assert seen("PATH") == os.environ["PATH"]


def test_the_server_log_is_private_and_appended(fake, tmp_path: Path) -> None:
    fake.list_tools()
    fake.list_tools()
    folder = tmp_path / "data" / "mcp"
    log = folder / "fake.log"
    assert (mode(folder), mode(log)) == (0o700, 0o600)
    assert log.read_text().count("fake server started") == 2


def test_a_server_without_a_command_line() -> None:
    with pytest.raises(McpUnavailable) as raised:
        client_for(FAKE_SERVER, get_settings()).list_tools()
    assert (raised.value.code, str(raised.value)) == ("no_command", "server fake: no_command")


def test_a_command_that_cannot_start(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", str(tmp_path / "no-such-program"))
    with pytest.raises(McpUnavailable) as raised:
        client_for(FAKE_SERVER, get_settings()).list_tools()
    assert str(raised.value) == "server fake: start_failed"


def test_a_server_that_stops(fake) -> None:
    with pytest.raises(McpUnavailable) as raised:
        fake.call_tool("stop", {})
    assert (raised.value.code, raised.value.__cause__) == ("closed", None)


def test_a_server_that_takes_too_long_is_ended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "2")
    pid_file = tmp_path / "pid"
    started = time.monotonic()
    with pytest.raises(McpUnavailable) as raised:
        client_for(FAKE_SERVER, get_settings()).call_tool(
            "wait", {"seconds": 30, "pid_file": str(pid_file)}
        )
    assert raised.value.code == "timeout"
    assert time.monotonic() - started < 10
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_the_sdk_and_no_telemetry() -> None:
    version = tuple(int(part) for part in importlib.metadata.version("mcp").split(".")[:2])
    assert version == (2, 3)
    assert importlib.util.find_spec("opentelemetry.sdk") is None


@pytest.fixture
def fake_moved(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
    return client_for(FAKE_SERVER, get_settings())


def test_two_calls_start_two_processes_and_a_thread_can_call(fake_moved) -> None:
    fake_moved.list_tools()
    fake_moved.call_tool("echo", {"text": "one"})
    log = get_settings().data_dir / "mcp" / "fake.log"
    assert log.read_text().count("fake server started") == 2
    found: list[str] = []

    def work() -> None:
        outcome = fake_moved.call_tool("echo", {"text": "from-thread"})
        found.append(outcome.structured["text"])

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert found == ["from-thread"]


def test_a_declared_variable_that_is_unset_stays_unset(
    fake_moved, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FAKE_PASSED", raising=False)
    seen = fake_moved.call_tool("env", {"name": "FAKE_PASSED"}).structured["result"]
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


def test_a_string_result_is_structured(fake_moved) -> None:
    outcome = fake_moved.call_tool("env", {"name": "PATH"})
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


def test_an_unexpected_session_error_passes_through(
    fake_moved, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(_self: object) -> None:
        raise RuntimeError("session broke")

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", broken)
    with pytest.raises(ExceptionGroup) as grouped:
        fake_moved.list_tools()
    assert any(isinstance(item, RuntimeError) for item in _leaves(grouped.value))


def test_a_bare_connection_error_is_closed(fake_moved, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise MCPError(-32000, "Connection closed")

    monkeypatch.setattr("conductor.mcp_client.client.stdio_client", boom)
    with pytest.raises(McpUnavailable) as raised:
        fake_moved.list_tools()
    assert (raised.value.code, raised.value.__cause__) == ("closed", None)
    assert "Connection closed" not in str(raised.value)


def test_a_closed_connection_and_a_mixed_group(fake_moved, monkeypatch: pytest.MonkeyPatch) -> None:
    async def closed(_self: object) -> None:
        raise MCPError(-32000, "Connection closed")

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", closed)
    with pytest.raises(McpUnavailable) as raised:
        fake_moved.list_tools()
    assert (raised.value.code, raised.value.__cause__) == ("closed", None)

    async def mixed(_self: object) -> None:
        raise ExceptionGroup("mixed", [MCPError(-32000, "Connection closed"), RuntimeError("nope")])

    monkeypatch.setattr("conductor.mcp_client.client.ClientSession.initialize", mixed)
    with pytest.raises(ExceptionGroup) as grouped:
        fake_moved.list_tools()
    assert any(isinstance(item, RuntimeError) for item in _leaves(grouped.value))
