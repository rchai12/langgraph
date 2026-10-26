# Review: Phase 2a

- Verdict: PASS
- Passed: 114
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

The `tests` step reported `114 passed` in 4.91s. No skipped, xfailed, or warnings summary. Sections tables, both with 0 failed:

```
Sections:
  core           93 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core           93 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/contracts/*" --fail-under=100` exited 0. `TOTAL` is `100%` (129 statements, 26 branches).

`.venv/bin/python -m pytest tests/unit/test_contracts_plans.py tests/unit/test_contracts_tasks.py --no-cov` reported `38 passed`.

`git diff --stat HEAD -- tests src/conductor/events.py` printed nothing.

Searches 1, 2, and 3 printed nothing.

## Scope

`tests/unit/test_contracts_plans.py` and `tests/unit/test_contracts_tasks.py` match the spec's blocks. Under `src/conductor/contracts/` the modules are `__init__.py`, `base.py`, `plans.py`, `tasks.py`, and `escalations.py`.

`git status --short` also lists edits the progress entry says this phase did not make: `.claude/skills/phase-architect/SKILL.md`, `docs/roadmap.md`, and untracked `.claude/skills/phase-architect/phase_status.py`. Those diffs are the architect skill and the roadmap. They were left out of this verdict.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_extra_fields_are_refused_and_code_may_pass_lists`, `test_a_task_spec_from_text_refuses_bad_values` (`"2"`); probe `text is strict`; `Contract` config has no `strict=True` |
| R2 | pass | `test_numbers_must_be_finite_in_json`, `test_numbers_must_be_finite_when_built`; probe `non-finite numbers everywhere`; `Contract` config has no `allow_inf_nan` |
| R3 | pass | `test_an_action_name_must_be_domain_dot_name`, `test_the_longest_names_are_accepted`; probe `names are ASCII only`; search 2 empty |
| R4 | pass | `test_a_route_names_its_rule_only_when_a_rule_decided`, `test_a_route_refuses_bad_values` |
| R5, R6 | pass | `test_a_plan_from_the_models_json`, `test_a_plan_has_one_to_eight_steps`, `test_a_plan_stays_in_one_domain`; `domain` is a `@property` on `Step` and `Plan` |
| R7 | pass | `test_a_task_spec_carries_earlier_results_and_round_trips`, `test_a_task_spec_from_text_refuses_bad_values`; `test_a_task_spec_keeps_seven_earlier_results` |
| R8 | pass | `test_a_result_has_output_or_an_error_never_both`; `test_a_task_error_message_of_500_characters_is_kept` |
| R9 | pass | `test_an_escalation_points_at_its_run`, `test_an_escalation_refuses_bad_values`; `test_an_escalation_refuses_an_empty_detail_and_a_bad_run_id` |
| R10 | pass | `test_problems_never_carry_what_was_given`, `test_problems_name_list_positions_and_stop_at_twenty`; probe `problems keep safe keys only`; search 3 empty |
| R11 | pass | `test_the_package_exports_exactly_its_public_names` |
| R12 | pass | search 1 empty; probe `contracts import nothing else from the project` |

Probes `every contract round-trips both ways` and `a schema for the plan exists` passed.

The coder's tests, one per bullet of "Tests to write":

| Bullet | Test |
|---|---|
| Assigning to a frozen field raises `ValidationError` | `test_assigning_to_a_field_is_refused` |
| `TaskError.message` of 500 is kept; `""` and 501 are refused | `test_a_task_error_message_of_500_characters_is_kept` |
| `TaskSpec.args` and `TaskResult.output` refuse JSON `NaN` with `NOT_FINITE_MESSAGE` | `test_task_output_and_args_refuse_nan_from_json` |
| `TaskSpec.context` of 7 is kept; 8 is refused | `test_a_task_spec_keeps_seven_earlier_results` |
| `Escalation.detail` `""` and `run_id` `"latest"` are refused | `test_an_escalation_refuses_an_empty_detail_and_a_bad_run_id` |
| Whole-object `loc` is `""`; a 64-character key is kept; 65 and `"café"` become `*` | `test_problems_name_the_whole_object_and_mask_long_or_unsafe_keys` |

Each asserts the exception type, the message or error code, or the returned value.

## Probe

`/tmp/probe_02a.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   names are ASCII only
ok   every contract round-trips both ways
ok   text is strict
ok   non-finite numbers everywhere
ok   a schema for the plan exists
ok   problems keep safe keys only
ok   contracts import nothing else from the project
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The file was then restored from the copy taken first. `git diff` for the four contract modules was empty afterwards.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_numbers_must_be_finite_in_json` for `NaN`: `Failed: DID NOT RAISE ValidationError` |
| 2 | `test_an_action_name_must_be_domain_dot_name` for `demo.echo.twice`: `Failed: DID NOT RAISE ValidationError` |
| 3 | `test_a_task_spec_from_text_refuses_bad_values` for `max_attempts` `"2"`: `Failed: DID NOT RAISE ValidationError` |
| 4 | `test_problems_never_carry_what_was_given`: loc was `args.card 4417-1234` |
| 5 | `test_problems_name_list_positions_and_stop_at_twenty`: `assert 25 == 20` |
| 6 | `test_a_plan_stays_in_one_domain`: `Failed: DID NOT RAISE ValidationError` |
| 7 | `test_a_route_names_its_rule_only_when_a_rule_decided` for `model` with `finance.prefix`: `Failed: DID NOT RAISE ValidationError` |
| 8 | `test_a_result_has_output_or_an_error_never_both` for `failed` with `{"partial": 1}`: `Failed: DID NOT RAISE ValidationError` |

## Project rules and progress

The model validators raise `ROUTE_MESSAGE`, `ONE_DOMAIN_MESSAGE`, `RESULT_MESSAGE`, or `NOT_FINITE_MESSAGE`. `problems_from` reads `loc` and `type`. There is no registry, domain catalogue, approval contract, step id, prompt, or Ollama schema, and `events.py` is unchanged.

`docs/progress.md` has `## Phase 2a: contracts (2026-10-26)` and `Tests: 70 -> 114 (given 38)`. Deviations: None. The follow-up about the extra working-tree files matches the status above.
