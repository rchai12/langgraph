# Verify Phase 4a: approval contracts and the policy

Spec: `docs/phases/phase-04a-approval-contracts-and-policy.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.contracts.approvals` and `conductor.policy` (critical), added `policy.py` to the critical modules, copied two given test files (34 tests), and wrote `tests/unit/test_policy_more.py`.

## 1. Gates

N is `308`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 342 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `policy.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/policy.py,*/conductor/contracts/approvals.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_contracts_approvals.py tests/unit/test_policy.py --no-cov` | exactly `34 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- tests src/conductor/contracts src/conductor/registry.py src/conductor/plancheck.py src/conductor/llm` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/policy.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|dataclasses|json|typing|pydantic|conductor\.contracts|conductor\.contracts\.approvals|conductor\.registry|conductor\.plancheck|conductor import clock, ids)( |$)"`
2. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/contracts/approvals.py | grep -v -E ":(from|import) conductor\.contracts\.(base|plans)( |$)"`
3. `git grep --untracked -n -E "model_validate\(" -- src/conductor/policy.py`

## 2. Scope paths

`git status --short` lists only: `src/conductor/contracts/approvals.py`, `src/conductor/policy.py`, `scripts/critical_modules.txt`, `docs/testing.md`, the two given test files, `tests/unit/test_policy_more.py`, `docs/progress.md`. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits (one line added each, and the "Planned" line removed). `conductor/contracts/__init__.py` is unchanged.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_closed_sets`, `test_a_request_time_must_say_its_zone`, the `+02:00` case of `test_a_request_that_does_not_hold_together`; read the fields against the Design | pass; the same |
| R2 | `test_the_digest_is_pinned` | pass |
| R3 | `test_a_request_that_does_not_hold_together`, `test_a_request_round_trips`; the coder's lone-step and `(1, 1)` tests; probe "a stored request with any argument changed no longer parses" | pass; ok |
| R4 | `test_a_decision_that_does_not_hold_together`, `test_a_decision_round_trips` | pass |
| R5 | `test_what_needs_approval`, `test_attempts_count_from_one`; the coder's `-1` test | pass |
| R6 | `test_a_read_only_plan_needs_no_approval`, `test_a_plan_with_a_side_effect_shows_every_step`; the coder's read-plus-propose test; probe "plan approval is asked exactly when a step is not read" | pass; ok |
| R7 | `test_a_step_request`; probe "step approval: propose and write always, implement on the first attempt only" | pass; ok |
| R8 | `test_an_approved_plan`, `test_an_approved_step_runs_with_its_own_arguments`, `test_a_rejection_ends_with_the_note`, `test_an_edit_approves_the_new_arguments`, `test_a_decision_that_is_refused`, `test_a_plan_cannot_be_edited`; the coder's order and plan-verdict tests; probes "a decision for other arguments is always stale", "an edit is approved exactly when the action's contract accepts it", "a rejection never carries arguments" | pass; ok |
| R9 | the coder's `SYNTHETIC-SECRET` test; probe "an edit is approved exactly ..." (no value in problems) | pass; ok |
| R10 | searches 1 to 3 | no output |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It checks every plan of one to four steps over four effects (340 plans) and 100 edits.

```python
"""Independent probe for Phase 4a. Run from the repository root with .venv/bin/python."""

import itertools
import json
import random
import re
from dataclasses import replace
from datetime import UTC, datetime

from pydantic import ValidationError

from conductor.contracts.approvals import ApprovalDecision, ApprovalRequest
from conductor.domains import demo
from conductor.plancheck import CheckedStep
from conductor.policy import (
    Approved,
    DecisionRefused,
    Rejected,
    apply_decision,
    plan_request,
    step_request,
)
from conductor.registry import Registry

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


RUN = "b" * 32
AT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ECHO, NOTE, DELEGATE = demo.DOMAIN.actions
DRAFT = replace(NOTE, name="draft", effect="propose")
domain = replace(demo.DOMAIN, actions=(ECHO, NOTE, DELEGATE, DRAFT))
registry = Registry((domain,))
ARGS = {
    "echo": demo.EchoArgs(text="hi"),
    "note": demo.NoteArgs(title="Milk"),
    "delegate": demo.DelegateArgs(task="Do it"),
    "draft": demo.NoteArgs(title="Draft"),
}


def steps_of(actions) -> tuple[CheckedStep, ...]:
    return tuple(
        CheckedStep(number=i, action=a, args=ARGS[a.name])
        for i, a in enumerate(actions, 1)
    )


plans = [
    combo
    for n in range(1, 5)
    for combo in itertools.product((ECHO, NOTE, DELEGATE, DRAFT), repeat=n)
]
right = True
for combo in plans:
    request = plan_request("demo", steps_of(combo), run_id=RUN)
    all_read = all(a.effect == "read" for a in combo)
    if all_read:
        right = right and request is None
    else:
        right = (
            right
            and request is not None
            and [s.effect for s in request.steps] == [a.effect for a in combo]
        )
check(
    f"plan approval is asked exactly when a step is not read ({len(plans)} plans)",
    right,
)

right = True
for action, attempt in itertools.product((ECHO, NOTE, DELEGATE, DRAFT), (1, 2, 3)):
    request = step_request("demo", steps_of((action,))[0], run_id=RUN, attempt=attempt)
    asked = action.effect in ("propose", "write") or (
        action.effect == "implement" and attempt == 1
    )
    right = right and (request is not None) == asked
check(
    "step approval: propose and write always, implement on the first attempt only",
    right,
)

requests = [
    r for r in (plan_request("demo", steps_of(c), run_id=RUN) for c in plans) if r
]
check(
    "every plan request round-trips",
    all(ApprovalRequest.from_json(r.model_dump_json()) == r for r in requests),
)

rng = random.Random(4)
tampered_refused = True
for request in rng.sample(requests, 100):
    data = json.loads(request.model_dump_json())
    step = rng.choice(data["steps"])
    key = rng.choice(sorted(step["args"]))
    step["args"][key] = "changed" if step["args"][key] != "changed" else "again"
    try:
        ApprovalRequest.from_json(json.dumps(data))
        tampered_refused = False
    except ValidationError:
        pass
check("a stored request with any argument changed no longer parses", tampered_refused)


def decision(request, **changes) -> ApprovalDecision:
    fields = {
        "approval_id": request.approval_id,
        "verdict": "approve",
        "args_sha256": request.args_sha256,
        "channel": "web",
        "decided_by": "owner",
        "decided_at": AT,
    }
    return ApprovalDecision(**{**fields, **changes})


note = step_request("demo", steps_of((NOTE,))[0], run_id=RUN)
others = [r.args_sha256 for r in requests if r.args_sha256 != note.args_sha256][:50]
stale = 0
for digest in others:
    try:
        apply_decision(note, decision(note, args_sha256=digest), registry)
    except DecisionRefused as error:
        stale += error.code == "stale"
check("a decision for other arguments is always stale", stale == len(others))

safe = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
values = ["", "x", "Home", "home", 3, None, True, ["home"], ["Home"], "y" * 81]
agree = True
for title, tags in itertools.product(values, values):
    edited = {"title": title, "tags": tags}
    try:
        expected = demo.NoteArgs.from_json(json.dumps(edited))
    except ValidationError:
        expected = None
    try:
        outcome = apply_decision(
            note, decision(note, verdict="edit", edited_args=edited), registry
        )
        agree = agree and outcome == Approved(args=expected, edited=True)
        agree = agree and type(outcome.args) is demo.NoteArgs
    except DecisionRefused as error:
        agree = agree and expected is None and error.code == "invalid_edit"
        agree = agree and all(safe.fullmatch(p.code) for p in error.problems)
        agree = agree and "Home" not in repr(error.problems)
check("an edit is approved exactly when the action's contract accepts it", agree)

outcome = apply_decision(note, decision(note, verdict="reject", note="no"), registry)
check("a rejection never carries arguments", outcome == Rejected(note="no"))

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_policy_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `implement` always asks (`needs_approval`) | `test_what_needs_approval`, `(DELEGATE, 3)` | `False` | `True` |
| 2 | a plan request even when every step is `read` (`plan_request`) | `test_a_read_only_plan_needs_no_approval` | `None` | a request |
| 3 | only the side-effect steps in the plan request (`plan_request`) | `test_a_plan_with_a_side_effect_shows_every_step` | both steps | the note only |
| 4 | `steps_digest` without `sort_keys=True` | `test_the_digest_is_pinned` | the pinned hash | another |
| 5 | the digest check removed (`ApprovalRequest`) | `test_a_request_that_does_not_hold_together`, `"0" * 64` | `DIGEST_MESSAGE` | accepted |
| 6 | the UTC check removed (`UtcTime`) | `test_a_request_that_does_not_hold_together`, `+02:00` | `UTC_MESSAGE` | accepted |
| 7 | the digest comparison removed (`apply_decision`) | `test_a_decision_that_is_refused`, `"0" * 64` | `stale` | `Approved` |
| 8 | edited arguments used without parsing (`apply_decision`) | `test_a_decision_that_is_refused`, `{"title": "", ...}` | `invalid_edit` | `Approved` |
| 9 | the digest checked before the approval id (`apply_decision`) | the coder's order test | `other_request` | `stale` |

Reasonable variations that are correct: one private helper that builds a `PlannedStep` for both request kinds; `match` on the verdict; `Approved` and `Rejected` with `slots=True`; the digest computed in a `model_validator(mode="after")`.

## 6. Project rules

- Searches 1 to 3.
- The only `False` that `needs_approval` returns for a non-`read` effect is `implement` with `attempt > 1`.
- Every `DecisionRefused` message is `decision refused: <code>`; its problems come from `problems_from` only.

## 7. Out of scope

Each must be absent: storage or SQLite, leases, commands, the graph or `interrupt`, events, expiry, replanning, editing a plan, re-exports from `conductor.contracts`, changes to existing contracts, the registry, plan checking, or `conductor.llm`.

## 8. Progress log

The entry exists, headed `## Phase 4a: approval contracts and the policy (...)`, with `Tests: 308 -> <passed> (given 34)`, and each deviation it lists is real and justified.
