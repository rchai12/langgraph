# Review: Phase 3c

- Verdict: PASS
- Passed: 308
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

The `tests` step reported `308 passed` in 13.88s. No skipped, xfailed, or warnings summary. The `critical coverage` step passed with `llm/decide.py` included. Sections tables, both with 0 failed:

```
Sections:
  core          287 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          287 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/llm/decide.py" --fail-under=100`, run on the data that check left, exited 0. `TOTAL` is `100%` (51 statements, 4 branches).

`.venv/bin/python -m pytest tests/unit/test_decide.py --no-cov` reported `19 passed`.

`.venv/bin/python scripts/check_reports.py`, run before this review was written, printed `Reports OK.` and exited 0.

`git diff HEAD -- tests` is the one added line `"model_unavailable",` in `test_the_closed_sets`. `git diff HEAD -- src/conductor/contracts` is the one added line `"model_unavailable",` at the end of `EscalationKind`.

Searches 1, 2, and 3 printed nothing.

## Scope

`git status --short` lists `docs/progress.md`, `docs/testing.md`, `scripts/critical_modules.txt`, `src/conductor/contracts/escalations.py`, `tests/unit/test_contracts_tasks.py`, `src/conductor/llm/decide.py`, `tests/unit/test_decide.py`, and `tests/unit/test_decide_more.py`.

`tests/unit/test_decide.py` matches the spec's block. `docs/testing.md` adds `` `llm/decide.py` (every model call: validation and its record; Phase 3c) `` after `plancheck.py`. `scripts/critical_modules.txt` adds `llm/decide.py` after `plancheck.py`.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_a_prompt_error_is_raised_before_anything_is_logged` |
| R2 | pass | `test_the_digest_is_read_for_every_decision`; `decide` builds the request, then takes `ids.new_id()`, then calls `model_info` |
| R3 | pass | `test_a_decision`, `test_thinking_needs_the_point_and_the_model`; `test_the_request_is_on_disk_when_chat_is_called`; probe `the logged body is what the model was sent` |
| R4 | pass | `test_a_reply_that_does_not_fit_raises` keeps `content` on the reply event; `test_a_script_error_leaves_only_the_request`; probe `every raw reply is logged as it came` |
| R5 | pass | `test_a_reply_that_does_not_fit_raises`; `test_any_done_reason_but_stop_is_cut_off_without_parsing`, `test_two_bad_fields_are_both_reported`; probe `a reply is accepted exactly when it stopped and parses strictly` |
| R6 | pass | `test_a_model_that_is_not_installed`, `test_a_model_that_fails_while_answering`; `test_a_timeout_is_logged_with_no_status` |
| R7 | pass | `test_a_decision`; `test_a_failing_reply_is_asked_once`; probe `each decision logs request, reply, and an error only on failure` |
| R8 | pass | `test_an_escalation_for_invalid_output`, `test_an_escalation_for_a_model_that_is_unavailable`, `test_the_closed_sets`; `test_every_unavailable_code_escalates_within_the_detail_limit`; probes `every escalation is a valid contract that round-trips`, `model failures escalate as model_unavailable` |
| R9 | pass | `test_no_reply_value_reaches_the_error`; probes `problems hold only codes and safe locations, never a value`, `no error event holds a reply value` |
| R10 | pass | searches 1, 2, and 3 empty |

The coder's tests cover each bullet of "Tests to write":

| Bullet | Test |
|---|---|
| The request event is on disk when `chat` is called | `test_the_request_is_on_disk_when_chat_is_called` |
| A `ScriptError` from an empty script passes through, and the log holds only the request | `test_a_script_error_leaves_only_the_request` |
| `"length"` with non-JSON, and `"load"`, give only `reply` `cut_off` | `test_any_done_reason_but_stop_is_cut_off_without_parsing` |
| Two bad fields are both reported, in field order | `test_two_bad_fields_are_both_reported` |
| `ModelUnavailable("timeout")` is logged with `status` `None` | `test_a_timeout_is_logged_with_no_status` |
| A failing reply is asked once | `test_a_failing_reply_is_asked_once` |
| Every unavailable code escalates within 500 characters and round-trips | `test_every_unavailable_code_escalates_within_the_detail_limit` |

Each asserts the event, the problems, the same error object, the call count, or the round-trip.

## Probe

`/tmp/probe_03c.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   every reply either decides or raises InvalidModelOutput
ok   a reply is accepted exactly when it stopped and parses strictly
ok   problems hold only codes and safe locations, never a value
ok   the log reads back whole
ok   each decision logs request, reply, and an error only on failure
ok   every raw reply is logged as it came
ok   the logged body is what the model was sent
ok   no error event holds a reply value
ok   every escalation is a valid contract that round-trips
ok   model failures escalate as model_unavailable
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. `decide.py` was then restored from the copy taken first. `git status --short` after the restore is the same set of paths.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_a_reply_that_does_not_fit_raises` for `not json`: the log was `model_request`, then `error` |
| 2 | `test_thinking_needs_the_point_and_the_model` for `(True, ("completion",))`: `assert True is False` |
| 3 | `test_a_reply_that_does_not_fit_raises` for `"length"`: `Failed: DID NOT RAISE InvalidModelOutput` |
| 4 | `test_two_bad_fields_are_both_reported` for `{"a": "1", "b": "2"}`: `Failed: DID NOT RAISE InvalidModelOutput` |
| 5 | `test_a_reply_that_does_not_fit_raises`: `ScriptError: no scripted reply left for demo_pick` |
| 6 | `test_a_model_that_is_not_installed`: `RunNotFound: no run aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` |
| 7 | `test_the_digest_is_read_for_every_decision`: both digests were `1` repeated |
| 8 | `test_an_escalation_for_a_model_that_is_unavailable`: the detail omitted `retry when Ollama answers` |

## Project rules and progress

`decide.py` imports the standard library, `pydantic.ValidationError`, `conductor.contracts`, `conductor.events`, `conductor.ids` through `from conductor import ids`, and `conductor.llm` modules. The only `.chat(` call under `src/conductor` is in `decide.py`. There is no loop, no sleep, no second `chat`, and no `except Exception`. Messages and `ERROR` payloads hold the decision id, the point name, codes, locations, and the HTTP status. There is no retry, repair, default, fallback model, new `EventKind`, success event, settings read, command, or graph. `points.py`, `prompts.py`, `model.py`, `ollama.py`, and `scripted.py` are unchanged, and the only contract edit is the one `EscalationKind` value.

`docs/progress.md` has `## Phase 3c: decide() (2026-11-08)` and `Tests: 282 -> 308 (given 19)`. Deviations: None. The public names it lists are the names this phase adds.
