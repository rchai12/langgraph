from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().astimezone().date()
