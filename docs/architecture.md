# Architecture

Status (2026-10-25): designed; nothing built yet. Phase 1 is specified.

## Goal

`conductor` is the framework for one supervisor agent that takes a person's request and gets it done through other systems: subagents (a coding agent and a verifier, later email, tasks, and scheduling) and local services that expose tools over MCP (the `finances` app first). It runs on the household's own Mac, on local models served by Ollama.

The design goal is **less variance**. A language model is used only where a decision cannot be written as code, and every one of those decisions is narrow, typed, validated, logged, and measured. When the model's answer does not fit, the agent stops and asks the person; it does not guess.

The systems the agent reaches are out of scope. This project builds the framework and the adapters that reach them.

## Principles

1. **Code decides wherever it can.** Routing rules, the approval policy, retries, dispatch, and validation are code. The model is asked only what code cannot answer: which domain an unrecognized request belongs to, which registered actions a request needs, and how to phrase an answer.
2. **Every model call is a decision point.** A decision point has a name, a versioned prompt template, a closed output schema (Pydantic, `extra="forbid"`, enumerations for every label), and fixed sampling: temperature 0, a fixed seed, a fixed context size, and a fixed thinking setting. The model is pinned by its digest, and the digest is recorded with every reply.
3. **Invalid output escalates.** A reply that does not parse or does not validate against its schema stops the run with an escalation the person answers. There is no silent retry and no "best effort" repair. A label of `unknown` (every classifier has one) escalates too.
4. **The model never names a tool freely.** The planner chooses from the actions a domain registers, through an enumeration built from the registry. A domain sees only its own tools. Arguments are validated against the action's schema before anything runs.
5. **Every side effect waits for a person**, decided by a policy written in code. The one exception is a coder's retry after the verifier fails its work, inside an implementation the person already approved.
6. **Everything is logged**: each node's input and output, every prompt, the model's reply and its reasoning, every tool call and result, every approval and escalation. Logs stay on the machine.
7. **Variance is measured, not assumed.** An evaluation harness runs a fixed set of requests many times against the real model and reports how often the answers agree.

## Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 (`/opt/homebrew/bin/python3.12`) | |
| Graph | `langgraph` 1.2 | `StateGraph`, `interrupt`, `Command(resume=...)` |
| Checkpoints | `langgraph-checkpoint-sqlite` 3.1 (`SqliteSaver`) | Threads survive restarts |
| Models | Ollama on 127.0.0.1, `ollama` Python client 0.6 | `format` = a JSON schema, `options` = temperature, seed, `num_ctx`; `think` set per decision point. No LangChain model wrappers |
| Tools | `mcp` Python SDK 2.x as a client, stdio transport | The same SDK the `finances` server uses |
| Contracts | `pydantic` 2, `pydantic-settings` 2 | |
| Commands | `typer` | |
| Approvals page | FastAPI on 127.0.0.1 (Phase 7) | No scripts from a CDN; the same hardening as `finances`' web UI |
| Tests / lint | `pytest`, `pytest-cov`, `ruff` | |

Versions found on 2026-10-25 in a scratch environment: langgraph 1.2.17, langgraph-checkpoint 4.3.0, langgraph-checkpoint-sqlite 3.1.2, ollama 0.6.3, mcp 2.3.0, pydantic 2.14.1, pydantic-settings 2.16.1, typer 0.27.3 (click 8.5.0), pytest 9.1.1, pytest-cov 7.1.0, ruff 0.17.2. Each phase adds only the dependencies it needs, with bounds.

Models: development uses `qwen3.8:27b` (installed) on a 48 GB MacBook Pro (M5 Pro); production moves to a 128 GB Mac Studio. On 48 GB, keep one model loaded: every decision point uses the same model until the evaluation harness shows a smaller one is as consistent for routing.

## The supervisor graph

```
request ─► route ─► plan ─► check plan ─► for each step: approve? ─► run step ─► check result ─► answer
            │        │          │                          │             │             │
          rules,   model:     code:                    interrupt()    tool action:  coding: verifier
          then     a typed    registry,                for every      call one MCP  FAIL → coder again,
          model    plan       schemas,                 side effect    tool; agent   at most 2 times,
          (closed                limits                               action: a     then escalate
          labels)                                                     subagent
```

Any node can **escalate**: the run records why, interrupts, and waits for the person to answer (clarify, edit, or cancel).

### Route

1. **Rules first** (pure code, `routing/rules.py`): an explicit prefix (`finance: ...`, `code: ...`), then keyword and pattern rules each domain registers. The first rule that matches decides, and its id is recorded.
2. **Classifier second**, only when no rule matches: a decision point whose schema is `{"domain": <enum of registered domains> | "unknown"}`. `unknown` escalates.

### Plan

A decision point whose output is a `Plan`: an ordered list of 1 to 8 `Step`s, each naming one registered action (an enumeration built from the chosen domain's actions only) and its arguments. Steps run in order. A step does not read another step's output through the model. When an agent action needs earlier results, code passes them in its `TaskSpec.context`.

### Check plan (code)

Each action exists in the routed domain; each step's arguments validate against the action's schema; the plan is within its limits. Any failure escalates with the validation errors.

### Approve

`policy.needs_approval(action)` decides from the action's **effect class**:

| Effect | Meaning | Approval |
|---|---|---|
| `read` | Reads only | none |
| `propose` | Writes only something a person reviews later (a `finances` proposal) | required |
| `write` | Changes something outside the agent (sends an email, creates an event, commits, pushes) | required |
| `implement` | Starts a coding agent on a spec | required once; retries after a verifier FAIL are not asked again |

**Approval is two-stage** (the owner's decision, 2026-10-27): before any step runs, the person approves the plan's shape (every step, its action, and its effect) once; then each `propose`, `write`, or `implement` step stops again just before it runs, with its exact arguments. A request that needs two domains is not planned: it escalates and asks the person to split it (one domain per plan, decided the same day). The graph calls `interrupt()` with an `ApprovalRequest` (action, arguments, a summary). The person approves, rejects, or edits the arguments in the terminal or on the approvals page. Both write the decision to the same store, then resume the thread. Edited arguments are validated again before the step runs.

### Run a step

- A **tool action** maps one-to-one to an MCP tool on one of its domain's servers. Code calls it with the validated arguments and validates the result against the action's result schema. No model is involved.
- An **agent action** hands a `TaskSpec` to a subagent (a LangGraph subgraph, or an adapter around an external agent such as the coder) and gets back a `TaskResult`. A subagent sees only its domain's tools.

### Answer

A decision point that turns the results into the reply, with the results passed in as data. It cannot call tools.

## Contracts (`conductor/contracts/`, pure Pydantic, no project imports)

- `Route`: `domain`, `decided_by` (`rule` or `model`), `rule_id` or `decision_id`.
- `Step`: `id` (`s1`, `s2`, ...), `action` (`<domain>.<name>`), `args`.
- `Plan`: `steps` (1 to 8).
- `TaskSpec`: `task_id`, `thread_id`, `run_id`, `domain`, `action`, `args`, `context` (earlier results), `max_attempts`.
- `TaskResult`: `task_id`, `status` (`succeeded`, `failed`, `escalated`), `output`, `error` (`kind`, `message`), `attempts`.
- `ApprovalRequest` and `ApprovalDecision` (`approve`, `reject`, `edit` with new arguments).
- `Escalation`: `kind` (`invalid_model_output`, `unknown_route`, `invalid_plan`, `tool_error`, `retries_exhausted`, `rejected`), `detail`.

All models are frozen and forbid extra fields. Exact fields are fixed in the phase that builds them.

## Domains and the action registry

A domain is declared in Python (`conductor/domains/<name>/`) as data: its name, its routing rules, its MCP servers (the command that starts each, and the environment variables passed through), and its actions. An action declares:

- `name`, `description` (shown to the planner);
- `kind`: `tool` (with the MCP server and tool name it maps to) or `agent` (with the subagent that runs it);
- `effect`: `read`, `propose`, `write`, or `implement`;
- `args`: a Pydantic model; `result`: a Pydantic model.

The registry checks at start-up that names are unique, every tool action's MCP tool exists on its server with a compatible input schema, and every domain's rules have unique ids. A domain cannot reach another domain's servers: the MCP client manager hands a subagent a session limited to its own domain's tools.

## Model client (`conductor/llm/`)

The only code that talks to Ollama, and only on 127.0.0.1. `decide(point, inputs) -> validated output`:

1. Renders the decision point's prompt template (a file under `conductor/prompts/`, with a version and a hash recorded).
2. Calls Ollama with the schema as `format`, the fixed options, and `think` as set for the point.
3. Logs the request, the raw reply, the reasoning, the model digest, and timings.
4. Validates the reply; on failure raises `InvalidModelOutput`, which the graph turns into an escalation.

A `ScriptedModel` with the same interface returns recorded replies, for tests and for replaying a logged run.

Prompts are structured: a fixed system section (role, rules, the closed set of answers), the inputs in labelled blocks, and the output schema. Rendered prompts are pinned by tests so that a prompt change is always deliberate.

## State, threads, and storage

Everything lives under the data folder (`CONDUCTOR_DATA_DIR`, default `./data`, gitignored, created `0700`):

| Path | What |
|---|---|
| `runs/<run_id>.jsonl` | The event log of one run, append-only, one JSON object per line, files `0600` |
| `conductor.db` | SQLite: LangGraph checkpoints (threads), approvals, escalations, thread leases |
| `evals/<timestamp>/` | Evaluation results |

A **thread** is a conversation that can last days (a LangGraph thread id). A **run** is one pass through the graph for one request in a thread, with its own event log. Only one process resumes a thread at a time (a lease row in `conductor.db`).

Long-term memory (preferences, contacts, summaries of past threads, optionally recalled through embeddings from a local Ollama model) is a late phase. It adds variance rather than removing it, so it stays off the routing and planning path and is passed in only as labelled context.

## The event log

`conductor/events.py` (critical module). Each event is `{run_id, seq, at, kind, node, payload}`: `seq` counts from 1 per run with no gaps, `at` is UTC with microseconds, and `payload` is any JSON value. Lines are written with sorted keys and flushed to disk before `append` returns. Reading a log checks every line and refuses a damaged one with its line number. The log is the record of what the agent did and why, and the source for replaying a run with `ScriptedModel`.

## Coding pipeline

The `code` domain automates the workflow already used by hand in the `finances` project:

1. The person asks for a phase to be implemented; approving `code.implement` starts it.
2. The coder adapter runs the configured coding agent (an external command, given the spec's path) in the project folder.
3. The verifier adapter runs the configured verifier with the matching verification guide; the verdict is read from the review file's `Verdict:` line by a strict parser (critical).
4. `FAIL`: the coder runs again with the findings, without asking, at most 2 times in all; still failing, the run escalates. `PASS`: the result is reported.
5. Committing and pushing are separate `write` actions, each approved.

## Approvals and escalations

Both appear in the terminal (`conductor approvals ...`) and on the approvals page (127.0.0.1, Phase 7), which share the store in `conductor.db`. Deciding records who decided, where, and when, then resumes the thread under its lease.

## Evaluation harness

`conductor eval run` (not part of `scripts/check.py`, since it needs the real model) reads a set of cases (a request plus the expected route, the expected actions in order, chosen arguments, or "must escalate"), runs each K times (default 5), and reports per case and overall:

- the share of replies that validated;
- route and plan accuracy against the expected values;
- **consistency**: the share of runs equal to the most common output;
- the escalation rate, and latency at the median and 95th percentile.

Each report records the model digests and prompt hashes, and compares with the previous report, so a change in variance can be traced to a prompt or model change.

## Package layout (planned)

```
conductor/
  AGENTS.md, CLAUDE.md          rules for coding agents
  pyproject.toml
  docs/                         architecture, roadmap, phase specs, verification guides, reviews, progress
  scripts/check.py              every check a phase must pass
  src/conductor/
    config.py                   Settings, get_settings() (Phase 1)
    clock.py, ids.py            now() in UTC and new ids, read through one function each (Phase 1)
    events.py                   the event log (Phase 1, critical)
    diagnostics.py              conductor doctor's checks (Phase 1)
    contracts/                  pure typed contracts (Phase 2)
    registry/                   domains and actions, plan checking (Phase 2)
    llm/                        the only Ollama code: model names (Phase 1), decide() (Phase 3)
    prompts/                    versioned prompt templates (Phase 3)
    store/                      conductor.db: approvals, escalations, leases (Phase 4)
    policy.py                   which actions need approval (Phase 4, critical)
    routing/, planning/         rules and decision points (Phase 5)
    graph/                      the supervisor graph (Phase 5)
    mcp_client/                 MCP sessions scoped per domain (Phase 6)
    web/                        the approvals page (Phase 7)
    evals/                      the evaluation harness (Phase 8)
    domains/                    finance (Phase 9), code (Phase 10), later others
    cli/                        Typer commands (thin)
  tests/                        unit, integration, e2e
  data/                         gitignored
```

### Dependency direction

```
cli, web  ─►  graph  ─►  routing, planning, policy, domains  ─►  llm, mcp_client, registry, store, events  ─►  contracts
```

`contracts` imports nothing from the project. `cli` and `web` contain no decisions.

## Privacy and safety boundary

- **Local models only.** `CONDUCTOR_OLLAMA_HOST` must be a loopback address; settings refuse anything else. Moving any decision point to a hosted model sends request text, tool results, and finance data off the machine, and needs this document revised first (the `finances` architecture has the same rule).
- **No telemetry.** LangGraph depends on `langchain-core`, which depends on `langsmith`. Tracing to LangSmith must stay off whatever the environment says; a guard test arrives with the phase that adds `langgraph`.
- **Network.** The only connections are to Ollama on loopback, MCP servers as child processes over stdio, and the approvals page bound to 127.0.0.1.
- **Logs hold everything**, including finance data from tool results. They live under the gitignored data folder with owner-only permissions and are never sent anywhere.
- **Tests** use synthetic data and touch no network beyond servers they start on 127.0.0.1.
