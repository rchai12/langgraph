from dataclasses import replace

import pytest
from pydantic import Field

from conductor import diagnostics, domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.mcp_client.check import (
    CheckProblem,
    ServerCheck,
    check_registry,
    check_servers,
    json_types,
)
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
                        "properties": {
                            "month": {"type": "string"},
                            "start": SPENDING.input_schema["properties"]["start"],
                        },
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


OPEN_OUTPUT_moved = {"additionalProperties": True, "type": "object"}


class Text(Contract):
    text: str


class Pair(Contract):
    month: str
    limit: int


class Saved(Contract):
    note_id: str


class Task(Contract):
    task: str


def test_nested_anyof_a_ref_to_anyof_and_a_repeated_type() -> None:
    nested = {"anyOf": [{"anyOf": [{"type": "string"}, {"type": "null"}]}, {"type": "integer"}]}
    assert json_types(nested, {}) == ("integer", "null", "string")
    defs = {"When": {"anyOf": [{"type": "string"}, {"type": "null"}]}}
    assert json_types({"$ref": "#/$defs/When"}, defs) == ("null", "string")
    assert json_types({"type": ["string", "string"]}, {}) == ("string",)
    assert json_types({"oneOf": [{"type": "integer"}, {"type": "string"}]}, {}) == (
        "integer",
        "string",
    )


def test_two_domains_are_listed_and_an_idle_server_has_no_problem() -> None:
    echo = ToolInfo(
        "echo",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        True,
    )
    read = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "one")
    advise = Action("advise", "Advise the lab.", "agent", "advisor", "implement", Task, Task)
    alpha = Domain("alpha", "First.", (read,), servers=(McpServer("one"),))
    beta = Domain("beta", "Second.", (advise,), servers=(McpServer("two"),))
    started: list[str] = []

    def connect(server: McpServer, settings: object) -> object:
        started.append(server.name)
        return _Client((echo,) if server.name == "one" else ())

    found = check_servers(Registry((alpha, beta)), get_settings(), connect=connect)
    assert started == ["one", "two"]
    assert [(item.server, item.actions, item.problems) for item in found] == [
        ("one", 1, ()),
        ("two", 0, ()),
    ]


def test_a_missing_tool_stops_before_the_read_only_rule() -> None:
    gone = Action("gone", "Missing tool.", "tool", "missing", "read", Text, Text, "ledger")
    domain = Domain("lab", "Lab.", (gone,), servers=(McpServer("ledger"),))
    texts = _texts(domain, ToolInfo("other", {"type": "object"}, OPEN_OUTPUT_moved, False))
    assert texts == ["action lab.gone: no tool missing on server ledger"]


def test_two_type_problems_stay_in_field_order() -> None:
    pair = Action("pair", "Two fields.", "tool", "get_spending", "read", Pair, Text, "ledger")
    domain = Domain("lab", "Lab.", (pair,), servers=(McpServer("ledger"),))
    tool = ToolInfo(
        "get_spending",
        {
            "type": "object",
            "properties": {"month": {"type": "integer"}, "limit": {"type": "string"}},
            "required": ["month", "limit"],
        },
        OPEN_OUTPUT_moved,
        True,
    )
    assert _texts(domain, tool) == [
        "action lab.pair: field month has types string, the tool's integer",
        "action lab.pair: field limit has types integer, the tool's string",
    ]


def test_an_output_schema_without_properties_passes() -> None:
    note = Action("note", "Write a note.", "tool", "write_note", "write", Text, Saved, "ledger")
    domain = Domain("lab", "Lab.", (note,), servers=(McpServer("ledger"),))
    tool = ToolInfo(
        "write_note",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        {"type": "object"},
        False,
    )
    assert _texts(domain, tool) == []


def test_the_next_server_is_checked_after_one_cannot_be_reached() -> None:
    down = Action("note", "Write a note.", "tool", "write_note", "write", Text, Saved, "down")
    up = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "up")
    domain = Domain("lab", "Lab.", (down, up), servers=(McpServer("down"), McpServer("up")))
    echo = ToolInfo(
        "echo",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        True,
    )

    def connect(server: McpServer, settings: object) -> object:
        if server.name == "down":
            raise McpUnavailable("down", "timeout")
        return _Client((echo,))

    found = check_servers(Registry((domain,)), get_settings(), connect=connect)
    assert [(item.server, item.tools, item.problems) for item in found] == [
        ("down", None, (CheckProblem("server down", "timeout"),)),
        ("up", 1, ()),
    ]


def test_a_secret_in_a_schema_title_stays_out_of_the_message() -> None:
    spend = Action("spend", "Spending.", "tool", "get_spending", "read", Pair, Text, "ledger")
    domain = Domain("finance", "Money.", (spend,), servers=(McpServer("ledger"),))
    tool = ToolInfo(
        "get_spending",
        {
            "title": "SYNTHETIC-SECRET",
            "description": "SYNTHETIC-SECRET",
            "type": "object",
            "properties": {
                "month": {
                    "title": "SYNTHETIC-SECRET",
                    "description": "SYNTHETIC-SECRET",
                    "type": "integer",
                },
                "limit": {"type": "integer"},
            },
            "required": ["month", "limit"],
        },
        {"title": "SYNTHETIC-SECRET", "type": "object"},
        True,
    )
    texts = _texts(domain, tool)
    assert texts == ["action finance.spend: field month has types string, the tool's integer"]
    assert all("SYNTHETIC-SECRET" not in text for text in texts)


def test_one_tool_and_one_action_use_the_singular(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "check_servers",
        lambda registry, settings: (ServerCheck("ledger", 1, 1, ()),),
    )
    monkeypatch.setattr(domains, "DOMAINS", ())
    lines = [check.line for check in diagnostics.run_checks(get_settings())]
    assert "ok    server ledger: 1 tool, 1 action checked" in lines


class _Client:
    def __init__(self, tools: tuple[ToolInfo, ...]) -> None:
        self.tools = tools

    def list_tools(self) -> tuple[ToolInfo, ...]:
        return self.tools


def _texts(domain: Domain, *tools: ToolInfo) -> list[str]:
    def connect(server: McpServer, settings: object) -> _Client:
        return _Client(tools)

    found = check_servers(Registry((domain,)), get_settings(), connect=connect)
    return [problem.text for item in found for problem in item.problems]
