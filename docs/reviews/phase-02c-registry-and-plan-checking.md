# Review: Phase 2c

- Verdict: PASS
- Passed: 202
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gate output

`.venv/bin/python scripts/check.py --first core` exited 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The `tests` step reported `202 passed` in 4.67s. No skipped, xfailed, or warnings summary. The `critical coverage` step passed with `plancheck.py` included. Sections tables, both with 0 failed:

```
Sections:
  core          181 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          181 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/plancheck.py,*/conductor/registry.py" --fail-under=100`, run on the data that check left, exited 0. `TOTAL` is `100%` (141 statements, 46 branches: `plancheck.py` 47 statements and 8 branches, `registry.py` 94 statements and 38 branches).

`.venv/bin/python -m pytest tests/unit/test_registry.py tests/unit/test_plancheck.py --no-cov` reported `26 passed`.

`.venv/bin/python scripts/check_reports.py`, run before this review was written, printed `Reports OK.` and exited 0.

`git diff --stat HEAD -- tests src/conductor/contracts` printed nothing.

Searches 1 and 2 printed nothing.

## Scope

`git status --short` lists `docs/progress.md`, `docs/testing.md`, `scripts/critical_modules.txt`, `src/conductor/domains/`, `src/conductor/plancheck.py`, `src/conductor/registry.py`, `tests/unit/test_plancheck.py`, `tests/unit/test_registry.py`, and `tests/unit/test_registry_more.py`.

The two given test files match the spec's blocks. `docs/testing.md` adds `` `plancheck.py` (plans checked against the registry; Phase 2c) `` after `reports.py`, and the Planned line is `Planned: the approval policy (Phase 4).` `scripts/critical_modules.txt` adds `plancheck.py` after `reports.py`.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_a_registry_refuses_a_bad_declaration`, `test_the_first_problem_in_declaration_order_is_named`; `test_a_target_of_64_characters_is_accepted`, `test_a_target_of_65_characters_is_refused`, `test_args_must_be_the_contract_class` |
| R2 | pass | `test_lookups` (`Registry(())`); `test_a_registry_keeps_the_names_it_was_built_with`; probe `the production list is empty and registers` |
| R3 | pass | `test_lookups`, `test_a_lookup_of_something_not_registered`; `test_an_action_name_without_a_dot` |
| R4 | pass | `test_the_demo_domain`; `demo.py` matches the Design (field names, order, bounds, defaults); `DOMAINS` is `()`; probe `every argument model has a schema` |
| R5 | pass | `test_a_plan_for_another_domain` |
| R6 | pass | `test_arguments_are_checked_strictly`, `test_every_bad_step_is_named`, `test_no_argument_value_reaches_a_problem`; search 2 empty |
| R7 | pass | `test_problems_stop_at_twenty`; probe `random arguments only ever reject cleanly` |
| R8 | pass | `test_a_plan_that_fits`; probes `eight good steps are numbered in order`, `the check leaves the plan as it was` |
| R9 | pass | search 1 empty; probe `plancheck imports little` |

The coder's tests cover each bullet of "Tests to write":

| Bullet | Test |
|---|---|
| A registry built from a list, then appended to, keeps the original names | `test_a_registry_keeps_the_names_it_was_built_with` |
| `action("demo")` raises `no action demo` | `test_an_action_name_without_a_dot` |
| A target of 64 characters is accepted, 65 refused; an args instance is refused | `test_a_target_of_64_characters_is_accepted`, `test_a_target_of_65_characters_is_refused`, `test_args_must_be_the_contract_class` |
| `true` for `max_minutes` is `int_type`; a JSON array is accepted for a tuple | `test_true_is_not_an_int`, `test_a_json_array_is_accepted_for_a_tuple` |
| Eight steps, only the last bad, names `steps.7...` | `test_only_the_last_step_is_named` |
| `CheckedStep.args` is the action's own args class | `test_parsed_args_are_the_actions_own_class` |

Each asserts the message, the problem location and code, or the parsed value. `test_an_empty_argument_location_is_the_prefix_only` asserts the empty-location case of R6: `loc` is `steps.0.args` and the reply text is absent from the problem.

## Probe

`/tmp/probe_02c.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   eight good steps are numbered in order
ok   random arguments only ever reject cleanly
ok   every argument model has a schema
ok   the check leaves the plan as it was
ok   plancheck imports little
ok   the production list is empty and registers
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The files were then restored from the copies taken first. `git status --short` after the restore is the same set of paths.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_arguments_are_checked_strictly` for `"max_minutes": "10"`: `Failed: DID NOT RAISE PlanRejected` |
| 2 | `test_a_plan_that_fits` for `"tags": ["home", "weekly"]`: `steps.0.args.tags` `tuple_type` |
| 3 | `test_every_bad_step_is_named`: one `unknown_action` problem, where the test requires three |
| 4 | `test_problems_stop_at_twenty`: `assert 40 == 20` |
| 5 | `test_arguments_are_checked_strictly`: `steps.1.args.max_minutes` `int_type` |
| 6 | `test_a_plan_for_another_domain` for `mail.send` under the demo route: `steps.0.action` `unknown_action` |
| 7 | `test_a_registry_refuses_a_bad_declaration` for `effect="implement"` on a tool: `Failed: DID NOT RAISE RegistryError` |
| 8 | `test_a_registry_refuses_a_bad_declaration` for `(PING, PING)`: `Failed: DID NOT RAISE RegistryError` |

## Project rules and progress

`plancheck.py` imports `json`, `dataclasses`, `pydantic.ValidationError`, `conductor.contracts`, and `conductor.registry`. Argument parsing goes through `from_json`. `DOMAINS` is `()`. The working tree has no routing rules, classifier, planner, planner schemas, prompts, approval policy, target-existence check, domain discovery, or edit under `src/conductor/contracts`.

`docs/progress.md` has `## Phase 2c: the registry and plan checking (2026-10-27)` and `Tests: 166 -> 202 (given 26)`. Deviations: None. The public names it lists are the names this phase adds.
