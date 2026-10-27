# Testing strategy

Applies to every phase. Phase specs list the specific tests; this file sets the rules and the layers.

## Layers

| Layer | Location | What it covers | Runs |
|---|---|---|---|
| Unit | `tests/unit/` | Pure functions and single modules: settings, the event log, contracts, rules, plan checking, the policy, prompt rendering | Every run; fast |
| Integration | `tests/integration/` | Modules together: the graph with `ScriptedModel` and an in-memory or temporary SQLite checkpointer, the store, MCP sessions against an in-process fake server | Every run |
| End-to-end | `tests/e2e/` | Commands through Typer's `CliRunner`; whole runs from request to answer with scripted models and fake servers | Every run |
| Evaluation | `conductor eval run` (Phase 8) | Consistency and accuracy against the real local model | By hand, never in `scripts/check.py` |

## Rules

1. **Synthetic data only** (`AGENTS.md` rule 5).
2. **No network.** `tests/conftest.py` blocks every connection that is not to 127.0.0.1 or a Unix socket, and points `CONDUCTOR_OLLAMA_HOST` at `http://127.0.0.1:9`, where nothing listens, so a test that forgets to replace the model fails fast instead of reaching a real Ollama. A test that needs an HTTP answer starts its own server on 127.0.0.1. MCP tests use the SDK's in-memory transport.
3. **No real model in tests.** Graph and node tests use `ScriptedModel` (from Phase 3) with recorded replies. Behaviour that depends on a real model is measured by the evaluation harness, not asserted in tests.
4. **Deterministic**: no dependence on today's date, the machine's time zone, dict or file-system order, or randomness. Time comes from replacing `conductor.clock.now`, ids from replacing `conductor.ids.new_id`.
5. **Isolated settings.** `tests/conftest.py` removes every `CONDUCTOR_*` variable from the environment and sets `CONDUCTOR_DATA_DIR` to a fresh temporary folder for each test. A phase that adds a setting adds nothing here: the prefix covers it.
6. **Every bug fix adds a test** that fails before the fix.
7. **Coverage**: branch coverage on every run, overall at least 90%. Every line and branch of each critical module is covered; `scripts/check.py` checks it.
8. **Expected values are literal**: whole lines and whole rows written out, never built by the code under test or by `str.format`.
9. Tests for a module live in the matching layer folder, named `test_<module>.py`. Shared helpers live in `tests/support.py`.

## Critical modules

A bug here lets the agent act without approval, lose its record, or accept output it should refuse, so every line and branch must be covered. The list lives in `scripts/critical_modules.txt` (paths relative to `src/conductor/`), which `scripts/check.py` reads; a phase that adds a critical module adds it there and here.

- `events.py` (the event log; Phase 1)
- `reports.py` (progress entries and reviews; Phase 2b)

Planned: plan checking (Phase 2), the approval policy (Phase 4).

## Commands

```zsh
.venv/bin/python scripts/check.py                  # lint, format, tests with coverage, critical coverage
.venv/bin/python scripts/check.py --first core     # the core section first; the full check only once it passes
.venv/bin/python scripts/check.py --section cli    # one section alone, no coverage (names in tests/sections.toml)
.venv/bin/python -m pytest                         # the tests alone, with coverage
```

A new test file belongs in the section of the code it tests: add a pattern to `tests/sections.toml` when `core` would take it otherwise.
