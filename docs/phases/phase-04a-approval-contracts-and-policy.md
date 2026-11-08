# Phase 4a: approval contracts and the policy

## Goal

The rules for when the agent must stop and ask, written as code, with no storage and no graph yet:

- `conductor.contracts.approvals`: `PlannedStep`, `ApprovalRequest` (a **plan** request shows every step with its effect and arguments; a **step** request shows one step's exact arguments), `ApprovalDecision` (approve, reject, or edit, who decided, on which channel, and when), and `steps_digest`, the SHA-256 that binds a decision to the exact steps it was shown;
- `conductor.policy` (critical): `needs_approval(action, attempt=)`, `plan_request`, `step_request`, and `apply_decision`, which turns a decision into `Approved` (with the arguments the step runs with) or `Rejected`, or refuses it.

The effects decide (architecture, "Approve"): `read` never asks; `propose` and `write` always ask; `implement` asks on the first attempt only, so the coder's retries after a verifier FAIL run without asking (`AGENTS.md` rule 7).

Decided with the owner (2026-11-08): a plan whose steps are **all `read` runs without the plan approval**; an **edit approves** the edited arguments in one decision once they validate (an invalid edit is refused and the request stays open); a **rejection ends the run**, with the person's note and no replanning; a pending approval **never expires**. From 2026-10-27: approval is two-stage, the plan first, then each step that has a side effect.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Approve", "Approvals and escalations")
- `src/conductor/contracts/base.py` (`Contract`, `Id`, `Name`, `ActionName`, `JsonObject`), `src/conductor/registry.py` (`Action`, `Effect`, `Registry`), `src/conductor/plancheck.py` (`CheckedStep`), `src/conductor/events.py` (how it requires UTC)

## Starting state

Phase 3c is built and committed: N is `308`. **Sections: core.** No `policy.py` or `contracts/approvals.py` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/contracts/approvals.py` | the approval contracts and `steps_digest` (Part 1); not re-exported from `conductor.contracts` (its `__all__` is pinned by an earlier test) |
| `src/conductor/policy.py` | `ATTEMPT_MESSAGE`, `RefusalCode`, `DecisionRefused`, `Approved`, `Rejected`, `needs_approval`, `plan_request`, `step_request`, `apply_decision` (Part 2, critical) |
| `scripts/critical_modules.txt` | add the line `policy.py` after `llm/decide.py` |
| `docs/testing.md` | under "Critical modules", add `` - `policy.py` (which steps wait for a person, and what a decision allows; Phase 4a) `` after the `llm/decide.py` line, and remove the line `Planned: the approval policy (Phase 4).` |
| `tests/unit/test_contracts_approvals.py`, `tests/unit/test_policy.py` | given |
| `tests/unit/test_policy_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Storing requests or decisions, `conductor.db`, leases, listing what is pending (Phase 4b); the `conductor approvals` commands (Phase 4c); the approvals page (Phase 7).
- The graph, `interrupt()`, resuming, recording a rejection as an escalation, events (Phase 5).
- Expiry, reminders, replanning after a rejection, editing a plan, approving several requests at once.
- Changes to `conductor.contracts`' existing modules or `__init__`, `registry.py`, `plancheck.py`, or `conductor.llm`.

## Dependencies

None new.

## Design

```python
# conductor/contracts/approvals.py: imports only the standard library, pydantic, conductor.contracts.base and .plans (MAX_STEPS)
STEP_COUNT_MESSAGE = "a step approval holds exactly one step"
NUMBERS_MESSAGE = "plan steps are numbered from 1 in order"
DIGEST_MESSAGE = "args_sha256 does not match the steps"
EDIT_MESSAGE = "edited_args go with an edit, and only with an edit"
UTC_MESSAGE = "time must be UTC"

ApprovalStage = Literal["plan", "step"]
Verdict = Literal["approve", "reject", "edit"]
Channel = Literal["terminal", "web"]
StepEffect = Literal["read", "propose", "write", "implement"]     # the same values as registry.Effect
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
UtcTime = Annotated[AwareDatetime, AfterValidator(...)]            # offset 0, else UTC_MESSAGE

class PlannedStep(Contract):
    number: int = Field(ge=1, le=MAX_STEPS)
    action: ActionName
    effect: StepEffect
    args: JsonObject

def steps_digest(steps: Sequence[PlannedStep]) -> str: ...

class ApprovalRequest(Contract):
    approval_id: Id
    run_id: Id
    stage: ApprovalStage
    steps: tuple[PlannedStep, ...] = Field(min_length=1, max_length=MAX_STEPS)
    args_sha256: Sha256
    requested_at: UtcTime

class ApprovalDecision(Contract):
    approval_id: Id
    verdict: Verdict
    args_sha256: Sha256         # the digest of the request it decides
    edited_args: JsonObject | None = None
    note: str = Field(default="", max_length=500)
    channel: Channel
    decided_by: Name            # a short label such as "owner"
    decided_at: UtcTime
```

```python
# conductor/policy.py
ATTEMPT_MESSAGE = "attempt must be at least 1"
RefusalCode = Literal["other_request", "stale", "edit_on_plan", "invalid_edit"]

class DecisionRefused(Exception):
    def __init__(self, code: RefusalCode, problems: tuple[FieldProblem, ...] = ()) -> None: ...
    code: RefusalCode
    problems: tuple[FieldProblem, ...]
    # str(): "decision refused: <code>"

@dataclass(frozen=True)
class Approved:
    args: Contract | None       # the step's arguments to run with; None for a plan approval
    edited: bool

@dataclass(frozen=True)
class Rejected:
    note: str

def needs_approval(action: Action, *, attempt: int = 1) -> bool: ...
def plan_request(domain: str, steps: Sequence[CheckedStep], *, run_id: str) -> ApprovalRequest | None: ...
def step_request(domain: str, step: CheckedStep, *, run_id: str, attempt: int = 1) -> ApprovalRequest | None: ...
def apply_decision(request: ApprovalRequest, decision: ApprovalDecision, registry: Registry) -> Approved | Rejected: ...
```

### Facts (from a spike: Pydantic 2.14)

- `AwareDatetime` in strict JSON accepts `"2026-11-08T09:00:00Z"` and `"...+02:00"`, refuses a time without an offset (`timezone_aware`), a number (`datetime_type`), and a bare date (`datetime_parsing`); it does not require UTC, hence the after-validator. `model_dump_json()` writes UTC as `Z`.
- A `ValueError` raised in a validator appears as `errors()[0]["msg"] == "Value error, <message>"` with type `value_error`; the given tests read it that way (tests may; production code never shows Pydantic's text).
- `NoteArgs.from_json` of `{"title": "", "pages": 3}` lists `pages` `extra_forbidden` before `title`: the given edit test does not mix the two.
- `model_dump(mode="json")` of `NoteArgs(title="Milk", tags=("home",))` is `{"title": "Milk", "body": "", "tags": ["home"]}`: defaults included, tuples as lists.

## Requirements

### Part 1: the contracts

- **R1.** The literals and fields are exactly as under Design. `UtcTime` refuses a time whose offset is not zero with `UTC_MESSAGE`.
- **R2.** `steps_digest(steps)` is the hexadecimal SHA-256 of `json.dumps([step.model_dump(mode="json") for step in steps], sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8.
- **R3.** `ApprovalRequest` checks, after its fields and in this order, raising `ValueError` with the message: a `step` request has exactly one step (`STEP_COUNT_MESSAGE`); a `plan` request's numbers are exactly 1, 2, …, n (`NUMBERS_MESSAGE`); `args_sha256 == steps_digest(steps)` (`DIGEST_MESSAGE`). So a stored request whose steps were changed no longer parses.
- **R4.** `ApprovalDecision` requires `edited_args` to be present exactly when `verdict == "edit"` (`EDIT_MESSAGE`).

### Part 2: the policy (critical)

- **R5.** `needs_approval` raises `ValueError(ATTEMPT_MESSAGE)` for an `attempt` below 1; otherwise `read` gives `False`, `propose` and `write` give `True`, `implement` gives `attempt == 1`.
- **R6.** `plan_request` returns `None` when no step needs approval at attempt 1 (every step is `read`). Otherwise it returns a `plan` request with every step, in order, as `PlannedStep(number=step.number, action=f"{domain}.{step.action.name}", effect=step.action.effect, args=step.args.model_dump(mode="json"))`, `approval_id = ids.new_id()`, `requested_at = clock.now()`, and the digest of those steps.
- **R7.** `step_request` returns `None` when `needs_approval(step.action, attempt=attempt)` is false, and otherwise a `step` request with that one step, built the same way.
- **R8.** `apply_decision` checks, in this order: `decision.approval_id` differs from the request's → `DecisionRefused("other_request")`; `decision.args_sha256` differs → `DecisionRefused("stale")`; then by verdict:
  - `reject` → `Rejected(note=decision.note)`;
  - `approve` on a plan → `Approved(args=None, edited=False)`; on a step → `Approved(args=<the step's args parsed by its action>, edited=False)`;
  - `edit` on a plan → `DecisionRefused("edit_on_plan")`; on a step → the edited arguments parsed by the action, `Approved(args=..., edited=True)`, or, when they do not fit, `DecisionRefused("invalid_edit", problems_from(error))`.

  The step's action is `registry.action(step.action)`; arguments are parsed with `action.args.from_json(json.dumps(args))`, as in plan checking (2c).
- **R9.** No `DecisionRefused` holds an argument's value: its message is constant plus the code, and its problems come only from `problems_from`.
- **R10.** `policy.py` imports only the standard library, `pydantic` (for `ValidationError`), `conductor.contracts` and `conductor.contracts.approvals`, `conductor.registry`, `conductor.plancheck` (for `CheckedStep`), and `clock` and `ids` as modules (`from conductor import clock, ids`); it never calls `model_validate`.

## Given tests

34 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_contracts_approvals.py` (14 tests)

```python
import hashlib
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from conductor.contracts.approvals import (
    DIGEST_MESSAGE,
    EDIT_MESSAGE,
    NUMBERS_MESSAGE,
    STEP_COUNT_MESSAGE,
    UTC_MESSAGE,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStage,
    Channel,
    PlannedStep,
    StepEffect,
    Verdict,
    steps_digest,
)
from conductor.registry import Effect

AT = datetime(2026, 11, 8, 9, 30, tzinfo=UTC)
ECHO = PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"})
NOTE = PlannedStep(
    number=2,
    action="demo.note",
    effect="write",
    args={"title": "Milk", "body": "", "tags": ["home"]},
)


def request(stage: str = "plan", steps=(ECHO, NOTE), **changes: object) -> ApprovalRequest:
    fields = {
        "approval_id": "1" * 32,
        "run_id": "a" * 32,
        "stage": stage,
        "steps": steps,
        "args_sha256": steps_digest(steps),
        "requested_at": AT,
    }
    return ApprovalRequest(**{**fields, **changes})


def decision(**changes: object) -> ApprovalDecision:
    fields = {
        "approval_id": "1" * 32,
        "verdict": "approve",
        "args_sha256": "e" * 64,
        "channel": "terminal",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


def test_the_closed_sets() -> None:
    assert get_args(ApprovalStage) == ("plan", "step")
    assert get_args(Verdict) == ("approve", "reject", "edit")
    assert get_args(Channel) == ("terminal", "web")
    assert get_args(StepEffect) == get_args(Effect)


def test_the_digest_is_pinned() -> None:
    text = (
        '[{"action":"demo.echo","args":{"text":"hi"},"effect":"read","number":1},'
        '{"action":"demo.note","args":{"body":"","tags":["home"],"title":"Milk"},'
        '"effect":"write","number":2}]'
    )
    assert steps_digest((ECHO, NOTE)) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert steps_digest((NOTE,)) != steps_digest((ECHO,))


def test_a_request_round_trips() -> None:
    for built in (request(), request("step", (NOTE,))):
        assert ApprovalRequest.from_json(built.model_dump_json()) == built


@pytest.mark.parametrize(
    ("stage", "steps", "changes", "message"),
    [
        ("step", (ECHO, NOTE), {}, STEP_COUNT_MESSAGE),
        ("plan", (ECHO, NOTE.model_copy(update={"number": 3})), {}, NUMBERS_MESSAGE),
        ("plan", (NOTE,), {}, NUMBERS_MESSAGE),
        ("plan", (ECHO, NOTE), {"args_sha256": "0" * 64}, DIGEST_MESSAGE),
        ("plan", (ECHO,), {"requested_at": "2026-11-08T09:30:00+02:00"}, UTC_MESSAGE),
    ],
)
def test_a_request_that_does_not_hold_together(
    stage: str, steps: tuple[PlannedStep, ...], changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        request(stage, steps, **changes)
    assert raised.value.errors()[0]["msg"] == f"Value error, {message}"


def test_a_request_time_must_say_its_zone() -> None:
    with pytest.raises(ValidationError) as raised:
        ApprovalRequest.from_json(
            request().model_dump_json().replace("2026-11-08T09:30:00Z", "2026-11-08T09:30:00")
        )
    assert raised.value.errors()[0]["type"] == "timezone_aware"


@pytest.mark.parametrize(
    ("changes", "kind"),
    [
        ({"verdict": "edit"}, EDIT_MESSAGE),
        ({"edited_args": {"title": "Eggs"}}, EDIT_MESSAGE),
        ({"note": "x" * 501}, "string_too_long"),
        ({"decided_by": "Owner"}, "string_pattern_mismatch"),
    ],
)
def test_a_decision_that_does_not_hold_together(changes: dict[str, object], kind: str) -> None:
    with pytest.raises(ValidationError) as raised:
        decision(**changes)
    error = raised.value.errors()[0]
    assert kind in (error["type"], error["msg"].removeprefix("Value error, "))


def test_a_decision_round_trips() -> None:
    edit = decision(verdict="edit", edited_args={"title": "Eggs"}, note="fewer", channel="web")
    for built in (decision(), decision(verdict="reject"), edit):
        assert ApprovalDecision.from_json(built.model_dump_json()) == built
    assert decision().note == ""
    assert decision().edited_args is None
```

`tests/unit/test_policy.py` (20 tests)

```python
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from conductor import clock, ids
from conductor.contracts import FieldProblem
from conductor.contracts.approvals import ApprovalDecision, PlannedStep, steps_digest
from conductor.domains import demo
from conductor.plancheck import CheckedStep
from conductor.policy import (
    ATTEMPT_MESSAGE,
    Approved,
    DecisionRefused,
    Rejected,
    apply_decision,
    needs_approval,
    plan_request,
    step_request,
)
from conductor.registry import Registry

AT = datetime(2026, 11, 8, 9, 30, tzinfo=UTC)
RUN = "a" * 32
APPROVAL = "1" * 32
ECHO, NOTE, DELEGATE = demo.DOMAIN.actions
PROPOSE = replace(NOTE, name="draft", effect="propose")
REGISTRY = Registry((demo.DOMAIN,))

ECHO_STEP = CheckedStep(number=1, action=ECHO, args=demo.EchoArgs(text="hi"))
NOTE_STEP = CheckedStep(number=2, action=NOTE, args=demo.NoteArgs(title="Milk", tags=("home",)))


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: AT)
    monkeypatch.setattr(ids, "new_id", lambda: APPROVAL)


@pytest.mark.parametrize(
    ("action", "attempt", "needed"),
    [
        (ECHO, 1, False),
        (PROPOSE, 1, True),
        (NOTE, 1, True),
        (NOTE, 2, True),
        (DELEGATE, 1, True),
        (DELEGATE, 3, False),
    ],
)
def test_what_needs_approval(action, attempt: int, needed: bool) -> None:
    assert needs_approval(action, attempt=attempt) is needed


def test_attempts_count_from_one() -> None:
    with pytest.raises(ValueError) as raised:
        needs_approval(NOTE, attempt=0)
    assert str(raised.value) == ATTEMPT_MESSAGE == "attempt must be at least 1"


def test_a_read_only_plan_needs_no_approval() -> None:
    assert plan_request("demo", (ECHO_STEP, replace(ECHO_STEP, number=2)), run_id=RUN) is None


def test_a_plan_with_a_side_effect_shows_every_step() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    steps = (
        PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"}),
        PlannedStep(
            number=2,
            action="demo.note",
            effect="write",
            args={"title": "Milk", "body": "", "tags": ["home"]},
        ),
    )
    assert request is not None
    assert (request.approval_id, request.run_id, request.stage) == (APPROVAL, RUN, "plan")
    assert request.steps == steps
    assert request.args_sha256 == steps_digest(steps)
    assert request.requested_at == AT


@pytest.mark.parametrize(
    ("step", "attempt", "asked"),
    [
        (ECHO_STEP, 1, False),
        (NOTE_STEP, 1, True),
        (CheckedStep(number=3, action=DELEGATE, args=demo.DelegateArgs(task="Build 4a")), 2, False),
    ],
)
def test_a_step_request(step: CheckedStep, attempt: int, asked: bool) -> None:
    request = step_request("demo", step, run_id=RUN, attempt=attempt)
    if not asked:
        assert request is None
        return
    assert request is not None
    assert request.stage == "step"
    assert [(s.number, s.action) for s in request.steps] == [(2, "demo.note")]


def decide_on(request, **changes: object) -> ApprovalDecision:
    fields = {
        "approval_id": request.approval_id,
        "verdict": "approve",
        "args_sha256": request.args_sha256,
        "channel": "terminal",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


def note_request():
    return step_request("demo", NOTE_STEP, run_id=RUN)


def test_an_approved_plan() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    assert apply_decision(request, decide_on(request), REGISTRY) == Approved(
        args=None, edited=False
    )


def test_an_approved_step_runs_with_its_own_arguments() -> None:
    request = note_request()
    outcome = apply_decision(request, decide_on(request), REGISTRY)
    assert outcome == Approved(args=demo.NoteArgs(title="Milk", tags=("home",)), edited=False)
    assert type(outcome.args) is demo.NoteArgs


def test_a_rejection_ends_with_the_note() -> None:
    request = note_request()
    decided = decide_on(request, verdict="reject", note="not today")
    assert apply_decision(request, decided, REGISTRY) == Rejected(note="not today")


def test_an_edit_approves_the_new_arguments() -> None:
    request = note_request()
    decided = decide_on(request, verdict="edit", edited_args={"title": "Eggs", "tags": ["home"]})
    assert apply_decision(request, decided, REGISTRY) == Approved(
        args=demo.NoteArgs(title="Eggs", tags=("home",)), edited=True
    )


@pytest.mark.parametrize(
    ("changes", "code", "problems"),
    [
        ({"approval_id": "2" * 32}, "other_request", ()),
        ({"args_sha256": "0" * 64}, "stale", ()),
        (
            {"verdict": "edit", "edited_args": {"title": "", "tags": ["Home"]}},
            "invalid_edit",
            (
                FieldProblem(loc="title", code="string_too_short"),
                FieldProblem(loc="tags.0", code="string_pattern_mismatch"),
            ),
        ),
    ],
)
def test_a_decision_that_is_refused(
    changes: dict[str, object], code: str, problems: tuple[FieldProblem, ...]
) -> None:
    request = note_request()
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, decide_on(request, **changes), REGISTRY)
    assert (raised.value.code, raised.value.problems) == (code, problems)
    assert str(raised.value) == f"decision refused: {code}"


def test_a_plan_cannot_be_edited() -> None:
    request = plan_request("demo", (ECHO_STEP, NOTE_STEP), run_id=RUN)
    decided = decide_on(request, verdict="edit", edited_args={"text": "bye"})
    with pytest.raises(DecisionRefused) as raised:
        apply_decision(request, decided, REGISTRY)
    assert raised.value.code == "edit_on_plan"
```

## Tests to write

In `tests/unit/test_policy_more.py`, each with its deciding input:

- R3: a `step` request may carry any number from 1 to 8 (a lone step 5 is valid); a `plan` request numbered `(1, 1)` is refused with `NUMBERS_MESSAGE`.
- R5: `needs_approval(DELEGATE, attempt=-1)` raises; `attempt=1` is the default.
- R6: a plan of a `read` step and a `propose` step asks, and the `read` step is shown in it too; `plan_request` reads `ids.new_id` and `clock.now` once each.
- R8: the order of the checks: a decision with another `approval_id` and another digest is `other_request`; an `edit` on a plan with a wrong digest is `stale`.
- R8: `reject` and `edit` on a plan request: `reject` gives `Rejected` with the note `""` when none was given.
- R8: an `approve` on a step parses the stored arguments, so the returned args are a new instance of the action's `args` class equal to the checked step's.
- R9: an invalid edit whose bad value is `"SYNTHETIC-SECRET"` leaves no trace of it in `str()`, `code`, or `problems`.

`policy.py` and `contracts/approvals.py` reach 100% of lines and branches (`policy.py` is critical).

## Rules for this phase

- **Critical module**: `policy.py` joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **Side effects need approval** (`AGENTS.md` rule 7): the one exception, `implement` after the first attempt, is the only place `needs_approval` returns `False` for an effect other than `read`.
- **A decision is bound to what was shown**: approval id and digest both match, or it is refused.
- **Contracts stay pure**: `contracts/approvals.py` imports nothing from the project outside `conductor.contracts.base` and `conductor.contracts.plans`.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 34 = 342 passed; `critical coverage` passed (it now includes `policy.py`);
- the given files: `.venv/bin/python -m pytest tests/unit/test_contracts_approvals.py tests/unit/test_policy.py --no-cov`, exactly `34 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/policy.py,*/conductor/contracts/approvals.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/policy.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|dataclasses|json|typing|pydantic|conductor\.contracts|conductor\.contracts\.approvals|conductor\.registry|conductor\.plancheck|conductor import clock, ids)( |$)"`
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/contracts/approvals.py | grep -v -E ":(from|import) conductor\.contracts\.(base|plans)( |$)"`
  - `git grep --untracked -n -E "model_validate\(" -- src/conductor/policy.py`
- `git diff --stat HEAD -- tests src/conductor/contracts src/conductor/registry.py src/conductor/plancheck.py src/conductor/llm` prints nothing (the new files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 4a: approval contracts and the policy (YYYY-MM-DD)`, with `Tests: 308 -> <passed> (given 34)`.
