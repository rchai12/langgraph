"""Probe for Phase 9j: one rule each for ids, requests and times, and every caller agrees.

Run from the repository root with .venv/bin/python docs/verification/probe-09j.py.
The last line is FAILURES <n>.
"""

import json
import os
import random
import string
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

failures = 0
rng = random.Random(9)


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def section(label: str, body: Callable[[], bool]) -> None:
    try:
        ok = body()
    except Exception as error:  # noqa: BLE001
        print(f"     {label}: raised {type(error).__name__}")
        ok = False
    check(label, ok)


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables: written from the spec, never read from the code.
HEX_DIGITS = "0123456789abcdef"
ID_LENGTH = 32
REQUEST_LIMIT = 2000
BLANKS = " \t\n\r"
REQUEST_TEXT = "a request must have 1 to 2000 characters"
UTC_TEXT = "time must be UTC"


def oracle_id(value: str) -> bool:
    return len(value) == ID_LENGTH and all(char in HEX_DIGITS for char in value)


def oracle_request(value: str) -> bool:
    return len(value) <= REQUEST_LIMIT and any(char not in BLANKS for char in value)


def oracle_display(moment: datetime) -> str:
    m = moment
    return f"{m.year:04d}-{m.month:02d}-{m.day:02d}T{m.hour:02d}:{m.minute:02d}:{m.second:02d}Z"


def oracle_stored(moment: datetime) -> str:
    return oracle_display(moment)[:-1] + f".{moment.microsecond:06d}Z"


# The oracle on known cases.
GOOD = "0123456789abcdef" * 2
assert oracle_id(GOOD) and not oracle_id(GOOD[:-1]) and not oracle_id(GOOD.upper())
assert not oracle_id(GOOD + "\n") and not oracle_id(" " + GOOD[1:])
assert oracle_request("a") and oracle_request(" a ") and oracle_request("x" * 2000)
assert not oracle_request("") and not oracle_request(" \n\t") and not oracle_request("x" * 2001)
KNOWN = datetime(2026, 11, 20, 9, 5, 7, 123, tzinfo=UTC)
assert oracle_display(KNOWN) == "2026-11-20T09:05:07Z"
assert oracle_stored(KNOWN) == "2026-11-20T09:05:07.000123Z"


def random_id() -> str:
    """A valid id with at most one change."""
    value = "".join(rng.choice(HEX_DIGITS) for _ in range(ID_LENGTH))
    where = rng.randrange(ID_LENGTH)
    change = rng.choice(["none", "none", "replace", "drop", "add", "upper", "newline", "space"])
    if change == "replace":
        value = value[:where] + rng.choice("ABCFgz_-.") + value[where + 1 :]
    elif change == "drop":
        value = value[:where] + value[where + 1 :]
    elif change == "add":
        value = value[:where] + rng.choice(HEX_DIGITS) + value[where:]
    elif change == "upper":
        value = value.upper()
    elif change == "newline":
        value = value + "\n"
    elif change == "space":
        value = " " + value
    return value


def check_ids() -> bool:
    from pydantic import TypeAdapter, ValidationError

    from conductor.contracts.base import Id, is_id
    from conductor.events import RUN_ID_MESSAGE, EventKind, EventLog
    from conductor.store import Store

    adapter = TypeAdapter(Id)
    holder = "f" * ID_LENGTH
    agree = True
    reached = {True: 0, False: 0}
    for trial in range(200):
        value = random_id()
        want = oracle_id(value)
        reached[want] += 1
        folder = Path(tempfile.mkdtemp())
        try:
            adapter.validate_python(value)
            contract = True
        except ValidationError:
            contract = False
        try:
            EventLog(folder / "runs").append(value, EventKind.RUN_STARTED)
            logged = True
        except ValueError as error:
            logged = False
            agree &= str(error) == RUN_ID_MESSAGE
        try:
            Store(folder / "conductor.db").acquire(value, holder)
            leased = True
        except ValueError:
            leased = False
        found = (is_id(value), contract, logged, leased)
        agree &= found == (want, want, want, want)
        if not want:
            # A run file whose name is not an id is skipped when runs are listed.
            listed = folder / f"listed-{trial}"
            listed.mkdir()
            (listed / f"{value}.jsonl").write_bytes(b"")
            agree &= EventLog(listed).runs() == []
    return agree and reached[True] >= 40 and reached[False] >= 40


def random_request() -> str:
    """A valid request with at most one change."""
    letters = string.ascii_letters + string.digits + "?.,'"
    value = "".join(rng.choice(letters) for _ in range(rng.randint(1, 60)))
    change = rng.choice(["none", "empty", "blank", "pad", "longest", "too-long"])
    if change == "empty":
        value = ""
    elif change == "blank":
        value = "".join(rng.choice(BLANKS) for _ in range(rng.randint(1, 20)))
    elif change == "pad":
        value = rng.choice(BLANKS) * 3 + value + rng.choice(BLANKS)
    elif change == "longest":
        value = (value * REQUEST_LIMIT)[:REQUEST_LIMIT]
    elif change == "too-long":
        value = (value * REQUEST_LIMIT)[: REQUEST_LIMIT + 1]
    return value


class NoModel:
    """A model that must not be asked: a valid request may reach it."""

    def model_info(self, name: str):
        raise LookupError("not asked")

    def chat(self, request):
        raise LookupError("not asked")


def check_requests() -> bool:
    from conductor.contracts.base import is_request
    from conductor.domains import demo
    from conductor.evals.cases import CaseFileError, load_cases
    from conductor.events import EventLog
    from conductor.registry import Registry
    from conductor.routing.route import route_request

    registry = Registry((demo.DOMAIN,))
    agree = True
    reached = {True: 0, False: 0}
    for _ in range(150):
        value = random_request()
        want = oracle_request(value)
        reached[want] += 1
        folder = Path(tempfile.mkdtemp())
        log = EventLog(folder / "runs")
        try:
            route_request(value, registry, model=NoModel(), model_name="m", log=log, run_id=GOOD)
            routed = True
        except ValueError as error:
            routed = str(error) != REQUEST_TEXT
        except Exception:  # noqa: BLE001
            routed = True
        case = folder / "cases.toml"
        text = f'[[case]]\nid = "a"\nrequest = {json.dumps(value)}\nroute = "demo"\n'
        case.write_text(text + 'plan = ["echo"]\n', encoding="utf-8")
        try:
            load_cases(case, registry)
            loaded = True
        except CaseFileError as error:
            loaded = not str(error).endswith("case 1: request must have 1 to 2000 characters")
        agree &= (is_request(value), routed, loaded) == (want, want, want)
    return agree and reached[True] >= 40 and reached[False] >= 40


def random_moment() -> datetime:
    start = datetime(1970, 1, 1, tzinfo=UTC)
    return start + timedelta(microseconds=rng.randrange(130 * 365 * 24 * 3600 * 10**6))


def check_times() -> bool:
    from typer.testing import CliRunner

    from conductor import clock, times
    from conductor.cli.main import app
    from conductor.events import EventKind, EventLog

    runner = CliRunner()
    agree = True
    saved = clock.now
    try:
        for _ in range(60):
            moment = random_moment()
            agree &= times.display(moment) == oracle_display(moment)
            agree &= times.stored(moment) == oracle_stored(moment)
            data = Path(tempfile.mkdtemp())
            os.environ["CONDUCTOR_DATA_DIR"] = str(data)
            clock.now = lambda moment=moment: moment
            EventLog(data / "runs").append(GOOD, EventKind.RUN_STARTED)
            line = (data / "runs" / f"{GOOD}.jsonl").read_text(encoding="utf-8")
            agree &= json.loads(line)["at"] == oracle_stored(moment)
            listed = runner.invoke(app, ["runs", "list"]).stdout
            agree &= listed == f"{GOOD}  {oracle_display(moment)}  1 event\n"
            shown = runner.invoke(app, ["runs", "show", GOOD]).stdout
            agree &= shown == f"   1  {oracle_stored(moment)}  run_started\n"
    finally:
        clock.now = saved
    return agree


def check_refusals() -> bool:
    from conductor import times

    agree = True
    reached = 0
    for _ in range(100):
        moment = random_moment()
        minutes = rng.choice([value for value in range(-14 * 60, 14 * 60 + 1, 15) if value])
        offset = rng.choice([timezone(timedelta(minutes=minutes)), None])
        local = moment.astimezone(offset) if offset else moment.replace(tzinfo=None)
        for name in ("display", "stored"):
            try:
                getattr(times, name)(local)
                agree = False
            except ValueError as error:
                agree &= str(error) == UTC_TEXT
                reached += 1
    return agree and reached == 200


section("200 random ids: the rule, Id, the event log and the store agree", check_ids)
section("150 random requests: the rule, routing and case files agree", check_requests)
section("60 random UTC times: display, stored, the event log and `runs` agree", check_times)
section("100 times that are not UTC are refused by both formats", check_refusals)

print(f"FAILURES {failures}")
