# Phase 9d: dollars in the answer, and the finance cases

## Goal

Three things, after which the finance domain is complete:
- **Dollars in the answer.** Before the answer point, code writes every integer field named `<name>_cents` as a dollar amount, `<name>_dollars`, so the model never does the arithmetic.
- **A day per case.** An evaluation case may fix the day its plans see, so a case such as "last month" expects the same dates on any day.
- **24 finance cases.** These are given in `evals/cases/finance.toml`.

Decided with the owner (2026-11-10):
- **Code converts cents to dollars**, deterministically, for every domain, before the answer point.
- **A case may set `today`**, a TOML date. Its plans see that day instead of the clock's.
- **Evaluations stay on routing and planning.** The answer is not evaluated; the conversion has offline given tests.
- **The architect tunes, and the spec gives the result.** The tuning spike (see Facts) found nothing worth changing, so this phase changes no description, rule, or template.

Decided by the architect, within those answers:
- A dollar amount is a string such as `"-42.10"`: a minus sign for a negative amount, whole dollars, a point, and two digits. It has no currency symbol and no thousands separator, so it is exact and the model formats it. A string keeps the trailing zero that a JSON number would lose.
- The run's log, its state, and its escalations keep the cents; only the answer's message changes.
- `eval run` still refuses a case file whose domain is not registered. The finance file says how to run it (any `CONDUCTOR_MCP__FINANCES` value registers the domain, and evaluations start no server).

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` ("Determinism rules"), `docs/architecture.md` ("Answer", "Evaluation harness")
- `src/conductor/planning/answer.py` (`answer_request`, `AnswerInputs`, `ANSWER_INPUT_BYTES`), `src/conductor/planning/plan.py` (`plan_fields`, `plan_request`), `src/conductor/evals/cases.py`, `src/conductor/evals/run.py` (`run_case`)
- `tests/unit/test_answer_bound.py`, `tests/unit/test_eval_cases.py`, `tests/unit/test_eval_run.py` (the existing tests of these modules)

## Starting state

Phase 9c is built and verified, and everything is committed: N is `971`. **Sections: cli, core.** No `with_dollars` exists, `EvalCase` has no `today`, and `evals/cases/` holds only `demo.toml`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/planning/answer.py` | `with_dollars`, and the converted answer message (Part 1) |
| `src/conductor/planning/plan.py` | a `today` keyword on `plan_fields` and `plan_request` (Part 2) |
| `src/conductor/evals/cases.py`, `src/conductor/evals/run.py` | `EvalCase.today`, its loading, and its use in each run (Part 2) |
| `evals/cases/finance.toml` | given (Part 3) |
| `tests/unit/test_answer_dollars.py`, `tests/unit/test_eval_today.py` | given |
| `tests/unit/test_dollars_more.py`, `tests/integration/test_dollars_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Any change to an action description, a rule, a template, or the domain modules.
- Evaluating the answer; running tools or the graph in an evaluation.
- A currency symbol, thousands separators, rounding, or any other format in code.
- Converting anything in the event log, the run state, the store, or an escalation.
- Skipping or warning about a case file whose domain is not registered; a new `eval run` option.
- Any change to the graph, the runtime, the MCP client, the web pages, `conductor.evals.report`, or the CLI.

## Dependencies

None new.

## Design

### Part 1: dollars in the answer

`conductor.planning.answer` gains `with_dollars(value: JsonValue) -> JsonValue` (Pydantic's `JsonValue`), a pure function that returns a new value and leaves its argument unchanged:
- a list becomes a list of each item converted;
- in an object, each key keeps its position. A key that ends in `_cents` with a non-empty name before it (`amount_cents`, not `cents` or `_cents`), whose value is an integer (`True` and `False` are not), becomes `<name>_dollars` with the value's dollar string. The exception: when the same object already has a key `<name>_dollars`, the `_cents` key stays as it is. Every other value is converted in turn;
- every other value (a string, a float, `None`, a boolean, an integer outside an object) stays as it is.

The dollar string of `c` cents is `"-"` when `c < 0`, then `abs(c) // 100`, a point, and `abs(c) % 100` as two digits: `-4210` gives `"-42.10"`, `-5` gives `"-0.05"`, `0` gives `"0.00"`, `123456` gives `"1234.56"`.

`answer_request` builds the answer's message from the results with each `output` converted. The message the model receives is `AnswerInputs(request=..., results=<converted>).model_dump_json(indent=2)`, and the `answer_too_large` bound of 9a is measured on that message, with the same detail text. The results the caller passed are not changed, so the run's `TOOL_RESULT` events and its state keep the cents.

### Part 2: a day per case

- `EvalCase` gains a last field, `today: date | None = None`. Earlier positional constructions stay valid.
- `load_cases` accepts the key `today`. When present, it must be a TOML date, which `tomllib` reads as a `datetime.date`. A date-time (read as a `datetime`, which is a subclass of `date`), a time, a string, or a number is refused with `case <n>: today must be a date such as 2026-11-10`. The check comes after every existing check of the case.
- `plan_fields(domain, today: date | None = None)` uses `today` when given, else `clock.today()`.
- `plan_request(..., today: date | None = None)` takes it as a keyword and passes it to `plan_fields`. The runtime and the graph call it as before.
- `run_case` passes `case.today` to `plan_request` in every run.

The report's case-file hash already covers a change of `today`, so nothing changes in `conductor.evals.report`.

### Part 3: the finance cases

`evals/cases/finance.toml` is given below. All 24 cases plan as if today were 2026-11-10, a Tuesday. Twenty-two expect a finance plan, one expects the plan to escalate (no action pays a bill), and one expects the route to escalate. The owner runs them with:

```sh
CONDUCTOR_MCP__FINANCES="fin mcp serve" .venv/bin/conductor eval run --cases evals/cases/finance.toml
```

## Facts

From a spike on 2026-11-10, on the owner's model (`qwen3.8:27b`), with synthetic requests and results only.

- **Baseline.** With the 9c descriptions and today fixed at 2026-11-10, the 24 cases were run three times each. 23 were right and consistent 3/3, with every reply valid. The one miss, "What did we spend yesterday?", planned `get_spending` and also `list_transactions` for the same day, in all three runs. That request can fairly mean "show the purchases".
- **Tuning.** Rewording `get_spending` ("enough alone") and `list_transactions` ("only to show transactions") left that case unchanged and the four nearest cases as they were. So the descriptions stay, and the case asks "How much did we spend yesterday?", which planned `get_spending` alone, 3/3.
- **Dates.** "Last month" planned `2026-10-01` to `2026-10-31`, and "yesterday" planned `2026-11-09` for both ends.
- **Cents.** Given a spending result in cents, the model wrote correct dollar amounts in two runs out of two. The conversion is there so that this never depends on the model.
- **TOML dates.** `tomllib` reads `2026-11-10` as `date`, `2026-11-10T09:00:00` as `datetime` (a subclass of `date`), and `09:00:00` as `time`. So the check is on the exact type.

## Requirements

### Part 1: dollars in the answer

- **R1.** `with_dollars` converts as under Design: key position kept, the argument unchanged, and every other value as it is.
- **R2.** `answer_request` sends the message built from the converted outputs, and measures the 24000-byte bound on that message.
- **R3.** The results passed to `answer_request` are not changed. A run's `TOOL_RESULT` events keep the cents.

### Part 2: a day per case

- **R4.** `EvalCase.today` and its loading, with the exact message, as under Design.
- **R5.** `plan_fields` and `plan_request` take `today`, and fall back to `clock.today()` when it is not given.
- **R6.** `run_case` plans every run on `case.today` when it is set, whatever `clock.today()` returns.

### Part 3: the cases and the rules

- **R7.** `evals/cases/finance.toml` is copied exactly, and loads with the finance domain registered.
- **R8.** Only the Scope's paths change. No earlier test changes.
- **R9.** `planning/answer.py`, `planning/plan.py`, `evals/cases.py`, and `evals/run.py` reach 100% of lines and branches.

## Given tests

29 new tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong. Before your change, `tests/unit/test_answer_dollars.py` fails to import (`with_dollars` does not exist), and every test of `tests/unit/test_eval_today.py` fails: `today` is an unknown key, `EvalCase` takes no sixth argument, and `plan_fields` takes no `today`.

`evals/cases/finance.toml` (given; copy it exactly)

```toml
# Evaluation cases for the finance domain. Synthetic requests only (AGENTS.md rule 5).
# Each case plans as if today were 2026-11-10, a Tuesday. Run with the finances command set
# (evals start no server): CONDUCTOR_MCP__FINANCES="fin mcp serve"
#   .venv/bin/conductor eval run --cases evals/cases/finance.toml

[[case]]
id = "spent-last-month"
request = "How much did we spend last month?"
today = 2026-11-10
route = "finance"
plan = ["get_spending"]
args = [{ start = "2026-10-01", end = "2026-10-31" }]

[[case]]
id = "spent-yesterday"
request = "How much did we spend yesterday?"
today = 2026-11-10
route = "finance"
plan = ["get_spending"]
args = [{ start = "2026-11-09", end = "2026-11-09" }]

[[case]]
id = "spending-by-merchant"
request = "Break down this month's spending by merchant"
today = 2026-11-10
route = "finance"
plan = ["get_spending"]
args = [{ by = "merchant" }]

[[case]]
id = "net-worth-now"
request = "What is our net worth right now?"
today = 2026-11-10
route = "finance"
plan = ["get_balances"]

[[case]]
id = "net-worth-trend"
request = "How has our net worth changed over the last 6 months?"
today = 2026-11-10
route = "finance"
plan = ["get_net_worth"]
args = [{ months = 6 }]

[[case]]
id = "account-balances"
request = "What's the balance of each account?"
today = 2026-11-10
route = "finance"
plan = ["get_balances"]

[[case]]
id = "grocer-transactions"
request = "Show the last 10 transactions at Corner Grocer"
today = 2026-11-10
route = "finance"
plan = ["list_transactions"]
args = [{ merchant = "Corner Grocer", limit = 10 }]

[[case]]
id = "uncategorized"
request = "Which transactions are uncategorized?"
today = 2026-11-10
route = "finance"
plan = ["list_uncategorized"]

[[case]]
id = "bills-two-weeks"
request = "What bills are due in the next two weeks?"
today = 2026-11-10
route = "finance"
plan = ["get_upcoming"]
args = [{ days = 14 }]

[[case]]
id = "subscriptions"
request = "Which subscriptions do we pay for?"
today = 2026-11-10
route = "finance"
plan = ["get_recurring"]
args = [{ income = false }]

[[case]]
id = "recurring-income"
request = "What recurring income do we get?"
today = 2026-11-10
route = "finance"
plan = ["get_recurring"]
args = [{ income = true }]

[[case]]
id = "over-budget"
request = "Are we over budget this month?"
today = 2026-11-10
route = "finance"
plan = ["get_budgets"]

[[case]]
id = "october-budgets"
request = "How did we do against our budgets in October?"
today = 2026-11-10
route = "finance"
plan = ["get_budgets"]
args = [{ month = "2026-10" }]

[[case]]
id = "forecast"
request = "Will any account run low over the next 30 days?"
today = 2026-11-10
route = "finance"
plan = ["get_forecast"]
args = [{ days = 30 }]

[[case]]
id = "three-months"
request = "Compare our net spending and income for the last 3 months"
today = 2026-11-10
route = "finance"
plan = ["month_over_month"]
args = [{ count = 3 }]

[[case]]
id = "unusual"
request = "Anything unusual in our spending this month?"
today = 2026-11-10
route = "finance"
plan = ["get_insights"]

[[case]]
id = "data-coverage"
request = "How up to date is our financial data?"
today = 2026-11-10
route = "finance"
plan = ["data_coverage"]

[[case]]
id = "paired-transfers"
request = "List the transfers between our accounts"
today = 2026-11-10
route = "finance"
plan = ["list_transfers"]

[[case]]
id = "propose-groceries"
request = "Propose the category Groceries for transaction 101"
today = 2026-11-10
route = "finance"
plan = ["propose_category"]
args = [{ transaction_id = 101, category = "Groceries" }]

[[case]]
id = "propose-rule"
request = "Propose a rule that puts merchants containing CORNER GROCER in Groceries, with transaction 101 as the example"
today = 2026-11-10
route = "finance"
plan = ["propose_rule"]
args = [{ example_id = 101, pattern = "CORNER GROCER", category = "Groceries", match = "contains" }]

[[case]]
id = "keep-note"
request = "finance: keep a note that we are saving for a new car"
today = 2026-11-10
route = "finance"
plan = ["log_advice"]

[[case]]
id = "open-proposals"
request = "Show my open proposals"
today = 2026-11-10
route = "finance"
plan = ["list_proposals"]
args = [{ status = "open" }]

[[case]]
id = "pay-a-bill"
request = "finance: pay the electricity bill now"
today = 2026-11-10
route = "finance"
plan = "escalate"

[[case]]
id = "not-finance"
request = "Book a flight to Lisbon for Friday"
today = 2026-11-10
route = "escalate"
```

`tests/unit/test_answer_dollars.py` (19 tests)

```python
import copy
from pathlib import Path

import pytest

from conductor.contracts import Escalation
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import (
    ANSWER_INPUT_BYTES,
    Answered,
    AnswerInputs,
    StepOutcome,
    answer_request,
    with_dollars,
)

RUN = "a" * 32
REQUEST = "What is our net worth?"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ({"amount_cents": -4210}, {"amount_dollars": "-42.10"}),
        ({"amount_cents": 0}, {"amount_dollars": "0.00"}),
        ({"amount_cents": 5}, {"amount_dollars": "0.05"}),
        ({"amount_cents": -5}, {"amount_dollars": "-0.05"}),
        ({"net_worth_cents": 123456}, {"net_worth_dollars": "1234.56"}),
        ({"big_cents": 100000000000001}, {"big_dollars": "1000000000000.01"}),
        (
            {"lines": [{"spent_cents": 4210, "label": "Groceries"}], "summary": {"net_cents": -1}},
            {
                "lines": [{"spent_dollars": "42.10", "label": "Groceries"}],
                "summary": {"net_dollars": "-0.01"},
            },
        ),
        ([{"bills_cents": -1299}, 7, "x"], [{"bills_dollars": "-12.99"}, 7, "x"]),
        ({"flag_cents": True}, {"flag_cents": True}),
        ({"rate_cents": 1.5}, {"rate_cents": 1.5}),
        ({"text_cents": "4210"}, {"text_cents": "4210"}),
        ({"none_cents": None}, {"none_cents": None}),
        ({"cents": 4210, "_cents": 4210}, {"cents": 4210, "_cents": 4210}),
        ({"amount_cents_total": 4210}, {"amount_cents_total": 4210}),
        (
            {"amount_cents": 4210, "amount_dollars": "set"},
            {"amount_cents": 4210, "amount_dollars": "set"},
        ),
        (4210, 4210),
    ],
    ids=[
        "negative",
        "zero",
        "five-cents",
        "minus-five-cents",
        "thousands",
        "large",
        "nested",
        "list",
        "bool",
        "float",
        "text",
        "null",
        "no-prefix",
        "inner-cents",
        "dollars-already",
        "scalar",
    ],
)
def test_cents_become_dollars(given: object, expected: object) -> None:
    assert with_dollars(given) == expected


def test_the_keys_keep_their_order_and_the_input_is_unchanged() -> None:
    given = {"a": 1, "x_cents": 250, "b": [{"y_cents": -3, "c": 2}]}
    kept = copy.deepcopy(given)
    found = with_dollars(given)
    assert list(found) == ["a", "x_dollars", "b"]
    assert list(found["b"][0]) == ["y_dollars", "c"]
    assert given == kept


def ask(tmp_path: Path, output: dict) -> tuple[ScriptedModel, object]:
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Done."}'))])
    found = answer_request(
        REQUEST,
        (StepOutcome(step=1, action="finance.get_balances", output=output),),
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    return model, found


def test_the_answer_reads_dollars(tmp_path: Path) -> None:
    output = {
        "accounts": [{"name": "Sample Checking", "balance_cents": -4210}],
        "net_worth_cents": 123456,
    }
    model, found = ask(tmp_path, output)
    sent = model.requests[0].user
    assert isinstance(found, Answered)
    assert '"balance_dollars": "-42.10"' in sent
    assert '"net_worth_dollars": "1234.56"' in sent
    assert "_cents" not in sent


def size(output: dict) -> int:
    inputs = AnswerInputs(
        request=REQUEST,
        results=(StepOutcome(step=1, action="finance.get_balances", output=output),),
    )
    return len(inputs.model_dump_json(indent=2).encode())


def test_the_bound_is_measured_on_the_dollars(tmp_path: Path) -> None:
    # "a_cents": 1000 becomes "a_dollars": "10.00", five bytes longer.
    pad = "x" * (ANSWER_INPUT_BYTES + 1 - size({"text": "", "a_dollars": "10.00"}))
    assert size({"text": pad, "a_dollars": "10.00"}) == ANSWER_INPUT_BYTES + 1
    assert size({"text": pad, "a_cents": 1000}) == ANSWER_INPUT_BYTES - 4
    model, found = ask(tmp_path, {"text": pad, "a_cents": 1000})
    assert found == Escalation(
        kind="answer_too_large",
        detail="the step results are 24001 bytes, more than 24000; ask for less",
        run_id=RUN,
    )
    assert model.requests == []
```

`tests/unit/test_eval_today.py` (10 tests)

```python
import json
from datetime import date
from pathlib import Path

import pytest

from conductor import clock
from conductor.domains import demo, finance
from conductor.evals.cases import CaseFileError, EvalCase, load_cases
from conductor.evals.run import run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.plan import plan_fields
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
CASE = '[[case]]\nid = "say-hi"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'
FINANCE = Path(__file__).resolve().parents[2] / "evals" / "cases" / "finance.toml"


@pytest.fixture(autouse=True)
def another_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: date(2031, 1, 1))


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.toml"
    path.write_text(text)
    return path


def test_a_case_may_name_its_today(tmp_path: Path) -> None:
    found = load_cases(write(tmp_path, CASE + "today = 2026-11-10\n"), REGISTRY)
    assert found == (
        EvalCase("say-hi", "demo: say hi", "demo", ("echo",), None, date(2026, 11, 10)),
    )
    assert load_cases(write(tmp_path, CASE), REGISTRY)[0].today is None


@pytest.mark.parametrize(
    "value",
    ['"2026-11-10"', "2026-11-10T09:00:00", "2026-11-10T09:00:00Z", "20261110", "09:00:00"],
    ids=["text", "local-datetime", "datetime", "number", "time"],
)
def test_today_must_be_a_date(tmp_path: Path, value: str) -> None:
    with pytest.raises(CaseFileError) as refused:
        load_cases(write(tmp_path, CASE + f"today = {value}\n"), REGISTRY)
    assert str(refused.value) == (
        f"{tmp_path / 'cases.toml'}: case 1: today must be a date such as 2026-11-10"
    )


def test_plan_fields_take_a_given_day() -> None:
    fields = plan_fields(demo.DOMAIN, today=date(2026, 11, 10))
    assert (fields["today"], fields["weekday"]) == ("2026-11-10", "Tuesday")
    fields = plan_fields(demo.DOMAIN)
    assert (fields["today"], fields["weekday"]) == ("2031-01-01", "Wednesday")


@pytest.mark.parametrize(
    ("today", "line"),
    [
        (date(2026, 11, 10), "Today is 2026-11-10, a Tuesday."),
        (None, "Today is 2031-01-01, a Wednesday."),
    ],
    ids=["given", "clock"],
)
def test_each_run_plans_on_the_case_day(tmp_path: Path, today: date | None, line: str) -> None:
    reply = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=reply))] * 2)
    case = EvalCase("say-hi", "demo: say hi", "demo", ("echo",), None, today)
    found = run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=2,
    )
    assert found.plan_ok == 2
    assert [line in request.system for request in model.requests] == [True, True]


def test_the_finance_cases_load_and_plan_on_one_day() -> None:
    found = load_cases(FINANCE, Registry((finance.DOMAIN,)))
    assert len(found) == 24
    assert {case.today for case in found} == {date(2026, 11, 10)}
    assert {case.route for case in found} == {"finance", "escalate"}
```

## Tests to write

Each with its deciding input:

- In `tests/unit/test_dollars_more.py`:
  - R1: amounts near a whole dollar: `-100` gives `"-1.00"`, `99` gives `"0.99"`, and `-101` gives `"-1.01"`.
  - R4: a case with both an invalid id and an invalid `today` reports the id's message, because `today` is checked last.
  - R5: `plan_request(..., today=date(2026, 11, 10))` plans with that day while `clock.today` is replaced by a function that raises, so the clock is not read.
- In `tests/integration/test_dollars_more.py` (with the fake finances server, as in `tests/integration/test_finance_more.py`):
  - R3: a `finance:` request with one `get_spending` step runs to `done`. The answer request's message holds `"spent_dollars": "42.10"` and no `_cents`, while the step's `TOOL_RESULT` output still holds `spent_cents` 4210 in its first line.

## Rules for this phase

- **Code decides** (AGENTS.md): the arithmetic is code, never asked of the model; the model only writes the reply.
- **Time from one place.** Code reads the day only through `clock.today()`, called through the module, unless a case gives it.
- **Synthetic data only.** The cases and every test use invented requests and amounts.
- **Constant messages.** The new message names the case number, never the value it refused.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 29 = 1000 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_answer_dollars.py tests/unit/test_eval_today.py --no-cov`, exactly `29 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/planning/answer.py,*/conductor/planning/plan.py,*/conductor/evals/cases.py,*/conductor/evals/run.py" --fail-under=100`;
- `grep -c "^## Phase 9d: " docs/progress.md` prints `1`, and then `.venv/bin/python scripts/check_reports.py --phase 9d` prints `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "clock\.today\(" -- src/conductor/evals`
  - `git grep --untracked -n -E "from conductor\.clock import" -- src`
- `git diff --stat HEAD -- src/conductor/domains src/conductor/prompts src/conductor/graph src/conductor/runtime.py src/conductor/store.py src/conductor/policy.py src/conductor/decisions.py src/conductor/web src/conductor/mcp_client src/conductor/llm src/conductor/routing src/conductor/cli src/conductor/config.py src/conductor/evals/report.py evals/cases/demo.toml tests` prints nothing (the new test files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 9d: dollars in the answer, and the finance cases (YYYY-MM-DD)`, with `Tests: 971 -> <passed> (given 29)`.
