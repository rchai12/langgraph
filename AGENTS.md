# Rules for AI coding agents

This file applies to every phase. Read it, then `docs/architecture.md`, then `docs/phase-conventions.md` (what every phase spec and guide assume), then the phase spec you were assigned.

## Scope discipline

- Implement **only** the phase you were assigned. Do not build features from later phases, even if it seems convenient.
- If the spec is ambiguous, pick the simplest option that satisfies the acceptance criteria and record the decision in `docs/progress.md`.
- If the spec seems wrong or impossible, stop and explain instead of improvising a large workaround.
- Do not add dependencies that the phase spec does not list. If you believe one is needed, stop and ask.
- When finished, append an entry to `docs/progress.md` in the form `docs/phase-conventions.md` gives.

## Running commands

- The project's interpreter is `.venv/bin/python`. Every command names it: `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff check .`, `.venv/bin/conductor doctor`.
- Never type `python`, `python3`, `ruff`, or `pytest` on their own. On this machine `python` does not exist, `python3` may be a different interpreter without the project's packages, and a bare `ruff` is a different installation.
- Do not activate the virtual environment. Each command runs in a new shell, so activation is lost before the next command.
- From Phase 1 on, `.venv/` exists. It is gitignored. Do not create another virtual environment and do not reinstall packages unless the phase spec has a step for it.
- If a command prints `command not found` or `No module named ...`, it was not typed as written. Stop and fix the command; do not skip the step.
- Before reporting a phase, run `.venv/bin/python scripts/check.py` as the spec's acceptance gives it. It must end with `All checks passed.`

## Privacy and safety rules (non-negotiable)

1. **Local models only.** The agent talks to Ollama on a loopback address (127.0.0.1, localhost, ::1) and to nothing else that runs a model. Never add a hosted model provider, an API key setting, or a LangChain model wrapper.
2. **No telemetry.** No tracing, analytics, crash reporting, or update checks. LangSmith tracing stays off whatever the environment says. Never install an OpenTelemetry SDK or exporter.
3. **Network.** Code may connect only to Ollama on loopback (inside `src/conductor/llm/`), to MCP servers it starts as child processes over stdio, and (from Phase 7) serve the approvals page on 127.0.0.1. Nothing else.
4. **Tests touch no network** except servers a test starts itself on 127.0.0.1. `tests/conftest.py` blocks every other connection, and points the Ollama host at a closed local port.
5. **Synthetic data only** in tests and fixtures: invented requests, merchants, names, amounts, email addresses. Never copy real data from `data/`, from the `finances` project, or from a mailbox.
6. **`data/` is gitignored** and holds everything a run produces. Never commit anything from it, never print it into a document.
7. **Side effects need approval.** No code path may run a `propose`, `write`, or `implement` action without an approval decision recorded for it, except the coder's retry after a verifier FAIL inside an approved implementation (Phase 10).

## Determinism rules

- **Code decides where it can.** A rule, a check, a retry, a policy, or a dispatch is written as code, never asked of the model.
- **Every model call goes through `decide()`** (from Phase 3) with a named decision point, a versioned prompt template, and a closed output schema. No other module calls Ollama.
- **Invalid model output escalates.** Never retry, repair, or guess around a reply that fails validation.
- **The model chooses only from enumerations** built from the registry. It never names a tool, a domain, or an action that is not registered.
- **Time and ids come from one place.** Read the current time only through `conductor.clock.now()` and new ids only through `conductor.ids.new_id()`, called through the module (`clock.now()`, not `from conductor.clock import now`), so tests can replace them.

## Architecture rules

- Layering (see `docs/architecture.md`): `contracts` imports nothing from this project. `cli` and `web` are thin and contain no decisions.
- All configuration comes from `conductor.config.get_settings()` (environment variables with prefix `CONDUCTOR_`). No hardcoded paths, no secrets in code.
- Use `pathlib.Path`. Development and deployment happen on macOS.
- Error messages are constant text plus identifiers (a run id, a line number, a field name). They never echo a request, a model reply, or a tool result.

## Code style

- Python 3.12+, type hints on all public functions.
- `ruff check .` and `ruff format --check .` must pass.
- Prefer small, pure functions. Docstrings only where the intent is not obvious.
- `pytest` must pass, including all tests from previous phases.

## Testing

Follow `docs/testing.md`: put tests in the right layer (`tests/unit`, `tests/integration`, `tests/e2e`), keep them deterministic and offline, keep coverage above the configured threshold, and add a failing-first test for every bug fix. If you add code to a module listed under "Critical modules", cover every line and branch.
