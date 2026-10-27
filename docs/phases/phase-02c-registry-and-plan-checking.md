# Phase 2c: the registry and plan checking

## Goal

What the agent can do, declared as data, and the code check that a model's plan asks only for that:

- `conductor.registry`: an `Action` (name, description, kind, target, effect, and its argument and result contracts), a `Domain` (a name, a description, its actions), and a `Registry` built once from a list of domains, which refuses a bad declaration at start-up;
- `conductor.domains`: one Python module per domain (the owner's decision, 2026-10-27) and the explicit tuple `DOMAINS`, empty until Phase 9; a `demo` domain for tests;
- `conductor.plancheck` (critical): `check_plan(plan, route, registry)` returns each step numbered, with its `Action` and its arguments parsed into the action's own contract, or raises `PlanRejected` with every problem as a `FieldProblem`, ready for an `invalid_plan` escalation (Phase 5).

Decided with the owner (2026-10-27): one domain per plan (a request that needs two escalates); approval is two-stage, the plan's shape first and then each side-effect step, so `check_plan` returns every step with its `effect` for the gate to show. Nothing here asks for approval; that is Phase 4.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Domains and the action registry", "Approve")
- `src/conductor/contracts/` (2a): `Contract.from_json`, `Plan`, `Route`, `FieldProblem`, `problems_from`, `MAX_PROBLEMS`, and the `Name` type in `contracts/base.py`

## Starting state

Phase 2b is built and committed: N is `166`. **Sections: core.** No `registry.py`, `plancheck.py`, or `domains/` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/registry.py` | `Action`, `Domain`, `Registry`, `RegistryError`, `NotRegistered` (Part 1) |
| `src/conductor/domains/__init__.py` | `DOMAINS: tuple[Domain, ...] = ()` |
| `src/conductor/domains/demo.py` | the demo domain (Part 2) |
| `src/conductor/plancheck.py` | `check_plan`, `CheckedStep`, `PlanRejected`, `PLAN_REJECTED_MESSAGE` (Part 3, critical) |
| `scripts/critical_modules.txt` | add the line `plancheck.py` after `reports.py` |
| `docs/testing.md` | under "Critical modules", add `- \`plancheck.py\` (plans checked against the registry; Phase 2c)` after the `reports.py` line, and remove "plan checking (Phase 2), " from the "Planned" line |
| `tests/unit/test_registry.py`, `tests/unit/test_plancheck.py` | given |
| `tests/unit/test_registry_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Routing rules, the classifier, the planner, JSON schemas for the planner, or prompts (Phases 3 and 5).
- The approval policy or anything that asks for approval (Phase 4).
- Binding `target` to an MCP tool or a subagent, or checking that it exists (Phase 6).
- Plans that span domains, chained plans, or steps that read earlier results.
- Loading domains from files, entry points, or any discovery; adding the demo domain to `DOMAINS`.
- Any change to `conductor.contracts`.

## Dependencies

None new.

## Design

```python
# conductor/registry.py
ActionKind = Literal["tool", "agent"]
Effect = Literal["read", "propose", "write", "implement"]

@dataclass(frozen=True)
class Action:
    name: str                  # a Name: ^[a-z][a-z0-9_]{0,31}$
    description: str           # 1 to 200 characters, shown to the planner later
    kind: ActionKind
    target: str                # ^[A-Za-z][A-Za-z0-9_.-]{0,63}$: the MCP tool or the subagent
    effect: Effect
    args: type[Contract]
    result: type[Contract]

@dataclass(frozen=True)
class Domain:
    name: str                  # a Name
    description: str           # 1 to 200 characters
    actions: tuple[Action, ...]

class RegistryError(Exception): ...
class NotRegistered(LookupError): ...

class Registry:
    def __init__(self, domains: Sequence[Domain]) -> None: ...
    @property
    def names(self) -> tuple[str, ...]: ...           # in the given order
    def domain(self, name: str) -> Domain: ...
    def action(self, full_name: str) -> Action: ...   # "demo.note"
```

```python
# conductor/plancheck.py
PLAN_REJECTED_MESSAGE = "the plan does not fit the registry"

@dataclass(frozen=True)
class CheckedStep:
    number: int                # the step's position, from 1
    action: Action
    args: Contract             # an instance of action.args

class PlanRejected(Exception):
    def __init__(self, problems: tuple[FieldProblem, ...]) -> None: ...   # str() is PLAN_REJECTED_MESSAGE
    problems: tuple[FieldProblem, ...]

def check_plan(plan: Plan, route: Route, registry: Registry) -> tuple[CheckedStep, ...]: ...
```

```python
# conductor/domains/demo.py: for tests; never in DOMAINS
class EchoArgs(Contract):
    text: str = Field(min_length=1, max_length=200)

class EchoResult(Contract):
    text: str

class NoteArgs(Contract):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=2000)
    tags: tuple[Name, ...] = Field(default=(), max_length=5)

class NoteResult(Contract):
    note_id: Id

class DelegateArgs(Contract):
    task: str = Field(min_length=1, max_length=500)
    max_minutes: int = Field(default=10, ge=1, le=60)

class DelegateResult(Contract):
    summary: str = Field(min_length=1, max_length=2000)

DOMAIN = Domain(
    name="demo",
    description="A domain for tests: echo text, write a note, delegate a task.",
    actions=(
        Action("echo", "Repeat the text back.", "tool", "echo", "read", EchoArgs, EchoResult),
        Action("note", "Write a note with a title, a body, and tags.", "tool", "write_note", "write", NoteArgs, NoteResult),
        Action("delegate", "Hand a task to the demo agent.", "agent", "demo_agent", "implement", DelegateArgs, DelegateResult),
    ),
)
```

Field order matters: errors come out in field order, and the given tests rely on it.

### Facts about Pydantic 2.14 (from a spike)

- `Model.model_validate(data, strict=True)` refuses a Python `list` for a `tuple` field (`tuple_type`), so a plan's `"tags": ["home"]` would fail. Parsing the same arguments as JSON with `strict=True` accepts a JSON array for a tuple and a whole number for a `float`, and still refuses `"10"` and `10.0` for an `int` and `true` for a `float`. So arguments are checked as text: `action.args.from_json(json.dumps(step.args))`, the same path a model's reply takes.
- In JSON mode, `extra_forbidden` errors can come before field errors of the same object; the given tests do not mix the two in one step.

## Requirements

### Part 1: the registry

- **R1.** `Registry(domains)` checks each domain in the given order, and inside it each action in order, and raises `RegistryError` with the first problem, using exactly these messages, `<d>` and `<a>` being the names as declared:

  | Checked, in this order | Message |
  |---|---|
  | domain name is a `Name` | `domain <d>: not a valid name` |
  | no earlier domain has the name | `domain <d>: declared twice` |
  | description 1 to 200 characters | `domain <d>: description must be 1 to 200 characters` |
  | at least one action | `domain <d>: has no actions` |
  | action name is a `Name` | `action <d>.<a>: not a valid name` |
  | no earlier action in the domain has the name | `action <d>.<a>: declared twice` |
  | description 1 to 200 characters | `action <d>.<a>: description must be 1 to 200 characters` |
  | kind | `action <d>.<a>: kind must be tool or agent` |
  | effect | `action <d>.<a>: effect must be read, propose, write, or implement` |
  | target pattern | `action <d>.<a>: target is not a valid name` |
  | `args` is a class and a subclass of `Contract` | `action <d>.<a>: args must be a Contract` |
  | `result` the same | `action <d>.<a>: result must be a Contract` |
  | `implement` only on an `agent` action | `action <d>.<a>: implement needs an agent action` |

- **R2.** An empty sequence is a valid registry (`names == ()`). The registry keeps its own copy: changing the sequence it was built from changes nothing.
- **R3.** `domain(name)` raises `NotRegistered(f"no domain {name}")`; `action(full_name)` raises `NotRegistered(f"no action {full_name}")` when the domain or the action is missing or the name has no `.`. Both return the very objects declared.

### Part 2: the domains

- **R4.** `conductor.domains.DOMAINS` is `()`. `conductor.domains.demo` declares the models and `DOMAIN` exactly as under Design.

### Part 3: plan checking (critical)

- **R5.** `check_plan` first checks the route: a domain not in the registry gives the single problem `FieldProblem(loc="route.domain", code="unknown_domain")`; then the plan: `plan.domain` other than `route.domain` gives the single problem `FieldProblem(loc="steps", code="wrong_domain")`. Either raises `PlanRejected` at once.
- **R6.** Then every step, in order (`i` counting from 0, as in Pydantic's locations): an action the domain does not have gives `FieldProblem(loc=f"steps.{i}.action", code="unknown_action")`; otherwise the arguments are parsed with `action.args.from_json(json.dumps(step.args))`, and each problem of `problems_from(error)` is kept with its `loc` prefixed by `steps.{i}.args` (joined with `.`; the prefix alone when the location is empty).
- **R7.** Problems from all steps are collected in order and cut to the first `MAX_PROBLEMS`. Any problem raises `PlanRejected(problems)`; `str()` of it is `PLAN_REJECTED_MESSAGE`. No problem holds an argument's value (they come only from `problems_from`).
- **R8.** With no problem, `check_plan` returns a tuple of `CheckedStep`, one per step, `number` from 1, `args` the parsed contract (defaults filled in).
- **R9.** `plancheck` imports only the standard library, `pydantic` (for `ValidationError`), `conductor.contracts`, and `conductor.registry`, and never calls `model_validate` (arguments go through `from_json`, R6).

## Given tests

26 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_registry.py` (20 tests)

```python
from dataclasses import replace

import pytest
from pydantic import BaseModel

from conductor.contracts import Contract
from conductor.domains import DOMAINS, demo
from conductor.registry import Action, Domain, NotRegistered, Registry, RegistryError


class PingArgs(Contract):
    target: str


class PingResult(Contract):
    ok: bool


PING = Action(
    name="ping",
    description="Check that a host answers.",
    kind="tool",
    target="ping",
    effect="read",
    args=PingArgs,
    result=PingResult,
)
NET = Domain(name="net", description="Network checks.", actions=(PING,))


def test_the_demo_domain() -> None:
    assert demo.DOMAIN.name == "demo"
    assert [
        (action.name, action.kind, action.target, action.effect) for action in demo.DOMAIN.actions
    ] == [
        ("echo", "tool", "echo", "read"),
        ("note", "tool", "write_note", "write"),
        ("delegate", "agent", "demo_agent", "implement"),
    ]
    assert DOMAINS == ()


def test_lookups() -> None:
    registry = Registry((demo.DOMAIN, NET))
    assert registry.names == ("demo", "net")
    assert registry.domain("net") is NET
    assert registry.action("net.ping") is PING
    assert registry.action("demo.note").effect == "write"
    assert Registry(()).names == ()


@pytest.mark.parametrize(
    ("lookup", "message"),
    [
        (lambda registry: registry.domain("mail"), "no domain mail"),
        (lambda registry: registry.action("net.trace"), "no action net.trace"),
        (lambda registry: registry.action("mail.send"), "no action mail.send"),
        (lambda registry: registry.action("ping"), "no action ping"),
    ],
)
def test_a_lookup_of_something_not_registered(lookup, message: str) -> None:
    with pytest.raises(NotRegistered) as raised:
        lookup(Registry((NET,)))
    assert str(raised.value) == message
    assert isinstance(raised.value, LookupError)


class LooseArgs(BaseModel):
    target: str


@pytest.mark.parametrize(
    ("domains", "message"),
    [
        ((replace(NET, name="Net"),), "domain Net: not a valid name"),
        ((NET, replace(NET, description="Other checks.")), "domain net: declared twice"),
        ((replace(NET, description=""),), "domain net: description must be 1 to 200 characters"),
        ((replace(NET, actions=()),), "domain net: has no actions"),
        (
            (replace(NET, actions=(replace(PING, name="Ping"),)),),
            "action net.Ping: not a valid name",
        ),
        ((replace(NET, actions=(PING, PING)),), "action net.ping: declared twice"),
        (
            (replace(NET, actions=(replace(PING, description="x" * 201),)),),
            "action net.ping: description must be 1 to 200 characters",
        ),
        (
            (replace(NET, actions=(replace(PING, kind="script"),)),),
            "action net.ping: kind must be tool or agent",
        ),
        (
            (replace(NET, actions=(replace(PING, effect="delete"),)),),
            "action net.ping: effect must be read, propose, write, or implement",
        ),
        (
            (replace(NET, actions=(replace(PING, target="ping now"),)),),
            "action net.ping: target is not a valid name",
        ),
        (
            (replace(NET, actions=(replace(PING, args=LooseArgs),)),),
            "action net.ping: args must be a Contract",
        ),
        (
            (replace(NET, actions=(replace(PING, result=dict),)),),
            "action net.ping: result must be a Contract",
        ),
        (
            (replace(NET, actions=(replace(PING, effect="implement"),)),),
            "action net.ping: implement needs an agent action",
        ),
    ],
)
def test_a_registry_refuses_a_bad_declaration(domains: tuple[Domain, ...], message: str) -> None:
    with pytest.raises(RegistryError) as raised:
        Registry(domains)
    assert str(raised.value) == message


def test_the_first_problem_in_declaration_order_is_named() -> None:
    bad_action = replace(PING, name="Ping")
    second = replace(NET, name="later", actions=(replace(PING, kind="script"),))
    with pytest.raises(RegistryError) as raised:
        Registry((replace(NET, actions=(PING, bad_action)), second))
    assert str(raised.value) == "action net.Ping: not a valid name"
```

`tests/unit/test_plancheck.py` (6 tests)

```python
import pytest

from conductor.contracts import FieldProblem, Plan, Route, Step
from conductor.domains import demo
from conductor.plancheck import PLAN_REJECTED_MESSAGE, CheckedStep, PlanRejected, check_plan
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
DEMO = Route(domain="demo", decided_by="rule", rule_id="demo.prefix")


def plan(*steps: tuple[str, dict]) -> Plan:
    return Plan(steps=tuple(Step(action=action, args=args) for action, args in steps))


def rejected(checked_plan: Plan, route: Route = DEMO) -> tuple[FieldProblem, ...]:
    with pytest.raises(PlanRejected) as raised:
        check_plan(checked_plan, route, REGISTRY)
    assert str(raised.value) == PLAN_REJECTED_MESSAGE
    return raised.value.problems


def test_a_plan_that_fits() -> None:
    steps = check_plan(
        plan(
            ("demo.echo", {"text": "hello"}),
            ("demo.note", {"title": "Groceries", "tags": ["home", "weekly"]}),
            ("demo.delegate", {"task": "tidy the notes"}),
        ),
        DEMO,
        REGISTRY,
    )
    assert steps == (
        CheckedStep(
            number=1,
            action=REGISTRY.action("demo.echo"),
            args=demo.EchoArgs(text="hello"),
        ),
        CheckedStep(
            number=2,
            action=REGISTRY.action("demo.note"),
            args=demo.NoteArgs(title="Groceries", body="", tags=("home", "weekly")),
        ),
        CheckedStep(
            number=3,
            action=REGISTRY.action("demo.delegate"),
            args=demo.DelegateArgs(task="tidy the notes", max_minutes=10),
        ),
    )
    assert [step.action.effect for step in steps] == ["read", "write", "implement"]
    assert PLAN_REJECTED_MESSAGE == "the plan does not fit the registry"


def test_arguments_are_checked_strictly() -> None:
    assert rejected(plan(("demo.delegate", {"task": "tidy", "max_minutes": "10"}))) == (
        FieldProblem(loc="steps.0.args.max_minutes", code="int_type"),
    )
    assert rejected(plan(("demo.delegate", {"task": "tidy", "max_minutes": 10.0}))) == (
        FieldProblem(loc="steps.0.args.max_minutes", code="int_type"),
    )


def test_every_bad_step_is_named() -> None:
    assert rejected(
        plan(
            ("demo.echo", {"text": "fine"}),
            ("demo.shout", {"text": "HELLO"}),
            ("demo.note", {"title": ""}),
            ("demo.echo", {}),
        )
    ) == (
        FieldProblem(loc="steps.1.action", code="unknown_action"),
        FieldProblem(loc="steps.2.args.title", code="string_too_short"),
        FieldProblem(loc="steps.3.args.text", code="missing"),
    )


def test_a_plan_for_another_domain() -> None:
    other = Route(domain="mail", decided_by="model")
    assert rejected(plan(("demo.echo", {"text": "hi"})), other) == (
        FieldProblem(loc="route.domain", code="unknown_domain"),
    )
    assert rejected(plan(("mail.send", {"to": "sam"}))) == (
        FieldProblem(loc="steps", code="wrong_domain"),
    )


def test_problems_stop_at_twenty() -> None:
    steps = [("demo.note", {"title": "", "body": "x" * 2001, "tags": ["A", "B", "C"]})] * 8
    problems = rejected(plan(*steps))
    assert len(problems) == 20
    assert problems[:5] == (
        FieldProblem(loc="steps.0.args.title", code="string_too_short"),
        FieldProblem(loc="steps.0.args.body", code="string_too_long"),
        FieldProblem(loc="steps.0.args.tags.0", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.0.args.tags.1", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.0.args.tags.2", code="string_pattern_mismatch"),
    )
    assert problems[19] == FieldProblem(loc="steps.3.args.tags.2", code="string_pattern_mismatch")


def test_no_argument_value_reaches_a_problem() -> None:
    problems = rejected(plan(("demo.note", {"title": "card 4417-1234", "card 4417-1234": 1})))
    assert problems == (FieldProblem(loc="steps.0.args.*", code="extra_forbidden"),)
    assert "4417" not in repr(problems)
```

## Tests to write

In `tests/unit/test_registry_more.py`, each with its deciding input:

- R2: a registry built from a `list`, which is then appended to, still has the original names.
- R3: `action("demo")` (no dot) raises `no action demo`.
- R1: a `target` of exactly 64 allowed characters is accepted, 65 refused; `args` given as an instance (`demo.EchoArgs(text="x")`) instead of the class is refused with the args message.
- R6: an argument that is `true` where `max_minutes` expects an `int` gives `int_type`; a `demo.note` with `"tags": ["home"]` passes (a JSON array for a tuple).
- R7: a plan of 8 steps whose last step alone is bad names only `steps.7...`.
- R8: `CheckedStep.args` is an instance of the action's own `args` class for each demo action.

`plancheck.py` reaches 100% of lines and branches (critical); `registry.py` and `domains/` are covered by the project gate.

## Rules for this phase

- **Critical module**: `plancheck.py` joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **No values in problems**: plan checking builds problems only from fixed codes and `problems_from`.
- **Declarations are data**: `Action` and `Domain` validate nothing themselves; the `Registry` does (R1).
- Earlier tests stay unchanged; `conductor.contracts` is not edited.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 26 = 192 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_registry.py tests/unit/test_plancheck.py --no-cov`, exactly `26 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/plancheck.py,*/conductor/registry.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/plancheck.py | grep -v -E "(__future__|dataclasses|json|typing|conductor\.contracts|conductor\.registry|pydantic)"`
  - `git grep --untracked -n -E "model_validate\(" -- src/conductor/plancheck.py`
- `git diff --stat HEAD -- tests src/conductor/contracts` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 2c: the registry and plan checking (YYYY-MM-DD)`, with `Tests: 166 -> <passed> (given 26)`.
