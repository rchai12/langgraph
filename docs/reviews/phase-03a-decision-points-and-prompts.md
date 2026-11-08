# Review: Phase 3a

- Verdict: PASS
- Passed: 242
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

The `tests` step reported `242 passed` in 5.21s. No skipped, xfailed, or warnings summary. Sections tables, both with 0 failed:

```
Sections:
  core          221 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core          221 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/llm/prompts.py,*/conductor/llm/points.py" --fail-under=100`, run on the data that check left, exited 0. `TOTAL` is `100%` (90 statements, 22 branches: `prompts.py` 31 statements and 6 branches, `points.py` 59 statements and 16 branches).

`.venv/bin/python -m pytest tests/unit/test_prompts.py tests/unit/test_points.py --no-cov` reported `32 passed`.

`.venv/bin/python scripts/check_reports.py`, run before this review was written, printed `Reports OK.` and exited 0.

`git diff --stat HEAD -- tests src/conductor/contracts src/conductor/registry.py src/conductor/events.py` printed nothing.

Searches 1 and 2 printed nothing.

## Scope

`git status --short` lists `docs/progress.md`, `pyproject.toml`, `src/conductor/domains/demo.py`, `src/conductor/llm/points.py`, `src/conductor/llm/prompts.py`, `src/conductor/prompts/`, `tests/unit/test_points.py`, `tests/unit/test_points_more.py`, and `tests/unit/test_prompts.py`.

The two given test files match the spec's blocks. `demo_pick.v1.md` matches the spec's block, 249 bytes, ending in one newline. `src/conductor/prompts/` holds that file and no `__init__.py`. `git diff HEAD -- pyproject.toml` adds only:

```
[tool.setuptools.package-data]
conductor = ["prompts/*.md"]
```

`git diff HEAD -- src/conductor/domains/demo.py` adds the `Literal` and `DecisionPoint` imports, then `PickInputs`, `PickOutput`, `PICK`, and `pick_fields` after `DOMAIN`.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_a_template_name_needs_a_name_and_a_version`, `test_a_missing_template`, `test_a_template_that_is_not_utf8`, `test_a_template_with_a_stray_dollar`; `test_a_name_of_32_characters_loads_and_version_999_is_a_name`, `test_a_bad_name_is_refused_before_the_file` |
| R2 | pass | `test_the_demo_template_loads`, `test_fields_are_sorted_and_named_once`; probe `one more byte changes the hash` |
| R3 | pass | `test_a_bad_point_is_refused`, `test_inputs_of_another_class_are_refused`; `test_a_bad_name_is_named_before_bad_inputs`, `test_think_is_named_before_the_reply_cap`, `test_the_reply_cap_bounds_are_accepted` |
| R4 | pass | `test_fields_must_match_the_template` |
| R5 | pass | `test_the_demo_request_is_pinned`, `test_a_field_value_is_not_substituted_again`, `test_trailing_whitespace_leaves_one_blank_line`; probe `the schema in the system message is the format sent` |
| R6 | pass | `test_the_request_stays_data`; probes `no input ever reaches the system message`, `every user message is the input as JSON` |
| R7 | pass | `test_the_demo_request_is_pinned`; probe `the seed and context are the pinned values` |
| R8 | pass | `test_the_chat_body`; `test_changing_the_body_does_not_change_the_request`; probe `the body is plain JSON and round-trips` |
| R9 | pass | `test_the_demo_point`; `demo.py` matches the Design; `test_pick_fields_follows_the_domain` |
| R10 | pass | searches 1 and 2 empty; the two `pyproject.toml` lines; probe `building a request opens no connection` |

The coder's tests cover each bullet of "Tests to write":

| Bullet | Test |
|---|---|
| A 32-character name loads, 33 is refused; `x.v999` reaches `not found` | `test_a_name_of_32_characters_loads_and_version_999_is_a_name` |
| `Bad.v1` is refused by name when `Bad.v1.md` exists | `test_a_bad_name_is_refused_before_the_file` |
| A bad name is named before `inputs=dict`; `think=1` is named before a reply cap of 0 | `test_a_bad_name_is_named_before_bad_inputs`, `test_think_is_named_before_the_reply_cap` |
| Reply caps of 1 and 8192 are accepted | `test_the_reply_cap_bounds_are_accepted` |
| A field value ending in `"\n\n  "` leaves one blank line before `SCHEMA_INTRO` | `test_trailing_whitespace_leaves_one_blank_line` |
| Changing `body()["options"]["seed"]` leaves the request and the next body unchanged | `test_changing_the_body_does_not_change_the_request` |
| `pick_fields()["actions"]` has one line per demo action, built from `DOMAIN` | `test_pick_fields_follows_the_domain` |

Each asserts the message, the parsed request, or the lines built from `DOMAIN`.

## Probe

`/tmp/probe_03a.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   the prompts folder holds only demo_pick.v1.md
ok   no input ever reaches the system message
ok   every user message is the input as JSON
ok   building twice gives the same request and body
ok   the body is plain JSON and round-trips
ok   the schema in the system message is the format sent
ok   one more byte changes the hash
ok   building a request opens no connection
ok   the seed and context are the pinned values
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The files were then restored from the copies taken first. `git status --short` after the restore is the same set of paths.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_the_demo_request_is_pinned`: user was `'{"request":...hello"}'` |
| 2 | `test_the_demo_request_is_pinned`: the schema in `system` was one line |
| 3 | `test_a_field_value_is_not_substituted_again`: `$5\n\nAnswer` was absent from `system` |
| 4 | `test_inputs_of_another_class_are_refused` for `LongerInputs`: `Failed: DID NOT RAISE PromptError` |
| 5 | `test_a_bad_point_is_refused` for `max_reply_tokens=True`: `Failed: DID NOT RAISE PromptError` |
| 6 | `test_fields_are_sorted_and_named_once`: `assert ('b', 'a') == ('a', 'b')` |
| 7 | `test_a_template_name_needs_a_name_and_a_version` for `demo_pick.v1.md`: `not found` |
| 8 | `test_changing_the_body_does_not_change_the_request`: `assert 1 == 7` |

## Project rules and progress

`prompts.py` and `points.py` import only the standard library, `conductor.contracts`, and `conductor.llm.prompts`. The only instruction sentence in `points.py` is `SCHEMA_INTRO`. Every `PromptError` message is one of the spec's, with the point or template name filled in. The new files open no socket and do not import `urllib`, `http`, or `ollama`. There is no `decide`, `ScriptedModel`, event logging, digest, capability lookup, routing or planner point, or setting for the seed, the context, or a per-point model. `conductor.contracts`, `conductor.registry`, and `conductor.events` are unchanged.

`docs/progress.md` has `## Phase 3a: decision points and prompts (2026-10-27)` and `Tests: 202 -> 242 (given 32)`. Deviations: None. The public names it lists are the names this phase adds.
