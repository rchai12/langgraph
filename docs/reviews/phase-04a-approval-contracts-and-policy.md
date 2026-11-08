# Review: Phase 4a

- Verdict: PASS
- Passed: 349
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

The `tests` step reported `349 passed` in 15.09s. No skipped, xfailed, or warnings summary. The `critical coverage` step passed with `policy.py` included. Sections tables, both with 0 failed:

```
Sections:
  core          328 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          328 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/policy.py,*/conductor/contracts/approvals.py" --fail-under=100`, run on the data that check left, exited 0. `TOTAL` is `100%` (123 statements, 32 branches: `approvals.py` 63 statements and 12 branches, `policy.py` 60 statements and 20 branches).

`.venv/bin/python -m pytest tests/unit/test_contracts_approvals.py tests/unit/test_policy.py --no-cov` reported `34 passed`.

`.venv/bin/python scripts/check_reports.py`, run before this review was written, printed `Reports OK.` and exited 0.

`git diff --stat HEAD -- tests src/conductor/contracts src/conductor/registry.py src/conductor/plancheck.py src/conductor/llm` printed nothing.

Searches 1, 2, and 3 printed nothing.

## Scope

`git status --short` lists `docs/progress.md`, `docs/testing.md`, `scripts/critical_modules.txt`, `src/conductor/contracts/approvals.py`, `src/conductor/policy.py`, `tests/unit/test_contracts_approvals.py`, `tests/unit/test_policy.py`, and `tests/unit/test_policy_more.py`.

The two given test files match the spec's blocks. `docs/testing.md` adds `` `policy.py` (which steps wait for a person, and what a decision allows; Phase 4a) `` after `llm/decide.py` and removes `Planned: the approval policy (Phase 4).` `scripts/critical_modules.txt` adds `policy.py` after `llm/decide.py`. `conductor/contracts/__init__.py` is unchanged.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_the_closed_sets`, `test_a_request_time_must_say_its_zone`, the `+02:00` case of `test_a_request_that_does_not_hold_together`; fields match the Design |
| R2 | pass | `test_the_digest_is_pinned` |
| R3 | pass | `test_a_request_that_does_not_hold_together`, `test_a_request_round_trips`; `test_a_lone_step_keeps_its_number_and_a_repeated_plan_number_is_refused`; probe `a stored request with any argument changed no longer parses` |
| R4 | pass | `test_a_decision_that_does_not_hold_together`, `test_a_decision_round_trips` |
| R5 | pass | `test_what_needs_approval`, `test_attempts_count_from_one`; `test_a_negative_attempt_is_refused_and_one_is_the_default` |
| R6 | pass | `test_a_read_only_plan_needs_no_approval`, `test_a_plan_with_a_side_effect_shows_every_step`; `test_a_plan_shows_the_read_step_beside_a_propose_step`; probe `plan approval is asked exactly when a step is not read` |
| R7 | pass | `test_a_step_request`; probe `step approval: propose and write always, implement on the first attempt only` |
| R8 | pass | `test_an_approved_plan`, `test_an_approved_step_runs_with_its_own_arguments`, `test_a_rejection_ends_with_the_note`, `test_an_edit_approves_the_new_arguments`, `test_a_decision_that_is_refused`, `test_a_plan_cannot_be_edited`; `test_the_approval_id_is_checked_before_the_digest`, `test_a_plan_rejection_keeps_an_empty_note`, `test_an_approved_step_parses_a_fresh_copy_of_its_arguments`; probes `a decision for other arguments is always stale`, `an edit is approved exactly when the action's contract accepts it`, `a rejection never carries arguments` |
| R9 | pass | `test_an_invalid_edit_does_not_echo_the_value`; the edit probe keeps values out of the problems |
| R10 | pass | searches 1, 2, and 3 empty |

The coder's tests cover each bullet of "Tests to write":

| Bullet | Test |
|---|---|
| A lone step numbered 5 is valid; a plan numbered `(1, 1)` is `NUMBERS_MESSAGE` | `test_a_lone_step_keeps_its_number_and_a_repeated_plan_number_is_refused` |
| `attempt=-1` raises; `attempt=1` is the default | `test_a_negative_attempt_is_refused_and_one_is_the_default` |
| A read step beside a propose step is shown; id and clock are read once | `test_a_plan_shows_the_read_step_beside_a_propose_step` |
| Another id and digest is `other_request`; an edit on a plan with a wrong digest is `stale` | `test_the_approval_id_is_checked_before_the_digest` |
| A plan rejection with no note is `Rejected(note="")` | `test_a_plan_rejection_keeps_an_empty_note` |
| An approved step parses a new instance of the action's args class | `test_an_approved_step_parses_a_fresh_copy_of_its_arguments` |
| `"SYNTHETIC-SECRET"` is absent from the message, the code, and the problems | `test_an_invalid_edit_does_not_echo_the_value` |

Each asserts the message, the code, the steps, the call counts, or that the parsed args are a different object.

## Probe

`/tmp/probe_04a.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   plan approval is asked exactly when a step is not read (340 plans)
ok   step approval: propose and write always, implement on the first attempt only
ok   every plan request round-trips
ok   a stored request with any argument changed no longer parses
ok   a decision for other arguments is always stale
ok   an edit is approved exactly when the action's contract accepts it
ok   a rejection never carries arguments
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The files were then restored from the copies taken first. `git status --short` after the restore is the same set of paths.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_what_needs_approval` for `(DELEGATE, 3)`: `assert True is False` |
| 2 | `test_a_read_only_plan_needs_no_approval`: a plan request was returned |
| 3 | `test_a_plan_with_a_side_effect_shows_every_step`: `ValidationError` for `ApprovalRequest` |
| 4 | `test_the_digest_is_pinned`: the hash was not the pinned one |
| 5 | `test_a_request_that_does_not_hold_together` for `"0" * 64`: `Failed: DID NOT RAISE ValidationError` |
| 6 | `test_a_request_that_does_not_hold_together` for `+02:00`: `Failed: DID NOT RAISE ValidationError` |
| 7 | `test_a_decision_that_is_refused` for `"0" * 64`: `Failed: DID NOT RAISE DecisionRefused` |
| 8 | `test_a_decision_that_is_refused` for the empty title: `Failed: DID NOT RAISE DecisionRefused` |
| 9 | `test_the_approval_id_is_checked_before_the_digest`: `assert 'stale' == 'other_request'` |

## Project rules and progress

`needs_approval` returns `False` for a non-`read` effect only when the effect is `implement` and the attempt is above 1. Every `DecisionRefused` message is `decision refused: <code>`, and its problems come from `problems_from`. `policy.py` calls `from_json`, not `model_validate`. The new modules have no storage, SQLite, leases, commands, graph, `interrupt`, events, expiry, or replanning, and they do not edit a plan. Existing contracts, the registry, plan checking, and `conductor.llm` are unchanged.

`docs/progress.md` has `## Phase 4a: approval contracts and the policy (2026-11-08)` and `Tests: 308 -> 349 (given 34)`. Deviations: None. The public names it lists are the names this phase adds.
