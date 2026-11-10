import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from conductor.registry import Registry

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CASE_KEYS = frozenset({"id", "request", "route", "plan", "args"})


@dataclass(frozen=True)
class EvalCase:
    id: str
    request: str
    route: str
    plan: tuple[str, ...] | Literal["escalate"] | None = None
    args: tuple[dict[str, Any], ...] | None = None


class CaseFileError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")


def load_cases(
    path: Path, registry: Registry, *, seen: set[str] | None = None
) -> tuple[EvalCase, ...]:
    known = set() if seen is None else seen
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        raise CaseFileError(path, "the file is not TOML") from None
    for key in parsed:
        if key != "case":
            raise CaseFileError(path, f"unknown key {key}")
    found = parsed.get("case")
    if not isinstance(found, list) or not found:
        raise CaseFileError(path, "the file needs at least one [[case]]")
    loaded: list[EvalCase] = []
    for number, item in enumerate(found, start=1):
        loaded.append(_case(path, registry, item, number, known))
    return tuple(loaded)


def _case(
    path: Path, registry: Registry, item: dict[str, Any], number: int, seen: set[str]
) -> EvalCase:
    for key in item:
        if key not in _CASE_KEYS:
            raise CaseFileError(path, f"case {number}: unknown key {key}")
    case_id = item.get("id")
    if not isinstance(case_id, str) or _ID.fullmatch(case_id) is None:
        raise CaseFileError(
            path, f"case {number}: id must be lowercase letters, digits, and dashes"
        )
    if case_id in seen:
        raise CaseFileError(path, f"case {number}: id {case_id} is used twice")
    request = item.get("request")
    if not isinstance(request, str) or not request.strip() or len(request) > 2000:
        raise CaseFileError(path, f"case {number}: request must have 1 to 2000 characters")
    route = item.get("route")
    if route != "escalate" and route not in registry.names:
        raise CaseFileError(path, f"case {number}: route must be a registered domain or escalate")
    plan = _plan(path, registry, item, number, route)
    args = _args(path, item, number, plan)
    seen.add(case_id)
    return EvalCase(case_id, request, route, plan, args)


def _plan(
    path: Path, registry: Registry, item: dict[str, Any], number: int, route: str
) -> tuple[str, ...] | Literal["escalate"] | None:
    if route == "escalate":
        if "plan" in item:
            raise CaseFileError(
                path, f"case {number}: a case that expects a route escalation has no plan"
            )
        return None
    if "plan" not in item:
        raise CaseFileError(path, f"case {number}: a routed case needs a plan")
    raw = item["plan"]
    names = {action.name for action in registry.domain(route).actions}
    if raw == "escalate":
        return "escalate"
    if isinstance(raw, list) and all(isinstance(name, str) and name in names for name in raw):
        return tuple(raw)
    raise CaseFileError(
        path, f"case {number}: plan must be a list of the domain's actions or escalate"
    )


def _args(
    path: Path,
    item: dict[str, Any],
    number: int,
    plan: tuple[str, ...] | Literal["escalate"] | None,
) -> tuple[dict[str, Any], ...] | None:
    if "args" not in item:
        return None
    raw = item["args"]
    if (
        not isinstance(plan, tuple)
        or not isinstance(raw, list)
        or len(raw) != len(plan)
        or any(not isinstance(table, dict) for table in raw)
    ):
        raise CaseFileError(path, f"case {number}: args must be one table per planned step")
    return tuple(dict(table) for table in raw)
