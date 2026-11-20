from datetime import datetime

from conductor.contracts.base import UTC_MESSAGE, is_utc

DISPLAY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
STORED_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def display(moment: datetime) -> str:
    if not is_utc(moment):
        raise ValueError(UTC_MESSAGE)
    return moment.strftime(DISPLAY_FORMAT)


def stored(moment: datetime) -> str:
    if not is_utc(moment):
        raise ValueError(UTC_MESSAGE)
    return moment.strftime(STORED_FORMAT)
