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

## Phase 2a: contracts (2026-10-26)
- Tests: 70 -> 114 (given 38)
- New public names: `contracts`: `MAX_ATTEMPTS`, `MAX_PROBLEMS`, `MAX_STEPS`, `NOT_FINITE_MESSAGE`, `ONE_DOMAIN_MESSAGE`, `RESULT_MESSAGE`, `ROUTE_MESSAGE`, `Contract`, `DecidedBy`, `Escalation`, `EscalationKind`, `FieldProblem`, `JsonObject`, `Plan`, `Route`, `Step`, `TaskError`, `TaskErrorKind`, `TaskResult`, `TaskSpec`, `TaskStatus`, `problems_from`; `contracts.base`: `Name`, `ActionName`, `RuleId`, `Id`
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - The working tree also has edits this phase did not make: `.claude/skills/phase-architect/SKILL.md`, `docs/roadmap.md`, and untracked `.claude/skills/phase-architect/phase_status.py`.

## Phase 2b: report checker (2026-10-26)
- Tests: 114 -> 166 (given 34)
- New public names: `reports`: `Problem`, `ProgressEntry`, `Finding`, `Review`, `phase_of`, `parse_progress`, `parse_review`, `check_reports`
- Changed files: 9
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2c: the registry and plan checking (2026-10-27)
- Tests: 166 -> 202 (given 26)
- New public names: `registry`: `ActionKind`, `Effect`, `Action`, `Domain`, `RegistryError`, `NotRegistered`, `Registry`; `domains`: `DOMAINS`; `domains.demo`: `EchoArgs`, `EchoResult`, `NoteArgs`, `NoteResult`, `DelegateArgs`, `DelegateResult`, `DOMAIN`; `plancheck`: `PLAN_REJECTED_MESSAGE`, `CheckedStep`, `PlanRejected`, `check_plan`
- Changed files: 9
- Deviations:
  - None
- Follow-ups:
  - None
