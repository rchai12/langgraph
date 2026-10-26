# Progress

The coding agent appends one entry per phase, in the form `docs/phase-conventions.md` gives. Earlier entries are never rewritten.

## Phase 1: skeleton (2026-10-25)
- Tests: 0 -> 70 (given 65)
- New public names: `conductor`: `__version__`; `config`: `LOOPBACK_HOSTS`, `OLLAMA_HOST_MESSAGE`, `MODEL_MESSAGE`, `SettingsError`, `Settings`, `get_settings`; `clock`: `now`; `ids`: `new_id`; `events`: `RUN_ID_MESSAGE`, `JsonValue`, `EventKind`, `Event`, `EventLogCorrupt`, `RunNotFound`, `RunSummary`, `check_run_id`, `EventLog`; `llm.tags`: `OllamaUnreachable`, `OllamaBadAnswer`, `fetch_model_names`; `diagnostics`: `MIN_PYTHON`, `Check`, `python_version`, `check_python`, `check_data_folder`, `check_ollama`, `run_checks`, `summary_line`; `cli.main`: `app`, `doctor`, `list_runs`, `show`
- Changed files: 6
- Deviations:
  - An invalid event raises ValueError("event is not valid"); the spec requires ValueError and does not pin this text.
- Follow-ups:
  - None
