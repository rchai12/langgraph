from datetime import UTC, datetime, timedelta, timezone

import pytest

from conductor import times
from conductor.contracts.base import UTC_MESSAGE

MOMENT = datetime(2026, 11, 20, 9, 5, 7, 123, tzinfo=UTC)


def test_the_display_and_stored_formats() -> None:
    assert (times.DISPLAY_FORMAT, times.STORED_FORMAT) == (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    assert times.display(MOMENT) == "2026-11-20T09:05:07Z"
    assert times.stored(MOMENT) == "2026-11-20T09:05:07.000123Z"


def test_a_zero_offset_time_is_utc() -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(0), "GMT"))
    assert (times.display(moment), times.stored(moment)) == (
        "2026-01-02T03:04:05Z",
        "2026-01-02T03:04:05.000000Z",
    )


@pytest.mark.parametrize("name", ["display", "stored"])
@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 11, 20, 9, 5, 7, tzinfo=timezone(timedelta(hours=2))),
        datetime(2026, 11, 20, 9, 5, 7),
    ],
    ids=["plus-two", "naive"],
)
def test_a_time_that_is_not_utc_is_refused(name: str, moment: datetime) -> None:
    with pytest.raises(ValueError) as raised:
        getattr(times, name)(moment)
    assert str(raised.value) == UTC_MESSAGE
