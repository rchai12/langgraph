import math
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue

NOT_FINITE_MESSAGE = "numbers must be finite"


def _reject_non_finite(value: object) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(NOT_FINITE_MESSAGE)


def _finite(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    _reject_non_finite(value)
    return value


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def from_json(cls, text: str | bytes) -> Self:
        return cls.model_validate_json(text, strict=True)


JsonObject = Annotated[dict[str, JsonValue], AfterValidator(_finite)]

Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ActionName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,31}$")]
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
