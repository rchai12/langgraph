# Phase 2a: contracts

## Goal

The typed messages every later phase passes around, in one pure package, `conductor.contracts`:

- `Route` (which domain a request goes to, and whether a rule or the model decided);
- `Step` and `Plan` (what the planner's decision point returns, Phase 5);
- `TaskSpec` and `TaskResult` (what a subagent receives and gives back);
- `Escalation` and `FieldProblem` (why a run stopped and waits for the person), with `problems_from`, which turns a validation error into field locations and error codes **without any of the values that failed**.

Text from outside (a model's reply, a stored checkpoint read back as JSON) is parsed strictly through one entry point, `from_json`. Checking a step's arguments against its action's own schema is Phase 2b's registry, not this phase.

Decided with the owner (2026-10-26): the model does not write step ids (a step's number is its position, counted by code); an escalation carries codes and locations and points at the run's event log, never the model's text or tool data; the approval contracts come with Phase 4.

## Read first

- `docs/phase-conventions.md` (everything this spec does not repeat)
- `AGENTS.md`, `docs/architecture.md` ("Contracts", "Principles")
- `src/conductor/events.py` for the house style of a Pydantic model (`ConfigDict(frozen=True, extra="forbid")`)

## Starting state

Phase 1 is built and committed: N is `70`. **Sections: core.** Pydantic is 2.14 (`.venv/bin/python -m pip show pydantic`). No package `src/conductor/contracts/` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/contracts/__init__.py` | re-exports exactly the names in `__all__` (R11) |
| `src/conductor/contracts/base.py` | `Contract`, `JsonObject`, the name and id types, `NOT_FINITE_MESSAGE` (Part 1) |
| `src/conductor/contracts/plans.py` | `Route`, `Step`, `Plan` (Part 2) |
| `src/conductor/contracts/tasks.py` | `TaskSpec`, `TaskResult`, `TaskError` (Part 3) |
| `src/conductor/contracts/escalations.py` | `Escalation`, `FieldProblem`, `problems_from` (Part 4) |
| `tests/unit/test_contracts_plans.py`, `tests/unit/test_contracts_tasks.py` | given |
| `tests/unit/test_contracts_more.py` | new: the coder's tests (Tests to write) |
| `docs/progress.md` | one new entry |

## Out of scope

- The registry, domains, actions, argument schemas per action, or checking a plan against them (2b).
- `ApprovalRequest`, `ApprovalDecision` (Phase 4).
- Step ids, dependencies between steps, or steps that read another step's output.
- Any change to `events.py` (its own `JsonValue` alias stays; `contracts` does not import it).
- Helpers that build contracts from the graph's state, JSON schemas for Ollama, or prompt text (Phases 3 and 5).

## Dependencies

None new.

## Design

```python
# conductor/contracts/base.py
NOT_FINITE_MESSAGE = "numbers must be finite"

class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def from_json(cls, text: str | bytes) -> Self: ...      # cls.model_validate_json(text, strict=True)

JsonObject = Annotated[dict[str, JsonValue], AfterValidator(<the finite check>)]   # pydantic.JsonValue

Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ActionName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,31}$")]
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
```

```python
# conductor/contracts/plans.py
MAX_STEPS = 8
ROUTE_MESSAGE = "a rule route needs a rule_id and a model route has none"
ONE_DOMAIN_MESSAGE = "every step must be in one domain"
DecidedBy = Literal["rule", "model"]

class Route(Contract):
    domain: Name
    decided_by: DecidedBy
    rule_id: RuleId | None = None

class Step(Contract):
    action: ActionName
    args: JsonObject                     # required: the planner always writes it, {} when empty

    @property
    def domain(self) -> str: ...         # the part before the dot

class Plan(Contract):
    steps: tuple[Step, ...]              # 1 to MAX_STEPS

    @property
    def domain(self) -> str: ...         # the steps' one domain
```

```python
# conductor/contracts/tasks.py
MAX_ATTEMPTS = 3
RESULT_MESSAGE = (
    "a succeeded result has output and no error; any other result has an error and no output"
)
TaskStatus = Literal["succeeded", "failed", "escalated"]
TaskErrorKind = Literal["invalid_args", "invalid_result", "tool_error", "agent_failed", "timeout"]

class TaskError(Contract):
    kind: TaskErrorKind
    message: str                          # 1 to 500 characters

class TaskResult(Contract):
    task_id: Id
    status: TaskStatus
    output: JsonObject | None = None
    error: TaskError | None = None
    attempts: int                         # 1 to MAX_ATTEMPTS

class TaskSpec(Contract):
    task_id: Id
    run_id: Id
    thread_id: Id
    step: int                             # the step's position in its plan, 1 to MAX_STEPS
    action: ActionName
    args: JsonObject
    context: tuple[TaskResult, ...] = ()  # results of earlier steps, at most MAX_STEPS - 1
    max_attempts: int = 1                 # 1 to MAX_ATTEMPTS

    @property
    def domain(self) -> str: ...
```

```python
# conductor/contracts/escalations.py
MAX_PROBLEMS = 20
EscalationKind = Literal[
    "invalid_model_output", "unknown_route", "invalid_plan",
    "tool_error", "retries_exhausted", "rejected",
]

class FieldProblem(Contract):
    loc: str                              # dotted location, "" for the whole object
    code: str                             # pattern ^[a-z][a-z0-9_-]{0,63}$ (Pydantic's codes use "-" too)

class Escalation(Contract):
    kind: EscalationKind
    detail: str                           # 1 to 500 characters
    run_id: Id                            # where the full record is: the run's event log
    problems: tuple[FieldProblem, ...] = ()   # at most MAX_PROBLEMS

def problems_from(error: ValidationError) -> tuple[FieldProblem, ...]: ...
```

The `Literal` sets are plain assignments (`DecidedBy = Literal[...]`), not `type` statements, so `typing.get_args` reads them.

### Facts about Pydantic 2.14 (from a spike)

- A model-wide `strict=True` refuses a Python `list` for a `tuple` field, which would break building contracts from parsed data and from LangGraph's checkpoints later. So `Contract` is **not** strict in its config; strictness applies only in `from_json`, where a JSON array is still accepted for a tuple.
- `pydantic.JsonValue` accepts `NaN` and `Infinity` from JSON even with `allow_inf_nan=False`, and with that setting Python input fails with a different error type. So `Contract` does **not** set `allow_inf_nan`; `JsonObject`'s own after-validator refuses every non-finite float at any depth, with `NOT_FINITE_MESSAGE`, on both paths.
- A `pattern` is matched with Rust's `regex` `is_match`, which is **not anchored**: every pattern needs `^` and `$`. Rust's `$` does not match before a final newline, so `"demo.echo\n"` is refused.
- A validation error's `loc` holds the keys of the input itself (`("args", "card 4417-1234")`), and its `type` may contain `-` (`invalid-json-value`).

## Requirements

### Part 1: the base

- **R1.** Every contract derives from `Contract`: frozen, extra fields refused. `from_json(text)` is `model_validate_json(text, strict=True)`: a number written as text (`"max_attempts":"2"`) is refused, not converted.
- **R2.** `JsonObject` refuses `NaN`, `Infinity`, and `-Infinity` anywhere inside it (in lists and objects at any depth), raising `ValueError(NOT_FINITE_MESSAGE)` from its validator, whether the contract is built in Python or read with `from_json`.
- **R3.** The name and id types are the anchored patterns under Design: a domain or action part is a lowercase letter then up to 31 of `a-z0-9_`; an action is exactly two parts joined by one `.`.

### Part 2: routes and plans

- **R4.** `Route`: a `rule` route has a `rule_id`; a `model` route has none. Otherwise a model validator raises `ValueError(ROUTE_MESSAGE)`.
- **R5.** `Step.args` is required; `Step.domain` is the part of `action` before the dot. Every `domain` in this phase is a plain `@property`, never a `computed_field`, so it is not dumped (a dumped field would be refused by `from_json` as extra).
- **R6.** `Plan.steps` has 1 to `MAX_STEPS` steps (`Field(min_length=1, max_length=MAX_STEPS)`), all in one domain, else a model validator raises `ValueError(ONE_DOMAIN_MESSAGE)`. `Plan.domain` is that domain.

### Part 3: tasks

- **R7.** `TaskSpec` bounds: `step` 1 to `MAX_STEPS`, `max_attempts` 1 to `MAX_ATTEMPTS` (`ge`/`le`), `context` at most `MAX_STEPS - 1` results. `TaskSpec.domain` as for a step.
- **R8.** `TaskResult`: `succeeded` needs `output` (an empty object counts) and no `error`; `failed` and `escalated` need an `error` and no `output`. Otherwise a model validator raises `ValueError(RESULT_MESSAGE)`. `attempts` is 1 to `MAX_ATTEMPTS`. `TaskError.message` is 1 to 500 characters.

### Part 4: escalations

- **R9.** `Escalation.detail` is 1 to 500 characters; `problems` at most `MAX_PROBLEMS`.
- **R10.** `problems_from(error)` returns one `FieldProblem` for each of the first `MAX_PROBLEMS` entries of `error.errors()`, in order: `code` is the entry's `type`; `loc` joins the location's parts with `.`, where an `int` is written as digits, a `str` matching `^[A-Za-z_][A-Za-z0-9_]{0,63}$` is kept, and any other `str` becomes `*`. It never reads `input`, `msg`, `ctx`, or `url`, so no value that failed validation reaches an escalation.

### Part 5: the package

- **R11.** `conductor.contracts` re-exports exactly the 22 names its given test lists, in `__all__`. `Name`, `ActionName`, `RuleId`, and `Id` stay in `conductor.contracts.base`.
- **R12.** Nothing under `src/conductor/contracts/` imports from `conductor` except `conductor.contracts` itself.

## Given tests

38 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_contracts_plans.py` (21 tests)

```python
import pytest
from pydantic import ValidationError

from conductor import contracts
from conductor.contracts import (
    MAX_STEPS,
    NOT_FINITE_MESSAGE,
    ONE_DOMAIN_MESSAGE,
    ROUTE_MESSAGE,
    Plan,
    Route,
    Step,
)


def problems(raised: pytest.ExceptionInfo[ValidationError]) -> list[tuple[str, str]]:
    return [
        (".".join(str(part) for part in error["loc"]), error["type"])
        for error in raised.value.errors()
    ]


def reason(raised: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(raised.value.errors()[0]["ctx"]["error"])


def test_a_plan_from_the_models_json() -> None:
    plan = Plan.from_json(
        '{"steps":[{"action":"finance.get_spending","args":{"month":"2026-09","by":["category"]}},'
        '{"action":"finance.list_accounts","args":{}}]}'
    )
    assert plan == Plan(
        steps=(
            Step(action="finance.get_spending", args={"month": "2026-09", "by": ["category"]}),
            Step(action="finance.list_accounts", args={}),
        )
    )
    assert plan.domain == "finance"
    assert plan.steps[0].domain == "finance"
    assert MAX_STEPS == 8


def test_extra_fields_are_refused_and_code_may_pass_lists() -> None:
    with pytest.raises(ValidationError) as raised:
        Route.from_json('{"domain":"finance","decided_by":"model","rule_id":null,"extra":1}')
    assert problems(raised) == [("extra", "extra_forbidden")]
    built = Plan.model_validate({"steps": [{"action": "demo.echo", "args": {}}]})
    assert built.steps == (Step(action="demo.echo", args={}),)


@pytest.mark.parametrize(
    "action",
    [
        "echo",
        "Demo.echo",
        "demo.echo.twice",
        "demo.echo\n",
        "a" * 33 + ".echo",
    ],
)
def test_an_action_name_must_be_domain_dot_name(action: str) -> None:
    with pytest.raises(ValidationError) as raised:
        Step(action=action, args={})
    assert problems(raised) == [("action", "string_pattern_mismatch")]


def test_the_longest_names_are_accepted() -> None:
    name = "a" + "b" * 31
    assert Step(action=f"{name}.{name}", args={}).domain == name


@pytest.mark.parametrize(
    "text",
    [
        '{"action":"demo.echo","args":{"n":NaN}}',
        '{"action":"demo.echo","args":{"deep":{"n":-Infinity}}}',
    ],
)
def test_numbers_must_be_finite_in_json(text: str) -> None:
    with pytest.raises(ValidationError) as raised:
        Step.from_json(text)
    assert reason(raised) == NOT_FINITE_MESSAGE
    assert NOT_FINITE_MESSAGE == "numbers must be finite"


def test_numbers_must_be_finite_when_built() -> None:
    with pytest.raises(ValidationError) as raised:
        Step(action="demo.echo", args={"values": [1.5, {"x": float("nan")}]})
    assert reason(raised) == NOT_FINITE_MESSAGE


@pytest.mark.parametrize("count", [0, 9])
def test_a_plan_has_one_to_eight_steps(count: int) -> None:
    steps = [{"action": "demo.echo", "args": {"n": n}} for n in range(count)]
    with pytest.raises(ValidationError) as raised:
        Plan.model_validate({"steps": steps})
    assert [kind for _, kind in problems(raised)] == ["too_short" if count == 0 else "too_long"]


def test_a_plan_stays_in_one_domain() -> None:
    with pytest.raises(ValidationError) as raised:
        Plan(
            steps=(Step(action="demo.echo", args={}), Step(action="finance.list_accounts", args={}))
        )
    assert reason(raised) == ONE_DOMAIN_MESSAGE
    assert ONE_DOMAIN_MESSAGE == "every step must be in one domain"


@pytest.mark.parametrize(
    ("decided_by", "rule_id", "ok"),
    [
        ("rule", "finance.prefix", True),
        ("model", None, True),
        ("rule", None, False),
        ("model", "finance.prefix", False),
    ],
)
def test_a_route_names_its_rule_only_when_a_rule_decided(
    decided_by: str, rule_id: str | None, ok: bool
) -> None:
    if ok:
        route = Route(domain="finance", decided_by=decided_by, rule_id=rule_id)
        assert (route.decided_by, route.rule_id) == (decided_by, rule_id)
        return
    with pytest.raises(ValidationError) as raised:
        Route(domain="finance", decided_by=decided_by, rule_id=rule_id)
    assert reason(raised) == ROUTE_MESSAGE
    assert ROUTE_MESSAGE == "a rule route needs a rule_id and a model route has none"


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("domain", "Finance", "string_pattern_mismatch"),
        ("decided_by", "guess", "literal_error"),
    ],
)
def test_a_route_refuses_bad_values(field: str, value: str, kind: str) -> None:
    given = {"domain": "finance", "decided_by": "rule", "rule_id": "finance.prefix", field: value}
    with pytest.raises(ValidationError) as raised:
        Route.model_validate(given)
    assert problems(raised) == [(field, kind)]


def test_the_package_exports_exactly_its_public_names() -> None:
    assert sorted(contracts.__all__) == [
        "Contract",
        "DecidedBy",
        "Escalation",
        "EscalationKind",
        "FieldProblem",
        "JsonObject",
        "MAX_ATTEMPTS",
        "MAX_PROBLEMS",
        "MAX_STEPS",
        "NOT_FINITE_MESSAGE",
        "ONE_DOMAIN_MESSAGE",
        "Plan",
        "RESULT_MESSAGE",
        "ROUTE_MESSAGE",
        "Route",
        "Step",
        "TaskError",
        "TaskErrorKind",
        "TaskResult",
        "TaskSpec",
        "TaskStatus",
        "problems_from",
    ]
```

`tests/unit/test_contracts_tasks.py` (17 tests)

```python
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from conductor.contracts import (
    MAX_ATTEMPTS,
    MAX_PROBLEMS,
    RESULT_MESSAGE,
    DecidedBy,
    Escalation,
    EscalationKind,
    FieldProblem,
    Plan,
    Step,
    TaskError,
    TaskErrorKind,
    TaskResult,
    TaskSpec,
    TaskStatus,
    problems_from,
)

TASK = "0123456789abcdef0123456789abcdef"
RUN = "fedcba9876543210fedcba9876543210"
THREAD = "00000000000000000000000000000001"
EARLIER = "00000000000000000000000000000002"


def reason(raised: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(raised.value.errors()[0]["ctx"]["error"])


def test_the_closed_sets() -> None:
    assert get_args(DecidedBy) == ("rule", "model")
    assert get_args(TaskStatus) == ("succeeded", "failed", "escalated")
    assert get_args(TaskErrorKind) == (
        "invalid_args",
        "invalid_result",
        "tool_error",
        "agent_failed",
        "timeout",
    )
    assert get_args(EscalationKind) == (
        "invalid_model_output",
        "unknown_route",
        "invalid_plan",
        "tool_error",
        "retries_exhausted",
        "rejected",
    )
    assert (MAX_ATTEMPTS, MAX_PROBLEMS) == (3, 20)


def test_a_task_spec_carries_earlier_results_and_round_trips() -> None:
    earlier = TaskResult(
        task_id=EARLIER, status="succeeded", output={"total_cents": -12345}, attempts=1
    )
    spec = TaskSpec(
        task_id=TASK,
        run_id=RUN,
        thread_id=THREAD,
        step=2,
        action="finance.get_spending",
        args={"month": "2026-09"},
        context=(earlier,),
    )
    assert (spec.max_attempts, spec.domain) == (1, "finance")
    assert TaskSpec.from_json(spec.model_dump_json()) == spec
    assert spec.model_dump(mode="json")["context"] == [
        {
            "task_id": EARLIER,
            "status": "succeeded",
            "output": {"total_cents": -12345},
            "error": None,
            "attempts": 1,
        }
    ]


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("task_id", TASK.upper(), "string_pattern_mismatch"),
        ("step", 9, "less_than_equal"),
        ("max_attempts", "2", "int_type"),
    ],
)
def test_a_task_spec_from_text_refuses_bad_values(field: str, value: object, kind: str) -> None:
    given = {
        "task_id": TASK,
        "run_id": RUN,
        "thread_id": THREAD,
        "step": 1,
        "action": "demo.echo",
        "args": {},
        field: value,
    }
    with pytest.raises(ValidationError) as raised:
        TaskSpec.from_json(json.dumps(given))
    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [((field,), kind)]


@pytest.mark.parametrize(
    ("status", "output", "error", "ok"),
    [
        ("succeeded", {"echo": "hi"}, None, True),
        ("failed", None, TaskError(kind="tool_error", message="server stopped"), True),
        ("succeeded", None, None, False),
        ("succeeded", {"echo": "hi"}, TaskError(kind="timeout", message="no answer"), False),
        ("failed", None, None, False),
        ("failed", {"partial": 1}, TaskError(kind="tool_error", message="server stopped"), False),
    ],
)
def test_a_result_has_output_or_an_error_never_both(
    status: str, output: dict | None, error: TaskError | None, ok: bool
) -> None:
    given = {"task_id": TASK, "status": status, "output": output, "error": error, "attempts": 1}
    if ok:
        assert TaskResult.model_validate(given).status == status
        return
    with pytest.raises(ValidationError) as raised:
        TaskResult.model_validate(given)
    assert reason(raised) == RESULT_MESSAGE
    assert RESULT_MESSAGE == (
        "a succeeded result has output and no error; any other result has an error and no output"
    )


def test_problems_never_carry_what_was_given() -> None:
    with pytest.raises(ValidationError) as raised:
        Step.model_validate(
            {"action": "Bad", "args": {"card 4417-1234": {1, 2}, "ok": b"secret 4417"}}
        )
    found = problems_from(raised.value)
    assert found == (
        FieldProblem(loc="action", code="string_pattern_mismatch"),
        FieldProblem(loc="args.*", code="invalid-json-value"),
        FieldProblem(loc="args.ok", code="invalid-json-value"),
    )
    assert "4417" not in repr(found)


def test_problems_name_list_positions_and_stop_at_twenty() -> None:
    with pytest.raises(ValidationError) as raised:
        Plan.model_validate({"steps": [{"action": "demo.echo", "args": {}}, {"action": "Bad"}]})
    assert problems_from(raised.value)[:2] == (
        FieldProblem(loc="steps.1.action", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.1.args", code="missing"),
    )
    with pytest.raises(ValidationError) as raised:
        Step.model_validate({"action": "demo.echo", "args": {f"k{n:02d}": {n} for n in range(25)}})
    found = problems_from(raised.value)
    assert len(found) == 20
    assert (found[0].loc, found[19].loc) == ("args.k00", "args.k19")


def test_an_escalation_points_at_its_run() -> None:
    escalation = Escalation(
        kind="invalid_plan",
        detail="the plan names an action the domain does not have",
        run_id=RUN,
        problems=(FieldProblem(loc="steps.0.action", code="unknown_action"),),
    )
    assert Escalation.from_json(escalation.model_dump_json()) == escalation
    assert Escalation(kind="unknown_route", detail="no domain fits", run_id=RUN).problems == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "gave_up"),
        ("detail", "x" * 501),
        ("problems", [{"loc": "a", "code": "missing"}] * 21),
    ],
)
def test_an_escalation_refuses_bad_values(field: str, value: object) -> None:
    given = {"kind": "rejected", "detail": "the person rejected the step", "run_id": RUN}
    given[field] = value
    with pytest.raises(ValidationError) as raised:
        Escalation.model_validate(given)
    assert [error["loc"][0] for error in raised.value.errors()] == [field]
```

## Tests to write

In `tests/unit/test_contracts_more.py`, one test per behaviour, each with its deciding input:

- Assigning to a field of any contract raises `ValidationError` (frozen).
- `TaskError.message` of exactly 500 characters is kept; `""` and 501 characters are refused.
- `TaskResult.output` and `TaskSpec.args` refuse `NaN` from JSON with `NOT_FINITE_MESSAGE` (the given tests check only `Step.args`).
- `TaskSpec.context` of 7 results is kept; of 8 is refused.
- `Escalation.detail` of `""` is refused; `run_id` `"latest"` is refused.
- `problems_from` on an error at the whole-object level (a `Plan` mixing domains) gives `loc` `""`; a key of exactly 64 allowed characters is kept, 65 becomes `*`; a key `"café"` becomes `*`.

Coverage of `src/conductor/contracts/` must reach 100% (the command under Acceptance).

## Rules for this phase

- **`contracts` imports nothing from the project** (R12), only the standard library and `pydantic`.
- **No values in errors.** The model validators' messages are the constants above; `problems_from` reads only `loc` and `type`.
- **Anchor every pattern** with `^` and `$`.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 38 = 108 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_contracts_plans.py tests/unit/test_contracts_tasks.py --no-cov`, exactly `38 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/contracts/*" --fail-under=100`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/contracts | grep -v "conductor.contracts"`
  - `git grep --untracked -n -E "pattern=r?\"[^^]" -- src/conductor/contracts`
  - `git grep --untracked -n -E "\[.(input|msg|ctx|url).\]" -- src/conductor/contracts`
- `git diff --stat HEAD -- tests src/conductor/events.py` prints nothing (new files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 2a: contracts (YYYY-MM-DD)`, with `Tests: 70 -> <passed> (given 38)`.
