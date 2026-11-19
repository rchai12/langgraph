import io
import json

import pytest

from conductor.llm import tags
from conductor.llm.tags import (
    Listed,
    OllamaBadAnswer,
    TooLarge,
    find_model,
    parse_tags,
    read_capped,
)

A = "a" * 64
B = "b" * 64
PLAIN = {"name": "plain:latest", "digest": A}
PLAIN_LISTED = Listed("plain:latest", A, (), None)


def body(*entries: object) -> bytes:
    return json.dumps({"models": list(entries)}).encode()


def test_the_limits_and_messages() -> None:
    assert (
        tags.MAX_BODY_BYTES,
        tags.UNEXPECTED_MESSAGE,
        tags.UNREACHABLE_MESSAGE,
        tags.TOO_LARGE_MESSAGE,
    ) == (1_048_576, "unexpected answer", "not reachable", "answer too large")
    assert issubclass(TooLarge, OllamaBadAnswer)
    assert str(TooLarge()) == "answer too large"


def test_a_listing_keeps_its_order_and_sorts_capabilities() -> None:
    listed = parse_tags(
        body({"name": "q:7b", "digest": B, "capabilities": ["thinking", "completion"]}, PLAIN)
    )
    assert listed == {
        "q:7b": Listed("q:7b", B, ("completion", "thinking"), None),
        "plain:latest": PLAIN_LISTED,
    }
    assert list(listed) == ["q:7b", "plain:latest"]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"name": "m:1"}, Listed("m:1", None, (), "no_digest")),
        ({"name": "m:1", "digest": "A" * 64}, Listed("m:1", None, (), "no_digest")),
        (
            {"name": "m:1", "digest": B, "capabilities": "thinking"},
            Listed("m:1", B, (), "bad_capabilities"),
        ),
        (
            {"name": "m:1", "digest": B, "capabilities": ["thinking", 1]},
            Listed("m:1", B, (), "bad_capabilities"),
        ),
        ({"name": "m:1", "digest": 1, "capabilities": "x"}, Listed("m:1", None, (), "no_digest")),
    ],
    ids=["missing", "upper", "caps-text", "caps-mixed", "both"],
)
def test_each_entry_is_judged_alone(entry: dict[str, object], expected: Listed) -> None:
    assert parse_tags(body(entry, PLAIN)) == {"m:1": expected, "plain:latest": PLAIN_LISTED}


@pytest.mark.parametrize(
    "entry",
    ["x", {"name": 3, "digest": B}, {"model": "m:1", "digest": B}],
    ids=["text", "number", "nameless"],
)
def test_an_entry_without_a_usable_name_is_skipped(entry: object) -> None:
    assert parse_tags(body(entry, PLAIN)) == {"plain:latest": PLAIN_LISTED}


def test_a_repeated_name_is_refused() -> None:
    twice = {"name": "m:1", "digest": A}
    listed = parse_tags(body(twice, {**twice, "digest": B}, PLAIN, twice))
    assert listed == {"m:1": Listed("m:1", None, (), "duplicate"), "plain:latest": PLAIN_LISTED}
    assert list(listed) == ["m:1", "plain:latest"]


@pytest.mark.parametrize(
    "sent", [b"not json", b"\xff", b'{"models": "x"}'], ids=["text", "not-utf8", "no-list"]
)
def test_an_answer_that_is_not_a_listing(sent: bytes) -> None:
    with pytest.raises(OllamaBadAnswer) as raised:
        parse_tags(sent)
    assert (type(raised.value), str(raised.value)) == (OllamaBadAnswer, "unexpected answer")


@pytest.mark.parametrize(
    ("names", "asked", "found"),
    [
        (["plain:latest"], "plain", "plain:latest"),
        (["plain:latest", "plain"], "plain", "plain"),
        (["plain:latest"], "plain:7b", None),
    ],
    ids=["latest", "exact", "other-tag"],
)
def test_finding_the_configured_model(names: list[str], asked: str, found: str | None) -> None:
    listed = parse_tags(body(*({"name": name, "digest": A} for name in names)))
    chosen = find_model(listed, asked)
    assert (chosen.name if chosen is not None else None) == found


class Strict:
    """A response body that refuses a read of everything, or of more than `most` bytes."""

    def __init__(self, data: bytes, most: int) -> None:
        self._data = io.BytesIO(data)
        self._most = most

    def read(self, size: int = -1) -> bytes:
        assert 0 <= size <= self._most
        return self._data.read(size)


@pytest.mark.parametrize(("size", "fits"), [(10, True), (11, False)])
def test_a_read_stops_one_byte_past_the_limit(size: int, fits: bool) -> None:
    response = Strict(b"x" * size, most=11)
    if fits:
        assert read_capped(response, 10) == b"x" * 10
    else:
        with pytest.raises(TooLarge):
            read_capped(response, 10)
