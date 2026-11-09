import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.shared.exceptions import MCPError

from conductor.config import Settings
from conductor.registry import McpServer

UnavailableCode = Literal["no_command", "start_failed", "timeout", "closed"]


class McpUnavailable(Exception):
    def __init__(self, server: str, code: UnavailableCode) -> None:
        self.server = server
        self.code = code
        super().__init__(f"server {server}: {code}")


@dataclass(frozen=True)
class ToolInfo:
    name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    read_only: bool | None


@dataclass(frozen=True)
class ToolOutcome:
    is_error: bool
    structured: dict[str, Any] | None


class McpClient:
    def __init__(self, server: McpServer, settings: Settings) -> None:
        self._server = server
        self._settings = settings

    def list_tools(self) -> tuple[ToolInfo, ...]:
        return self._run(_listed)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        return self._run(lambda session: _called(session, name, arguments))

    def _run(self, work: Callable[[ClientSession], Awaitable[Any]]) -> Any:
        command = self._settings.mcp_command(self._server.name)
        if command is None:
            raise McpUnavailable(self._server.name, "no_command")
        try:
            return asyncio.run(self._session(command, work))
        except TimeoutError:
            raise McpUnavailable(self._server.name, "timeout") from None
        except OSError:
            raise McpUnavailable(self._server.name, "start_failed") from None
        except MCPError:
            raise McpUnavailable(self._server.name, "closed") from None
        except BaseExceptionGroup as error:
            if all(isinstance(leaf, MCPError) for leaf in _leaves(error)):
                raise McpUnavailable(self._server.name, "closed") from None
            raise

    async def _session(
        self,
        command: tuple[str, ...],
        work: Callable[[ClientSession], Awaitable[Any]],
    ) -> Any:
        parameters = StdioServerParameters(
            command=command[0],
            args=list(command[1:]),
            env=_environment(self._server),
        )
        log_path = _log_path(self._settings.data_dir, self._server.name)
        with anyio.fail_after(self._settings.mcp_timeout_seconds):
            with log_path.open("a", encoding="utf-8") as errlog:
                async with stdio_client(parameters, errlog=errlog) as (read, write):
                    async with ClientSession(
                        read,
                        write,
                        read_timeout_seconds=self._settings.mcp_timeout_seconds,
                    ) as session:
                        await session.initialize()
                        return await work(session)


def client_for(server: McpServer, settings: Settings) -> McpClient:
    return McpClient(server, settings)


def _environment(server: McpServer) -> dict[str, str]:
    found = dict(get_default_environment())
    for name in server.env:
        if name in os.environ:
            found[name] = os.environ[name]
    return found


def _log_path(data_dir: Path, name: str) -> Path:
    folder = data_dir / "mcp"
    path = folder / f"{name}.log"
    if not folder.exists():
        folder.mkdir(parents=True, mode=0o700)
        folder.chmod(0o700)
    if not path.exists():
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    return path


def _leaves(error: BaseException) -> tuple[BaseException, ...]:
    if isinstance(error, BaseExceptionGroup):
        found: list[BaseException] = []
        for item in error.exceptions:
            found.extend(_leaves(item))
        return tuple(found)
    return (error,)


async def _listed(session: ClientSession) -> tuple[ToolInfo, ...]:
    found = await session.list_tools()
    return tuple(_tool_info(tool) for tool in found.tools)


def _tool_info(tool: Any) -> ToolInfo:
    annotations = tool.annotations
    return ToolInfo(
        name=tool.name,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        read_only=None if annotations is None else annotations.read_only_hint,
    )


async def _called(session: ClientSession, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    result = await session.call_tool(name, arguments)
    structured = None if result.is_error else result.structured_content
    return ToolOutcome(is_error=result.is_error, structured=structured)
