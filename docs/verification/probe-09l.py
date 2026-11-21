"""Probe for Phase 9l: the split finance catalog is the same catalog as before.

The oracle is the predecessor's `domains/finance.py`, read from commit 02162d5 with git and
loaded as its own module. Every action, schema, rule and argument check of the new package must
match it. Run from the repository root with .venv/bin/python docs/verification/probe-09l.py.
The last line is FAILURES <n>.
"""

import importlib.util
import json
import os
import random
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

failures = 0
rng = random.Random(9)
BEFORE = "02162d5"


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

# A valid base for every action that has required arguments; the rest start from {}.
REASON = "Seen at the grocer every week."
BASE = {
    "find_merchants": {"phrase": "grocer"},
    "propose_category": {"transaction_id": 101, "category": "Groceries", "reason": REASON},
    "propose_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_not_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_rule": {"example_id": 101, "pattern": "GROCER", "category": "Food", "reason": REASON},
    "propose_merchant_alias": {"example_id": 101, "target": "Corner Grocer", "reason": REASON},
    "propose_group": {"name": "Household", "example_id": 101, "reason": REASON},
    "propose_new_category": {"name": "Pets", "group": "Food", "example_id": 7, "reason": REASON},
    "propose_rule_change": {"rule_id": 1, "reason": REASON},
    "propose_category_change": {"name": "Groceries", "reason": REASON},
    "propose_finding_status": {"type": "spike", "status": "handled", "reason": REASON},
    "log_advice": {"text": "Review the streaming subscriptions in December."},
}
POOL = (
    DROP,
    None,
    "",
    " x",
    "x" * 100,
    "x" * 101,
    "x" * 200,
    "x" * 201,
    "a\nb",
    0,
    1,
    -1,
    40,
    41,
    1000,
    1001,
    -1001,
    True,
    2.5,
    "2026-01",
    "2026-13",
    "2026-11-20",
    "contains",
    "regex",
    "spike",
    "ignored",
    [],
    {},
)


def load_before():
    text = subprocess.run(
        ["git", "show", f"{BEFORE}:src/conductor/domains/finance.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    path = Path(tempfile.mkdtemp()) / "finance_before.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("finance_before", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def facts(action) -> tuple:
    return (
        action.name,
        action.description,
        action.kind,
        action.target,
        action.effect,
        action.server,
        action.args.__name__,
        action.result.__name__,
        json.dumps(action.args.model_json_schema(), sort_keys=True),
        json.dumps(action.result.model_json_schema(), sort_keys=True),
    )


def verdict(contract, value: dict) -> tuple:
    from pydantic import ValidationError

    from conductor.contracts import problems_from

    try:
        return ("sent", contract.from_json(json.dumps(value)).model_dump(mode="json"))
    except ValidationError as error:
        return ("refused", [(problem.loc, problem.code) for problem in problems_from(error)])


before = load_before()
# The oracle on known cases: the predecessor is the 31-tool catalog with its own bounds.
assert (len(before.READS), len(before.PROPOSALS)) == (20, 11)
assert before.ACTIONS == (*before.READS, *before.PROPOSALS)
ORACLE = {action.name: action for action in before.ACTIONS}
assert verdict(ORACLE["list_transactions"].args, {"limit": 40})[0] == "sent"
assert verdict(ORACLE["list_transactions"].args, {"limit": 41})[0] == "refused"
assert verdict(ORACLE["log_advice"].args, BASE["log_advice"])[0] == "sent"
assert facts(ORACLE["get_balances"]) == facts(before.READS[1])


def check_layout() -> bool:
    from conductor.domains import finance
    from conductor.domains.finance import common, proposals, reads

    return (
        Path(finance.__file__).name == "__init__.py"
        and finance.READS is reads.READS
        and finance.PROPOSALS is proposals.PROPOSALS
        and finance.SERVER is common.SERVER
    )


def check_catalog() -> bool:
    from conductor.domains import finance

    return (
        [facts(action) for action in finance.ACTIONS]
        == [facts(action) for action in before.ACTIONS]
        and [facts(action) for action in finance.READS] == [facts(a) for a in before.READS]
        and finance.RULES == before.RULES
        and finance.SERVER == before.SERVER
        and (finance.DOMAIN.name, finance.DOMAIN.description, finance.DOMAIN.servers)
        == (before.DOMAIN.name, before.DOMAIN.description, before.DOMAIN.servers)
        and finance.DOMAIN.actions == finance.ACTIONS
    )


def check_arguments() -> bool:
    from conductor.domains import finance

    new = {action.name: action for action in finance.ACTIONS}
    agree = True
    reached = {"sent": 0, "refused": 0}
    for _ in range(2000):
        name = rng.choice(list(ORACLE))
        fields = list(ORACLE[name].args.model_fields) or ["extra"]
        value = one_change(BASE.get(name, {}), rng.choice(fields), rng.choice(POOL))
        want = verdict(ORACLE[name].args, value)
        agree &= verdict(new[name].args, value) == want
        reached[want[0]] += 1
    return agree and min(reached.values()) >= 250


section("the catalog is a package: reads, proposals and common", check_layout)
section("31 actions, their schemas, rules and domain are as before", check_catalog)
section("2000 random arguments: sent or refused exactly as before", check_arguments)

print(f"FAILURES {failures}")
