from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from conductor.config import Settings
from conductor.mcp_client.client import McpClient, McpUnavailable, ToolInfo, client_for
from conductor.registry import Action, McpServer, Registry

CHECK_FAILED_MESSAGE = "the tool check failed"


@dataclass(frozen=True)
class CheckProblem:
    where: str
    message: str

    @property
    def text(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass(frozen=True)
class ServerCheck:
    server: str
    tools: int | None
    actions: int
    problems: tuple[CheckProblem, ...]


class ToolCheckFailed(Exception):
    def __init__(self, problems: tuple[CheckProblem, ...]) -> None:
        self.problems = problems
        super().__init__(CHECK_FAILED_MESSAGE)


def json_types(schema: dict[str, Any], defs: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(set(_collect(schema, defs))))


def check_servers(
    registry: Registry,
    settings: Settings,
    *,
    connect: Callable[[McpServer, Settings], McpClient] = client_for,
) -> tuple[ServerCheck, ...]:
    found: list[ServerCheck] = []
    for name in registry.names:
        domain = registry.domain(name)
        for server in domain.servers:
            found.append(_check_server(domain.name, domain.actions, server, settings, connect))
    return tuple(found)


def check_registry(
    registry: Registry,
    settings: Settings,
    *,
    connect: Callable[[McpServer, Settings], McpClient] = client_for,
) -> tuple[CheckProblem, ...]:
    problems: list[CheckProblem] = []
    for item in check_servers(registry, settings, connect=connect):
        problems.extend(item.problems)
    return tuple(problems)


def _collect(schema: dict[str, Any], defs: dict[str, Any]) -> list[str]:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _collect(defs[name], defs)
    members = schema.get("anyOf")
    if members is None:
        members = schema.get("oneOf")
    if members is not None:
        found: list[str] = []
        for member in members:
            found.extend(_collect(member, defs))
        return found
    kind = schema.get("type")
    if isinstance(kind, str):
        return [kind]
    if isinstance(kind, list):
        return list(kind)
    return ["any"]


def _check_server(
    domain: str,
    actions: tuple[Action, ...],
    server: McpServer,
    settings: Settings,
    connect: Callable[[McpServer, Settings], McpClient],
) -> ServerCheck:
    named = tuple(
        action for action in actions if action.kind == "tool" and action.server == server.name
    )
    try:
        listed = connect(server, settings).list_tools()
    except McpUnavailable as error:
        problem = CheckProblem(f"server {server.name}", error.code)
        return ServerCheck(server.name, None, len(named), (problem,))
    tools = {tool.name: tool for tool in listed}
    problems: list[CheckProblem] = []
    for action in named:
        problems.extend(_action_problems(domain, action, server.name, tools))
    return ServerCheck(server.name, len(listed), len(named), tuple(problems))


def _action_problems(
    domain: str, action: Action, server: str, tools: dict[str, ToolInfo]
) -> tuple[CheckProblem, ...]:
    where = f"action {domain}.{action.name}"
    tool = tools.get(action.target)
    if tool is None:
        return (CheckProblem(where, f"no tool {action.target} on server {server}"),)
    problems: list[CheckProblem] = []
    args_schema = action.args.model_json_schema()
    input_schema = tool.input_schema
    _input_problems(where, args_schema, input_schema, problems)
    if action.effect == "read" and tool.read_only is not True:
        problems.append(CheckProblem(where, "a read action needs a tool marked read-only"))
    output = tool.output_schema
    if output is None:
        problems.append(CheckProblem(where, "the tool declares no output schema"))
        return tuple(problems)
    if "properties" in output:
        _output_problems(where, action.result.model_json_schema(), output, problems)
    return tuple(problems)


def _input_problems(
    where: str,
    args_schema: dict[str, Any],
    input_schema: dict[str, Any],
    problems: list[CheckProblem],
) -> None:
    args_defs = args_schema.get("$defs", {})
    input_defs = input_schema.get("$defs", {})
    input_properties = input_schema.get("properties", {})
    for field, field_schema in args_schema.get("properties", {}).items():
        if field not in input_properties:
            problems.append(CheckProblem(where, f"field {field} is not in the tool's input"))
            continue
        args_types = _joined(field_schema, args_defs)
        tool_types = _joined(input_properties[field], input_defs)
        if args_types != tool_types:
            problems.append(
                CheckProblem(
                    where, f"field {field} has types {args_types}, the tool's {tool_types}"
                )
            )
    args_properties = args_schema.get("properties", {})
    for field in input_schema.get("required", []):
        if field not in args_properties:
            problems.append(
                CheckProblem(where, f"the tool requires {field}, which the action does not have")
            )


def _output_problems(
    where: str,
    result_schema: dict[str, Any],
    output: dict[str, Any],
    problems: list[CheckProblem],
) -> None:
    result_defs = result_schema.get("$defs", {})
    output_defs = output.get("$defs", {})
    result_properties = result_schema.get("properties", {})
    for field, field_schema in output["properties"].items():
        if field not in result_properties:
            problems.append(
                CheckProblem(
                    where, f"the tool's result field {field} is not in the action's result"
                )
            )
            continue
        result_types = _joined(result_properties[field], result_defs)
        output_types = _joined(field_schema, output_defs)
        if result_types != output_types:
            problems.append(
                CheckProblem(
                    where,
                    f"result field {field} has types {result_types}, the tool's {output_types}",
                )
            )
    promised = output.get("required", [])
    for field in result_schema.get("required", []):
        if field not in promised:
            problems.append(CheckProblem(where, f"the tool does not promise result field {field}"))


def _joined(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    return "|".join(json_types(schema, defs))
