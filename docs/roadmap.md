# Roadmap

Each phase is one coding session for a capable coding agent and ends with every check green. From Phase 2 on, a spec is about half the size of Phase 1 (about 10 requirements and 30 given tests), so most rows below become two or more lettered sub-phases (`2a`, `2b`, ...); numbers are never reused or renumbered. Specs are written one or two phases ahead, from the code that exists.

Status (2026-11-09): Phases 1 to 5b are built and verified (500 tests). Phase 5c (the supervisor graph) is specified.

**Build order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11; 12 and 13 when wanted.

| # | Phase | Outcome | Spec |
|---|---|---|---|
| 1 | Skeleton | Installable package, settings that refuse a non-local model host, the event log (critical), `conductor doctor`, `conductor runs list/show`, `scripts/check.py` with sections and a critical coverage gate, test guards (no network, isolated settings) | [phase-01](phases/phase-01-skeleton.md) |
| 2 | Contracts and the registry | Typed `Route`, `Step`, `Plan`, `TaskSpec`, `TaskResult`, `Escalation` (the approval contracts move to Phase 4); domains and actions declared as data; plan checking against the registry (critical); a `demo` domain for tests | [phase-02a](phases/phase-02a-contracts.md) (the contracts); [phase-02b](phases/phase-02b-report-checker.md) (the report checker: `scripts/check_reports.py` validates the progress entry and every review against `docs/phase-conventions.md`, run by both agents as their last step, and the base for Phase 10's verdict parser); [phase-02c](phases/phase-02c-registry-and-plan-checking.md) (the registry and plan checking) |
| 3 | Model client | `decide()` over Ollama with a JSON-schema format, fixed sampling, the model digest, and full logging; versioned prompt templates; `ScriptedModel`; invalid output raises. Split: 3a decision points, templates, and the request (pure); 3b the Ollama transport over the standard library (chat, digest and capabilities from `/api/tags`, typed transport errors) and `ScriptedModel`, against a fake on 127.0.0.1; 3c `decide()` (critical): thinking by capability, validation, model-unavailable and invalid-output errors, the events. The spike (2026-10-27, Ollama 0.40.11, `qwen3.8:27b`) found structured output reliable and repeatable with thinking on and off | [phase-03a](phases/phase-03a-decision-points-and-prompts.md); [phase-03b](phases/phase-03b-ollama-client-and-scripted-model.md); [phase-03c](phases/phase-03c-decide.md) |
| 4 | Approvals and escalations store | `conductor.db` with approvals, escalations, and thread leases; the approval policy (critical); `conductor approvals list/show/approve/reject/edit`. Split: 4a the approval contracts and the policy (pure, critical); 4b the store in `conductor.db` (approvals, escalations, leases); 4c the `conductor approvals` and escalation commands | [phase-04a](phases/phase-04a-approval-contracts-and-policy.md); [phase-04b](phases/phase-04b-store.md); [phase-04c](phases/phase-04c-approvals-and-escalations-commands.md) |
| 5 | The supervisor graph | Rules then classifier routing, the planner, plan checking, the approval interrupt and resume, tool and agent steps on the `demo` domain, escalation, the SQLite checkpointer; `conductor ask` and `conductor resume`; LangSmith tracing guarded off. Split (decided 2026-11-09): 5a routing (rules, then the classifier; also `check_reports.py --phase` and the digest in `conductor doctor`); 5b planning, plan checking, and the answer point; 5c the graph in memory, with the approval interrupt and resume; 5d `checkpoints.db`, leases, `conductor ask` and `conductor resume` | [phase-05a](phases/phase-05a-routing.md); [phase-05b](phases/phase-05b-planning-and-answering.md) (planning and the answer point); [phase-05c](phases/phase-05c-supervisor-graph.md) (the graph in memory) |
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
