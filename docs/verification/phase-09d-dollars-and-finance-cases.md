# Verify Phase 9d: dollars in the answer, and the finance cases

Spec: `docs/phases/phase-09d-dollars-and-finance-cases.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 9d` on your own report.

**First, check that the coder ran.** If `git status --short` lists neither a changed `src/conductor/planning/answer.py` nor `tests/unit/test_dollars_more.py`, stop. Report under "For the architect" that there is no implementation to verify, and write no review file, because a FAIL review without a progress entry breaks `check_reports.py` on `main`.

The coder:
- added `with_dollars` to `conductor.planning.answer`, and built the answer's message from the converted outputs;
- added `today` to `EvalCase`, its loading, `plan_fields`, `plan_request`, and `run_case`;
- copied `evals/cases/finance.toml` and two given test files (29 tests), and wrote `tests/unit/test_dollars_more.py` and `tests/integration/test_dollars_more.py`.

## 1. Gates

N is `971`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; at least 1000 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/planning/answer.py,*/conductor/planning/plan.py,*/conductor/evals/cases.py,*/conductor/evals/run.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_answer_dollars.py tests/unit/test_eval_today.py --no-cov` | exactly `29 passed` |
| `grep -c "^## Phase 9d: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9d` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/domains src/conductor/prompts src/conductor/graph src/conductor/runtime.py src/conductor/store.py src/conductor/policy.py src/conductor/decisions.py src/conductor/web src/conductor/mcp_client src/conductor/llm src/conductor/routing src/conductor/cli src/conductor/config.py src/conductor/evals/report.py evals/cases/demo.toml tests` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "clock\.today\(" -- src/conductor/evals`
2. `git grep --untracked -n -E "from conductor\.clock import" -- src`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks: `evals/cases/finance.toml` and the two test files.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_cents_become_dollars` (16 cases), `test_the_keys_keep_their_order_and_the_input_is_unchanged`; the coder's near-a-dollar test; probe check 1 | pass; ok |
| R2 | `test_the_answer_reads_dollars`, `test_the_bound_is_measured_on_the_dollars`; probe check 2 | pass; ok |
| R3 | read `answer_request`: the caller's results are not reassigned or mutated; the coder's integration test; probe check 5 | as said; pass; ok |
| R4 | `test_a_case_may_name_its_today`, `test_today_must_be_a_date` (5 cases); the coder's order test; probe check 3 | pass; ok |
| R5 | `test_plan_fields_take_a_given_day`; the coder's clock-raises test; search 2 | pass; no output |
| R6 | `test_each_run_plans_on_the_case_day` (2 cases); search 1; probe check 4 | pass; no output; ok |
| R7 | the given-file comparison; `test_the_finance_cases_load_and_plan_on_one_day` | equal; pass |
| R8 | the protected diff and `git status` | as in the Gates |
| R9 | the coverage gate | as in the Gates |

## 4. Probe

Save the probe outside the repository, run it from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok`, and the last must be `FAILURES 0`.

It checks:
- 1: 3000 random JSON trees (signed amounts up to 10^12, booleans, floats, `_cents` without a name, keys that only contain `_cents`, keys whose `_dollars` already exists), against its own conversion: equal, the keys in order, the argument unchanged.
- 2: 200 answers of 1 to 800 lines of amounts. The model gets exactly the message built from the probe's own conversion, or the run escalates as `answer_too_large` with that message's size, and asks no model.
- 3: eleven TOML values for `today` (dates, date-times with and without an offset, a time, a string, a number, an array, a table, a boolean). Each is accepted exactly when `tomllib` reads a plain `date`.
- 4: 30 cases of random days and run counts, with `clock.today` returning a new day at every call. Every plan request names the case's day and weekday.
- 5: a run over the fake finances server: the log keeps `net_worth_cents`, and the answer's message holds `"net_worth_dollars": "1234.56"` and no `_cents`.

A stop at its `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 9d. Run from the repository root with .venv/bin/python."""

import copy
import json
import os
import random
import shlex
import sys
import tempfile
import tomllib
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path

from conductor import clock
from conductor.config import get_settings
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning import answer, plan
from conductor.registry import Registry

failures = 0
rng = random.Random(94)


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


# The oracle's own conversion, written from the spec.
def dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}{whole}.{part:02d}"


def oracle(value: object) -> object:
    if isinstance(value, list):
        return [oracle(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        name = key[: -len("_cents")] if key.endswith("_cents") else ""
        if name and type(item) is int and f"{name}_dollars" not in value:
            out[f"{name}_dollars"] = dollars(item)
        else:
            out[key] = oracle(item)
    return out


assert dollars(-5) == "-0.05" and dollars(123456) == "1234.56" and dollars(0) == "0.00"
assert oracle({"a_cents": -4210, "b": [{"c_cents": True}]}) == {
    "a_dollars": "-42.10",
    "b": [{"c_cents": True}],
}
assert oracle({"_cents": 1, "x_cents": 1, "x_dollars": "k"}) == {
    "_cents": 1,
    "x_cents": 1,
    "x_dollars": "k",
}
assert list(oracle({"z": 1, "y_cents": 2})) == ["z", "y_dollars"]

KEYS = ["amount_cents", "net_cents", "_cents", "cents", "a_cents_b", "label", "amount_dollars"]


def tree(depth: int) -> object:
    roll = rng.random()
    if depth > 2 or roll < 0.4:
        return rng.choice(
            [rng.randint(-(10**12), 10**12), rng.randint(-150, 150), 0, True, False, None,
             1.5, "4210", "x"]
        )
    if roll < 0.6:
        return [tree(depth + 1) for _ in range(rng.randint(0, 3))]
    keys = rng.sample(KEYS, rng.randint(0, 4))
    return {key: tree(depth + 1) for key in keys}


def check_conversion() -> bool:
    agree = True
    for _ in range(3000):
        given = tree(0)
        kept = copy.deepcopy(given)
        found = answer.with_dollars(given)
        want = oracle(given)
        agree &= found == want and given == kept
        if isinstance(want, dict):
            agree &= list(found) == list(want)
    return agree


section("3000 random JSON trees convert as the oracle says, in order, input unchanged",
        check_conversion)


def check_answer_message() -> bool:
    agree = True
    log = EventLog(Path(tempfile.mkdtemp()))
    for number in range(200):
        count = rng.choice([1, 2, 50, 400, 800])
        output = {"items": [{"spent_cents": rng.randint(-(10**9), 10**9), "n": i}
                            for i in range(count)], "total_cents": rng.randint(-99, 99)}
        outcome = answer.StepOutcome(step=1, action="finance.get_spending", output=output)
        converted = answer.StepOutcome(step=1, action="finance.get_spending",
                                       output=oracle(output))
        message = answer.AnswerInputs(request="How much?", results=(converted,))
        text = message.model_dump_json(indent=2)
        size = len(text.encode())
        model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Ok."}'))])
        found = answer.answer_request("How much?", (outcome,), model=model, model_name="m",
                                      log=log, run_id=f"{number:032x}")
        if size > answer.ANSWER_INPUT_BYTES:
            agree &= getattr(found, "kind", None) == "answer_too_large"
            agree &= f"are {size} bytes" in found.detail and model.requests == []
        else:
            agree &= [request.user for request in model.requests] == [text]
    return agree


section("200 answers send exactly the converted message, bounded on its own size",
        check_answer_message)


def check_today_values() -> bool:
    from conductor.evals.cases import CaseFileError, load_cases

    registry = Registry((demo.DOMAIN,))
    folder = Path(tempfile.mkdtemp())
    base = '[[case]]\nid = "hi"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'
    values = ["2026-11-10", "1999-12-31", "2031-02-28", '"2026-11-10"', "2026-11-10T00:00:00",
              "2026-11-10 08:00:00+01:00", "00:00:00", "20261110", "[2026-11-10]",
              "{ day = 2026-11-10 }", "true"]
    agree = True
    for text in values:
        path = folder / "c.toml"
        path.write_text(base + f"today = {text}\n")
        parsed = tomllib.loads(path.read_text())["case"][0]["today"]
        want = type(parsed) is date
        try:
            found = load_cases(path, registry)[0].today
            agree &= want and found == parsed
        except CaseFileError as error:
            agree &= not want and str(error).endswith(
                "case 1: today must be a date such as 2026-11-10")
    return agree and not isinstance(time(0), date) and isinstance(datetime(2026, 1, 1), date)


section("today is accepted exactly when TOML reads a plain date", check_today_values)


def check_runs_use_the_day() -> bool:
    from conductor.evals.cases import EvalCase
    from conductor.evals.run import run_case

    days = iter(date(2030, 1, 1 + n % 28) for n in range(10**6))
    clock.today = lambda: next(days)
    agree = True
    for _ in range(30):
        day = date(rng.randint(2000, 2040), rng.randint(1, 12), rng.randint(1, 28))
        runs = rng.randint(1, 4)
        reply = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
        model = ScriptedModel([ScriptedReply("plan", ModelReply(content=reply))] * runs)
        case = EvalCase("hi", "demo: say hi", "demo", ("echo",), None, day)
        run_case(case, Registry((demo.DOMAIN,)), model=model, model_name="m",
                 log=EventLog(Path(tempfile.mkdtemp())), runs=runs)
        weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                   "Sunday")[day.weekday()]
        line = f"Today is {day.isoformat()}, a {weekday}."
        agree &= [line in request.system for request in model.requests] == [True] * runs
    fields = plan.plan_fields(demo.DOMAIN)
    agree &= fields["today"].startswith("2030-01-")
    return agree


section("30 cases plan every run on their own day while the clock moves", check_runs_use_the_day)


def check_a_real_run() -> bool:
    from conductor.runtime import ask, open_runtime

    fake = Path("tests/fake_finances_server.py").resolve()
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
    os.environ["CONDUCTOR_MCP__FINANCES"] = command
    os.environ["CONDUCTOR_MCP_TIMEOUT"] = "10"
    plan_reply = json.dumps({"steps": [{"action": "get_balances", "args": {}}]})
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=plan_reply)),
                           ScriptedReply("answer", ModelReply(content='{"reply": "Ok."}'))])
    with open_runtime(get_settings(), model=model) as runtime:
        done = ask(runtime, "finance: what is our net worth")
        events = runtime.log.read(done.run_id)
    output = [e.payload["output"] for e in events if e.kind == EventKind.TOOL_RESULT][0]
    sent = model.requests[1].user
    return (done.status == "done" and output["net_worth_cents"] == 123456
            and '"net_worth_dollars": "1234.56"' in sent and "_cents" not in sent)


section("a run over the fake keeps cents in its log and sends dollars to the answer",
        check_a_real_run)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The coder's two test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the coder's code, in the coder's form of the named rule. Run the deciding test by its full node id with `PYTHONDONTWRITEBYTECODE=1` and `-vv`, see it fail, and restore it with the reverse edit, not by copying a saved file back. Afterwards, run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.

Write down what each broken run printed. A different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|
| 1 | the minus sign left out of the dollar string | `tests/unit/test_answer_dollars.py::test_cents_become_dollars[negative]` | `'-42.10'` | `'42.10'` |
| 2 | whole dollars and cents taken from the signed value instead of its absolute value, the sign kept | `tests/unit/test_answer_dollars.py::test_cents_become_dollars[minus-five-cents]` | `'-0.05'` | a string with `95` in it (for `divmod(-5, 100)`, that is `(-1, 95)`) |
| 3 | `isinstance(value, int)` without excluding booleans | `tests/unit/test_answer_dollars.py::test_cents_become_dollars[bool]` | `{'flag_cents': True}` | `'flag_dollars': '0.01'` |
| 4 | lists returned without converting their items | `tests/unit/test_answer_dollars.py::test_cents_become_dollars[list]` | `'bills_dollars': '-12.99'` | `'bills_cents': -1299` |
| 5 | the bound measured on the message before conversion | `tests/unit/test_answer_dollars.py::test_the_bound_is_measured_on_the_dollars` | `answer_too_large` | `Answered(reply='Done.'` |
| 6 | `isinstance(value, date)` instead of the exact type, in the loader | `tests/unit/test_eval_today.py::test_today_must_be_a_date[local-datetime]` | `CaseFileError` | `DID NOT RAISE` |
| 7 | `run_case` not passing `case.today` to `plan_request` | `tests/unit/test_eval_today.py::test_each_run_plans_on_the_case_day[given]` | `[True, True]` | `[False, False]` |
| 8 | the `_dollars` check removed, so an existing `<name>_dollars` key does not stop the conversion | `tests/unit/test_answer_dollars.py::test_cents_become_dollars[dollars-already]` | `'amount_cents': 4210` kept | `'amount_cents'` missing |
| 9 | `plan_fields` ignoring its `today` argument | `tests/unit/test_eval_today.py::test_plan_fields_take_a_given_day` | `'2026-11-10'` | `'2031-01-01'` |

Reasonable variations that are correct: the conversion written as a loop or as recursion; the dollar string built with `divmod` or with `//` and `%`; `today` checked inside `_case` or in a helper; converting with `model_copy(update=...)` or by building new `StepOutcome`s.

## 6. Project rules

- Searches 1 and 2.
- No template, description, or rule changed (the protected diff).
- Every test uses invented requests and amounts; the model in tests is `ScriptedModel`.
- The new message names the case number, never the refused value.

## 7. Out of scope

Each must be absent:
- a change to an action description, a rule, a template, or a domain module;
- answer evaluations, or tools or the graph run by an evaluation;
- a currency symbol, separators, or rounding in code;
- converted values in the event log, the run state, the store, or an escalation;
- skipping or warning about unregistered case files, or a new `eval run` option.

## 8. Progress log

The entry exists, headed `## Phase 9d: dollars in the answer, and the finance cases (...)`, with `Tests: 971 -> <passed> (given 29)`, and each deviation it lists is real and justified.
