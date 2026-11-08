# Review: Phase 3b

- Verdict: PASS
- Passed: 282
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gate output

`.venv/bin/python scripts/check.py --first core,cli` exited 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core,cli): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The `tests` step reported `282 passed` in 14.70s. No skipped, xfailed, or warnings summary. Sections tables, both with 0 failed:

```
Sections:
  cli            21 passed    0 failed    0 skipped
  core          261 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          261 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/llm/model.py,*/conductor/llm/ollama.py,*/conductor/llm/scripted.py" --fail-under=100`, run on the data that check left, exited 0. `TOTAL` is `100%` (179 statements, 54 branches: `model.py` 29 statements and 2 branches, `ollama.py` 113 statements and 42 branches, `scripted.py` 37 statements and 10 branches).

`.venv/bin/python -m pytest tests/unit/test_ollama.py tests/unit/test_scripted.py tests/unit/test_config_timeout.py --no-cov` reported `32 passed`.

`.venv/bin/python scripts/check_reports.py`, run before this review was written, printed `Reports OK.` and exited 0.

`git diff --stat HEAD -- src/conductor/llm/tags.py src/conductor/llm/points.py src/conductor/llm/prompts.py src/conductor/contracts tests/unit tests/e2e tests/conftest.py` printed nothing.

Searches 1 and 2 printed nothing.

## Scope

`git status --short` lists `docs/progress.md`, `src/conductor/config.py`, `tests/support.py`, `src/conductor/llm/model.py`, `src/conductor/llm/ollama.py`, `src/conductor/llm/scripted.py`, `tests/unit/test_config_timeout.py`, `tests/unit/test_ollama.py`, `tests/unit/test_ollama_more.py`, and `tests/unit/test_scripted.py`.

`tests/support.py` and the three given test files match the spec's blocks. `git diff HEAD -- src/conductor/config.py` adds `import re`, `TIMEOUT_MESSAGE`, the `model_timeout` field, the `model_timeout_seconds` property, and the one pattern check after the model check.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_tags_with_an_http_error`, `test_a_model_that_is_not_installed`; `model.py` has the Design fields and defaults |
| R2 | pass | `test_the_chat_request`; `test_the_post_body_keeps_non_ascii_text`; probe `model_info asks the given host every time, whatever OLLAMA_HOST says` |
| R3 | pass | `test_a_chat_http_error`, `test_nothing_listening`, `test_a_silent_server_times_out`; `test_a_tags_404_is_an_http_error`, `test_opener_errors_keep_their_codes`; probe `HTTP errors carry only the code and status` |
| R4 | pass | `test_the_model_info_is_read_from_the_tags`, `test_a_model_that_is_not_installed`, `test_tags_that_do_not_fit`; `test_a_tagged_name_does_not_match_latest_and_bad_tags_are_refused`; probe `an untagged name finds :latest, a tagged one itself` |
| R5 | pass | `test_a_chat_answer_becomes_a_reply`, `test_a_short_chat_answer_gets_defaults`, `test_a_chat_answer_that_does_not_fit`; `test_counts_thinking_and_the_done_reason`; probe `any reply text comes back as it was sent` |
| R6 | pass | `test_tags_that_do_not_fit` for `not json`; `test_a_body_that_is_not_utf8`; probe `every cut of a good answer is bad_answer` |
| R7 | pass | `test_replies_come_in_order`, `test_a_reply_for_another_point`, `test_no_reply_left`, `test_a_scripted_failure_is_raised_in_its_turn`; probe `a long script plays in order and then runs out` |
| R8 | pass | `test_the_model_info`; `test_the_script_keeps_its_own_copy_and_uses_up_a_wrong_point` |
| R9 | pass | `test_config_timeout.py`; probe `exactly 1 to 3600 are accepted` |
| R10 | pass | searches 1 and 2 empty |

The coder's tests cover each bullet of "Tests to write":

| Bullet | Test |
|---|---|
| A 404 from `/api/tags` is `http_error 404` | `test_a_tags_404_is_an_http_error` |
| A connect timeout, a reset, and an `IncompleteRead` keep their codes | `test_opener_errors_keep_their_codes` |
| `plain:7b` against `plain:latest` is `not_installed`; `{"models": "x"}` and a name of `3` are `bad_answer` | `test_a_tagged_name_does_not_match_latest_and_bad_tags_are_refused` |
| `eval_count` of `true` and `-1` are `bad_answer`; `thinking: null` is `""`; a `done_reason` of `7` is `bad_answer` | `test_counts_thinking_and_the_done_reason` |
| A body of `b"\xff"` is `bad_answer` | `test_a_body_that_is_not_utf8` |
| A post containing `"Résumé"` keeps those UTF-8 bytes | `test_the_post_body_keeps_non_ascii_text` |
| The script keeps its own copy, and a wrong point uses up the reply | `test_the_script_keeps_its_own_copy_and_uses_up_a_wrong_point` |

Each asserts the code, the message, the bytes, or `remaining`. `test_answers_outside_the_documented_shape` asserts `bad_answer` for a JSON array, a non-object tag entry, a non-string capability, and a non-string `thinking`.

## Probe

`/tmp/probe_03b.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   any reply text comes back as it was sent
ok   every cut of a good answer is bad_answer
ok   HTTP errors carry only the code and status
ok   an untagged name finds :latest, a tagged one itself
ok   model_info asks the given host every time, whatever OLLAMA_HOST says
ok   a long script plays in order and then runs out
ok   exactly 1 to 3600 are accepted
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The files were then restored from the copies taken first. `git status --short` after the restore is the same set of paths.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_a_silent_server_times_out`: `('unreachable', 'model unavailable: unreachable')` |
| 2 | `test_the_chat_request`: `model unavailable: unreachable` |
| 3 | `test_the_model_info_is_read_from_the_tags` for `"plain"`: `model unavailable: not_installed` |
| 4 | `test_the_model_info_is_read_from_the_tags`: capabilities ended `thinking`, `completion` |
| 5 | `test_the_model_info_is_read_from_the_tags`: `assert ['/api/tags'] == ['/api/tags', '/api/tags']` |
| 6 | `test_a_tags_404_is_an_http_error`: `not_installed` |
| 7 | `test_a_reply_for_another_point`: `Failed: DID NOT RAISE ScriptError` |
| 8 | `test_a_timeout_out_of_range_or_not_whole` for `" 30 "`: `Failed: DID NOT RAISE SettingsError` |
| 9 | `test_the_post_body_keeps_non_ascii_text`: the UTF-8 bytes of `Résumé` were absent |
| 10 | `test_counts_thinking_and_the_done_reason` for `eval_count: true`: `Failed: DID NOT RAISE ModelUnavailable` |

## Project rules and progress

`ollama.py` sets one header, `Content-Type: application/json`, and only on the POST. Every `ModelUnavailable` and `ScriptError` message is one of the spec's. `ollama.py` has no retry and no sleep. The new modules do not call `decide`, choose `think` from capabilities, check `done_reason` beyond requiring a string, validate reply content, log events, escalate, cache tags, stream, send `keep_alive`, or call `/api/show` or `/api/ps`. `tags.py`, `points.py`, `prompts.py`, and `conductor.contracts` are unchanged.

`docs/progress.md` has `## Phase 3b: the Ollama client and the scripted model (2026-11-08)` and `Tests: 242 -> 282 (given 32)`. Deviations: None. The public names it lists are the names this phase adds.
