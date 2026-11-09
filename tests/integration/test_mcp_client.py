import importlib.metadata
import importlib.util
import os
import shlex
import stat
import sys
import time
from pathlib import Path

import pytest

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
