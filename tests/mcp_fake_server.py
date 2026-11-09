"""A small MCP server for the tests, started as a child process over stdio.

Run it as: <python> tests/mcp_fake_server.py
"""

import os
import sys
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel

server = MCPServer("fake")


class Echoed(BaseModel):
    text: str


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def echo(text: str) -> Echoed:
    """Repeat the text back."""
    return Echoed(text=text)


@server.tool()
def fail(reason: str) -> Echoed:
    """Always fails, with the reason in its error."""
    raise ValueError(reason)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def env(name: str) -> str:
    """The value of an environment variable in this process, or <unset>."""
    return os.environ.get(name, "<unset>")


@server.tool()
def stop() -> str:
    """Ends this process at once."""
    os._exit(3)


@server.tool()
def wait(seconds: int, pid_file: str) -> str:
    """Writes this process's id to pid_file, then sleeps."""
    Path(pid_file).write_text(str(os.getpid()))
    time.sleep(seconds)
    return "woke"


if __name__ == "__main__":
    print("fake server started", file=sys.stderr, flush=True)
    server.run("stdio")
