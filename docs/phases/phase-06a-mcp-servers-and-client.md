# Phase 6a: MCP servers and the client

## Goal

The first part of reaching tools over MCP, with nothing in the graph changed yet:

- **declarations**: a domain names its MCP servers (`McpServer`), each with the environment variables it may receive; a tool action names the server it runs on;
- **settings**: each server's command line comes from `CONDUCTOR_MCP__<NAME>`, and one timeout, `CONDUCTOR_MCP_TIMEOUT`, bounds every call;
- **the client** (`conductor.mcp_client.client`, critical): a synchronous client over the official `mcp` SDK that starts a server as a child process over stdio, lists its tools or calls one tool, and stops it again, mapping every way a server can fail to four constant codes.

Decided with the owner (2026-11-09): Phase 6 has **three parts** (6a declarations and the client; 6b the start-up check of tool schemas and `conductor doctor`; 6c the MCP step runner in the runtime); a server process lives for **one call**; a server's command comes from **a setting per server**; the start-up check (6b) compares **fields**, not whole schemas; a domain may have **one or more named servers**; a server's stderr goes to **a private log file**; the call timeout is **a setting, default 60 seconds**.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rules 2 and 3), `docs/architecture.md` ("Domains and the action registry", "Privacy and safety boundary")
- `src/conductor/registry.py`, `src/conductor/config.py`, `src/conductor/store.py` (how private files are made)

## Starting state

Phase 5e is built and verified, and everything is committed: N is `564`. **Sections: core.** `mcp` is not installed. No `conductor/mcp_client/` exists.

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | add `"mcp>=2.3,<2.4",` to `dependencies`, after `langgraph-checkpoint-sqlite`; then run `.venv/bin/python -m pip install -e ".[dev]"` once |
| `src/conductor/registry.py` | `McpServer`, `Domain.servers`, `Action.server`, and their checks (Part 1) |
| `src/conductor/config.py` | `mcp`, `mcp_timeout`, `mcp_timeout_seconds`, `mcp_command`, and their checks (Part 2) |
| `src/conductor/mcp_client/__init__.py` | empty |
| `src/conductor/mcp_client/client.py` | the client (Part 3, critical) |
| `scripts/critical_modules.txt` | add the line `mcp_client/client.py` after `runtime.py` |
| `docs/testing.md` | under "Critical modules", add `` - `mcp_client/client.py` (what a tool server receives, and every way it can fail; Phase 6a) `` after the `runtime.py` line |
| `tests/mcp_fake_server.py` | given: a small MCP server the tests start as a child process (not a test module) |
| `tests/unit/test_mcp_declarations.py`, `tests/integration/test_mcp_client.py` | given |
| `tests/unit/test_mcp_declarations_more.py`, `tests/integration/test_mcp_client_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- The start-up check of tools against actions, `conductor doctor` (6b); the MCP step runner, the runtime, the graph, any command (6c); the finance domain (Phase 9).
- Long-lived sessions, a background event loop or thread, reconnecting; resources, prompts, sampling, elicitation, roots, notifications, progress; any transport but stdio.
- Reading a tool's text content; logging tool arguments or results anywhere.
- Changes to the demo domain, contracts, the graph, the runtime, or the CLI.

## Dependencies

`mcp>=2.3,<2.4` (2.3.0 is current and is what `finances` serves with). It brings `anyio`, `httpx2`, `jsonschema`, `mcp-types`, `opentelemetry-api`, `pyjwt`, `python-multipart`, `sse-starlette`, `starlette`, and `uvicorn`; the project uses only `mcp.ClientSession`, `mcp.StdioServerParameters`, `mcp.client.stdio` (`stdio_client`, `get_default_environment`), `mcp.shared.exceptions.MCPError`, and `anyio.fail_after`. `opentelemetry-api` without an SDK records nothing (`AGENTS.md` rule 2 forbids the SDK and exporters, which stay uninstalled).

## Design

```python
# conductor/registry.py: added and changed
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")   # and not starting with "CONDUCTOR_"

@dataclass(frozen=True)
class McpServer:
    name: str
    env: tuple[str, ...] = ()        # variables passed through to the server, when set

@dataclass(frozen=True)
class Action:
    ...                               # the seven 2c fields, unchanged
    server: str | None = None         # the McpServer a tool action runs on

@dataclass(frozen=True)
class Domain:
    ...                               # name, description, actions, rules, unchanged
    servers: tuple[McpServer, ...] = ()
```

The registry checks, with these messages (`<d>` the domain, `<s>` the server, `<a>` the action):

| Checked | Message |
|---|---|
| after the domain's description and before its actions, for each server in order: its name against the registry's name pattern | `server <d>.<s>: not a valid name` |
| a second server of that name in the domain | `server <d>.<s>: declared twice` |
| a server name an earlier domain declared | `server <d>.<s>: also declared by <earlier domain>` |
| each environment name (counting from 1) against `_ENV_NAME`, refusing any that starts with `CONDUCTOR_` | `server <d>.<s>: environment name <n> is not valid` |
| after an action's 2c checks: a `server` the domain does not declare | `action <d>.<a>: no server <server> in this domain` |
| a tool action with no `server` in a domain that has servers | `action <d>.<a>: a tool action of a domain with servers names one` |
| an agent action with a `server` | `action <d>.<a>: only a tool action names a server` |

```python
# conductor/config.py: added
MCP_TIMEOUT_MESSAGE = "must be whole seconds from 1 to 600"
MCP_COMMAND_MESSAGE = "must be a command line"
MCP_NAME_MESSAGE = "not a server name"
MCP_MAPPING_MESSAGE = "must map server names to command lines"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONDUCTOR_", env_nested_delimiter="__")
    ...
    mcp_timeout: str = "60"          # after demo
    mcp: dict[str, str] = {}         # CONDUCTOR_MCP__<NAME>=<command line>; keys arrive lowercased

    @property
    def mcp_timeout_seconds(self) -> int: ...
    def mcp_command(self, name: str) -> tuple[str, ...] | None: ...   # shlex.split of mcp[name], or None
```

The checks, after the `CONDUCTOR_DEMO` problem: `mcp_timeout` must fully match `^[1-9][0-9]{0,2}$` and be at most 600 (`CONDUCTOR_MCP_TIMEOUT: must be whole seconds from 1 to 600`); then, for each key of `mcp` in sorted order, a key that is not a valid server name gives `CONDUCTOR_MCP__<KEY in upper case>: not a server name`, and a value that `shlex.split` refuses or splits into nothing gives `CONDUCTOR_MCP__<KEY in upper case>: must be a command line`. When building `Settings()` itself raises a `ValidationError` (only `CONDUCTOR_MCP` set to JSON that is not an object of strings can), `get_settings` raises `SettingsError("CONDUCTOR_MCP: must map server names to command lines")` alone, from `None`.

```python
# conductor/mcp_client/client.py (critical)
UnavailableCode = Literal["no_command", "start_failed", "timeout", "closed"]

class McpUnavailable(Exception):
    def __init__(self, server: str, code: UnavailableCode) -> None: ...   # str(): "server <name>: <code>"
    server: str
    code: UnavailableCode

@dataclass(frozen=True)
class ToolInfo:
    name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    read_only: bool | None           # the tool's readOnlyHint, or None without annotations

@dataclass(frozen=True)
class ToolOutcome:
    is_error: bool
    structured: dict[str, Any] | None   # the structured content of a successful call; None on an error

class McpClient:
    def list_tools(self) -> tuple[ToolInfo, ...]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...

def client_for(server: McpServer, settings: Settings) -> McpClient: ...
```

Each `list_tools` or `call_tool` is one whole session, run with `asyncio.run` from synchronous code:

1. the command is `settings.mcp_command(server.name)`; `None` raises `McpUnavailable(name, "no_command")` before anything starts;
2. the environment is `get_default_environment()` (the SDK's safe set: `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`) plus each of `server.env` that is set in this process, and nothing else;
3. the server's stderr is appended to `<data_dir>/mcp/<name>.log`, the folder made `0700` and the file made `0600` when missing (with `os.open`, as `store.py` does), whatever the umask;
4. inside `anyio.fail_after(<the timeout>)`: `stdio_client(StdioServerParameters(command=argv[0], args=argv[1:], env=...), errlog=<the log>)`, then `ClientSession(read, write, read_timeout_seconds=<the timeout>)`, `initialize()`, and the one request;
5. failures map to codes, raised `from None`: an `OSError` while starting (no such program, not executable) is `start_failed`; a `TimeoutError` is `timeout`; an `MCPError`, alone or as every leaf of the exception groups `anyio` wraps it in, is `closed`; anything else passes through.

`list_tools` returns a `ToolInfo` per tool, in the server's order. `call_tool` returns `ToolOutcome(result.is_error, None if result.is_error else result.structured_content)`. A tool error (the tool raised, refused its arguments, or does not exist) is a `ToolOutcome` with `is_error` true, not an exception. No text content is read or kept.

## Facts about the MCP SDK

Found on 2026-11-09 with `mcp` 2.3.0, against a server built with `mcp.server.mcpserver.MCPServer` (as `finances` builds its own):

- `ClientSession(read, write, read_timeout_seconds=...)`, `await session.initialize()`, `list_tools()` (`.tools`, each with `name`, `input_schema`, `output_schema`, `annotations.read_only_hint`), and `call_tool(name, arguments)` returning a `CallToolResult` with `is_error`, `structured_content`, and `content`.
- **Tool failures are results, not exceptions**: a tool that raises, arguments the tool refuses, and an unknown tool name all give `is_error=True` with a text message. That text can hold the arguments (`input_value=5` in a refused argument's message), so it is never read.
- A tool returning a Pydantic model gets that model's output schema and structured content; `str` and `list[...]` returns are wrapped as `{"result": ...}`; `dict[str, Any]` (every `finances` tool) gets `{"additionalProperties": true, "type": "object"}` and its dict as structured content; a bare `dict` return gets **no** output schema and **no** structured content.
- `stdio_client` passes the child only `DEFAULT_INHERITED_ENV_VARS` (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`) unless `env` is given: a variable set in the parent did not reach the server. The server's stderr goes to `errlog`.
- Starting a Python stdio server, initializing, and calling one tool took about 0.25 seconds.
- A missing program raises `FileNotFoundError` at once. A server that never answers, or writes non-protocol lines, raises `TimeoutError` from `anyio.fail_after`, about 2 seconds after the timeout (the SDK waits that long for the process to end). A server that exits, at start or during a call, raises an `ExceptionGroup` (nested) whose leaves are all `MCPError("Connection closed")`. In every case no server process was left running.
- `mcp` depends on `opentelemetry-api`; without `opentelemetry-sdk` installed, nothing is recorded or sent.

## Requirements

### Part 1: declarations

- **R1.** `McpServer`, `Action.server`, and `Domain.servers` are as under Design, each new field with its default, so every existing declaration (the demo domain included) is unchanged.
- **R2.** The registry checks servers and server references in the Design's order, with its messages.

### Part 2: settings

- **R3.** `Settings.mcp`, `mcp_timeout`, `mcp_timeout_seconds`, and `mcp_command`, their checks, their order, and the `CONDUCTOR_MCP` mapping message are as under Design; no message contains a command line or a value.

### Part 3: the client (critical)

- **R4.** `client_for` and `McpClient` run each `list_tools` and `call_tool` as one whole session in the Design's five steps; no session, process, or event loop outlives the call.
- **R5.** A server receives exactly the SDK's safe variables plus its declared ones that are set; in particular no `CONDUCTOR_` variable and no undeclared variable.
- **R6.** The server's stderr is appended to its private log file as under Design.
- **R7.** `list_tools` and `call_tool` return `ToolInfo` and `ToolOutcome` as under Design; a tool error is an outcome, and no text of it is kept.
- **R8.** Every failure to reach a server is `McpUnavailable` with one of the four codes, raised `from None`, with the message `server <name>: <code>`; other exceptions pass through.

### Part 4: the rules

- **R9.** `mcp` is imported only in `conductor/mcp_client/`; `client.py` imports from the project only `conductor.config` and `conductor.registry`; nothing else in `src/` imports `conductor.mcp_client` yet. No OpenTelemetry SDK is installed.
- **R10.** `mcp_client/client.py` reaches 100% of lines and branches and joins the critical modules; `registry.py` and `config.py` stay at 100%.

## Given tests

24 tests in two files (counting each parameter set), and the fake server they start. Do not change them; if one fails, the code is wrong.

`tests/mcp_fake_server.py` (given; copy it exactly)

```python
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
```

`tests/unit/test_mcp_declarations.py` (15 tests)

```python
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
```

`tests/integration/test_mcp_client.py` (9 tests)

```python
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
```

## Tests to write

In `tests/unit/test_mcp_declarations_more.py`, each with its deciding input:

- R2: an environment name of 65 characters is refused; the server checks come before the action checks (a domain with a bad server name and a bad action names the server); a domain with no servers keeps tool actions with no `server` (the demo domain).
- R3: a key that is not a server name (`CONDUCTOR_MCP__9LEDGER`) gives `not a server name`; with two bad keys, their problems come in sorted order after the timeout's; `mcp_command` of a quoted path with spaces keeps it whole.

In `tests/integration/test_mcp_client_more.py`:

- R4: two calls in a row start two processes (the log gets two start lines); a call from inside a thread works.
- R5: a declared variable that is not set is not passed (the server sees `<unset>`).
- R6: with umask `0o022` (set and restored in the test), an existing log folder made `0755` by the test is left as it is, but a new log file is `0600`.
- R7: a tool returning `str` (`env`) gives `{"result": ...}` as `structured`.
- R8: a command that is not executable (the fake server's path itself) gives `start_failed`; an exception other than these four from inside the session (replace `ClientSession.initialize` with one that raises `RuntimeError`) passes through.

## Rules for this phase

- **Network** (`AGENTS.md` rule 3): the only new connection is a child process over stdio; no port, no HTTP. Tests start only `tests/mcp_fake_server.py` and programs that cannot speak MCP.
- **No telemetry** (`AGENTS.md` rule 2): no OpenTelemetry SDK or exporter; the given test checks it.
- **Privacy**: a server sees only the environment the Design names; tool arguments and results are never logged by conductor; the server's own log stays under the data folder, private.
- **Critical module**: `mcp_client/client.py` joins `scripts/critical_modules.txt` and `docs/testing.md`.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 24 = 588 passed; `critical coverage` passed (it now includes `mcp_client/client.py`);
- the given files: `.venv/bin/python -m pytest tests/unit/test_mcp_declarations.py tests/integration/test_mcp_client.py --no-cov`, exactly `24 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/registry.py,*/conductor/config.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 6a`, after the progress entry: `Reports OK.`;
- `.venv/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"` prints a `2.3.x` version, and `.venv/bin/python -c "import importlib.util as u; print(u.find_spec('opentelemetry.sdk'))"` prints `None`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) mcp|^(from|import) anyio" -- src | grep -v "^src/conductor/mcp_client/"`
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/mcp_client | grep -v -E ":(from conductor\.config|from conductor\.registry) import "`
  - `git grep --untracked -n -E "conductor\.mcp_client" -- src | grep -v "^src/conductor/mcp_client/"`
  - `git grep --untracked -n -E "\.content\b|\.text\b|logging|print\(" -- src/conductor/mcp_client`
- `git diff --stat HEAD -- src/conductor/contracts src/conductor/domains src/conductor/graph src/conductor/runtime.py src/conductor/cli tests/unit/test_registry.py tests/unit/test_registry_more.py tests/unit/test_config.py tests/support.py tests/conftest.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 6a: MCP servers and the client (YYYY-MM-DD)`, with `Tests: 564 -> <passed> (given 24)`.
