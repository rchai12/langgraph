# Phase 9o: Immutable validated settings

## Goal

`conductor.config.get_settings` validates the environment, then assigns two normalised values (`data_dir` made absolute, `ollama_host` without a trailing slash) onto a mutable `Settings`. Any later caller could change a setting the checks already accepted. Two more problems:
- Every pydantic `ValidationError` is reported as `CONDUCTOR_MCP: must map server names to command lines`. That is right only while `mcp` is the one field that can fail inside the model.
- A `CONDUCTOR_MCP` value that is not JSON at all raises pydantic-settings' own `SettingsError`, which nothing catches. `conductor doctor` prints a traceback.

This phase does three things:
- freezes `Settings`, normalising first;
- makes the server mapping read-only;
- reports every construction failure against the field that failed, with constant text.

Accepted values, properties, refusal messages and their order stay exactly as today.

Decided with the owner (2026-11-21):
- **Freezing.** `Settings` is frozen. `get_settings` keeps today's checks and messages on the value it reads, then returns a normalised copy made with `model_copy(update=...)`. The checks do not move into pydantic validators.
- **Server mapping.** `settings.mcp` is a read-only mapping: setting or deleting a key raises `TypeError`. It still compares equal to a dict.
- **Text that is not JSON.** A `CONDUCTOR_MCP` that pydantic-settings cannot decode is refused as `CONDUCTOR_MCP: must map server names to command lines`, like any other settings problem.
- **Critical.** `config.py` joins the critical modules: every line and branch is covered, and it is listed in `scripts/critical_modules.txt` and `docs/testing.md`. The architect has added the `docs/testing.md` line; the coder adds the `critical_modules.txt` line.

Decided by the architect, within those answers:
- Each field has one constant message in `FIELD_MESSAGES`, in field order. The eight existing messages keep their text. `data_dir` gets `DATA_DIR_MESSAGE = "must be a folder path"`.
- `validation_problems(error)` turns a `ValidationError` into `CONDUCTOR_<FIELD>: <message>` lines. It reads only each error's location, never its input or text. It gives one line per failing field, in field order, so a nested `mcp.bank` error is reported once as `CONDUCTOR_MCP`. A location that is not a field gives `CONDUCTOR_<NAME>: is not a setting` (`NOT_A_SETTING_MESSAGE`).
- The undecodable case is mapped to `CONDUCTOR_MCP` because `mcp` is the only field pydantic-settings decodes as JSON. A given test pins that every other field is `str` or `Path`, so a new complex field must revisit this.
- A construction failure reports only its own problems, as today. The field checks run only on a constructed value.
- pydantic-settings' JSON decoding stays on. The spike showed that `NoDecode` drops today's merge of `CONDUCTOR_MCP` with `CONDUCTOR_MCP__<NAME>` and refuses `null`.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/config.py` (all of it).
- `tests/unit/test_config.py`, `test_config_timeout.py`, `test_mcp_declarations.py` and `test_mcp_declarations_more.py`: they pin today's values and messages and must keep passing unchanged.
- `src/conductor/cli/common.py` `load_settings`: how a `SettingsError` reaches the terminal.

## Starting state

Phase 9n is built and verified, and everything is committed: N is `1480`. **Sections: core and cli.** `config.py` is 119 lines and not yet critical. Nothing outside `get_settings` assigns to a settings object, and no test constructs `Settings` directly. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/config.py` | frozen `Settings`, read-only `mcp`, `FIELD_MESSAGES`, `DATA_DIR_MESSAGE`, `NOT_A_SETTING_MESSAGE`, `validation_problems`, and `get_settings` normalising by copy and mapping both construction failures |
| `scripts/critical_modules.txt` | one new line: `config.py` |
| `tests/unit/test_config_loading.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Any change to a default, an accepted value, a property, a refusal message, or the order and `; ` joining of problems.
- New settings, a `.env` file, a settings cache or singleton, or `lru_cache` on `get_settings`.
- Moving today's checks into pydantic validators, or turning the string fields into `int` or `bool` fields.
- Changes outside `config.py`: callers keep reading the same attributes and properties.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: a frozen `Settings`

- `model_config` adds `frozen=True`. Assigning any field raises `ValidationError` with type `frozen_instance`.
- `mcp` is typed `Mapping[str, str]` and holds a `types.MappingProxyType`, both by default and when read from the environment. A field validator, with the default validated, is enough. The spike checked that a `MappingProxyType` default cannot be deep-copied, so the default must be built, not shared.
- The fields, their order, their defaults and the properties are otherwise unchanged.

### Part 2: `get_settings`

1. Construct `Settings()` in a `try`.
   - On a pydantic `ValidationError`, raise `SettingsError("; ".join(validation_problems(error)))`.
   - On pydantic-settings' `SettingsError` (imported from `pydantic_settings`, under another name), raise `SettingsError(f"CONDUCTOR_MCP: {MCP_MAPPING_MESSAGE}")`.
   - Both use `from None`.
2. Run today's checks, in today's order and with today's messages, on the constructed value. The host check uses the host as read.
3. If there are problems, raise them joined with `; ` as today.
4. Otherwise return `settings.model_copy(update={"data_dir": settings.data_dir.absolute(), "ollama_host": settings.ollama_host.rstrip("/")})`.

### Part 3: `validation_problems`

```python
FIELD_MESSAGES: dict[str, str]  # field name -> message, in Settings.model_fields order

def validation_problems(error: ValidationError) -> list[str]:
```

For each error in `error.errors()`, take `loc[0]`. Report each name once, as `CONDUCTOR_<NAME upper>: <FIELD_MESSAGES[name]>`, in field order. A name that is not a field goes last, as `CONDUCTOR_<NAME upper>: is not a setting`. The function never reads `input`, `msg` or `ctx`.

## Facts

Checked on 2026-11-21 with pydantic 2.14.1 and pydantic-settings 2.16.1, in synthetic models outside the repository:
- From the environment, only `mcp` can fail validation today. Every other field is `str` or `Path`, and any text is valid for them. `{"ledger": 1}` fails at `('mcp', 'ledger')`, `[1]` at `('mcp',)`, and `CONDUCTOR_MCP__LEDGER__BIN=x` at `('mcp', 'ledger')`.
- `CONDUCTOR_MCP=notjson` raises `pydantic_settings.exceptions.SettingsError` (a `ValueError`, not a `ValidationError`) whose text names the field. Today `conductor doctor` crashes with it.
- `CONDUCTOR_MCP={"a": "b"}` together with `CONDUCTOR_MCP__LEDGER=x` merges to both keys, and `CONDUCTOR_MCP=null` gives `{}`. With `NoDecode` the merge loses `ledger` and `null` is refused.
- With `frozen=True`, assignment raises `ValidationError` (`frozen_instance`). `model_copy(update=...)` returns a frozen copy with the new values and keeps the read-only mapping. `hash()` of such a settings object raises `TypeError` (the mapping is unhashable); nothing in `src` hashes settings.
- Keyword construction gives one error per field: `Settings(model=1)` is `string_type` at `('model',)`, `Settings(data_dir=1)` is `path_type`, `Settings(mcp=1)` is `dict_type`, and `Settings(nope=1)` is `extra_forbidden` at `('nope',)`.
- `MappingProxyType({"a": "1"}) == {"a": "1"}` is true, so the existing `settings.mcp == {...}` assertions hold.
- The probe loads the predecessor's `config.py` from commit 1725edc with `git show` and plays 1500 environments. Each is a valid base with one change. It compares the old and new outcomes. On today's code, the comparison of accepted and refused environments printed `ok`. The 36 crashed environments and the frozen check printed `FAIL`. With the trailing-slash strip removed in a scratch copy, the comparison printed `FAIL`.

## Requirements

### Part 1: frozen settings

- **R1.** A `Settings` returned by `get_settings` refuses assignment to every field with a `frozen_instance` validation error, and the value stays as it was.
- **R2.** `settings.mcp` refuses setting and deleting keys with `TypeError`, by default and when read from the environment. It reads `CONDUCTOR_MCP` and `CONDUCTOR_MCP__<NAME>` as today, merge and `null` included.
- **R3.** `get_settings` returns `data_dir` absolute (links not resolved) and `ollama_host` without trailing slashes, and the returned value is frozen.

### Part 2: errors name their field

- **R4.** `FIELD_MESSAGES` maps every field, in field order, to its constant message; `DATA_DIR_MESSAGE` and `NOT_A_SETTING_MESSAGE` are as given.
- **R5.** `validation_problems` names each failing field once, in field order, with its message, and a name that is not a field as `is not a setting`. It reads only error locations.
- **R6.** A `CONDUCTOR_MCP` that cannot be decoded, or whose value has the wrong shape, is refused with exactly `CONDUCTOR_MCP: must map server names to command lines`. The error is `conductor.config.SettingsError`, has no cause, and suppresses its context.
- **R7.** `conductor doctor` with such a value prints `Error: CONDUCTOR_MCP: must map server names to command lines` on standard error, nothing on standard output, and exits 1 without a traceback.

### Part 3: the same settings

- **R8.** For every environment the old code accepted or refused, the values, properties, commands and messages are as before. `mcp` is still the only field decoded from JSON.

### Part 4: the rules

- **R9.** Only the Scope's paths change. Given files and existing tests stay byte-identical. There is no `noqa` or `pragma: no cover` in `config.py`. `config.py` is listed in `scripts/critical_modules.txt` and 100% covered (lines and branches).

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, 28 of the given tests fail and 7 pass, and names-only stubs give the same counts. The 7 are regression guards on today's behaviour:
- the two mapping reads (merge and `null`);
- the three wrong-shape refusals;
- the JSON-field rule;
- the doctor's wrong-shape case.

| File | What it is |
|---|---|
| `tests/unit/test_config_frozen.py` | R1 to R6 and R8: assignment refused (9 cases), the read-only mapping (2), today's mapping reads (2), normalising before the freeze, undecodable (3) and wrong-shape (3) mappings, one message per field (9), field order and once each, a name that is not a setting, the message table, and the JSON-field rule (33 tests from 11 functions) |
| `tests/e2e/test_cli_settings.py` | R7: `conductor doctor` with an undecodable and a wrong-shape mapping (2 tests from 1 function) |
| `docs/verification/probe-09o.py` | the probe, run by its path in Acceptance |

Given test count: **35**.

## Tests to write

In `tests/unit/test_config_loading.py` (section `core`):
- R6: `CONDUCTOR_MCP=notjson` together with `CONDUCTOR_MODEL="   "` is refused with only the `CONDUCTOR_MCP` message (a construction failure reports only its own problems).
- R3: a host elsewhere with a trailing slash (`CONDUCTOR_OLLAMA_HOST=http://10.0.0.5:11434/`) is refused with today's host message alone; the strip never makes it acceptable.
- R5: `validation_problems` for `Settings(mcp={"bank": 1}, nope=2)` gives the `CONDUCTOR_MCP` line, then `CONDUCTOR_NOPE: is not a setting`.
- R9: any branch of `config.py` that the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- The model host stays on loopback: the host check runs before the copy and on the value as read.
- Error messages stay constant text plus identifiers (a variable name). Nothing echoes an environment value; never use `str()` of a `ValidationError` or of pydantic-settings' error.
- All configuration still comes from `get_settings()`.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9o` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1515 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/config.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_config_frozen.py tests/e2e/test_cli_settings.py --no-cov -q` | `35 passed` |
| `.venv/bin/python docs/verification/probe-09o.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_config_frozen.py tests/e2e/test_cli_settings.py docs/verification/probe-09o.py src/conductor/cli src/conductor/web src/conductor/diagnostics.py pyproject.toml` | no output |
| `git diff 1725edc --stat -- tests ':!tests/unit/test_config_frozen.py' ':!tests/e2e/test_cli_settings.py' ':!tests/unit/test_config_loading.py'` | no output |
| `grep -c '^config.py$' scripts/critical_modules.txt` | `1` |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9o: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9o` (after writing progress) | `Reports OK.` |

The second diff row compares against 1725edc (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Immutable validated settings`, with `--tests-before 1480 --given 35`.
