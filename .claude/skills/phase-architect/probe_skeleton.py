"""Skeleton of a phase probe. Copy it to the scratchpad as probe_NNx.py and fill it in.

Rules it follows (SKILL.md, step 18):
- the oracle is built from the probe's own tables, never from the code under test;
- the oracle checks itself on known cases (the assert lines) before it judges the code;
- random inputs are a valid base with at most one change;
- every check runs inside section(), so an exception prints FAIL and the run continues.

Run from the repository root with .venv/bin/python <path>. The last line is FAILURES <n>.
"""

import os
import random
import tempfile
from collections.abc import Callable

failures = 0
rng = random.Random(1)


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


def one_change(base: dict, field: str, value: object) -> dict:
    """A copy of base with one field set to value, or removed when value is DROP."""
    changed = dict(base)
    if value is DROP:
        changed.pop(field, None)
    else:
        changed[field] = value
    return changed


DROP = object()

for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables: written from the spec, never read from the code.
LOW, HIGH = 1, 40
BASE = {"limit": 20}


def oracle_ok(sent: dict) -> bool:
    value = sent.get("limit", 20)
    return type(value) is int and LOW <= value <= HIGH


# The oracle on known cases.
assert oracle_ok(BASE) and oracle_ok({"limit": HIGH}) and not oracle_ok({"limit": HIGH + 1})
assert not oracle_ok({"limit": True}) and oracle_ok(one_change(BASE, "limit", DROP))


def check_example() -> bool:
    agree = True
    for _ in range(100):
        value = rng.choice([LOW - 1, LOW, HIGH, HIGH + 1, True, "3", DROP])
        sent = one_change(BASE, "limit", value)
        want = oracle_ok(sent)
        got = want  # replace with the code under test, for example a contract's from_json
        agree &= got == want
    return agree


section("100 random limits are accepted exactly when in bounds", check_example)

print(f"FAILURES {failures}")
