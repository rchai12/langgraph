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

## Phase 3a: decision points and prompts (2026-10-27)
- Tests: 202 -> 242 (given 32)
- New public names: `llm.prompts`: `PROMPTS_DIR`, `PromptError`, `PromptTemplate`, `load_template`; `llm.points`: `SEED`, `CONTEXT_TOKENS`, `MAX_REPLY_TOKENS`, `SCHEMA_INTRO`, `DecisionPoint`, `ModelRequest`, `build_request`; `domains.demo`: `PickInputs`, `PickOutput`, `PICK`, `pick_fields`
- Changed files: 9
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 3b: the Ollama client and the scripted model (2026-11-08)
- Tests: 242 -> 282 (given 32)
- New public names: `llm.model`: `UnavailableCode`, `ModelUnavailable`, `ModelInfo`, `ModelReply`, `Model`; `llm.ollama`: `OllamaModel`; `llm.scripted`: `SCRIPTED_INFO`, `ScriptError`, `ScriptedReply`, `ScriptedModel`; `config`: `TIMEOUT_MESSAGE`, `Settings.model_timeout`, `Settings.model_timeout_seconds`
- Changed files: 10
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 3c: decide() (2026-11-08)
- Tests: 282 -> 308 (given 19)
- New public names: `llm.decide`: `INVALID_OUTPUT_MESSAGE`, `RETRY_HINT`, `InvalidModelOutput`, `Decision`, `decide`, `escalation_for`
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 4a: approval contracts and the policy (2026-11-08)
- Tests: 308 -> 349 (given 34)
- New public names: `contracts.approvals`: `STEP_COUNT_MESSAGE`, `NUMBERS_MESSAGE`, `DIGEST_MESSAGE`, `EDIT_MESSAGE`, `UTC_MESSAGE`, `ApprovalStage`, `Verdict`, `Channel`, `StepEffect`, `Sha256`, `UtcTime`, `PlannedStep`, `steps_digest`, `ApprovalRequest`, `ApprovalDecision`; `policy`: `ATTEMPT_MESSAGE`, `RefusalCode`, `DecisionRefused`, `Approved`, `Rejected`, `needs_approval`, `plan_request`, `step_request`, `apply_decision`
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 4b: the store (2026-11-08)
- Tests: 349 -> 378 (given 22)
- New public names: `store`: `SCHEMA_VERSION`, `LEASE_SECONDS`, `BUSY_SECONDS`, `ID_MESSAGE`, `StoreError`, `NotFound`, `AlreadyDecided`, `LeaseHeld`, `LeaseLost`, `StoredApproval`, `StoredEscalation`, `Lease`, `Store`; `contracts.approvals`: `Answer`, `EscalationAnswer`; `config`: `Settings.db_path`
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 4c: the approvals and escalations commands (2026-11-08)
- Tests: 378 -> 423 (given 33)
- New public names: `decisions`: `NOTE_MESSAGE`, `decide_approval`, `answer_escalation`; `config`: `DECIDED_BY_MESSAGE`, `Settings.decided_by`
- Changed files: 11
- Deviations:
  - The Phase 4b progress entry was missing, so this phase adds it; `check_reports.py` rejects the committed 4b review without one.
- Follow-ups:
  - None
