# Phase 8a: running evaluation cases

## Goal

The first half of the evaluation harness: `conductor eval run` runs a set of synthetic cases against the real model and prints how consistent and how accurate its decisions are.

- **cases** (`conductor.evals.cases`): TOML files under `evals/cases/`, each case a request and what should come of it (the route, the plan's actions, optionally some arguments, or an escalation);
- **running** (`conductor.evals.run`): each case runs K times through **the decision points only**, `route_request` then `plan_request`: no graph, no approval, no step, so an evaluation can never cause a side effect;
- **numbers**, one line per case and one overall: consistency first (the share of runs that agree with the most common outcome), then route, plan, and argument accuracy, valid replies, escalations, and the median and 95th-percentile model time;
- a small repair from 7b: every button on the approvals page says what it does.

Decided with the owner (2026-11-09): Phase 7 ends with 7b; Phase 8 has **two parts** (8a these runs and numbers; 8b each report saved with the model digests and prompt hashes, and compared with the previous one); an evaluation goes through **the decision points only**; cases live **in the repository as TOML**; **K is 5 by default** (`--runs`), with **consistency as the headline**.

Decided by the architect, within those answers: an evaluation's registry is the one a real run sees (`domains.registered(settings)`), so the demo cases need `CONDUCTOR_DEMO=true`; model time is the sum of the `total_ns` Ollama reports for a run's replies (from the event log), so no new clock is read and tests can set it; expected arguments are matched on the keys a case gives.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 5: synthetic data only), `docs/architecture.md` ("Evaluation harness")
- `src/conductor/routing/route.py`, `src/conductor/planning/plan.py`, `src/conductor/events.py` (`MODEL_REPLY` payloads), `src/conductor/domains/__init__.py` (`registered`), `src/conductor/cli/main.py`, `src/conductor/web/app.py` and `src/conductor/web/templates/detail.html` (the buttons)

## Starting state

Phase 7b is built and verified, and everything is committed: N is `744`. **Sections: cli, core.** No `conductor/evals/` and no `evals/` folder exist. No new dependency (`tomllib` is in the standard library).

## Scope

| Path | What |
|---|---|
| `evals/cases/demo.toml` | given: five cases for the demo domain |
| `src/conductor/evals/__init__.py` | empty |
| `src/conductor/evals/cases.py` | `EvalCase`, `CaseFileError`, `load_cases` (Part 1) |
| `src/conductor/evals/run.py` | `MAX_RUNS`, `CaseResult`, `run_case`, `case_line`, `overall_line`, `model_for` (Part 2) |
| `src/conductor/cli/main.py` | `conductor eval run` (Part 3) |
| `src/conductor/web/app.py`, `src/conductor/web/templates/detail.html` | the button labels and field labels (Part 4) |
| `tests/unit/test_eval_cases.py`, `tests/unit/test_eval_run.py`, `tests/e2e/test_cli_eval.py`, `tests/e2e/test_web_labels.py` | given |
| `tests/unit/test_eval_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Saving reports, model digests, prompt hashes, comparing with an earlier report (8b).
- The answer decision point, the graph, approvals, steps, tools; parallel runs; any change to routing, planning, or `decide`.
- Cases from real requests; cases outside the repository; any domain but the registered ones.
- Running evaluations in `scripts/check.py` or in tests against a real model.

## Dependencies

None new.

## Design

A case file is TOML with only `[[case]]` tables, each with only these keys:

| Key | Holds | Rule |
|---|---|---|
| `id` | the case's name | fully matches `^[a-z0-9][a-z0-9-]{0,63}$`; unique across all files loaded together |
| `request` | the request text | a string whose `strip()` is not empty, at most 2000 characters |
| `route` | the expected route | a registered domain's name, or `escalate` (the route escalates as `unknown_route`) |
| `plan` | the expected plan | for a routed case, required: a list of that domain's action names in order, or `escalate` (the plan escalates as `invalid_plan`); for `route = "escalate"`, absent |
| `args` | expected arguments, optional | only with a list `plan`: one table per step; a run's step matches when it has each key of the table with that value (keys the case leaves out are not compared) |

```python
# conductor/evals/cases.py
@dataclass(frozen=True)
class EvalCase:
    id: str
    request: str
    route: str                                        # a domain, or "escalate"
    plan: tuple[str, ...] | Literal["escalate"] | None = None
    args: tuple[dict[str, Any], ...] | None = None

class CaseFileError(Exception): ...                   # str(): "<path>: <message>"

def load_cases(path: Path, registry: Registry, *, seen: set[str] | None = None) -> tuple[EvalCase, ...]: ...
```

`load_cases` reads one file (`seen` carries the ids of files loaded before it) and raises `CaseFileError` with the first problem, in this order and with these messages: `the file is not TOML` (from `tomllib`, its text never shown); a top-level key other than `case`: `unknown key <key>`; no case: `the file needs at least one [[case]]`; then for each case `n` (from 1), in order: `case <n>: unknown key <key>`; `case <n>: id must be lowercase letters, digits, and dashes` (also when missing or not a string); `case <n>: id <id> is used twice`; `case <n>: request must have 1 to 2000 characters`; `case <n>: route must be a registered domain or escalate`; `case <n>: a case that expects a route escalation has no plan`; `case <n>: a routed case needs a plan`; `case <n>: plan must be a list of the domain's actions or escalate`; `case <n>: args must be one table per planned step` (also with a `plan` of `escalate`). No message holds a request or a value from the file other than a key or an id.

```python
# conductor/evals/run.py
MAX_RUNS = 100
RUNS_MESSAGE = "runs must be 1 to 100"

@dataclass(frozen=True)
class CaseResult:
    case_id: str
    runs: int
    consistent: int        # runs whose outcome equals the most common outcome
    route_ok: int
    plan_ok: int
    args_ok: int | None    # None when the case gives no args
    valid: int             # runs with no invalid_model_output escalation
    escalated: int         # runs that ended in any escalation
    unavailable: int       # runs that ended in a model_unavailable escalation
    seconds: tuple[float, ...]   # model time of each run, in order

def model_for(settings: Settings) -> Model: ...        # OllamaModel(settings.ollama_host, timeout=settings.model_timeout_seconds)
def run_case(case: EvalCase, registry: Registry, *, model: Model, model_name: str, log: EventLog, runs: int) -> CaseResult: ...
def case_line(result: CaseResult) -> str: ...
def overall_line(results: Sequence[CaseResult]) -> str: ...
```

`run_case` refuses `runs` outside 1 to `MAX_RUNS` with `ValueError(RUNS_MESSAGE)`. Each run takes `run_id = ids.new_id()` and calls `route_request(case.request, registry, model=..., model_name=..., log=log, run_id=run_id)`, then, when routed, `plan_request(routed, registry, ...)` with the same run id. Its **outcome** is:

- `{"route": "escalate:<kind>"}` when the route escalated;
- `{"route": <domain>, "plan": "escalate:<kind>"}` when the plan escalated;
- `{"route": <domain>, "plan": [[<action name>, <args>], ...]}` otherwise (action names without the domain, args as in the `Plan`).

Two outcomes are the same when their `json.dumps(..., sort_keys=True)` are equal. Per run: the route is right when it is the case's domain, or, for `escalate`, an `unknown_route` escalation; the plan is right, for a `route = "escalate"` case, exactly when the route is; otherwise when the route is right and the plan is the case's actions in order, or, for `plan = "escalate"`, an `invalid_plan` escalation; the args are right when the plan is right and each step holds the case's table (only for cases with `args`). A run's seconds are the sum of the `total_ns` of the `MODEL_REPLY` events logged under its run id, divided by 10⁹ (0 when there is none).

`case_line(result)`:

```text
<id>  consistent <c>/<K>  route <r>/<K>  plan <p>/<K>  args <a>/<K>  valid <v>/<K>  escalated <e>/<K>  p50 <x>s  p95 <y>s
```

with `args -` when `args_ok` is `None`, and the times to two decimals. `overall_line(results)`:

```text
overall  <n> cases  consistent <sum>/<total>  route ...  plan ...  args <sum>/<total of cases with args>  valid ...  escalated ...  p50 <x>s  p95 <y>s
```

summing each count over the cases (`args -` when no case has args), with the percentiles over every run's seconds. Percentiles are nearest-rank: the value at position `ceil(q × n)` (at least 1) of the sorted list.

`conductor eval run [--cases PATH] [--runs N]` (defaults `evals/cases` and 5): checks `--runs` first (`Error: --runs must be 1 to 100`); `PATH` is one `.toml` file or a folder whose `*.toml` files are loaded in sorted order (none found: `Error: no case files at <PATH>`, the path as given); every file is loaded with one shared `seen` before any run (a `CaseFileError`: `Error: <its text>`); the registry is `Registry(domains.registered(settings))`; the model is `run.model_for(settings)`, read through the module; the log is `EventLog(settings.data_dir / "evals" / "runs")`. It prints `case_line` for each case as it finishes, then `overall_line`, and exits 0. Errors are one `Error:` line on stderr and exit 1.

**The page's labels** (Part 4): every form on the detail pages gets a submit button whose text says what it does, `Approve`, `Reject`, `Edit and approve`, `Retry`, `Cancel`, in that order on each page, and its note field `<label for="note-<verb>">Note</label>` with `<textarea id="note-<verb>" name="note">` (`<verb>` the last part of the form's path); the edit form's text box is labelled `<label for="args-edit">Arguments (JSON)</label>` with `id="args-edit"`. Nothing else on the page changes.

## Facts

- `tomllib.loads` raises `tomllib.TOMLDecodeError` for text that is not TOML; its message quotes the file, so it is never shown.
- `MODEL_REPLY` events carry `total_ns` (Ollama's `total_duration`; `ScriptedModel` replies carry what the test gives); a rule route makes no model call, so its run's seconds are the plan's alone.
- A model that is down gives a `model_unavailable` escalation (3c), counted under `escalated` and `unavailable`, not as an invalid reply.
- Temperature 0 and seed 7 (3a) should make repeated runs agree; a run that disagrees is a finding about the model or the prompt, which is what the consistency number is for.

## Requirements

### Part 1: cases

- **R1.** `EvalCase`, `load_cases`, and `CaseFileError` are as under Design, with the checks in that order and those messages; the given `evals/cases/demo.toml` loads.

### Part 2: running

- **R2.** `run_case` refuses a bad `runs` count, then runs the case that many times through `route_request` and `plan_request` only, one new run id each.
- **R3.** Outcomes, sameness, and the right-or-not of route, plan, and args are as under Design; `consistent` is the count of the most common outcome.
- **R4.** `valid`, `escalated`, `unavailable`, and `seconds` are as under Design; seconds come from the run's `MODEL_REPLY` events only.
- **R5.** `case_line` and `overall_line` print exactly the Design's text, with nearest-rank percentiles.

### Part 3: the command

- **R6.** `conductor eval run` checks, loads, and runs as under Design, prints a line per case and the overall line, and exits 0; its errors are one `Error:` line and exit 1.

### Part 4: the page's labels

- **R7.** The buttons and labels are as under Design; every earlier web test passes unchanged.

### Part 5: the rules

- **R8.** `conductor/evals/` imports from the project only `conductor` (for `ids`), `conductor.config`, `conductor.contracts`, `conductor.events`, `conductor.llm.model`, `conductor.llm.ollama`, `conductor.planning.plan`, `conductor.registry`, and `conductor.routing.route`; it never imports the graph, the runtime, the store, policy, decisions, or MCP, and so can never run a step.
- **R9.** `scripts/check.py` does not run an evaluation; tests use `ScriptedModel` only.
- **R10.** `evals/cases.py`, `evals/run.py`, `cli/main.py`, and `web/app.py` reach 100% of lines and branches.

## Given tests

32 tests in four files (counting each parameter set), and the given case file. Do not change them; if one fails, the code is wrong.

`evals/cases/demo.toml` (given; copy it exactly)

```toml
# Evaluation cases for the demo domain. Synthetic requests only (AGENTS.md rule 5).
# Run with CONDUCTOR_DEMO=true: .venv/bin/conductor eval run

[[case]]
id = "repeat-hello"
request = "Please repeat after me: hello there"
route = "demo"
plan = ["echo"]
args = [{ text = "hello there" }]

[[case]]
id = "note-milk"
request = "Write down that we need milk"
route = "demo"
plan = ["note"]

[[case]]
id = "echo-then-note"
request = "Echo the word ready, then write a note titled Ready"
route = "demo"
plan = ["echo", "note"]

[[case]]
id = "no-action-fits"
request = "demo: book a table for two at eight"
route = "demo"
plan = "escalate"

[[case]]
id = "no-domain-fits"
request = "What is the weather in Lisbon tomorrow?"
route = "escalate"
```

`tests/unit/test_eval_cases.py` (15 tests)

```python
from pathlib import Path

import pytest

from conductor.domains import demo
from conductor.evals.cases import CaseFileError, EvalCase, load_cases
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
GIVEN = Path(__file__).resolve().parents[2] / "evals" / "cases" / "demo.toml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_given_demo_cases_load() -> None:
    cases = load_cases(GIVEN, REGISTRY)
    assert [case.id for case in cases] == [
        "repeat-hello",
        "note-milk",
        "echo-then-note",
        "no-action-fits",
        "no-domain-fits",
    ]
    assert cases[0] == EvalCase(
        id="repeat-hello",
        request="Please repeat after me: hello there",
        route="demo",
        plan=("echo",),
        args=({"text": "hello there"},),
    )
    assert (cases[3].plan, cases[4].route, cases[4].plan) == ("escalate", "escalate", None)
    assert cases[1].args is None


def problem(tmp_path: Path, text: str) -> str:
    path = write(tmp_path, text)
    with pytest.raises(CaseFileError) as raised:
        load_cases(path, REGISTRY)
    assert str(raised.value).startswith(f"{path}: ")
    return str(raised.value)[len(f"{path}: ") :]


CASE = '[[case]]\nid = "a"\nrequest = "Echo hi"\nroute = "demo"\nplan = ["echo"]\n'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[[case]\n", "the file is not TOML"),
        ('title = "x"\n', "unknown key title"),
        ("", "the file needs at least one [[case]]"),
        (CASE + 'colour = "red"\n', "case 1: unknown key colour"),
        (
            CASE.replace('id = "a"', 'id = "A b"'),
            "case 1: id must be lowercase letters, digits, and dashes",
        ),
        (CASE + CASE, "case 2: id a is used twice"),
        (
            CASE.replace('request = "Echo hi"', 'request = "  "'),
            "case 1: request must have 1 to 2000 characters",
        ),
        (
            CASE.replace('route = "demo"', 'route = "travel"'),
            "case 1: route must be a registered domain or escalate",
        ),
        (
            CASE.replace('["echo"]', '["send"]'),
            "case 1: plan must be a list of the domain's actions or escalate",
        ),
        (
            CASE.replace('route = "demo"', 'route = "escalate"'),
            "case 1: a case that expects a route escalation has no plan",
        ),
        (CASE.replace('plan = ["echo"]\n', ""), "case 1: a routed case needs a plan"),
        (
            CASE + 'args = [{ text = "hi" }, { text = "again" }]\n',
            "case 1: args must be one table per planned step",
        ),
        (
            CASE.replace('id = "a"\n', ""),
            "case 1: id must be lowercase letters, digits, and dashes",
        ),
    ],
)
def test_what_a_case_file_may_not_hold(tmp_path: Path, text: str, message: str) -> None:
    assert problem(tmp_path, text) == message


def test_a_problem_never_quotes_the_request(tmp_path: Path) -> None:
    text = CASE.replace('request = "Echo hi"', 'request = "SYNTHETIC-SECRET"').replace(
        'route = "demo"', 'route = "nowhere"'
    )
    assert "SYNTHETIC-SECRET" not in problem(tmp_path, text)
```

`tests/unit/test_eval_run.py` (8 tests)

```python
import json
from pathlib import Path

import pytest

from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.run import CaseResult, case_line, overall_line, run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
ECHO = EvalCase(
    id="say-hi",
    request="Say hi back to me",
    route="demo",
    plan=("echo",),
    args=({"text": "hi"},),
)
ROUTE = '{"domain": "demo"}'


def plan(*steps: tuple[str, dict]) -> str:
    return json.dumps({"steps": [{"action": a, "args": args} for a, args in steps]})


def scripted(*replies) -> ScriptedModel:
    made = []
    for point, content, seconds in replies:
        reply = (
            content
            if isinstance(content, ModelUnavailable)
            else ModelReply(content=content, total_ns=int(seconds * 1e9))
        )
        made.append(ScriptedReply(point, reply))
    return ScriptedModel(made)


def run(case: EvalCase, model: ScriptedModel, tmp_path: Path, runs: int) -> CaseResult:
    return run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=runs,
    )


def test_three_runs_that_agree(tmp_path: Path) -> None:
    replies = [("route", ROUTE, 1.0), ("plan", plan(("echo", {"text": "hi"})), 2.0)] * 3
    result = run(ECHO, scripted(*replies), tmp_path, 3)
    assert result == CaseResult(
        case_id="say-hi",
        runs=3,
        consistent=3,
        route_ok=3,
        plan_ok=3,
        args_ok=3,
        valid=3,
        escalated=0,
        unavailable=0,
        seconds=(3.0, 3.0, 3.0),
    )
    assert case_line(result) == (
        "say-hi  consistent 3/3  route 3/3  plan 3/3  args 3/3  valid 3/3  escalated 0/3"
        "  p50 3.00s  p95 3.00s"
    )


def test_runs_that_disagree(tmp_path: Path) -> None:
    replies = [
        ("route", ROUTE, 1.0),
        ("plan", plan(("echo", {"text": "hi"})), 1.0),
        ("route", ROUTE, 1.0),
        ("plan", plan(("echo", {"text": "Hi!"})), 3.0),
        ("route", '{"domain": "unknown"}', 0.5),
        ("route", ROUTE, 1.0),
        ("plan", plan(("note", {"title": "hi"})), 2.0),
    ]
    result = run(ECHO, scripted(*replies), tmp_path, 4)
    assert (result.consistent, result.route_ok, result.plan_ok, result.args_ok) == (1, 3, 2, 1)
    assert (result.valid, result.escalated, result.unavailable) == (4, 1, 0)
    assert result.seconds == (2.0, 4.0, 0.5, 3.0)
    assert case_line(result).endswith("p50 2.00s  p95 4.00s")


def test_an_invalid_reply_and_an_unavailable_model(tmp_path: Path) -> None:
    replies = [
        ("route", ROUTE, 1.0),
        ("plan", '{"steps": [{"action": "send", "args": {}}]}', 1.0),
        ("route", ModelUnavailable("timeout"), 0),
    ]
    result = run(ECHO, scripted(*replies), tmp_path, 2)
    assert (result.valid, result.escalated, result.unavailable) == (1, 2, 1)
    assert (result.route_ok, result.plan_ok) == (1, 0)


def test_a_case_that_expects_escalations(tmp_path: Path) -> None:
    no_domain = EvalCase(id="weather", request="Weather in Lisbon?", route="escalate")
    result = run(no_domain, scripted(("route", '{"domain": "unknown"}', 1.0)), tmp_path, 1)
    assert (result.route_ok, result.plan_ok, result.args_ok, result.escalated) == (1, 1, None, 1)
    nothing_fits = EvalCase(id="table", request="demo: book a table", route="demo", plan="escalate")
    result = run(nothing_fits, scripted(("plan", '{"steps": []}', 1.0)), tmp_path, 1)
    assert (result.route_ok, result.plan_ok, result.escalated) == (1, 1, 1)
    assert "args -" in case_line(result)


def test_a_rule_route_asks_the_model_only_to_plan(tmp_path: Path) -> None:
    case = EvalCase(id="prefixed", request="demo: say hi", route="demo", plan=("echo",))
    model = scripted(("plan", plan(("echo", {"text": "hi"})), 1.5))
    result = run(case, model, tmp_path, 1)
    assert (result.consistent, result.plan_ok, result.seconds) == (1, 1, (1.5,))
    assert [request.point for request in model.requests] == ["plan"]


def test_the_overall_line(tmp_path: Path) -> None:
    first = CaseResult("a", 2, 2, 2, 2, 2, 2, 0, 0, (1.0, 2.0))
    second = CaseResult("b", 2, 1, 2, 1, None, 1, 1, 1, (3.0, 4.0))
    assert overall_line((first, second)) == (
        "overall  2 cases  consistent 3/4  route 4/4  plan 3/4  args 2/2  valid 3/4"
        "  escalated 1/4  p50 2.00s  p95 4.00s"
    )


@pytest.mark.parametrize("runs", [0, 101])
def test_runs_are_1_to_100(tmp_path: Path, runs: int) -> None:
    with pytest.raises(ValueError) as raised:
        run(ECHO, scripted(), tmp_path, runs)
    assert str(raised.value) == "runs must be 1 to 100"
```

`tests/e2e/test_cli_eval.py` (6 tests)

```python
import json
from pathlib import Path

import pytest

from conductor.evals import run as evals_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run

CASES = """[[case]]
id = "say-hi"
request = "demo: say hi"
route = "demo"
plan = ["echo"]
args = [{ text = "hi" }]

[[case]]
id = "weather"
request = "demo: what is the weather"
route = "demo"
plan = "escalate"
"""


@pytest.fixture
def cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases"
    path.mkdir()
    (path / "demo.toml").write_text(CASES, encoding="utf-8")
    return path


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[ScriptedReply]:
    replies: list[ScriptedReply] = []
    monkeypatch.setattr(evals_run, "model_for", lambda settings: ScriptedModel(replies))
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    return replies


def plan_reply(steps: list, seconds: float) -> ScriptedReply:
    content = json.dumps({"steps": steps})
    return ScriptedReply("plan", ModelReply(content=content, total_ns=int(seconds * 1e9)))


def test_eval_run_prints_a_line_per_case_and_overall(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend(
        [plan_reply(echo, 1.0), plan_reply(echo, 1.0), plan_reply([], 2.0), plan_reply([], 2.0)]
    )
    result = run("eval", "run", "--cases", cases, "--runs", "2")
    assert (result.exit_code, result.stderr) == (0, "")
    assert result.stdout.splitlines() == [
        "say-hi  consistent 2/2  route 2/2  plan 2/2  args 2/2  valid 2/2  escalated 0/2"
        "  p50 1.00s  p95 1.00s",
        "weather  consistent 2/2  route 2/2  plan 2/2  args -  valid 2/2  escalated 2/2"
        "  p50 2.00s  p95 2.00s",
        "overall  2 cases  consistent 4/4  route 4/4  plan 4/4  args 2/2  valid 4/4"
        "  escalated 2/4  p50 1.00s  p95 2.00s",
    ]


def test_five_runs_by_default_from_one_file(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0)] * 5)
    single = cases / "only.toml"
    single.write_text(CASES.split("\n\n")[0] + "\n", encoding="utf-8")
    result = run("eval", "run", "--cases", single)
    assert result.stdout.splitlines()[0].startswith("say-hi  consistent 5/5")


def test_runs_are_logged_under_the_data_folder(cases: Path, model: list, tmp_path: Path) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0), plan_reply([], 1.0)])
    run("eval", "run", "--cases", cases, "--runs", "1")
    assert len(list((tmp_path / "data" / "evals" / "runs").glob("*.jsonl"))) == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--runs", "0"), "Error: --runs must be 1 to 100\n"),
        (("--cases", "nowhere"), "Error: no case files at nowhere\n"),
    ],
)
def test_errors(cases: Path, model: list, args: tuple[str, ...], message: str) -> None:
    result = run("eval", "run", *args)
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", message)


def test_a_bad_case_file_names_itself(cases: Path, model: list) -> None:
    bad = cases / "bad.toml"
    bad.write_text('[[case]]\nid = "x"\nrequest = "hi"\nroute = "travel"\n', encoding="utf-8")
    result = run("eval", "run", "--cases", cases)
    assert (result.exit_code, result.stdout) == (1, "")
    assert result.stderr == f"Error: {bad}: case 1: route must be a registered domain or escalate\n"
```

`tests/e2e/test_web_labels.py` (3 tests)

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.store import Store
from conductor.web.app import create_app

FIRST = "1" * 32


class Quiet:
    def start(self, run_id: str) -> None:
        pass

    def running(self, run_id: str) -> bool:
        return False

    def error(self, run_id: str) -> str | None:
        return None


@pytest.fixture
def page(tmp_path: Path) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=Quiet()), base_url="http://127.0.0.1:8766")


def add(tmp_path: Path, stage: str) -> Store:
    db = Store(tmp_path / "data" / "conductor.db")
    step = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id="a" * 32,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )
    return db


def buttons(text: str) -> list[str]:
    return [part.split("</button>")[0] for part in text.split('<button type="submit">')[1:]]


@pytest.mark.parametrize(
    ("stage", "labels"),
    [("step", ["Approve", "Reject", "Edit and approve"]), ("plan", ["Approve", "Reject"])],
)
def test_each_approval_form_says_what_it_does(
    tmp_path: Path, page: TestClient, stage: str, labels: list[str]
) -> None:
    add(tmp_path, stage)
    text = page.get(f"/approvals/{FIRST}").text
    assert buttons(text) == labels
    assert '<label for="note-approve">Note</label>' in text


def test_each_escalation_form_says_what_it_does(tmp_path: Path, page: TestClient) -> None:
    db = add(tmp_path, "step")
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id="a" * 32)
    )
    text = page.get(f"/escalations/{raised.escalation_id}").text
    assert buttons(text) == ["Retry", "Cancel"]
```

## Tests to write

In `tests/unit/test_eval_more.py`, each with its deciding input:

- R1: an id used in an earlier file (through `seen`) is refused as used twice; a `plan` that is a number, and `args` with `plan = "escalate"`, give their messages; a request of exactly 2000 characters loads.
- R3: `args` that name a key the step does not have are not right; a plan with the right actions in another order is not right; a `plan = "escalate"` case whose plan escalated as `invalid_model_output` is not right.
- R4: a run with two model replies (route by the classifier, then the plan) sums both `total_ns`.
- R5: one run gives p50 and p95 equal to it; `overall_line` with no case having args prints `args -`.
- R6: `--runs 101` is refused; a folder with two files runs the cases of both, in file order then case order.

## Rules for this phase

- **No side effects**: an evaluation reaches only `route_request` and `plan_request`; the import search below allows only the modules R8 names, so the graph, the runtime, the store, and MCP are never imported by `conductor.evals`.
- **Synthetic data only** (`AGENTS.md` rule 5): the given cases are invented; cases are reviewed like code.
- **Network**: only the model, through `OllamaModel` on the configured loopback host.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 32 = 776 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_eval_cases.py tests/unit/test_eval_run.py tests/e2e/test_cli_eval.py tests/e2e/test_web_labels.py --no-cov`, exactly `32 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/evals/*.py,*/conductor/cli/main.py,*/conductor/web/app.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 8a`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/evals | grep -v -E ":from conductor(\.config|\.contracts|\.events|\.llm\.model|\.llm\.ollama|\.planning\.plan|\.registry|\.routing\.route)? import "`
  - `git grep --untracked -n -E "eval" -- scripts/check.py`
- `git diff --stat HEAD -- src/conductor/routing src/conductor/planning src/conductor/llm src/conductor/graph src/conductor/runtime.py tests/e2e/test_web_pages.py tests/e2e/test_web_decide.py tests/e2e/test_web_runs.py tests/support.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 8a: running evaluation cases (YYYY-MM-DD)`, with `Tests: 744 -> <passed> (given 32)`.
