# Phase 6b: the tool check and the doctor

## Goal

Before any run can use a tool, code checks that the tool is what the domain says it is:

- `conductor.mcp_client.check` (critical): for every server of every registered domain, list its tools once and compare each tool action with its tool: the tool exists, the action's argument fields fit the tool's input, **a `read` action's tool is marked read-only**, and the tool declares an output schema whose fields, when it lists any, fit the action's result;
- the runtime runs this check **once per opening, before its first run call** (`ask` or `resume`), and **refuses the run** when anything is wrong; the commands print every problem;
- `conductor doctor` shows one line per server.

Decided with the owner (2026-11-09): the check runs **each time the runtime opens**; a failed check **refuses the runtime**; a `read` action **needs a tool with `readOnlyHint: true`** (a `propose` or `write` action may use any tool), because a `read` step runs without approval; a tool **must declare an output schema**, and its fields are compared **when it lists any** (an open object, as every `finances` tool returns, is checked per call in 6c). Earlier (6a): fields are compared, not whole schemas.

Decided by the architect for this phase, within those answers: the check runs in `runtime.ask` and `runtime.resume` (once per opened runtime) rather than inside `open_runtime`, so a decision command run with `--no-resume`, which only records, never starts a server (otherwise a broken server would also block rejecting or cancelling), and `open_runtime`'s signature stays as 5d made it (the 5e tests replace it with a stand-in that takes only `model`).

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 7), `docs/architecture.md` ("Domains and the action registry")
- `src/conductor/mcp_client/client.py` (6a), `src/conductor/registry.py`, `src/conductor/runtime.py`, `src/conductor/domains/__init__.py`, `src/conductor/diagnostics.py`, `src/conductor/cli/main.py`, `tests/mcp_fake_server.py`

## Starting state

Phase 6a is built and verified, and everything is committed: N is `600`. **Sections: cli, core.** No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/mcp_client/check.py` | the check (Part 1, critical) |
| `src/conductor/domains/__init__.py` | `registered(settings)` (Part 2) |
| `src/conductor/runtime.py` | `check_tools`, and the check before `ask` and `resume` (Part 2) |
| `src/conductor/cli/main.py` | printing a failed check (Part 2) |
| `src/conductor/diagnostics.py` | the server lines of `conductor doctor` (Part 3) |
| `scripts/critical_modules.txt` | add the line `mcp_client/check.py` after `mcp_client/client.py` |
| `docs/testing.md` | under "Critical modules", add `` - `mcp_client/check.py` (a tool action runs only on the tool it says, and a `read` action only on a read-only tool; Phase 6b) `` after the `mcp_client/client.py` line |
| `tests/unit/test_tool_check.py`, `tests/e2e/test_cli_tool_check.py` | given |
| `tests/unit/test_tool_check_more.py`, `tests/e2e/test_cli_tool_check_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Calling tools for steps, checking results per call, the step runner (6c); the finance domain (Phase 9).
- Caching the check, checking in the background, retrying a server, leaving a failing domain out.
- Comparing descriptions, titles, defaults, bounds, formats, enums, or nested fields; comparing a `propose` or `write` action's tool hints.
- Changes to `client.py`, the registry, contracts, the graph, or the given tests of earlier phases.

## Dependencies

None new.

## Design

```python
# conductor/mcp_client/check.py (critical)
CHECK_FAILED_MESSAGE = "the tool check failed"

@dataclass(frozen=True)
class CheckProblem:
    where: str                      # "server <s>" or "action <domain>.<action>"
    message: str

    @property
    def text(self) -> str: ...      # f"{where}: {message}"

@dataclass(frozen=True)
class ServerCheck:
    server: str
    tools: int | None               # how many tools the server listed; None when it could not be reached
    actions: int                    # how many tool actions name this server
    problems: tuple[CheckProblem, ...]

class ToolCheckFailed(Exception):   # str(): CHECK_FAILED_MESSAGE
    problems: tuple[CheckProblem, ...]

def json_types(schema: dict[str, Any], defs: dict[str, Any]) -> tuple[str, ...]: ...
def check_servers(registry: Registry, settings: Settings, *, connect: Callable[[McpServer, Settings], McpClient] = client_for) -> tuple[ServerCheck, ...]: ...
def check_registry(registry: Registry, settings: Settings, *, connect: ... = client_for) -> tuple[CheckProblem, ...]: ...   # every problem of check_servers, in order
```

`json_types(schema, defs)`, sorted and without repeats: a `"type"` that is a string gives that type, a list gives its members; `"$ref": "#/$defs/<Name>"` gives the types of `defs[<Name>]`; `"anyOf"` or `"oneOf"` gives the types of all its members; anything else gives `("any",)`.

`check_servers` goes through the registry's domains in order, and each domain's servers in order. For each server it calls `connect(server, settings).list_tools()` once. An `McpUnavailable` gives one problem, `CheckProblem("server <s>", <code>)`, and that server's actions are not checked. Otherwise each tool action naming the server, in declaration order, is checked as below, `where` being `action <domain>.<action>`. A server with no tool action is still listed (its `actions` is 0). A registry without servers starts nothing.

The checks of one action, in this order, with these messages (`A` is `action.args.model_json_schema()`, `T` the tool's `input_schema`, types written joined by `|`):

| # | Rule | Message |
|---|---|---|
| 1 | a tool named `action.target` is listed; otherwise stop here | `no tool <target> on server <s>` |
| 2 | for each property of `A`, in order: it is a property of `T` | `field <f> is not in the tool's input` |
| 3 | and its `json_types` (with `A`'s and `T`'s own `$defs`) are equal | `field <f> has types <A's>, the tool's <T's>` |
| 4 | each name in `T`'s `required`, in order, is a property of `A` | `the tool requires <f>, which the action does not have` |
| 5 | an action with effect `read` needs `read_only` to be `True` | `a read action needs a tool marked read-only` |
| 6 | the tool has an output schema `O`; otherwise stop here | `the tool declares no output schema` |
| 7 | when `O` has `properties`: each of them, in order, is a property of the result schema `R` (`action.result.model_json_schema()`) | `the tool's result field <f> is not in the action's result` |
| 8 | and its types equal `R`'s | `result field <f> has types <R's>, the tool's <O's>` |
| 9 | and each name in `R`'s `required`, in order, is in `O`'s `required` | `the tool does not promise result field <f>` |

An `O` without `properties` (an open object) passes 7 to 9.

```python
# conductor/domains/__init__.py: added
def registered(settings: Settings) -> tuple[Domain, ...]: ...   # DOMAINS, plus demo.DOMAIN at the end when settings.demo_on
```

```python
# conductor/runtime.py: added
def check_tools(runtime: Runtime) -> None: ...   # check_registry(runtime.registry, <its settings>); problems raise ToolCheckFailed
```

`open_runtime` builds its registry as `Registry(domains.registered(settings))` (read through the module, so tests can replace `domains.DOMAINS`) and is otherwise as in 5d, with the same signature; it keeps the settings it was given for `check_tools`. `check_tools(runtime)` runs `check_registry` and raises `ToolCheckFailed(problems)` when there is any; after one success it does nothing more for that runtime. `ask` and `resume` call it first, before an id is taken, a lease acquired, or a run looked up.

The commands: `ask`, `resume`, and the five decision commands (when they resume) print a `ToolCheckFailed` as `Error: the tool check failed` on stderr, then one line `  <problem text>` per problem, and exit 1; for a decision command the recorded line stays on stdout before it, as for any failed resume (5e). A decision command run with `--no-resume` never calls `ask` or `resume`, so it starts no server.

`conductor doctor`: after the model line, one line per server of `domains.registered(settings)`, from `check_servers`, in order:

| Case | Line |
|---|---|
| reached, no problem | `ok    server <s>: <n> tool(s), <m> action(s) checked` (`1 tool`, `5 tools`, `1 action`, `0 actions`) |
| not reached | `FAIL  server <s>: <code>` |
| a problem of an action | `FAIL  server <s>: <the problem's text>`, one line per problem |

Each `FAIL` line counts in the summary. Without servers, the output is as before.

## Facts about the tools the check meets

From `finances` (its 31 tools, listed through the SDK's in-memory `Client`, on 2026-11-09), and the SDK as in 6a:

- Every read tool carries `readOnlyHint: true`; the `propose_*` tools and `log_advice` carry `false`.
- Every tool's output schema is `{"additionalProperties": true, "title": "<name>DictOutput", "type": "object"}`, with no `properties`: result fields are checked per call (6c), not here.
- Input fields are plain (`{"type": "string"}`, `{"type": "integer", "minimum": ...}`) or optional dates as `{"anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]}`; an action contract field `str | None = None` gives `{"anyOf": [{"type": "string"}, {"type": "null"}]}`, so both have the types `null|string`.
- A tool's input schema lists `required` only when it has required fields (`find_merchants` has `["phrase"]`, most read tools none).
- Listing the fake server's tools over stdio takes about 0.25 seconds, so a runtime with one server opens about that much slower.

## Requirements

### Part 1: the check (critical)

- **R1.** `json_types` is as under Design.
- **R2.** `check_servers` lists each server once, in order, and returns a `ServerCheck` per server; `check_registry` returns all their problems in order; a registry without servers calls `connect` never.
- **R3.** The nine checks of one action run in the Design's order with its messages, stopping after 1 or 6 as it says.
- **R4.** A server that cannot be reached is one problem with its code, and none of its actions is checked.
- **R5.** Every message is the Design's constant text with names, types, and codes only; no schema, description, or value is put into one.

### Part 2: the runtime and the commands

- **R6.** `domains.registered`, `check_tools`, and the check at the start of `ask` and `resume` are as under Design: a failed check raises `ToolCheckFailed` before any id, lease, event, or checkpoint; a passed check is not repeated within one runtime.
- **R7.** The commands print a failed check as under Design; a `--no-resume` command starts no server.

### Part 3: the doctor

- **R8.** `conductor doctor` prints the server lines as under Design and counts each `FAIL` line.

### Part 4: the rules

- **R9.** `check.py` imports from the project only `conductor.config`, `conductor.mcp_client.client`, and `conductor.registry`; it never calls a tool (only `list_tools`).
- **R10.** `mcp_client/check.py` reaches 100% of lines and branches and joins the critical modules; `runtime.py`, `cli/main.py`, `diagnostics.py`, and `domains/__init__.py` stay at 100%.

## Given tests

26 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_tool_check.py` (20 tests)

```python
from dataclasses import replace

import pytest
from pydantic import Field

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.mcp_client.check import CheckProblem, check_registry, json_types
from conductor.mcp_client.client import McpUnavailable, ToolInfo
from conductor.registry import Action, Domain, McpServer, Registry


class SpendArgs(Contract):
    month: str
    limit: int = Field(default=50, ge=1, le=200)
    start: str | None = None


class Open(Contract):
    rows: list[str] = []


class Note(Contract):
    note_id: str


OPEN_OUTPUT = {"additionalProperties": True, "title": "get_spendingDictOutput", "type": "object"}
SPENDING = ToolInfo(
    name="get_spending",
    input_schema={
        "type": "object",
        "properties": {
            "month": {"title": "Month", "type": "string"},
            "limit": {"default": 50, "maximum": 200, "minimum": 1, "type": "integer"},
            "start": {"anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]},
            "by": {"default": "category", "type": "string"},
        },
        "required": ["month"],
    },
    output_schema=OPEN_OUTPUT,
    read_only=True,
)
WRITE_NOTE = ToolInfo(
    name="write_note",
    input_schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": []},
    output_schema={
        "type": "object",
        "properties": {"note_id": {"type": "string"}},
        "required": ["note_id"],
    },
    read_only=False,
)


class Title(Contract):
    title: str


SPEND = Action("spend", "Spending.", "tool", "get_spending", "read", SpendArgs, Open, "ledger")
NOTE = Action("note", "Write a note.", "tool", "write_note", "write", Title, Note, "ledger")
FINANCE = Domain("finance", "Money.", (SPEND, NOTE), servers=(McpServer("ledger"),))


class FakeClient:
    def __init__(self, tools: tuple[ToolInfo, ...] | McpUnavailable) -> None:
        self.tools = tools
        self.listed = 0

    def list_tools(self) -> tuple[ToolInfo, ...]:
        self.listed += 1
        if isinstance(self.tools, McpUnavailable):
            raise self.tools
        return self.tools


def check(domain: Domain, *tools: ToolInfo, unavailable: str | None = None):
    found = McpUnavailable("ledger", unavailable) if unavailable else tools
    clients: dict[str, FakeClient] = {}

    def connect(server: McpServer, settings):
        return clients.setdefault(server.name, FakeClient(found))

    problems = check_registry(Registry((domain,)), get_settings(), connect=connect)
    return [problem.text for problem in problems], clients


@pytest.mark.parametrize(
    ("schema", "types"),
    [
        ({"type": "string"}, ("string",)),
        ({"anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]}, ("null", "string")),
        ({"type": ["integer", "null"]}, ("integer", "null")),
        ({"$ref": "#/$defs/Inner"}, ("object",)),
        ({"enum": ["a", "b"]}, ("any",)),
    ],
)
def test_the_json_types_of_a_field(schema: dict, types: tuple[str, ...]) -> None:
    defs = {"Inner": {"type": "object", "properties": {}}}
    assert json_types(schema, defs) == types


def test_a_domain_that_fits_its_server() -> None:
    texts, clients = check(FINANCE, SPENDING, WRITE_NOTE)
    assert texts == []
    assert clients["ledger"].listed == 1


def test_a_registry_without_servers_starts_nothing() -> None:
    def connect(server, settings):
        raise AssertionError("a server was started")

    from conductor.domains import demo

    assert check_registry(Registry((demo.DOMAIN,)), get_settings(), connect=connect) == ()


@pytest.mark.parametrize(
    ("tools", "message"),
    [
        ((WRITE_NOTE,), "action finance.spend: no tool get_spending on server ledger"),
        (
            (
                replace(
                    SPENDING,
                    input_schema={
                        **SPENDING.input_schema,
                        "properties": {"month": {"type": "string"}, "start": {"type": "string"}},
                    },
                ),
                WRITE_NOTE,
            ),
            "action finance.spend: field limit is not in the tool's input",
        ),
        (
            (
                replace(
                    SPENDING,
                    input_schema={
                        **SPENDING.input_schema,
                        "properties": {
                            **SPENDING.input_schema["properties"],
                            "month": {"type": "integer"},
                        },
                    },
                ),
                WRITE_NOTE,
            ),
            "action finance.spend: field month has types string, the tool's integer",
        ),
        (
            (
                replace(
                    SPENDING, input_schema={**SPENDING.input_schema, "required": ["month", "by"]}
                ),
                WRITE_NOTE,
            ),
            "action finance.spend: the tool requires by, which the action does not have",
        ),
        (
            (replace(SPENDING, read_only=None), WRITE_NOTE),
            "action finance.spend: a read action needs a tool marked read-only",
        ),
        (
            (replace(SPENDING, read_only=False), WRITE_NOTE),
            "action finance.spend: a read action needs a tool marked read-only",
        ),
        (
            (replace(SPENDING, output_schema=None), WRITE_NOTE),
            "action finance.spend: the tool declares no output schema",
        ),
        (
            (
                SPENDING,
                replace(
                    WRITE_NOTE,
                    output_schema={
                        "type": "object",
                        "properties": {"note_id": {"type": "string"}, "url": {"type": "string"}},
                        "required": ["note_id"],
                    },
                ),
            ),
            "action finance.note: the tool's result field url is not in the action's result",
        ),
        (
            (
                SPENDING,
                replace(
                    WRITE_NOTE,
                    output_schema={"type": "object", "properties": {"note_id": {"type": "string"}}},
                ),
            ),
            "action finance.note: the tool does not promise result field note_id",
        ),
        (
            (
                SPENDING,
                replace(
                    WRITE_NOTE,
                    output_schema={
                        "type": "object",
                        "properties": {"note_id": {"type": "integer"}},
                        "required": ["note_id"],
                    },
                ),
            ),
            "action finance.note: result field note_id has types string, the tool's integer",
        ),
    ],
)
def test_what_the_check_refuses(tools: tuple[ToolInfo, ...], message: str) -> None:
    texts, _ = check(FINANCE, *tools)
    assert texts == [message]


def test_a_write_action_may_use_a_read_only_tool() -> None:
    texts, _ = check(FINANCE, SPENDING, replace(WRITE_NOTE, read_only=True))
    assert texts == []


def test_a_server_that_cannot_be_reached_is_one_problem() -> None:
    texts, clients = check(FINANCE, unavailable="start_failed")
    assert texts == ["server ledger: start_failed"]
    assert clients["ledger"].listed == 1


def test_problems_come_in_declaration_order() -> None:
    texts, _ = check(FINANCE, replace(SPENDING, read_only=False))
    assert texts == [
        "action finance.spend: a read action needs a tool marked read-only",
        "action finance.note: no tool write_note on server ledger",
    ]
    assert CheckProblem(where="server ledger", message="timeout").text == "server ledger: timeout"
```

`tests/e2e/test_cli_tool_check.py` (6 tests)

```python
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import diagnostics, domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.mcp_client.check import ToolCheckFailed
from conductor.registry import Action, Domain, McpServer
from conductor.runtime import ask, check_tools, open_runtime, resume
from conductor.store import Store
from tests.support import fake_ollama, run

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


ECHO = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
SHOUT = Action("shout", "Fail on purpose.", "tool", "fail", "read", Reason, Text, "fake")
LAB = Domain("lab", "Lab tools.", (ECHO,), servers=(McpServer("fake"),))
BROKEN = Domain("lab", "Lab tools.", (ECHO, SHOUT), servers=(McpServer("fake"),))
PROBLEM = "action lab.shout: a read action needs a tool marked read-only"


@pytest.fixture(autouse=True)
def fake_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CONDUCTOR_MCP__FAKE", f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    )
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def test_the_check_passes_when_the_tools_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    with open_runtime(get_settings()) as opened:
        assert opened.registry.names == ("lab",)
        check_tools(opened)


def test_a_run_is_refused_when_the_tools_do_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    with open_runtime(get_settings()) as opened:
        with pytest.raises(ToolCheckFailed) as raised:
            ask(opened, "lab: echo hi")
        assert opened.log.runs() == []
    assert str(raised.value) == "the tool check failed"
    assert [problem.text for problem in raised.value.problems] == [PROBLEM]


def test_a_server_without_a_command_line_refuses_a_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    monkeypatch.delenv("CONDUCTOR_MCP__FAKE")
    with open_runtime(get_settings()) as opened:
        with pytest.raises(ToolCheckFailed) as raised:
            resume(opened, "3" * 32)
    assert [problem.text for problem in raised.value.problems] == ["server fake: no_command"]


def test_ask_prints_every_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    result = run("ask", "lab: echo hi")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        f"Error: the tool check failed\n  {PROBLEM}\n",
    )


def test_recording_without_resuming_skips_the_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    step = PlannedStep(number=1, action="lab.echo", effect="read", args={"text": "hi"})
    request = ApprovalRequest(
        approval_id="1" * 32,
        run_id="2" * 32,
        stage="step",
        steps=(step,),
        args_sha256=steps_digest((step,)),
        requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
    )
    Store(tmp_path / "data" / "conductor.db").add_request(request)
    rejected = run("approvals", "reject", "1" * 32, "--no-resume")
    assert (rejected.exit_code, rejected.stdout) == (0, f"Rejected {'1' * 32}.\n")
    resumed = run("approvals", "approve", "1" * 32, "--yes")
    assert resumed.exit_code == 1


def test_the_doctor_checks_each_server(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_ollama() as (fake, host):
        fake.models("qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setattr(domains, "DOMAINS", (LAB,))
        good = run("doctor")
        monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
        bad = run("doctor")
    assert good.stdout.splitlines()[4:] == [
        "ok    server fake: 5 tools, 1 action checked",
        "All checks passed.",
    ]
    assert bad.stdout.splitlines()[4:] == [f"FAIL  server fake: {PROBLEM}", "1 check failed."]
    assert (good.exit_code, bad.exit_code) == (0, 1)
```

## Tests to write

In `tests/unit/test_tool_check_more.py`, each with its deciding input:

- R1: nested `anyOf` inside `anyOf`; a `$ref` to a definition with `anyOf`; `{"type": ["string", "string"]}` gives one `string`.
- R2: two domains with one server each are listed in order; a server with no tool action gives `actions` 0 and no problem.
- R3: a missing tool stops the action's checks (a read action on a missing tool gives one problem, not the read-only one too); a field present with two type problems in one action gives both, in field order; an output schema without `properties` but with `type: object` passes.
- R4: after a server that cannot be reached, the next server is still checked.
- R5: a tool whose description and schema title contain `SYNTHETIC-SECRET` gives problems without it.

In `tests/e2e/test_cli_tool_check_more.py`:

- R6: `domains.registered` with and without the demo setting; two `ask` calls on one runtime list the server's tools once (count the start lines in `data/mcp/fake.log`); `open_runtime` alone starts no server.
- R7: `resume` and `escalations retry` print the failed check the same way; `escalations cancel --no-resume` works with a broken server.
- R8: a server that cannot be reached (`CONDUCTOR_MCP__FAKE` unset) prints `FAIL  server fake: no_command`; with two problems, two `FAIL` lines and `2 checks failed.`; a server with no tool action prints `0 actions checked`.

## Rules for this phase

- **Side effects need approval** (`AGENTS.md` rule 7): a `read` action runs without approval, so the check refuses a `read` action whose tool is not marked read-only.
- **Network**: only the servers' own stdio; `list_tools` only, never `call_tool`.
- **Critical module**: `mcp_client/check.py` joins `scripts/critical_modules.txt` and `docs/testing.md`.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 26 = 626 passed; `critical coverage` passed (it now includes `mcp_client/check.py`);
- the given files: `.venv/bin/python -m pytest tests/unit/test_tool_check.py tests/e2e/test_cli_tool_check.py --no-cov`, exactly `26 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/runtime.py,*/conductor/cli/main.py,*/conductor/diagnostics.py,*/conductor/domains/__init__.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 6b`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/mcp_client/check.py | grep -v -E ":(from conductor\.config|from conductor\.mcp_client\.client|from conductor\.registry) import "`
  - `git grep --untracked -n -E "call_tool" -- src/conductor/mcp_client/check.py src/conductor/diagnostics.py src/conductor/runtime.py`
  - `git grep --untracked -n -E "domains\.DOMAINS" -- src | grep -v "^src/conductor/domains/__init__.py:"`
- `git diff --stat HEAD -- src/conductor/mcp_client/client.py src/conductor/registry.py src/conductor/contracts src/conductor/graph tests/unit tests/integration tests/e2e/test_cli_doctor.py tests/e2e/test_cli_ask.py tests/support.py tests/mcp_fake_server.py` prints nothing (new files are untracked, so it does not show them).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 6b: the tool check and the doctor (YYYY-MM-DD)`, with `Tests: 600 -> <passed> (given 26)`.
