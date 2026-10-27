# Verify Phase 2c: the registry and plan checking

Spec: `docs/phases/phase-02c-registry-and-plan-checking.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.registry`, `conductor.domains` (with `DOMAINS = ()` and the demo domain), and `conductor.plancheck` (critical), added `plancheck.py` to the critical modules, copied two given test files (26 tests), and wrote `tests/unit/test_registry_more.py`.

## 1. Gates

N is `166`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 192 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `plancheck.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/plancheck.py,*/conductor/registry.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_registry.py tests/unit/test_plancheck.py --no-cov` | exactly `26 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- tests src/conductor/contracts` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/plancheck.py | grep -v -E "(__future__|dataclasses|json|typing|conductor\.contracts|conductor\.registry|pydantic)"`
2. `git grep --untracked -n -E "model_validate\(" -- src/conductor/plancheck.py`

## 2. Scope paths

`git status --short` lists only: `src/conductor/registry.py`, `src/conductor/domains/`, `src/conductor/plancheck.py`, `scripts/critical_modules.txt`, `docs/testing.md`, the two given test files, `tests/unit/test_registry_more.py`, `docs/progress.md`. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_registry_refuses_a_bad_declaration`, `test_the_first_problem_in_declaration_order_is_named`; the coder's target-length and args-instance tests | pass |
| R2 | `test_lookups` (`Registry(())`); the coder's list-then-append test; probe "the production list is empty and registers" | pass; ok |
| R3 | `test_lookups`, `test_a_lookup_of_something_not_registered`; the coder's `action("demo")` test | pass |
| R4 | `test_the_demo_domain`; read `demo.py` against the spec's Design (field names, order, bounds, defaults); probe "every argument model has a schema" | the same; ok |
| R5 | `test_a_plan_for_another_domain` | pass |
| R6 | `test_arguments_are_checked_strictly`, `test_every_bad_step_is_named`, `test_no_argument_value_reaches_a_problem`; search 2 | pass; no output |
| R7 | `test_problems_stop_at_twenty`; probe "random arguments only ever reject cleanly" | pass; ok |
| R8 | `test_a_plan_that_fits`; probes "eight good steps ...", "the check leaves the plan as it was" | pass; ok |
| R9 | search 1; probe "plancheck imports little" | no output; ok |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it.

```python
"""Probe for Phase 2c. Save outside the repository; run from the repository root with
.venv/bin/python <path>. Every line ends in ok; the last line is FAILURES 0."""

import ast
import random
from collections.abc import Callable
from pathlib import Path

FAILURES = 0


def check(name: str, test: Callable[[], None]) -> None:
    global FAILURES
    try:
        test()
        print(f"ok   {name}")
    except Exception as error:  # noqa: BLE001 - a probe reports every failure and goes on
        FAILURES += 1
        print(f"FAIL {name}: {type(error).__name__}: {error}")


def expect(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def eight_good_steps_are_numbered_in_order() -> None:
    from conductor.contracts import Plan, Route, Step
    from conductor.domains import demo
    from conductor.plancheck import check_plan
    from conductor.registry import Registry

    registry = Registry([demo.DOMAIN])
    steps = tuple(Step(action="demo.echo", args={"text": f"line {n}"}) for n in range(8))
    checked = check_plan(Plan(steps=steps), Route(domain="demo", decided_by="model"), registry)
    expect([step.number for step in checked] == [1, 2, 3, 4, 5, 6, 7, 8], "numbers")
    expect([step.args.text for step in checked] == [f"line {n}" for n in range(8)], "order")
    expect(isinstance(checked, tuple), type(checked).__name__)


def random_arguments_only_ever_reject_cleanly() -> None:
    from conductor.contracts import MAX_PROBLEMS, Plan, Route, Step
    from conductor.domains import demo
    from conductor.plancheck import PlanRejected, check_plan
    from conductor.registry import Registry

    registry = Registry([demo.DOMAIN])
    route = Route(domain="demo", decided_by="model")
    values = [None, True, 0, -1, 61, 1.5, "", "x" * 2001, "ok", ["a"], ["B"], {"k": 1}, [1, 2]]
    keys = ["text", "title", "body", "tags", "task", "max_minutes", "other", "Bad Key"]
    actions = ["demo.echo", "demo.note", "demo.delegate", "demo.missing"]
    chooser = random.Random(2026)
    accepted = rejected = 0
    for _ in range(2000):
        steps = []
        for _ in range(chooser.randint(1, 8)):
            args = {chooser.choice(keys): chooser.choice(values) for _ in range(chooser.randint(0, 4))}
            steps.append(Step(action=chooser.choice(actions), args=args))
        try:
            check_plan(Plan(steps=tuple(steps)), route, registry)
            accepted += 1
        except PlanRejected as error:
            rejected += 1
            expect(1 <= len(error.problems) <= MAX_PROBLEMS, f"{len(error.problems)} problems")
            for problem in error.problems:
                expect(problem.loc.startswith("steps."), problem.loc)
    expect(accepted > 0 and rejected > 0, f"accepted {accepted}, rejected {rejected}")


def every_argument_model_has_a_schema() -> None:
    from conductor.domains import demo

    for action in demo.DOMAIN.actions:
        for model in (action.args, action.result):
            schema = model.model_json_schema()
            expect(schema.get("additionalProperties") is False, f"{model.__name__} allows extras")


def the_check_leaves_the_plan_as_it_was() -> None:
    from conductor.contracts import Plan, Route, Step
    from conductor.domains import demo
    from conductor.plancheck import check_plan
    from conductor.registry import Registry

    plan = Plan(steps=(Step(action="demo.note", args={"title": "T", "tags": ["home"]}),))
    before = plan.model_dump_json()
    check_plan(plan, Route(domain="demo", decided_by="model"), Registry([demo.DOMAIN]))
    expect(plan.model_dump_json() == before, "plan changed")


def plancheck_imports_little() -> None:
    allowed = ("conductor.contracts", "conductor.registry")
    tree = ast.parse(Path("src/conductor/plancheck.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("conductor"):
            expect(node.module.startswith(allowed), node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                expect(not alias.name.startswith("conductor"), alias.name)


def the_production_list_is_empty_and_registers() -> None:
    from conductor.domains import DOMAINS
    from conductor.registry import Registry

    expect(DOMAINS == (), repr(DOMAINS))
    expect(Registry(DOMAINS).names == (), "names")


for name, test in [
    ("eight good steps are numbered in order", eight_good_steps_are_numbered_in_order),
    ("random arguments only ever reject cleanly", random_arguments_only_ever_reject_cleanly),
    ("every argument model has a schema", every_argument_model_has_a_schema),
    ("the check leaves the plan as it was", the_check_leaves_the_plan_as_it_was),
    ("plancheck imports little", plancheck_imports_little),
    ("the production list is empty and registers", the_production_list_is_empty_and_registers),
]:
    check(name, test)

print(f"FAILURES {FAILURES}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_registry_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | arguments parsed without strictness, `action.args.model_validate_json(json.dumps(step.args))` (`check_plan`) | `test_arguments_are_checked_strictly`, `"max_minutes": "10"` | `int_type` | accepted |
| 2 | arguments parsed with `action.args.model_validate(step.args, strict=True)` (`check_plan`) | `test_a_plan_that_fits`, `"tags": ["home", "weekly"]` | accepted | `tuple_type` |
| 3 | stop at the first bad step (`check_plan`) | `test_every_bad_step_is_named` | 3 problems | 1 |
| 4 | no `MAX_PROBLEMS` cut (`check_plan`) | `test_problems_stop_at_twenty` | 20 | 40 |
| 5 | step index from 1 in `loc` (`check_plan`) | `test_arguments_are_checked_strictly` | `steps.0.args.max_minutes` | `steps.1.args.max_minutes` |
| 6 | the plan-domain check removed (`check_plan`) | `test_a_plan_for_another_domain`, `mail.send` under the demo route | `steps` `wrong_domain` | `steps.0.action` `unknown_action` |
| 7 | the implement-needs-agent rule removed (`Registry.__init__`) | `test_a_registry_refuses_a_bad_declaration`, `effect="implement"` on a tool | refused | accepted |
| 8 | duplicate actions allowed (`Registry.__init__`) | `test_a_registry_refuses_a_bad_declaration`, `(PING, PING)` | `declared twice` | accepted |

Reasonable variations that are correct: lookups through dicts built in `__init__`; `Action` and `Domain` with `slots=True`; a private helper for the location prefix; `PlanRejected` storing problems as an attribute set in `__init__`.

## 6. Project rules

- Searches 1 and 2.
- `DOMAINS` is `()`: the demo domain is never in the production list.

## 7. Out of scope

Each must be absent: routing rules, a classifier, a planner, planner schemas, prompts; an approval policy; checks that `target` exists; multi-domain plans; domain discovery or loading from files; any change to `conductor.contracts`.

## 8. Progress log

The entry exists, headed `## Phase 2c: the registry and plan checking (...)`, with `Tests: 166 -> <passed> (given 26)`, and each deviation it lists is real and justified.
