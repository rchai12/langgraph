# Verify Phase 9b: the finance read actions

Spec: `docs/phases/phase-09b-finance-read-actions.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 9b` on your own report.

The coder:
- copied the given domain module, the saved schemas, the fake server, and two given test files (45 tests);
- made `registered` add finance when its command is set;
- gave the plan point 16384 context tokens;
- wrote `tests/unit/test_finance_more.py` and `tests/integration/test_finance_more.py`.

## 1. Gates

N is `859`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 904 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/domains/__init__.py,*/conductor/domains/finance.py,*/conductor/planning/plan.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_finance_domain.py tests/integration/test_finance_steps.py --no-cov` | exactly `45 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 9b` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/runtime.py src/conductor/graph src/conductor/store.py src/conductor/web src/conductor/evals src/conductor/prompts src/conductor/llm src/conductor/planning/answer.py src/conductor/routing src/conductor/domains/demo.py src/conductor/config.py src/conductor/diagnostics.py tests/support.py tests/conftest.py tests/mcp_fake_server.py` | no output |
| `git diff --stat HEAD -- tests` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "\"effect\"|, \"(propose|write|implement)\"" -- src/conductor/domains/finance.py`
2. `git grep --untracked -n -E "Projects/finances|finances/(data|\.venv)|bin/fin\b" -- tests src`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks: the domain module, `tests/finances_tools.json`, the fake server, and the two test files.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | the given-file comparison; `test_twenty_read_actions_on_one_server`, `test_every_action_fits_the_real_read_tools`, `test_the_defaults`, `test_arguments_at_their_bounds_are_sent` (10 cases), `test_arguments_past_their_bounds_are_refused` (16 cases), `test_results_name_the_top_fields_and_leave_the_rest_open`, `test_the_fake_server_returns_a_result_each_action_accepts`, `test_finance_words_route_by_rule` (6 cases), `test_a_finance_word_and_a_demo_word_conflict`; the coder's defaults test; probe checks 1 to 3 | equal; pass; ok |
| R2 | `test_finance_is_registered_when_its_command_is_set` (4 cases); the coder's missing-program test; probe check 4; `tests/unit/test_registry.py` unchanged | pass; ok |
| R3 | `test_the_plan_point_has_a_larger_context`; the coder's demo test | pass |
| R4 | `test_the_fake_lists_the_real_read_tools`; probe check 5 | pass; ok |
| R5 | `test_a_finance_request_runs_its_reads_without_asking`; the coder's prefix test | pass |
| R6 | the protected diffs and `git status` | as in the Gates |
| R7 | search 2; read the coder's two test files for any path into `finances` or a run of `fin` | no output; none |
| R8 | the coverage gate | as in the Gates |

## 4. Probe

Save the probe outside the repository, run it from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok`, and the last must be `FAILURES 0`.

It checks:
- 3000 random argument sets: ints around each bound, months and dates valid and not, labels in three character widths, wrong JSON types, and choices. Each is compared with the probe's own table of every field's bound.
- 2000 random results: one top-level field dropped, added, of a wrong type, or with new nested fields, or a `NaN`. Each is compared with its own table of every action's top-level fields.
- 2000 random requests of finance, demo, and filler words, compared with its own phrase matcher.
- `registered` under all eight combinations of the finances command, the demo, and another server's command.
- The tool check against the fake server.

A stop at its `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 9b. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import re
import shlex
import sys
import tempfile
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from conductor import domains
from conductor.config import get_settings
from conductor.domains import demo, finance
from conductor.mcp_client.check import check_servers
from conductor.registry import Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(92)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()
ACTIONS = {action.name: action for action in finance.DOMAIN.actions}
REAL = json.loads(Path("tests/finances_tools.json").read_text())

# The oracle's own table of every argument: (kind, bound).
INTS = {
    ("get_net_worth", "months"): (1, 24),
    ("list_transactions", "limit"): (1, 40),
    ("list_transactions", "offset"): (0, 5000),
    ("month_over_month", "count"): (1, 12),
    ("get_upcoming", "days"): (1, 90),
    ("get_forecast", "days"): (1, 60),
    ("list_uncategorized", "limit"): (1, 40),
    ("list_transfers", "limit"): (1, 20),
    ("find_merchants", "limit"): (1, 20),
    ("list_proposals", "limit"): (1, 20),
    ("list_advice", "limit"): (1, 20),
}
MONTHS = {("month_over_month", "month"), ("get_insights", "month"), ("get_budgets", "month")}
DATES = {(a, f) for a in ("list_transactions", "get_spending") for f in ("start", "end")}
LABELS = {
    ("list_transactions", f): 100
    for f in ("text", "account", "person", "category", "group", "merchant", "bank", "card")
} | {("get_forecast", "account"): 100}
CHOICES = {
    ("list_transactions", "kind"): {
        "",
        "spending",
        "income",
        "transfer",
        "unsorted_in",
        "pending",
        "refund",
    },
    ("get_spending", "by"): {"category", "group", "merchant", "person", "account", "bank", "card"},
    ("list_proposals", "status"): {"open", "accepted", "declined"},
}
BOOLS = {
    ("list_accounts", "include_inactive"),
    ("get_recurring", "income"),
    ("get_recurring", "include_inactive"),
}
PHRASE = ("find_merchants", "phrase")
FIELDS = {}
for table in (INTS, MONTHS, DATES, LABELS, CHOICES, BOOLS, {PHRASE}):
    for name, field in table:
        FIELDS.setdefault(name, []).append(field)


def month_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if value == "":
        return True
    found = re.fullmatch(r"([0-9]{4})-([0-9]{2})", value)
    return found is not None and 1 <= int(found.group(2)) <= 12


def date_ok(value: object) -> bool:
    if value is None:
        return True
    found = isinstance(value, str) and re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", value)
    if not found:
        return False
    try:
        date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return False
    return True


def field_ok(name: str, field: str, value: object) -> bool:
    key = (name, field)
    if key in INTS:
        low, high = INTS[key]
        return type(value) is int and low <= value <= high
    if key in MONTHS:
        return month_ok(value)
    if key in DATES:
        return date_ok(value)
    if key in LABELS:
        return isinstance(value, str) and len(value) <= LABELS[key]
    if key in CHOICES:
        return isinstance(value, str) and value in CHOICES[key]
    if key in BOOLS:
        return type(value) is bool
    assert key == PHRASE
    return isinstance(value, str) and 1 <= len(value) <= 100


def random_value(name: str, field: str) -> object:
    key = (name, field)
    if key in INTS:
        low, high = INTS[key]
        return rng.choice([low - 1, low, high, high + 1, rng.randint(low, high), True, "3", 2.0])
    if key in MONTHS:
        year, month = rng.randint(1999, 2031), rng.randint(0, 13)
        return rng.choice(
            [
                "",
                f"{year}-{month:02d}",
                f"{year}-{month}",
                f"{year}{month:02d}",
                f"{year}-{month:02d}-01",
                202611,
            ]
        )
    if key in DATES:
        year, month, day = rng.randint(1999, 2031), rng.randint(0, 13), rng.randint(0, 32)
        return rng.choice([None, f"{year}-{month:02d}-{day:02d}", "last month", 20261001])
    if key in CHOICES:
        return rng.choice([*sorted(CHOICES[key]), "purchase", "Category", "", 1])
    if key in BOOLS:
        return rng.choice([True, False, 0, 1, "true", None])
    char = rng.choice(["x", "é", "𝄞"])
    return rng.choice([char * rng.randint(0, 120), 7, None])


# the oracle on known cases
assert field_ok("list_transactions", "limit", 40) and not field_ok("list_transactions", "limit", 41)
assert not field_ok("list_transactions", "limit", True)
assert month_ok("") and month_ok("2026-12") and not month_ok("2026-13") and not month_ok("2026-1")
assert date_ok("2024-02-29") and not date_ok("2026-02-29") and not date_ok("20261001")
assert field_ok("find_merchants", "phrase", "é" * 100) and not field_ok(*PHRASE, "")
assert set(FIELDS) | {
    "get_balances",
    "list_categories",
    "list_rules",
    "list_transfer_suggestions",
    "data_coverage",
} == set(REAL)

# 1. arguments
agree = True
for _ in range(3000):
    name = rng.choice(sorted(FIELDS))
    chosen = rng.sample(FIELDS[name], rng.randint(1, len(FIELDS[name])))
    sent = {field: random_value(name, field) for field in chosen}
    if name == "find_merchants" and "phrase" not in sent:
        sent["phrase"] = "grocer"
    want = all(field_ok(name, field, value) for field, value in sent.items())
    try:
        ACTIONS[name].args.from_json(json.dumps(sent))
        got = True
    except ValidationError:
        got = False
    agree &= got == want
check("3000 random argument sets are accepted exactly when every field is in its bounds", agree)

# 2. results: the oracle's own table of top-level fields
ROWS, NAMES, INT, STR, BOOL, OPT, OBJ = "rows", "names", "int", "str", "bool", "int|null", "obj"
TOP = {
    "list_accounts": {"accounts": ROWS},
    "get_balances": {
        "accounts": ROWS,
        "cash_cents": INT,
        "cards_cents": INT,
        "other_cents": INT,
        "net_worth_cents": INT,
        "without_balance": NAMES,
    },
    "get_net_worth": {"as_of": STR, "points": ROWS},
    "list_transactions": {"transactions": ROWS, "next_offset": OPT},
    "get_spending": {"start": STR, "end": STR, "by": STR, "lines": ROWS, "summary": OBJ},
    "month_over_month": {"months": ROWS},
    "get_insights": {"month": STR, "findings": ROWS, "merchants": ROWS, "set_aside": ROWS},
    "get_recurring": {"as_of": STR, "income": BOOL, "series": ROWS},
    "get_upcoming": {
        "start": STR,
        "end": STR,
        "items": ROWS,
        "bills_cents": INT,
        "income_cents": INT,
    },
    "get_forecast": {"start": STR, "end": STR, "accounts": ROWS, "no_balance": NAMES},
    "get_budgets": {"month": STR, "budgets": ROWS},
    "list_uncategorized": {"total": INT, "transactions": ROWS},
    "list_categories": {"categories": ROWS},
    "list_rules": {"rules": ROWS},
    "list_transfers": {"total": INT, "pairs": ROWS},
    "list_transfer_suggestions": {"suggestions": ROWS},
    "data_coverage": {"as_of": STR, "accounts": ROWS, "problems": ROWS},
    "find_merchants": {"matches": ROWS},
    "list_proposals": {"proposals": ROWS},
    "list_advice": {"advice": ROWS},
}
GOOD = {
    ROWS: [{"a": 1, "b": {"c": [1, "x", None]}}],
    NAMES: ["Sample Checking"],
    INT: 5,
    STR: "2026-11-10",
    BOOL: True,
    OPT: None,
    OBJ: {"spent_cents": 1, "x": [1]},
}
BAD = {
    ROWS: [[1], [1, 2], "x", [{"a": float("nan")}]],
    NAMES: [[1], "x"],
    INT: ["5", True, 1.5],
    STR: [5, None],
    BOOL: [1, "true"],
    OPT: ["1", 1.5],
    OBJ: [[1], "x"],
}


def rows_like(kind: str) -> object:
    return GOOD[kind]


assert list(TOP) == list(REAL)
agree = True
for _ in range(2000):
    name = rng.choice(list(TOP))
    body = {field: rows_like(kind) for field, kind in TOP[name].items()}
    want = True
    change = rng.choice(["none", "drop", "extra", "bad", "nested"])
    field = rng.choice(list(body))
    if change == "drop":
        del body[field]
        want = False
    elif change == "extra":
        body["new_top_field"] = 1
        want = False
    elif change == "bad":
        body[field] = rng.choice(BAD[TOP[name][field]])
        want = False
    elif change == "nested" and TOP[name][field] == ROWS:
        body[field] = [{"new": {"deep": [True]}}, {}]
    if TOP[name].get(field) == OPT and change == "none":
        body[field] = rng.choice([None, 0, 40])
    try:
        ACTIONS[name].result.from_json(json.dumps(body))
        got = True
    except ValidationError:
        got = False
    agree &= got == want
check("2000 random results are accepted exactly when the top-level fields fit", agree)

# 3. rules, against the oracle's own phrase list
FIN = {
    "spending": ["spending", "spent"],
    "budgets": ["budget", "budgets"],
    "balances": ["balance", "balances", "net worth"],
    "transactions": ["transactions", "uncategorized"],
    "bills": ["bills", "subscriptions", "recurring"],
    "transfers": ["transfers"],
}
DEMO = {"echo": ["echo", "repeat after me"], "note": ["note", "write down"]}
FILLER = [
    "how",
    "much",
    "did",
    "we",
    "spend",
    "net",
    "worth",
    "write",
    "down",
    "transfer",
    "bill",
    "after",
    "me",
    "repeat",
    "the",
    "Budget!",
    "SPENT,",
    "net-worth",
]


def oracle_route(text: str) -> object:
    tokens = re.findall(r"[a-z0-9]+", text.lower())

    def has(phrase: str) -> bool:
        want = phrase.split(" ")
        return any(tokens[i : i + len(want)] == want for i in range(len(tokens)))

    matched = [f"finance.{n}" for n, ps in FIN.items() if any(has(p) for p in ps)]
    matched += [f"demo.{n}" for n, ps in DEMO.items() if any(has(p) for p in ps)]
    if not matched:
        return None
    if len({m.split(".")[0] for m in matched}) > 1:
        return ("conflict", tuple(matched))
    return ("route", matched[0])


assert oracle_route("Are we over BUDGET?") == ("route", "finance.budgets")
assert oracle_route("net-worth please") == ("route", "finance.balances")
assert oracle_route("write down what we spent") == ("conflict", ("finance.spending", "demo.note"))
assert oracle_route("how much did we spend") is None
registry = Registry((finance.DOMAIN, demo.DOMAIN))
agree = True
for _ in range(2000):
    words = rng.choices(
        FILLER + [p for ps in FIN.values() for p in ps] + ["note", "echo"], k=rng.randint(1, 8)
    )
    text = " ".join(words)
    found = match_rules(text, registry)
    want = oracle_route(text)
    if want is None:
        agree &= found is None
    elif want[0] == "conflict":
        agree &= found == RuleConflict(want[1])
    else:
        agree &= isinstance(found, RuleRoute) and found.route.rule_id == want[1]
        agree &= found.route.domain == "finance" or want[1].startswith("demo.")
check("2000 random requests route as the phrase list says", agree)

# 4. registration
agree = True
for finances_set in (False, True):
    for demo_on in (False, True):
        for other in (False, True):
            for key in ("CONDUCTOR_MCP__FINANCES", "CONDUCTOR_DEMO", "CONDUCTOR_MCP__LEDGER"):
                os.environ.pop(key, None)
            if finances_set:
                os.environ["CONDUCTOR_MCP__FINANCES"] = "fin mcp serve"
            if other:
                os.environ["CONDUCTOR_MCP__LEDGER"] = "fin mcp serve"
            os.environ["CONDUCTOR_DEMO"] = "true" if demo_on else "false"
            want = ((finance.DOMAIN,) if finances_set else ()) + ((demo.DOMAIN,) if demo_on else ())
            agree &= domains.registered(get_settings()) == want
check("finance is registered exactly when its command is set, before demo", agree)

# 5. the tool check against the fake server
os.environ["CONDUCTOR_DEMO"] = "false"
os.environ.pop("CONDUCTOR_MCP__LEDGER", None)
fake = Path("tests/fake_finances_server.py").resolve()
os.environ["CONDUCTOR_MCP__FINANCES"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
found = check_servers(Registry(domains.registered(get_settings())), get_settings())
check(
    "the tool check finds 20 tools, 20 actions, no problems on the fake",
    [(item.server, item.tools, item.actions, item.problems) for item in found]
    == [("finances", 20, 20, ())],
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The coder's two test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function or file, run the deciding test, see it fail, and restore. Run them with `PYTHONDONTWRITEBYTECODE=1` and `-vv`. Restore with the reverse edit, not by copying a saved file back. Afterwards, run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.

Write down what each broken run printed. A different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is. Rows 6 and 7 change the given module, to show the given tests guard it.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `is None` instead of `is not None` for the finances command (`registered`) | `test_finance_is_registered_when_its_command_is_set[none]` | `()` | `(finance.DOMAIN,)`: "Left contains one more item" |
| 2 | the demo placed before finance (`registered`) | `test_finance_is_registered_when_its_command_is_set[finance-demo]` | `(finance.DOMAIN, demo.DOMAIN)` | "At index 0 diff": the demo domain first |
| 3 | `mcp_command("finance")`, the domain's name, instead of `"finances"`, the server's (`registered`) | `test_finance_is_registered_when_its_command_is_set[finance]` | `(finance.DOMAIN,)` | `()`: "Right contains one more item" |
| 4 | `context_tokens=PLAN_CONTEXT_TOKENS` removed (`plan_point`) | `test_the_plan_point_has_a_larger_context` | `(16384, 16384, 4096)` | `(16384, 8192, 4096)` |
| 5 | `DOMAINS` set to `(finance.DOMAIN,)` (`domains/__init__.py`) | `test_finance_is_registered_when_its_command_is_set[none]` | `()` | `(finance.DOMAIN,)` |
| 6 | `le=40` changed to `le=41` in the `limit` of `LimitArgs` and of `TransactionsArgs` (`finance.py`) | `test_arguments_past_their_bounds_are_refused[transactions-limit-41]` | `ValidationError` | `Failed: DID NOT RAISE` |
| 7 | `SERVER = McpServer("finances")`, without `FIN_DATA_DIR` (`finance.py`) | `test_twenty_read_actions_on_one_server` | `env=('FIN_DATA_DIR',)` | the two servers differ: `env=()` |

Reasonable variations that are correct: importing `finance` at the top of `domains/__init__.py` or inside `registered`, and building the result with a list instead of tuple unpacking, as long as the order is `DOMAINS`, finance, demo.

## 6. Project rules

- Searches 1 and 2.
- Every finance action has effect `read`. No `propose_*` tool or `log_advice` is declared.
- No test starts `fin` or reads from the `finances` project. The fake's results and the coder's tests use invented data only.
- No test opens a connection; the model in tests is `ScriptedModel`.

## 7. Out of scope

Each must be absent:
- proposal or write actions;
- finance evaluation cases;
- template or prompt changes;
- a doctor line for an unregistered domain;
- a new setting;
- cutting or summarising results;
- changes to the tool check, `McpRunner`, the MCP client, the graph, the runtime, the store, the web pages, or the evaluation harness.

## 8. Progress log

The entry exists, headed `## Phase 9b: the finance read actions (...)`, with `Tests: 859 -> <passed> (given 45)`, and each deviation it lists is real and justified.
