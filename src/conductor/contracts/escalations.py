import re
from typing import Literal

from pydantic import Field, ValidationError

from conductor.contracts.base import Contract, Id

MAX_PROBLEMS = 20
EscalationKind = Literal[
    "invalid_model_output",
    "unknown_route",
    "invalid_plan",
    "tool_error",
    "retries_exhausted",
    "rejected",
]
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class FieldProblem(Contract):
    loc: str
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")


class Escalation(Contract):
    kind: EscalationKind
    detail: str = Field(min_length=1, max_length=500)
    run_id: Id
    problems: tuple[FieldProblem, ...] = Field(default=(), max_length=MAX_PROBLEMS)


def _location(parts: tuple[object, ...]) -> str:
    rendered: list[str] = []
    for part in parts:
        if type(part) is int:
            rendered.append(str(part))
        elif _SAFE_KEY.fullmatch(part):  # type: ignore[arg-type]
            rendered.append(part)  # type: ignore[arg-type]
        else:
            rendered.append("*")
    return ".".join(rendered)


def problems_from(error: ValidationError) -> tuple[FieldProblem, ...]:
    return tuple(
        FieldProblem(loc=_location(entry["loc"]), code=entry["type"])
        for entry in error.errors()[:MAX_PROBLEMS]
    )
