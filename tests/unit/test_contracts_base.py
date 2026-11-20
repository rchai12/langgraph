from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, TypeAdapter

from conductor.contracts import approvals, base
from conductor.contracts.base import (
    ID_PATTERN,
    MAX_REQUEST,
    REQUEST_MESSAGE,
    UTC_MESSAGE,
    Contract,
    Id,
    is_contract_type,
    is_id,
    is_request,
    is_utc,
)
from conductor.domains.demo import PickInputs
from conductor.planning.answer import AnswerInputs
from conductor.planning.plan import PlanInputs
from conductor.routing import route
from conductor.routing.route import RouteInputs

HEX = "0123456789abcdef0123456789abcdef"


class Sample(Contract):
    value: int


class Plain(BaseModel):
    value: int


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (HEX, True),
        (HEX[:31], False),
        (HEX + "0", False),
        (HEX.upper(), False),
        ("g" + HEX[1:], False),
        (HEX + "\n", False),
        (None, False),
    ],
    ids=["ok", "short", "long", "upper", "not-hex", "newline", "none"],
)
def test_an_id_is_32_lowercase_hex(value: object, expected: bool) -> None:
    assert is_id(value) is expected


def test_the_id_pattern_is_one_rule() -> None:
    assert ID_PATTERN == "^[0-9a-f]{32}$"
    assert TypeAdapter(Id).json_schema() == {"pattern": ID_PATTERN, "type": "string"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a", True),
        ("x" * 2000, True),
        ("  a  ", True),
        ("", False),
        (" \n\t ", False),
        ("x" * 2001, False),
        (7, False),
    ],
    ids=["one", "longest", "padded", "empty", "blank", "too-long", "not-text"],
)
def test_a_request_has_1_to_2000_characters(value: object, expected: bool) -> None:
    assert is_request(value) is expected


def test_the_request_rule_has_one_message_and_one_schema() -> None:
    assert (MAX_REQUEST, REQUEST_MESSAGE) == (2000, "a request must have 1 to 2000 characters")
    assert route.REQUEST_MESSAGE is base.REQUEST_MESSAGE
    found = [
        model.model_json_schema()["properties"]["request"]
        for model in (RouteInputs, PlanInputs, AnswerInputs, PickInputs)
    ]
    expected = {"maxLength": 2000, "minLength": 1, "title": "Request", "type": "string"}
    assert found == [expected] * 4


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Sample, True),
        (Contract, True),
        (Sample(value=1), False),
        (Plain, False),
        (list[Sample], False),
        (None, False),
    ],
    ids=["subclass", "base", "instance", "plain-model", "generic", "none"],
)
def test_a_contract_type(value: object, expected: bool) -> None:
    assert is_contract_type(value) is expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 11, 20, 9, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 20, 9, 0, tzinfo=timezone(timedelta(0), "GMT")), True),
        (datetime(2026, 11, 20, 9, 0, tzinfo=timezone(timedelta(hours=2))), False),
        (datetime(2026, 11, 20, 9, 0), False),
    ],
    ids=["utc", "zero-offset", "plus-two", "naive"],
)
def test_a_utc_time(moment: datetime, expected: bool) -> None:
    assert is_utc(moment) is expected


def test_the_utc_message_is_one_rule() -> None:
    assert UTC_MESSAGE == "time must be UTC"
    assert approvals.UTC_MESSAGE is base.UTC_MESSAGE
