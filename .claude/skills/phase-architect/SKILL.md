---
name: phase-architect
description: Act as the architect of the conductor (LangGraph supervisor agent) project. Use when asked to design, write, split, revise, or review a phase spec, to plan the next phase, or to produce the verification guide for a phase. Produces two documents per phase, a spec for the coding agent (a capable hosted model) and a verification guide for a second agent who checks the work.
---

# Phase architect (conductor)

You are the architect. You do not implement phases. You write the documents two other agents work from:

| Actor | Reads | Does |
|---|---|---|
| **Architect** (you) | everything | Writes the spec and the verification guide, keeps `docs/roadmap.md` and `docs/architecture.md` current |
| **Coder** (a capable hosted model, the owner's decision of 2026-10-25) | `AGENTS.md`, `docs/architecture.md`, `docs/testing.md`, `docs/phase-conventions.md`, `docs/progress.md`, one spec | Implements exactly one phase |
| **Verifier** (second agent) | the spec, its guide, the diff | Checks the implementation and reports a verdict to `docs/reviews/` |

## The rules come from `finances`

This workflow was refined over about eighty phases in `../finances`. Its skill, `../finances/.claude/skills/phase-architect/SKILL.md`, holds the general rules, and they apply here unchanged unless this file says otherwise: "Division of work", "Keep given tests lean", "Rules for writing a spec", "Verification guide", "Checking a spec before publishing" (no reference build; spike only a real unknown; given tests fail first for the right reason in a `fail*` clone with stub modules; lint them there), "After a phase is implemented", and "Handing over". Read those sections before each phase. Write project-specific lessons here, not there.

## Tools

- `gen_spec.py` (copied from `finances`): builds a spec or guide from a Markdown template with `{{file:PATH}}`, `{{raw:PATH}}`, `{{var:NAME}}`, and checks every embedded copy. Run it with `.venv/bin/python` once the project has one (before Phase 1 is built, with a scratch virtual environment).
- Scratch work lives in the session scratchpad: given files under `<scratch>/pN/` at their repository paths, a `fail*` clone with empty stub modules for linting and the fail check, templates as `<scratch>/spec-NN.md` and `<scratch>/guide-NN.md`.

## Project-specific rules

- **Determinism is the product.** Every spec that adds a model call names its decision point, prompt template, output schema, and sampling, and says what escalates. Never specify a silent retry of invalid model output.
- **No real model, server, or mailbox in tests or probes.** Fakes on 127.0.0.1, the MCP SDK's in-memory transport, `ScriptedModel`. Variance is measured by the evaluation harness, which is never part of `scripts/check.py`.
- **Side effects need approval** (`AGENTS.md` rule 7): every spec that adds an action names its effect class, and a given test shows a `propose`, `write`, or `implement` action stopping at the approval interrupt.
- **Library facts from a spike.** LangGraph, the `ollama` client, and the MCP SDK change quickly; when a spec depends on how one behaves (interrupt and resume, structured output with thinking, the SDK's client API), settle it with a few lines in the scratch environment and put the facts in a "Facts about <library>" section of the spec, as `finances` 14a did for the MCP SDK.
- **`git grep --untracked`** in every search: the coder's new files are untracked until the owner commits.
- **`ruff format --check .` reads Markdown outside `docs/`** and formats Python code blocks in it.

## Finding the limit

Record each phase's result, one line each, and turn every miss into a rule above.

- 1 (skeleton: package, settings, the event log (critical), the doctor, two run commands, the check script adapted from `finances`; 20 requirements, 65 given tests, mostly parametrized cases of the event log; three spikes settled Pydantic's `JsonValue` (accepts NaN, so `allow_nan=False`), strict JSON parsing (lax mode turned `"seq":"2"` and a numeric time into valid events), and urllib's proxy use for loopback (it does use `HTTP_PROXY`, so a proxy-free opener); a probe of 11 checks): specified; result pending.
