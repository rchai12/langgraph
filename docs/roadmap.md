# Roadmap

Each phase is one coding session for a capable coding agent and ends with every check green. From Phase 2 on, a spec is about half the size of Phase 1 (about 10 requirements and 30 given tests), so most rows below become two or more lettered sub-phases (`2a`, `2b`, ...); numbers are never reused or renumbered. Specs are written one or two phases ahead, from the code that exists.

Status (2026-11-18): Phases 1 to 8 and 9a to 9e are built and verified (1096 tests). The verified findings in [codebase-audit.md](codebase-audit.md) are accepted planning input. Audit remediation continues before the coding pipeline: 9f–9r remain planned and unspecified. From 9f on, specs commit their given files and probes instead of embedding them (`docs/phase-conventions.md`).

**Build order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9a–9d (complete) → 9e → 9f → 9g → 9h → 9i → 9j → 9k → 9l → 9m → 9n → 9o → 9p → 9q → 9r → 10 → 11; 12 and 13 when wanted; 14 (Discord approvals) after the shared Discord service contract exists, independently of 12/13. Existing phase numbers retain their meaning.

| # | Phase | Outcome | Spec |
|---|---|---|---|
| 1 | Skeleton | Installable package, settings that refuse a non-local model host, the event log (critical), `conductor doctor`, `conductor runs list/show`, `scripts/check.py` with sections and a critical coverage gate, test guards (no network, isolated settings) | [phase-01](phases/phase-01-skeleton.md) |
| 2 | Contracts and the registry | Typed `Route`, `Step`, `Plan`, `TaskSpec`, `TaskResult`, `Escalation` (the approval contracts move to Phase 4); domains and actions declared as data; plan checking against the registry (critical); a `demo` domain for tests | [phase-02a](phases/phase-02a-contracts.md) (the contracts); [phase-02b](phases/phase-02b-report-checker.md) (the report checker: `scripts/check_reports.py` validates the progress entry and every review against `docs/phase-conventions.md`, run by both agents as their last step, and the base for Phase 10's verdict parser); [phase-02c](phases/phase-02c-registry-and-plan-checking.md) (the registry and plan checking) |
| 3 | Model client | `decide()` over Ollama with a JSON-schema format, fixed sampling, the model digest, and full logging; versioned prompt templates; `ScriptedModel`; invalid output raises. Split: 3a decision points, templates, and the request (pure); 3b the Ollama transport over the standard library (chat, digest and capabilities from `/api/tags`, typed transport errors) and `ScriptedModel`, against a fake on 127.0.0.1; 3c `decide()` (critical): thinking by capability, validation, model-unavailable and invalid-output errors, the events. The spike (2026-10-27, Ollama 0.40.11, `qwen3.8:27b`) found structured output reliable and repeatable with thinking on and off | [phase-03a](phases/phase-03a-decision-points-and-prompts.md); [phase-03b](phases/phase-03b-ollama-client-and-scripted-model.md); [phase-03c](phases/phase-03c-decide.md) |
| 4 | Approvals and escalations store | `conductor.db` with approvals, escalations, and thread leases; the approval policy (critical); `conductor approvals list/show/approve/reject/edit`. Split: 4a the approval contracts and the policy (pure, critical); 4b the store in `conductor.db` (approvals, escalations, leases); 4c the `conductor approvals` and escalation commands | [phase-04a](phases/phase-04a-approval-contracts-and-policy.md); [phase-04b](phases/phase-04b-store.md); [phase-04c](phases/phase-04c-approvals-and-escalations-commands.md) |
| 5 | The supervisor graph | Rules then classifier routing, the planner, plan checking, the approval interrupt and resume, tool and agent steps on the `demo` domain, escalation, the SQLite checkpointer; `conductor ask` and `conductor resume`; LangSmith tracing guarded off. Split (decided 2026-11-09): 5a routing (rules, then the classifier; also `check_reports.py --phase` and the digest in `conductor doctor`); 5b planning, plan checking, and the answer point; 5c the graph in memory, with the approval interrupt and resume; 5d the runtime: `checkpoints.db`, leases around every start and resume, the demo setting; 5e `conductor ask`, `conductor resume`, and deciding then resuming in the approvals and escalations commands (5d split in two, decided 2026-11-09) | [phase-05a](phases/phase-05a-routing.md); [phase-05b](phases/phase-05b-planning-and-answering.md) (planning and the answer point); [phase-05c](phases/phase-05c-supervisor-graph.md) (the graph in memory); [phase-05d](phases/phase-05d-runtime.md) (the runtime); [phase-05e](phases/phase-05e-run-commands.md) (the run commands) |
| 6 | MCP client | Server configs per domain, sessions over stdio scoped to a domain's tools, tool actions bound to MCP tools with argument and result validation, the start-up check of tool schemas; tests against a fake MCP server started as a child process. Split (decided 2026-11-09): 6a server declarations, settings, and the client; 6b the start-up check of tool schemas and `conductor doctor`; 6c the MCP step runner in the runtime | [phase-06a](phases/phase-06a-mcp-servers-and-client.md); [phase-06b](phases/phase-06b-tool-check-and-doctor.md); [phase-06c](phases/phase-06c-tool-steps-over-mcp.md) |
| 7 | Approvals page | A FastAPI page on 127.0.0.1 listing pending approvals and escalations, deciding them, and resuming the thread; form token, origin check, no telemetry. Split (decided 2026-11-09): 7a `conductor web` on 127.0.0.1 with the host check, security headers, and read-only pages; 7b the deciding forms (form token, origin check, `conductor.decisions`) and resuming in the background | [phase-07a](phases/phase-07a-approvals-page-read-only.md); [phase-07b](phases/phase-07b-deciding-on-the-page.md) |
| 8 | Evaluation harness | Cases as files, K runs each against the real model, schema-valid rate, accuracy, consistency, escalation rate, latency; reports compared with the previous one. Split (decided 2026-11-09): 8a cases as TOML in `evals/cases/`, K runs (5) through the route and plan decision points only, consistency first; 8b saved reports with digests and prompt hashes, compared with the previous one | [phase-08a](phases/phase-08a-running-evaluation-cases.md); [phase-08b](phases/phase-08b-saved-and-compared-reports.md) |
| 9 | Finance domain | Read actions over the `finances` MCP server's read tools (`fin mcp serve`), its proposal tools as `propose` actions, an answer decision point; evaluation cases for finance requests. Split (decided 2026-11-10): 9a groundwork (today in the plan prompt, a context size per decision point, the answer's 16384-token context and 24000-byte bound); 9b the 20 read tools as actions, with bounded arguments and results; 9c the 11 write tools as `propose` actions, their ids taken from the request (planning again after the reads would be a later phase); 9d dollars in the answer (code converts `_cents`), a fixed day per evaluation case, and 24 finance cases (the tuning spike changed no description) | [phase-09a](phases/phase-09a-today-and-a-bounded-answer.md); [phase-09b](phases/phase-09b-finance-read-actions.md); [phase-09c](phases/phase-09c-finance-proposals.md); [phase-09d](phases/phase-09d-dollars-and-finance-cases.md) |
| 9e | Runtime ownership and status reads | Remove the process-wide `_SERVICES` owner; pass required services explicitly. Read checkpoint status without compiling a graph, constructing a model or opening unused runtime services. Repeated run-page polling releases resources; validate checkpoint status/interrupts and raise safe `RunError` for malformed state. Audits 1, 5 | [phase-09e](phases/phase-09e-runtime-ownership-and-status.md) (verified) |
| 9f | Background job lifecycle | Bound retained completed threads and errors, preserve active-run exclusion and observable outcomes, and define shutdown behavior so server shutdown need not wait for the full model timeout. Coordinate retention with 9h so cleanup does not erase unacknowledged failure evidence. Audit 1 | Planned |
| 9g | One bounded Ollama model listing | Share one `/api/tags` parser between doctor and model calls; isolate an invalid entry from unrelated valid models; reject a missing/invalid digest for the selected model. Cap tags and chat response reads, including missing or dishonest length headers. Preserve intentional caller-specific timeouts and proxy-free loopback access. Audits 2, 9 | Planned |
| 9h | Recover a failed web resume | Offer a protected resume control after a recorded decision when state permits it; reuse the recorded decision without applying it twice. Preserve leases, stale-decision checks and stopped-node restrictions. Keep durable, sanitized failure evidence and an actionable page message. Never log arbitrary exception text. Audits 3, 1 | Planned |
| 9i | Private storage primitives | Share owner-only directory/file creation across events, store, runtime, MCP logs and evaluation reports; correct doctor permissions for an existing data directory. Preserve append behavior and SQLite sidecar protections. Audit 6 | Planned |
| 9j | Shared validation and presentation contracts | Consolidate the 32-hex id shape, request bounds, Contract-type predicate and UTC display format without importing project modules into `contracts`. Keep wire shapes, validation order, messages and display output stable unless an explicit correction says otherwise. Audit 6 | Planned |
| 9k | Smaller graph and structured failures | Extract node construction from the supervisor without changing interrupt/replay boundaries. Record runner cause codes as structured event fields, preserving unknown-outcome visibility for writes. Keep critical coverage on all extracted approval and execution logic. Checkpoint validation is addressed in 9e; coder attempts remain in Phase 10. Audit 5 | Planned |
| 9l | Finance catalog split | Separate read and proposal contracts/actions, retaining compatible public imports, action order, descriptions, tighter local bounds and all 31 tools. Keep models hand-written and fake-server/captured-schema comparison independent; document the three-artifact update checklist. Do not generate contracts from captured JSON or add tools. Audit 4 | Planned |
| 9m | CLI command groups | Split approvals, escalations, evaluation and web commands into modules and share decision/confirmation/resume plumbing. Preserve command names, options, exit codes and output, and keep decisions in the existing policy/service layer. Audit 6 | Planned |
| 9n | Named web handlers | Extract nested route bodies and share approval/escalation record-and-resume plumbing, carrying forward 9h recovery. Preserve Host/origin/token checks, headers, escaping, redirects and security behavior on every response. Audits 3, 6 | Planned |
| 9o | Immutable validated settings | Normalize before freezing settings; keep accepted host/path behavior and caller compatibility. Map validation errors to the actual configuration field with constant safe text instead of reporting every failure as `CONDUCTOR_MCP`. Audit 9 | Planned |
| 9p | Event-log ownership and listing | Define and enforce append ownership across EventLog instances/processes so sequences cannot duplicate. Reduce repeated whole-log scans for listings and initial sequence discovery while retaining corruption detection and append-only records; specify cache invalidation and bounded resource use before implementation. Audit 9 | Planned |
| 9q | Behavior-based test organization | Consolidate phase-suffixed test files by module/behavior in small family-by-family specs, preserving collected cases, assertions, section assignments and coverage. Reconcile testing docs, conventions and architect templates so future given/coder test separation does not recreate `*_more.py` sprawl. Audit 7 | Planned |
| 9r | Broader lint gates | Introduce unused-argument and complexity checks after the module splits, with explicit thresholds and reviewed behavior-preserving repairs. No blanket ignores or per-file exemptions to hide large modules. Use the installed Ruff; no new dependency is assumed. Audit 9 | Planned |
| 10 | Coding pipeline | After audit remediation: coder and independent verifier adapters around external agents, the strict verdict parser (critical), automatic retry after FAIL (at most 2), escalation, commit and push as separately approved `write` actions. Persist and pass attempt/approved-implementation identity through State and `_ask_step`; only a verifier FAIL within that approved implementation skips renewed implementation approval. Any store schema change ships with a versioned migration and upgrade tests (audits 5, 6) | |
| 11 | Replay | Re-run a logged run with `ScriptedModel` from its event log; turn a real run into a regression test | |
| 12 | External domains: email, tasks and calendar | Email remains a separate domain. Tasks and calendar share one tasks domain over `docket mcp serve` on stdio: five `read` actions and six approved `write` actions, code-filled retry keys, bounded contracts, fake/schema compatibility checks and evaluation cases. Calendar reads require tasking stage 8 as well as its stage 6 MCP server. See the handoff plan below | Planned |
| 13 | Long-term memory | Preferences and past-thread summaries through LangGraph's store, optionally recalled by local embeddings, passed in as labelled context only | |
| 14 | Discord approvals and escalation answers | A third decision channel through the shared Discord service, with owner-checked presses, the same `conductor.decisions` and store, stale-step protection and first-decision-wins semantics. No Conductor bot or direct Discord connection; edits remain terminal/web. Replaces the notification backlog item. Depends on the shared service contract and explicit network/privacy design updates | Planned |

## Audit remediation plan (2026-11-17)

Owner direction: the audit findings are verified; integrate them into the next
phases. This plan accepts them without reopening the audit. Ordering, grouping
and keeping Phase 10's established number are architect decisions. Phase 9e was
specified in [the spec](phases/phase-09e-runtime-ownership-and-status.md) and
[its guide](verification/phase-09e-runtime-ownership-and-status.md), and is built
and verified (2026-11-18). The owner chose graph-free
checkpoint reads and generic 503 for malformed saved state on 2026-11-17. Later
remediation specs remain to be written and validated one or two phases ahead from
the actual predecessor, following the normal size limits. Split an oversized row before
writing given tests. In particular, 9q is a sequence of small test-family changes,
not permission for a whole-suite rewrite in one coding session; allocate unused
lettered phase ids after 9r for additional slices and update this build order.

The sequential build order above is the delivery order. The important dependencies
are: 9e before 9f/9h/9k; 9f and 9g before 9h; shared helpers 9i/9j before the
CLI/web splits; 9k–9n before 9q/9r; all remediation before Phase 10. Behavior
changes have failing-first tests; pure extractions retain public contracts and
meaningful regression assertions. Any remediation that changes the store schema must
include a versioned migration and upgrade tests at that point, rather than wait
for Phase 10. Extracted critical logic remains on the critical
coverage list. Synthetic offline tests and the existing acceptance gates apply.

| Verified finding | Disposition and completion evidence to require in its spec |
|---|---|
| 1: retained graph/services and expensive status reads | 9e: repeated status polling constructs no graph/model, releases services, and validates malformed checkpoint status/interrupts as `RunError` rather than casts or `KeyError` |
| 1: retained resumer threads/errors and shutdown | 9f: repeated completed jobs stay within a specified retention bound, active jobs remain protected, and shutdown is bounded with durable error handoff to 9h |
| 2: inconsistent tags parsing | 9g: doctor and model agree for a selected model when another entry is malformed; preserve explicit doctor/run timeout differences |
| 3: failed page resume and copied decision handlers | 9h recovery tests cover already-recorded decisions, duplicate POSTs, forbidden resumes and safe durable errors; 9n removes duplicated handler plumbing |
| 4: finance catalog duplication/growth | 9l: all tool/schema compatibility checks and tighter local bounds survive the split; fake and captured schemas remain independent checks |
| 5: supervisor size and lost failure codes | 9k: graph node/interrupt semantics and cause-code events are pinned; 9e covers malformed checkpoints |
| 5: unwired implementation attempt | Phase 10: verifier FAIL can retry only the same approved implementation within its cap; restart and rejection paths cannot bypass approval |
| 6: timestamps, ids, private files, Contract checks and request bounds | 9i/9j: migrate every listed caller with parity and permission tests; keep `contracts` independent |
| 6: CLI and web size/duplication | 9m/9n: command/output and response/security regression checks; shared decisions still go through policy |
| 6: store evolution | Phase 10: migration before the first schema change, preserving approvals, decisions, escalations and leases; leave the parallel approval/escalation methods alone until a real third record type justifies abstraction |
| 7: phase-suffixed tests contradict documentation | 9q: family-level collection comparison and unchanged behavior/coverage; update prospective naming rules and templates together |
| 8: stale architecture status and package tree | Corrected in this planning update to the built Phase 9d baseline; future phases update the affected layout when they ship |
| 9: misleading settings errors and mutable validated values | 9o: field-specific safe errors, normalization and mutation refusal |
| 9: uncapped HTTP response reads | 9g: bounded tags/chat reads reject oversize responses without echoing their content |
| 9: full event-log scans and duplicate sequence risk | 9p: synthetic multi-writer/reopen/corruption cases plus a listing/scan-cost regression check; preserve full corruption detection |
| 9: narrow Ruff rules | 9r: new rules pass with concrete repairs and no blanket suppression |

Keep the audit as the original evidence record. Its suggested exception-message
retention is constrained by `AGENTS.md`: store constant error text and allowlisted
codes/type labels plus identifiers, never arbitrary library exception messages.
Do not add general retry of model output, new model providers, real-service
checks, telemetry, new finance tools or dependencies as part of remediation.
The audit's positive findings remain constraints: approval revalidation, tracing
off, private SQLite sidecars and invalid-output escalation must keep their tests.

## Tasks and Discord handoff plan (2026-11-17)

Source: [Tasks app: what Conductor needs to know](handoffs/langgraph.md), written
2026-11-14. Incorporate its integration decisions here; its statement that tasking
has nothing built is historical, not a current readiness assertion. Before writing
an integration spec, check the owning project's current contracts and shipped
schemas. Tasking's roadmap places MCP in stage 6 and calendar reads in stage 8;
a stage-6 server alone does not establish calendar readiness. No live service is
needed for Conductor development or verification.

### Phase 12: tasks and calendar together

Keep email as a separate domain; do not create a separate calendar domain/server.
Specify Phase 12 in small slices: first code-filled arguments and runner context,
then task reads, approved writes, calendar reads once available, and evaluation
cases. Allocate the lettered ids when each spec is written; these are outcomes
and dependencies, not executable assignments.

| Handoff finding | Phase 12 requirement and verification target |
|---|---|
| Five reads | `list_tasks`, `get_task`, `list_proposals`, `list_events`, `check_availability` become `read` actions. Bound paging/ranges/results, check `readOnlyHint: true` and output schemas, and name failed calendar backends instead of silently omitting them |
| Six writes; Conductor approval is final | `create_task`, `change_deadline`, `plan_work_time`, `snooze_task`, `complete_task`, `cancel_task` become `write`, never `propose`. Each stops for Conductor approval; the approved call applies immediately without a second tasking approval. Creation uses source `agent` |
| No proposal approval tool | Listing proposals is allowed; no registered action accepts or approves a tasking proposal. Assert the action inventory excludes that capability |
| Code-generated `request_key` | Derive `<run id>:<step id>` in code for each write, stable across retries/restarts of that step and distinct for other steps. The planner cannot supply or override it. Define how Action declares injected fields, how runner context carries both ids, and how the tool check validates the full server input schema while the planner sees only model-supplied fields. Cover the current `StepRunner.run(action, args)` limitation explicitly |
| Unknown write outcome | Preserve structured `timeout`/`closed` visibility from 9k, ask before retrying, and resend the same key. Fake-server tests show one side effect after a lost response and retry; no automatic retry or new key that defeats deduplication |
| Deadlines and planned work | Send `date`, nullable `time`, and `time_zone`; a date without time means 17:00 in that zone, and the resulting deadline stays a fixed instant while travelling. Pin timezone/DST boundary behavior in synthetic cases. Select planned work time using availability first; specify how a later write is bound to that read without model-invented step-output references |
| Untrusted titles and local calendar data | Titles are plain text of at most 100 characters and treated as data in planner/answer prompts. Calendar event titles/times stay local, like finance results. Results use ISO times and ids; refusals are constant codes without echoed input |
| Transport | Configure `CONDUCTOR_MCP__TASKS` to launch `docket mcp serve` as a child over stdio. Do not call tasking's HTTP API on port 8767 or connect Conductor directly to Google, iCloud, Outlook or their credentials |
| Routing and evidence | Add task/reminder/deadline/calendar/schedule/free-time keyword rules with ambiguity tests against existing domains. Keep one domain per plan. Use a synthetic fake checked against saved server schemas, tighter local bounds, and fixed-date evaluation cases; evaluations execute no writes |

The injected-argument contract must be ready before registering task writes.
Do not simply add `request_key` to the planner schema to satisfy today's tool
check. Keep read-derived arguments explicit: the present planner does not consume
earlier step results, so availability-dependent writes require a specified data
flow or separate read then approved request, not an implicit replanning feature.

### Phase 14: Discord decision channel

Depends on the shared Discord service's published card/press contract, including
authentication, owner identity and delivery semantics. It can follow remediation
without waiting for the tasks domain; the service is an external prerequisite,
not something Conductor implements. Split channel contracts, card delivery and
press handling into small specs once that prerequisite exists.

- The shared service owns the bot token and Gateway connection. Conductor posts
  cards through its loopback interface and receives forwarded presses on
  loopback; Conductor runs no bot and makes no direct Discord connection.
- Cards represent both `ApprovalRequest` and `Escalation`, with the summary and
  exact arguments covered by the decision. Approval cards offer Approve/Reject;
  escalation cards offer Retry/Cancel. Edits stay in the terminal or web page.
- Add `discord` to the closed decision-channel contract (currently terminal/web),
  preserving compatibility with stored decisions. Every authenticated press also
  checks the owner's Discord user id before calling `conductor.decisions`.
- All three channels use the same store, policy revalidation and stale-steps
  digest. Test cross-channel races, repeated/old presses and non-owner presses;
  only the first valid decision wins. Resumes retain existing lease protection.
- Before implementation, update `AGENTS.md` and the architecture's network and
  privacy boundaries for this precise service interface and card payload. The
  existing loopback-only approvals page/model rules do not silently authorize a
  new HTTP client or sending sensitive arguments to Discord. Specify which exact
  arguments may leave the machine and refuse unsupported payloads; never send
  whole event logs, prompts, model replies or unrelated calendar/finance results.
- Pin safe card rendering of untrusted text, bounded payloads, authenticated
  callback refusal and service-unavailable behavior against fakes. Delivery retries
  must not record an approval or execute a step. No live Discord in acceptance.

This phase supersedes the old waiting-approval phone-notification backlog item:
the card is both notification and decision surface. It does not reopen the
already completed terminal/web phases or move tasks writes into the finance
proposal model. Exact service endpoints, card limits and callback authentication
are prerequisites to settle from the owning service contract, not guessed here.

## Backlog

- Moving to the Mac Studio: model choices per decision point, re-run the evaluation harness, compare consistency.
