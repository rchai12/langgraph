from conductor import diagnostics, domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.mcp_client.check import CheckProblem, ServerCheck, check_servers, json_types
from conductor.mcp_client.client import McpUnavailable, ToolInfo
from conductor.registry import Action, Domain, McpServer, Registry

OPEN_OUTPUT = {"additionalProperties": True, "type": "object"}


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
    texts = _texts(domain, ToolInfo("other", {"type": "object"}, OPEN_OUTPUT, False))
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
        OPEN_OUTPUT,
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
