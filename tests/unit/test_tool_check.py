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
