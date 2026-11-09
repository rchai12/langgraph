# Review: Phase 5b

- Verdict: PASS
- Passed: 500
- Findings: 0
- Approved deviations: None
- For the architect: spot 9's broken column expects AssertionError because the model was asked; moving the results count to after decide still builds AnswerInputs first, so the deciding test fails on that validation message and the model stays uncalled

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first core` exited 0. The `tests` step reported `500 passed` in 18.84s. No skipped, xfailed, or warnings summary. `critical coverage` passed. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

Sections, each with 0 failed. The first section run, then the full run:

```
Sections:
  core          449 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            51 passed    0 failed    0 skipped
  core          449 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/planning/*.py" --fail-under=100` exited 0. `TOTAL` is `100%` (89 statements, 8 branches).

`.venv/bin/python -m pytest tests/unit/test_plan.py tests/unit/test_answer.py --no-cov` printed `20 passed`.

`.venv/bin/python scripts/check_reports.py --phase 5b`, before this report, printed `Reports OK.`

The protected `git diff --stat` printed nothing. Searches 1 to 4 printed nothing. `git status --short` lists 10 lines, all in the Scope table. The two prompts and `tests/unit/test_plan.py` and `tests/unit/test_answer.py` are byte-equal to the spec fences. `docs/testing.md` and `scripts/critical_modules.txt` carry the two planning lines after `routing/route.py`.

## Progress

`## Phase 5b: planning and answering (2026-11-09)` with `Tests: 472 -> 500 (given 20)`. The 500 is 472 plus the 20 given tests plus 8 coder tests. Deviations: None. Follow-ups: None. Changed files: 10, the count of `git status --short` lines.

## Requirements

- R1: `test_the_plan_point_and_its_prompt`, `test_a_domain_of_one_action`, `test_fields_list_every_action_and_the_union_keeps_declaration_order`. `plan_output` builds `<action>_step` in domain order, `Union.__getitem__(tuple(step_types))` with `Field(discriminator="action")`, and `Field(max_length=MAX_STEPS)` with no minimum. The probe line on the schema passed.
- R2: `test_a_model_that_cannot_answer_escalates` in `test_plan.py`, `test_a_route_to_an_unregistered_domain_is_a_mistake`, `test_the_output_holds_each_action_to_its_own_arguments`, `test_a_script_error_passes_and_an_unreachable_model_escalates`. `plan_request` calls `decide` once on node `plan`. `InvalidModelOutput` and `ModelUnavailable` go to `escalation_for`. `ScriptError` and `NotRegistered` (`LookupError`, `no domain lab`) pass through.
- R3: `test_a_plan`, `test_an_empty_plan_escalates`, `test_a_check_in_the_arguments_counts_as_invalid_output`, `test_a_plan_the_check_refuses_escalates`, `test_omitted_arguments_keep_their_defaults_and_eight_steps_plan`. Empty steps use `NO_FIT_MESSAGE`. Other steps become `Plan` with `f"{domain.name}.{step.action}"` and `model_dump(mode="json")`, then `plancheck.check_plan`. `PlanRejected` uses `PLAN_REJECTED_MESSAGE` and the error's problems. The probe's planner-reply and check-once lines passed (`planned` 117, `empty` 242, `invalid` 1141).
- R4: `test_an_answer_needs_1_to_8_results`, `test_the_request_is_checked_as_in_routing`, `test_a_full_request_and_eight_results_reach_the_model_and_the_request_is_first`. The request check uses `REQUEST_MESSAGE` and runs before the results check.
- R5: `test_the_answer_point_and_its_prompt`, `test_an_answer`, `test_a_model_that_cannot_answer_escalates` in `test_answer.py`, `test_an_invalid_reply_is_the_escalation_and_a_script_error_passes`. One `decide` on `ANSWER_POINT`, node `answer`, empty fields. Success returns `Answered`.
- R6: `test_a_blank_reply_escalates`, `test_a_reply_of_2000_characters_is_kept_and_2001_is_too_long`. The validator raises `ValueError(BLANK_MESSAGE)`. The probe's reply line passed. `answer.v1.md` matches the spec.
- R7: searches 1 to 3. Neither module reads settings, the clock, or ids. `check_plan` is called through `plancheck`.
- R8: `test_a_secret_stays_out_of_every_escalation` (extra argument, empty plan, refused check, request text `SYNTHETIC-SECRET`). The probe's secret line passed. Escalations use `decision <id>: no registered action fits the request`, `decision <id>: the plan does not fit the registry`, or `escalation_for`. The `ValueError`s are `REQUEST_MESSAGE`, `RESULTS_MESSAGE`, and `BLANK_MESSAGE`.
- R9: event pairs in `test_a_plan` and `test_an_answer` use nodes `plan` and `answer`. `test_the_model_is_shown_the_stripped_request` shows the routed request `say hello` on a `demo.prefix` route. The output schema is built from the routed domain only.
- R10: the coverage gate and `critical coverage`.

## Probe

Every line started with `ok` and the last line was `FAILURES 0`.

```
ok   every planner reply is planned, or escalates, as the arguments say ({'planned': 117, 'empty': 242, 'invalid': 1141})
ok   the planner's schema offers exactly the domain's actions, in order
ok   every plan goes through plancheck.check_plan exactly once
ok   a reply is kept exactly when it has 1 to 2000 characters and is not blank
ok   no escalation carries the request or the reply's text
FAILURES 0
```

## Spot checks

Each change failed its deciding test. Reverse edits left `plan.py` and `answer.py` equal to the text from before the spots. `__pycache__` was removed afterwards.

| # | Result |
|---|---|
| 1 | 3 failed, 1 passed. The empty title case asserted one `string_too_short` problem and found a longer problem list. |
| 2 | `test_an_empty_plan_escalates` failed: a `too_short` problem, where the intact code returns `invalid_plan` with no problems. |
| 3 | `test_the_plan_point_and_its_prompt` failed on the pinned schema. |
| 4 | `test_a_plan` raised `ValidationError` for `Step`. |
| 5 | `test_a_plan` failed the `Plan` equality once defaults were excluded. |
| 6 | `test_a_plan_the_check_refuses_escalates` returned `Planned`. |
| 7 | `InvalidModelOutput` was raised on all four output cases. |
| 8 | the `" \n "` case failed `isinstance(found, Escalation)` (1 failed, 1 passed; `""` still fails `min_length`). |
| 9 | both counts failed the message assertion with `AnswerInputs` validation text (`too_short`, `too_long`). `NoModel` was not reached. |

## Out of scope

No graph, `interrupt`, approval call, step runner, or new dependency. The protected paths are unchanged. `pyproject.toml` is unchanged. `src/conductor/planning/__init__.py` is empty.
