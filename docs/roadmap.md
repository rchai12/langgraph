# Roadmap

Each phase is one coding session for a capable coding agent and ends with every check green. A phase too large for one session is split into lettered sub-phases (`5a`, `5b`, ...); numbers are never reused or renumbered. Specs are written one or two phases ahead, from the code that exists.

Status (2026-10-25): Phase 1 is specified. Nothing is built yet.

**Build order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11; 12 and 13 when wanted.

| # | Phase | Outcome | Spec |
|---|---|---|---|
| 1 | Skeleton | Installable package, settings that refuse a non-local model host, the event log (critical), `conductor doctor`, `conductor runs list/show`, `scripts/check.py` with sections and a critical coverage gate, test guards (no network, isolated settings) | [phase-01](phases/phase-01-skeleton.md) |
| 2 | Contracts and the registry | Typed `Route`, `Step`, `Plan`, `TaskSpec`, `TaskResult`, `ApprovalRequest`, `Escalation`; domains and actions declared as data; plan checking against the registry (critical); a `demo` domain for tests | |
| 3 | Model client | `decide()` over Ollama with a JSON-schema format, fixed sampling, the model digest, and full logging; versioned prompt templates; `ScriptedModel`; invalid output raises; a spike on `qwen3.8`'s structured output with thinking on and off | |
| 4 | Approvals and escalations store | `conductor.db` with approvals, escalations, and thread leases; the approval policy (critical); `conductor approvals list/show/approve/reject/edit` | |
| 5 | The supervisor graph | Rules then classifier routing, the planner, plan checking, the approval interrupt and resume, tool and agent steps on the `demo` domain, escalation, the SQLite checkpointer; `conductor ask` and `conductor resume`; LangSmith tracing guarded off. Probably split into 5a (routing and planning nodes) and 5b (graph assembly) | |
| 6 | MCP client | Server configs per domain, sessions over stdio scoped to a domain's tools, tool actions bound to MCP tools with argument and result validation, the start-up check of tool schemas; tests against an in-process fake MCP server | |
| 7 | Approvals page | A FastAPI page on 127.0.0.1 listing pending approvals and escalations, deciding them, and resuming the thread; form token, origin check, no telemetry | |
| 8 | Evaluation harness | Cases as files, K runs each against the real model, schema-valid rate, accuracy, consistency, escalation rate, latency; reports compared with the previous one | |
| 9 | Finance domain | Read actions over the `finances` MCP server's read tools (`fin mcp serve`), its proposal tools as `propose` actions, an answer decision point; evaluation cases for finance requests | |
| 10 | Coding pipeline | Coder and verifier adapters around external agents, the strict verdict parser (critical), automatic retry after FAIL (at most 2), escalation, commit and push as approved `write` actions | |
| 11 | Replay | Re-run a logged run with `ScriptedModel` from its event log; turn a real run into a regression test | |
| 12 | Email, calendar, tasks | One domain each over their MCP servers, when those systems exist | |
| 13 | Long-term memory | Preferences and past-thread summaries through LangGraph's store, optionally recalled by local embeddings, passed in as labelled context only | |

## Backlog

- A notification when an approval is waiting (phone push), once the approvals page exists.
- Moving to the Mac Studio: model choices per decision point, re-run the evaluation harness, compare consistency.
