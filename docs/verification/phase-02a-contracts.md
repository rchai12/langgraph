# Verify Phase 2a: contracts

Spec: `docs/phases/phase-02a-contracts.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict.

The coder created the pure package `conductor.contracts` (routes, plans, tasks, escalations, and `problems_from`), copied two given test files (38 tests), and wrote `tests/unit/test_contracts_more.py`.

## 1. Gates

N is `70`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 108 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/contracts/*" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_contracts_plans.py tests/unit/test_contracts_tasks.py --no-cov` | exactly `38 passed` |
| `git diff --stat HEAD -- tests src/conductor/events.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/contracts | grep -v "conductor.contracts"`
2. `git grep --untracked -n -E "pattern=r?\"[^^]" -- src/conductor/contracts`
3. `git grep --untracked -n -E "\[.(input|msg|ctx|url).\]" -- src/conductor/contracts`

## 2. Scope paths

`git status --short` lists only `src/conductor/contracts/`, the two given test files, `tests/unit/test_contracts_more.py`, and `docs/progress.md`. The given test files equal the spec's blocks.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_extra_fields_are_refused_and_code_may_pass_lists`, `test_a_task_spec_from_text_refuses_bad_values` (the `"2"` case); probe "text is strict"; read `Contract`: no `strict=True` in its config | pass; ok |
| R2 | `test_numbers_must_be_finite_in_json`, `test_numbers_must_be_finite_when_built`; probe "non-finite numbers everywhere"; read `Contract`: no `allow_inf_nan` | pass; ok |
| R3 | `test_an_action_name_must_be_domain_dot_name`, `test_the_longest_names_are_accepted`; probe "names are ASCII only"; search 2 | pass; ok; no output |
| R4 | `test_a_route_names_its_rule_only_when_a_rule_decided`, `test_a_route_refuses_bad_values` | pass |
| R5, R6 | `test_a_plan_from_the_models_json`, `test_a_plan_has_one_to_eight_steps`, `test_a_plan_stays_in_one_domain` | pass |
| R7 | `test_a_task_spec_carries_earlier_results_and_round_trips`, `test_a_task_spec_from_text_refuses_bad_values`; the coder's context test (7 kept, 8 refused) | pass |
| R8 | `test_a_result_has_output_or_an_error_never_both`; the coder's message-length test | pass |
| R9 | `test_an_escalation_points_at_its_run`, `test_an_escalation_refuses_bad_values` | pass |
| R10 | `test_problems_never_carry_what_was_given`, `test_problems_name_list_positions_and_stop_at_twenty`; probe "problems keep safe keys only"; search 3 | pass; ok; no output |
| R11 | `test_the_package_exports_exactly_its_public_names` | pass |
| R12 | search 1; probe "contracts import nothing else from the project" | no output; ok |

Also: probe "every contract round-trips both ways" (JSON and Python) and "a schema for the plan exists".

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it.

```python
"""Probe for Phase 2a. Save outside the repository; run from the repository root with
.venv/bin/python <path>. Every line ends in ok; the last line is FAILURES 0."""

import ast
from collections.abc import Callable
from pathlib import Path

FAILURES = 0
A = "0123456789abcdef0123456789abcdef"
B = "fedcba9876543210fedcba9876543210"
C = "00000000000000000000000000000003"


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


def refused(build: Callable[[], object]) -> list[tuple[str, str]]:
    from pydantic import ValidationError

    try:
        build()
    except ValidationError as error:
        return [(".".join(map(str, item["loc"])), item["type"]) for item in error.errors()]
    raise AssertionError("accepted")


def names_are_ascii_only() -> None:
    from conductor.contracts import Route, Step

    for action in ("demo١.echo", "demö.echo", "demo.echö", "demo..echo", ".echo"):
        expect(refused(lambda: Step(action=action, args={})) != [], action)
    expect(refused(lambda: Route(domain="finance\n", decided_by="model")) != [], "newline")


def every_contract_round_trips_both_ways() -> None:
    from conductor.contracts import (
        Escalation,
        FieldProblem,
        Plan,
        Route,
        Step,
        TaskError,
        TaskResult,
        TaskSpec,
    )

    failed = TaskResult(
        task_id=B,
        status="failed",
        error=TaskError(kind="timeout", message="no answer in 30 s"),
        attempts=3,
    )
    done = TaskResult(task_id=C, status="succeeded", output={"rows": [{"a": 1.25}]}, attempts=1)
    contracts = [
        Route(domain="code", decided_by="rule", rule_id="code.prefix-1"),
        Plan(steps=(Step(action="code.implement", args={"phase": "2a", "dry": False}),)),
        TaskSpec(
            task_id=A,
            run_id=B,
            thread_id=C,
            step=8,
            action="code.implement",
            args={"nested": {"list": [None, True, "é"]}},
            context=(failed, done),
            max_attempts=3,
        ),
        failed,
        Escalation(
            kind="retries_exhausted",
            detail="the verifier failed the work three times",
            run_id=A,
            problems=(FieldProblem(loc="", code="value_error"),),
        ),
    ]
    for contract in contracts:
        kind = type(contract)
        expect(kind.from_json(contract.model_dump_json()) == contract, f"{kind.__name__} json")
        expect(kind.model_validate(contract.model_dump()) == contract, f"{kind.__name__} python")


def text_is_strict() -> None:
    from conductor.contracts import TaskResult

    text = '{"task_id":"%s","status":"succeeded","output":{},"error":null,"attempts":%s}'
    expect(TaskResult.from_json(text % (A, "1")).attempts == 1, "plain int")
    for attempts in ("1.0", '"1"', "true"):
        expect(refused(lambda: TaskResult.from_json(text % (A, attempts))) != [], attempts)


def non_finite_numbers_everywhere() -> None:
    from conductor.contracts import NOT_FINITE_MESSAGE, TaskResult, TaskSpec

    for build in (
        lambda: TaskSpec(
            task_id=A,
            run_id=B,
            thread_id=C,
            step=1,
            action="demo.echo",
            args={"a": [[{"b": float("-inf")}]]},
        ),
        lambda: TaskResult(task_id=A, status="succeeded", output={"x": float("inf")}, attempts=1),
        lambda: TaskResult.from_json(
            '{"task_id":"%s","status":"succeeded","output":{"x":[NaN]},"error":null,"attempts":1}'
            % A
        ),
    ):
        from pydantic import ValidationError

        try:
            build()
        except ValidationError as error:
            expect(NOT_FINITE_MESSAGE in str(error), str(error)[:120])
        else:
            raise AssertionError("accepted")


def a_schema_for_the_plan_exists() -> None:
    from conductor.contracts import Plan, Step

    for kind in (Plan, Step):
        schema = kind.model_json_schema()
        expect(schema.get("additionalProperties") is False, f"{kind.__name__} allows extras")


def problems_keep_safe_keys_only() -> None:
    from pydantic import ValidationError

    from conductor.contracts import Step, problems_from

    long_ok = "k" * 64
    too_long = "k" * 65
    try:
        Step(action="demo.echo", args={long_ok: {1}, too_long: {2}, "a b": {3}, "_x9": {4}})
    except ValidationError as error:
        locs = [problem.loc for problem in problems_from(error)]
        expect(locs == [f"args.{long_ok}", "args.*", "args.*", "args._x9"], repr(locs))
    else:
        raise AssertionError("accepted")


def contracts_import_nothing_else_from_the_project() -> None:
    for path in sorted(Path("src/conductor/contracts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [("." * node.level) + (node.module or "")]
            for module in modules:
                outside = module.startswith("conductor") and not module.startswith(
                    "conductor.contracts"
                )
                expect(not outside and not module.startswith(".."), f"{path.name}: {module}")


for name, test in [
    ("names are ASCII only", names_are_ascii_only),
    ("every contract round-trips both ways", every_contract_round_trips_both_ways),
    ("text is strict", text_is_strict),
    ("non-finite numbers everywhere", non_finite_numbers_everywhere),
    ("a schema for the plan exists", a_schema_for_the_plan_exists),
    ("problems keep safe keys only", problems_keep_safe_keys_only),
    ("contracts import nothing else from the project", contracts_import_nothing_else_from_the_project),
]:
    check(name, test)

print(f"FAILURES {FAILURES}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_contracts_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named place, run the deciding test, see it fail, restore.

| # | Change (place) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the finite check removed from `JsonObject`, `allow_inf_nan=False` put in `Contract`'s config (`base.py`) | `test_numbers_must_be_finite_in_json`, the `NaN` case | refused with `numbers must be finite` | accepted |
| 2 | `^` and `$` removed from `ActionName`'s pattern (`base.py`) | `test_an_action_name_must_be_domain_dot_name`, `demo.echo.twice` | `string_pattern_mismatch` | accepted |
| 3 | `strict=True` removed from `from_json` (`base.py`) | `test_a_task_spec_from_text_refuses_bad_values`, `max_attempts` `"2"` | `int_type` | accepted as 2 |
| 4 | `problems_from` keeps every `str` part of `loc` (`escalations.py`) | `test_problems_never_carry_what_was_given` | `args.*` | `args.card 4417-1234` |
| 5 | `problems_from` without the `MAX_PROBLEMS` cut (`escalations.py`) | `test_problems_name_list_positions_and_stop_at_twenty` | 20 | 25 |
| 6 | the one-domain check removed from `Plan` (`plans.py`) | `test_a_plan_stays_in_one_domain` | refused | accepted |
| 7 | `Route` checks only that a `rule` route has a `rule_id` (`plans.py`) | `test_a_route_names_its_rule_only_when_a_rule_decided`, `model` with `finance.prefix` | refused | accepted |
| 8 | `TaskResult` lets `failed` carry `output` (`tasks.py`) | `test_a_result_has_output_or_an_error_never_both`, `failed` with `{"partial": 1}` | refused | accepted |

Reasonable variations that are correct: the finite check written as a recursive function or a loop; the `Literal` sets defined in `base.py` and imported; private helpers inside the five modules. `domain` must be a plain `@property`: a `computed_field` would be dumped and then refused by `from_json` as an extra field.

## 6. Project rules

- Searches 1 to 3.
- The model validators raise only the spec's constant messages.

## 7. Out of scope

Each must be absent: a registry, domains, or per-action schemas; approval contracts; step ids or step dependencies; any change to `events.py`; prompt text or Ollama schemas.

## 8. Progress log

The entry exists in the form of `docs/phase-conventions.md`, headed `## Phase 2a: contracts (...)`, with `Tests: 70 -> <passed> (given 38)`, and each deviation it lists is real and justified.
