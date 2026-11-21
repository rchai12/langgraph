# Verify Phase 9o: Immutable validated settings

Spec: `docs/phases/phase-09o-immutable-validated-settings.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09o-immutable-validated-settings.md`.

## First: establish that the coder ran

- No `## Phase 9o: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09o-immutable-validated-settings.md docs/verification/phase-09o-immutable-validated-settings.md tests/unit/test_config_frozen.py tests/e2e/test_cli_settings.py docs/verification/probe-09o.py` must succeed. The gates judge against a committed baseline.

The coder:
- froze `Settings` and made `settings.mcp` a read-only mapping;
- made `get_settings` return a normalised copy and map both construction failures (pydantic's `ValidationError` and pydantic-settings' decoding error) to constant per-field messages;
- added `FIELD_MESSAGES`, `DATA_DIR_MESSAGE`, `NOT_A_SETTING_MESSAGE` and `validation_problems`;
- added `config.py` to `scripts/critical_modules.txt` and wrote `tests/unit/test_config_loading.py`.

## 1. Gates

N is `1480`. Given count: 35. `.venv/bin/python scripts/accept.py --phase 9o --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1515 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/config.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_config_frozen.py tests/e2e/test_cli_settings.py --no-cov -q` | `35 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09o.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_config_frozen.py tests/e2e/test_cli_settings.py docs/verification/probe-09o.py src/conductor/cli src/conductor/web src/conductor/diagnostics.py pyproject.toml` | no output |
| G6 | `git diff 1725edc --stat -- tests ':!tests/unit/test_config_frozen.py' ':!tests/e2e/test_cli_settings.py' ':!tests/unit/test_config_loading.py'` | no output |
| G7 | `grep -c '^config.py$' scripts/critical_modules.txt` | `1` |
| G8 | `git status --short --untracked-files=all` | only the Scope paths |
| G9 | `grep -c '^## Phase 9o: ' docs/progress.md` | `1` |
| G10 | `.venv/bin/python scripts/check_reports.py --phase 9o` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_loaded_setting_cannot_be_reassigned` (9 cases); probe check 1; search 8 | pass; `ok`; silent |
| R2 | `test_the_server_mapping_is_read_only` (2 cases), `test_the_server_mapping_is_read_as_today` (2 cases); probe check 1 | pass; `ok` |
| R3 | `test_settings_are_normalised_before_they_are_frozen`; `tests/unit/test_config.py` (in G1); the coder's trailing-slash host test | pass |
| R4 | `test_every_setting_has_its_message` | pass |
| R5 | `test_a_validation_error_names_the_field_that_failed` (9 cases), `test_problems_follow_field_order_once_each`, `test_a_name_that_is_not_a_setting_is_reported_as_such`; search 9; the coder's mixed `validation_problems` test | pass; silent; pass |
| R6 | `test_mcp_text_that_is_not_json_names_the_mcp_setting` (3 cases), `test_an_mcp_value_of_the_wrong_shape_names_the_mcp_setting` (3 cases); probe check 3; the coder's undecodable-plus-model test | pass; `ok`; pass |
| R7 | `test_doctor_reports_a_bad_server_mapping_without_a_traceback` (2 cases) | pass |
| R8 | probe check 2; `test_only_the_server_mapping_is_decoded_from_json`; the existing config and MCP tests (in G1) | `ok`; pass; pass |
| R9 | G2, G5 to G8; search 7 | as given; silent |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

Read `get_settings` against the spec's Part 2: the host check on the value as read, the copy made only after every check passed, and both `except` branches raising with `from None`. Read `validation_problems` against Part 3: it touches only `loc`.

## 3. Probe

The probe is the given file `docs/verification/probe-09o.py` (G4). Its oracle is the predecessor's `config.py`, read from commit 1725edc with `git show` and loaded as its own module. It plays 1500 environments, each a valid base (all nine settings plus one server) with one change drawn from a table: a host, a timeout, a port, a name, `demo`, a data folder, a `CONDUCTOR_MCP` text or a `CONDUCTOR_MCP__<NAME>`. It records whether the old code accepted the environment (every field, property and server command), refused it (the message) or crashed (pydantic-settings' decoding error). It requires at least 400 accepted, 400 refused and 30 crashed. It checks:
- every accepted environment's settings refuse assignment to each field (`frozen_instance`) and a new server key (`TypeError`);
- every accepted or refused environment gives the same outcome on the new code;
- every crashed environment is refused on the new code with `CONDUCTOR_MCP: must map server names to command lines`.

Before handover the architect ran it on today's code. Reach was 749 accepted, 715 refused and 36 crashed. Checks 1 and 3 printed `FAIL` and check 2 printed `ok`. When the trailing-slash strip was removed in a scratch copy, check 2 printed `FAIL`. So a check-2 failure on the build points at a changed value, property or message.

A stop at its own `assert` lines, or a `git show` failure, is the probe's fault (or a missing commit). Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/config.py
git grep --untracked -n -E 'settings\.[a-z_]+ = |object\.__setattr__|__dict__\[' -- src
git grep --untracked -n -E '"input"|"msg"|"ctx"|str\(error\)|NoDecode|enable_decoding' -- src/conductor/config.py
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09o`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match). Then run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09o`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a test that cannot see the change (say which in "For the architect").

Each change below is the shape of an edit; copy the exact old text from the coder's line.

| # | Change (module) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | in `model_config`, replace `frozen=True` with `frozen=False` (`config.py`) | `tests/unit/test_config_frozen.py::test_a_loaded_setting_cannot_be_reassigned[model]` | raises `frozen_instance` | assignment kept, `model` is `other:1b` |
| S2 | in the `mcp` validator, replace the returned `MappingProxyType(...)` with its argument wrapped in `dict(...)` (`config.py`) | `tests/unit/test_config_frozen.py::test_the_server_mapping_is_read_only[one server]` | `TypeError` | `bank` added |
| S3 | in `get_settings`, delete `from None` from the `raise` in the pydantic-settings branch (`config.py`) | `tests/unit/test_config_frozen.py::test_mcp_text_that_is_not_json_names_the_mcp_setting[word]` | `(None, True)` | `(None, False)` |
| S4 | in `validation_problems`, replace the once-per-field collection with appending a line for every error (`config.py`) | `tests/unit/test_config_frozen.py::test_problems_follow_field_order_once_each` | `CONDUCTOR_MCP` once | `CONDUCTOR_MCP` twice |
| S5 | in `get_settings`, replace `settings.data_dir.absolute()` in the copy's update with `settings.data_dir` (`config.py`) | `tests/unit/test_config_frozen.py::test_settings_are_normalised_before_they_are_frozen` | `<tmp>/agent/../data` | `agent/../data` |

Notes for tracing:
- S1: `setattr` succeeds, so `pytest.raises` fails first; the value then differs too.
- S2: with a plain dict the item assignment succeeds and `pytest.raises(TypeError)` fails first.
- S3: without `from None`, Python keeps the decoding error as the context and `__suppress_context__` is false; the message still matches.
- S4: `mcp={"bank": 1, "ledger": 2}` gives two errors at `('mcp', 'bank')` and `('mcp', 'ledger')`. If the coder keeps fields once with a dict or set, write the change as appending to a list instead.
- S5: the relative path is kept because the test's working folder is `tmp_path` and `Path("agent/../data")` compares unequal to the absolute one.

Spot rows that make the same change in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- The read-only wrap written as a `field_validator` with `validate_default=True`, or as a `default_factory` plus a validator. Either is fine as long as the default is read-only too.
- `validation_problems` building its order from `Settings.model_fields` or from `FIELD_MESSAGES`.
- pydantic-settings' error imported as `from pydantic_settings import SettingsError as DecodeError` or a similar name, or reached as `pydantic_settings.SettingsError`.
- Private helpers in `config.py` for the field checks, as long as the order and messages are as today.
- Extra behaviour tests in `tests/unit/test_config_loading.py`.

## 7. Out of scope

Each must be absent:
- A changed default, accepted value, property, refusal message, problem order or `; ` joining.
- New settings, a `.env` file, caching of `get_settings`, or typed `int`/`bool` fields.
- Today's checks moved into pydantic validators.
- Any change outside `config.py` and the Scope paths.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09o-immutable-validated-settings.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9o`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9o` must print `Reports OK.`
