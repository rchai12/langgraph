# Review: Phase 1

- Verdict: PASS
- Passed: 70
- Findings: 0
- Approved deviations: An invalid event raises ValueError("event is not valid"); the spec requires ValueError and does not pin this text.
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

The `tests` step reported `70 passed` in 5.29s. No skipped, xfailed, or warnings summary. Sections tables, both with 0 failed:

```
Sections:
  cli            21 passed    0 failed    0 skipped
  core           49 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            21 passed    0 failed    0 skipped
  core           49 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/events.py,*/conductor/config.py,*/conductor/llm/tags.py,*/conductor/diagnostics.py" --fail-under=100` exited 0. `TOTAL` is `100%` (258 statements, 56 branches).

`.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_events.py tests/e2e/test_cli_doctor.py tests/e2e/test_cli_runs.py --no-cov` reported `65 passed`.

`.venv/bin/python -m pip list` contains the project, pip from the virtual environment, and the packages named in `pyproject.toml` with their dependencies. No `langgraph`, `langchain`, `langsmith`, `ollama`, `mcp`, `fastapi`, `httpx`, `requests`, or `opentelemetry`.

Searches 4, 5, and 6 printed nothing.

## Scope

Phase 1 is commit `7f64209`. That commit contains only the spec's Scope paths. Each given file matches its block in the spec: `pyproject.toml`, `scripts/check.py`, `scripts/critical_modules.txt`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, and the four given test files. Under `src/conductor/` the modules are `__init__.py`, `clock.py`, `config.py`, `ids.py`, `events.py`, `diagnostics.py`, `llm/__init__.py`, `llm/tags.py`, `cli/__init__.py`, and `cli/main.py`.

`git status --short` at review time also lists later documents outside this phase: modifications to `.claude/skills/phase-architect/SKILL.md` and `docs/roadmap.md`, plus untracked `docs/phases/phase-02a-contracts.md` and `docs/verification/phase-02a-contracts.md`. `.venv/` does not appear. Those paths are not part of the Phase 1 commit and were not treated as Phase 1 code.

## Requirements

| Id | Result | Evidence |
|---|---|---|
| R1 | pass | `test_the_defaults`; `get_settings` builds a new `Settings` each call, `model_config` sets only `env_prefix`, and pydantic-settings' default `env_file` is `None` |
| R2 | pass | `test_a_relative_data_folder_is_made_absolute_without_resolving_links` |
| R3 | pass | `test_a_host_on_this_machine_is_kept_without_a_trailing_slash`, `test_a_host_elsewhere_is_refused`; probe `hosts on this machine only` |
| R4, R5 | pass | `test_every_problem_is_named_in_field_order`; the raised type is `SettingsError` |
| R6 | pass | search 4 empty; `clock.now` is `datetime.now(UTC)`; `ids.new_id` is `uuid.uuid4().hex`; probe `new ids are run ids and differ`, `the real clock round-trips` |
| R7 | pass | `test_a_run_id_that_is_not_32_lowercase_hex_is_refused`, `test_a_good_run_id_is_returned_as_it_is`; `append` and `read` call `check_run_id` before a path is built |
| R8 | pass | `test_each_event_is_one_line_with_sorted_keys`, `test_only_the_owner_can_read_the_folder_and_files`, `test_each_append_is_synced_to_disk`; probe `an existing folder keeps its mode; files are 0600` |
| R9 | pass | `test_a_payload_that_is_not_json_writes_nothing`, `test_a_time_that_is_not_utc_is_refused` |
| R10 | pass | `test_a_new_log_on_the_same_folder_continues_the_count`; probe `another process continues the count` |
| R11 | pass | `test_a_damaged_log_is_refused_with_its_line`, `test_reading_a_run_that_does_not_exist`; probes `line separators stay inside one line`, `strict lines are refused`, `a large payload round-trips` |
| R12 | pass | `test_runs_newest_first_then_by_id`, `test_runs_of_a_folder_not_made_yet` |
| R13 | pass | `test_something_else_answering`, `test_a_proxy_in_the_environment_is_not_used`; probe `a silent server times out`; search 5 empty |
| R14 | pass | `diagnostics.py` calls `python_version()` and `tags.fetch_model_names` (`from conductor.llm import tags`) |
| R15, R16 | pass | every test in `test_cli_doctor.py` |
| R17 | pass | `test_everything_ready`, `test_ollama_not_running`; probe `the installed command runs doctor` |
| R18, R19 | pass | `test_cli_runs.py`; probe `the installed command shows a run` |
| R20 | pass | `test_show_refuses`, `test_a_damaged_log_stops_both_commands`, `test_settings_that_point_elsewhere`, `test_settings_that_point_elsewhere_stop_before_any_check` |

The coder's five tests assert the behaviour they cover: folder mode `0o755` kept and the file at `0o600`, a last line without a newline read back field by field, two different 32-character ids, `OllamaUnreachable("not reachable")` from a silent `127.0.0.1` listener, and `python_version()` equal to `sys.version_info[:3]`. They replace `conductor.clock.now` where they append, and they do not call a real Ollama.

## Probe

`/tmp/probe_01.py`, run from the repository root, then deleted. Every line ended in `ok`. Last line: `FAILURES 0`.

```
ok   line separators stay inside one line
ok   a large payload round-trips
ok   another process continues the count
ok   an existing folder keeps its mode; files are 0600
ok   new ids are run ids and differ
ok   the real clock round-trips
ok   strict lines are refused
ok   hosts on this machine only
ok   a silent server times out
ok   the installed command runs doctor
ok   the installed command shows a run
FAILURES 0
```

## Spot checks

Each broken change made the deciding test fail. The file was then restored from the copy taken first. `git diff` for `events.py`, `config.py`, `tags.py`, and `diagnostics.py` was empty afterwards.

| # | Deciding test failed as required |
|---|---|
| 1 | `test_a_payload_that_is_not_json_writes_nothing` nan and inf: `Failed: DID NOT RAISE ValueError` |
| 2 | `test_a_damaged_log_is_refused_with_its_line` for `"seq":"2"`: `Failed: DID NOT RAISE EventLogCorrupt` |
| 3 | probe `line separators stay inside one line`: `EventLogCorrupt` on line 1 |
| 4 | `test_a_host_elsewhere_is_refused` for `http://127.0.0.1@example.com:11434`: `Failed: DID NOT RAISE SettingsError` |
| 5 | `test_a_proxy_in_the_environment_is_not_used`: stdout began `FAIL  ollama` |
| 6 | `test_each_append_is_synced_to_disk`: `assert 0 == 2` |
| 7 | `test_the_model_must_be_pulled` for `qwen3-coder` with `qwen3-coder:latest`: `FAIL  model qwen3-coder` |
| 8 | `test_runs_newest_first_then_by_id`: equal times came out with `RUN_A` before `RUN_C` |
| 9 | `test_a_new_log_on_the_same_folder_continues_the_count`: `assert 1 == 3` |
| 10 | `test_only_the_owner_can_read_the_folder_and_files`: mode `0o644` |

## Project rules and progress

Raises in `events.py` and `tags.py`, and `typer.echo(..., err=True)` in `cli/main.py`, use constant text plus a run id, a line number, a seq, or a field name. `README.md` puts its commands in `zsh` blocks and describes a local Ollama model. There is no `env_file`, no `.env`, no `src/conductor/__main__.py`, no logging configuration, no log rotation, and no writer lock. The commands are `doctor`, `runs list`, and `runs show`, with `--payload` on `show`.

`docs/progress.md` has `## Phase 1: skeleton (2026-10-25)`, `Tests: 0 -> 70 (given 65)`, and the deviation above. That deviation is real: invalid payloads and non-UTC times raise `ValueError("event is not valid")`. It is justified because the spec does not pin the text, and a bare `ValidationError` would include the rejected value in its message.
