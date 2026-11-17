# Codebase audit

Date: 2026-11-15. Scope: `src/conductor/`, `tests/`, and the docs a later change is likely to trust (`docs/architecture.md`, `docs/testing.md`). This is a static reading of the tree as of phase 9d (1006 tests recorded in `docs/progress.md`). No phase was implemented, and nothing here was run against Ollama or a live MCP server.

The project is in better shape than its size suggests. Decisions go through `decide()`, side effects go through `policy`, files under `data/` are created `0600`, the approvals page binds to loopback and sends a strict content policy, and tests outnumber production code by about two to one. The findings below are the places that will get expensive, or quietly wrong, as the code domain and more finance tools land.

Counts below are physical lines.

| Area | Files | Lines |
|---|---:|---:|
| `src/` | 51 | 6,252 |
| `tests/` | 106 | 14,059 |
| Production modules of 300 lines or more | 6 | see below |

## Findings

Severity is about the cost of leaving it: what breaks in a long-running `conductor web`, what sends a person down a dead end, and what the next phase is likely to copy.

### 1. High: the web process keeps every graph it builds

`build_graph` stores the run's services in a process-wide dict and never removes them.

```115:134:src/conductor/graph/supervisor.py
_SERVICES: dict[int, Services] = {}
...
    compiled = graph.compile(checkpointer=checkpointer)
    _SERVICES[id(compiled)] = services
    return compiled
```

`start_run` reads that dict back (`supervisor.py` line 142). The compiled graph already closes over the same services, so the dict is a second owner. Python reuses an id only after the object is gone, so this does not point a live graph at the wrong services. It does keep the `Services` object (registry, store, log, model, runner) for the life of the process.

`conductor web` builds a new runtime for every view of a run, including the page that refreshes every five seconds while a resume is in progress:

```323:330:src/conductor/web/app.py
    @api.get("/runs/{run_id}")
    def run(run_id: str, request: Request) -> Response:
        ...
        try:
            with runtime.open_runtime(settings) as opened:
                found = runtime.state(opened, run_id)
```

Each of those calls compiles a graph, opens `checkpoints.db`, and constructs an `OllamaModel`, then drops the graph and leaves the services dict entry behind. `Resumer` has the same shape: `_threads` and `_errors` in `web/jobs.py` grow by one entry per run and are never pruned, and the worker threads are not daemons, so a model call (default timeout 300 seconds) can keep the process up after the server has been asked to stop.

Reading a run's status does not need a compiled graph. A later change should drop the global dict (pass the log into `start_run` with the graph) and read checkpoint state without `build_graph`.

### 2. Medium: two parsers of `/api/tags`, and they disagree

Doctor and the model client both GET `/api/tags` through a proxy-free opener, and each parses the body itself.

- `llm/tags.py` (`fetch_models`) keeps a model whose digest is missing or not 64 hex characters, and stores `None`.
- `llm/ollama.py` (`_entry`) raises `ModelUnavailable("bad_answer")` when any entry in the list fails that check, before it looks for the configured model.

`diagnostics.check_ollama` only fails the digest check for the model it was asked about. One unrelated model with a bad digest leaves `conductor doctor` green and turns every `decide()` into `model_unavailable`. Timeouts differ too: doctor uses 3 seconds, runs use `CONDUCTOR_MODEL_TIMEOUT`.

There is one Ollama. One function should parse `/api/tags`, and both callers should use it. A bad entry should affect that entry, not the whole list.

### 3. Medium: a failed resume on the page has no second chance

The page records a decision, then resumes in a background thread (`web/app.py` `_record_approval` and `_record_escalation`, `web/jobs.py` `_run`). If that resume raises anything other than `RunError` or `ToolCheckFailed`, the thread stores the fixed text `"the resume failed"` and drops the exception. Nothing is written to the event log.

The run page prints that sentence and, once the thread has finished, stops refreshing (`templates/run.html`). It has no control that calls resume again. The approval or escalation is already decided, so its page no longer shows a form. The run is still waiting on its interrupt. The terminal command `conductor resume` can continue it. The page cannot.

The same two record functions are copies of each other (open a store, call `decisions`, map six exception types, start a resume, redirect). A change to the failure path has to be made twice.

### 4. Medium: `domains/finance.py` is a hand-written catalog that will keep growing

552 lines, almost all of them one Pydantic model per finances tool, then the same facts again as `Action` descriptions. Reads and proposals already have helpers (`_read`, `_propose`). The file is still one module, imported whole, and it is the planner's schema: `planning/plan.py` rebuilds a discriminated union of every action on every plan.

The same 31 tools exist again in `tests/fake_finances_server.py` (424 lines) and again as captured schemas in `tests/finances_tools.json`. The tests compare the fake server with the captured schemas, which is the right check, and it still means every new tool is edited in three places that do not share types.

Split reads and proposals into two modules before the next finances addition. Leave the models hand-written. Generating them from the captured JSON would hide the bounds this project deliberately sets tighter than the server.

### 5. Medium: the supervisor graph is one 482-line closure, and the coder retry is not wired

`graph/supervisor.py` is the right place for the graph, and the node split (`ask_*` writes the request, `wait_*` only reads, then `interrupt`) matches the LangGraph rule that a resumed node runs from its first line. The file is still where the next hard feature has to go.

`policy.needs_approval` treats `implement` as approval-free when `attempt` is greater than 1. Nothing in the graph passes `attempt`. `State` has no attempt field, and `_ask_step` calls `policy.step_request` with the default of 1. The exception the architecture describes (a coder retry after a verifier FAIL, inside an implementation the person already approved) is policy-only. Phase 10 will look implemented if it only calls `needs_approval`, and it will still ask again.

`_run_step` (44 lines) also records every runner failure as `"error": "tool_error"` in the event payload. The cause code (`timeout`, `closed`, and the rest) is only inside the escalation's detail string. A write whose outcome is unknown is supposed to be visible before the person retries it. The detail has the code; the event row does not.

`run_state` and `resume_run` use `cast` for status, reply, and the waiting id. A checkpoint that is waiting with neither `approval_id` nor `escalation_id` raises `KeyError` rather than `RunError`.

### 6. Medium: command and page code repeat the same small decisions

These are short, and each copy is locally obvious. Together they are how a privacy or formatting rule drifts.

| Repeated decision | Copies |
|---|---|
| Format an instant as `%Y-%m-%dT%H:%M:%SZ` | `views.py`, `cli/main.py` (`_when` and a third literal in `list_runs`), `web/app.py` |
| Accept a 32-hex id | `contracts/base.py` `Id`, `store.py`, `web/app.py`, and `events.py` (same shape, unanchored, used with `fullmatch`) |
| Create a directory `0700` and a file `0600` | `events.py`, `store.py`, `runtime.py`, `mcp_client/client.py`, `evals/report.py`. `diagnostics.py` creates the data folder and does not `chmod` it after `mkdir` |
| `isinstance(value, type) and issubclass(value, Contract)` | `registry.py`, `llm/points.py` |
| "1 to 2000 characters" for a request | `routing/route.py` (the message and a `Field`), `graph/supervisor.py`, `planning/answer.py`, `planning/plan.py`, `evals/cases.py` |

`cli/main.py` is 512 lines and holds every command. `approve` / `reject` / `edit` and `retry` / `cancel` are the same skeleton: load the row, optionally confirm, call `decisions`, print a line, maybe resume. `web/app.py` is 394 lines, of which `create_app` is 198 (line 197 to the end of the file) with the routes nested inside it. Both files are still readable. They will not stay that way once a third channel or the code-domain commands arrive. Split the Typer groups (`approvals`, `escalations`, `eval`, `web`) into modules, and move the nested route bodies in `create_app` out to named functions the way `_home` and `_detail` already are.

`store.py` (351 lines) repeats the same shape for approvals and escalations: insert, fetch, list the open ones, update a JSON column, refuse a second decision. That parallel is easier to follow than a generic table helper, and it should stay until a real third record type appears. What it does not have is a migration. Any `user_version` other than 1, or a version-1 file that is not empty, raises `StoreError`. The next column (an attempt count, a coder task) needs a version bump and a written migration, not another table pasted beside the first two.

### 7. Medium: tests for one module are split by phase, under names the testing doc forbids

`docs/testing.md` says a module's tests live in `test_<module>.py`. The tree has 35 files named `*_more.py` (`test_store_more.py`, `test_finance_more.py`, `test_supervisor_more.py`, and so on), plus further splits such as `test_finance_proposals_more.py`. They exist so a later phase could add cases without rewriting the earlier file. The result is that the tests for one behavior are spread across files whose names say when they were added, not what they cover.

`tests/sections.toml` only distinguishes `scripts`, `cli`, and everything else as `core`, so the split is not load-bearing for `scripts/check.py`. Folding them back is a large diff with no behavior change. Do it at a phase boundary, one module at a time, rather than letting phase 10 add `test_code_more.py`.

### 8. Low: docs the next agent is told to read describe a project that has not been built

`AGENTS.md` says to read `docs/architecture.md` first. That file still opens with "Status (2026-10-25): designed; nothing built yet. Phase 1 is specified." The package layout is marked "planned" and shows `registry/` and `store/` as packages. Both are single modules (`registry.py`, `store.py`), and `plancheck.py` sits beside them. The dependency arrow and the privacy rules in that file are still accurate. The status and the tree are not, and a coding agent that trusts them will look for modules that do not exist.

### 9. Low: a few sharp edges that are safe today and easy to get wrong later

- `get_settings` turns every Pydantic `ValidationError` into `CONDUCTOR_MCP: must map server names to command lines` (`config.py` lines 77 to 80). That message is right for the one field that currently fails inside the model. A new typed field will report the wrong variable.
- `Settings` is not frozen, and `get_settings` assigns `data_dir` and `ollama_host` after validation. Callers can change a setting the validator already accepted.
- `OllamaModel._read` and `tags.fetch_models` call `response.read()` with no cap. Both talk only to loopback. A broken local server can still force a large allocation.
- `EventLog.runs` parses every line of every run to print a list, and the first `append` for a run in a new `EventLog` parses the whole file again to learn the next `seq`. Fine at household scale. The in-memory counter is also per `EventLog` instance, so two writers on one file would mint duplicate sequence numbers. The lease makes that unlikely for a run. The eval harness writes a different folder and does not take a lease.
- Ruff is limited to `E`, `F`, `I`, `B`, and `UP`. Unused arguments (the `settings` parameter on many CLI closures), complexity, and the duplicated helpers above are invisible to `scripts/check.py`. Widening the selection is a separate change. It should not be done by silencing new rules in the large files.

## What is already in good shape

Worth leaving alone while the items above are fixed.

- Layering holds. `contracts` does not import the rest of the project. `decide()` is the only model call. Routing rules, plan checks, and approval are code.
- Invalid model output becomes an escalation. The client does not retry a reply that fails validation.
- A decision is applied in `decisions.py` and applied again from the store when the graph resumes. The second check is what makes a stale or edited approval fail closed.
- The approvals page checks the `Host` header, sets `script-src 'none'`, uses autoescape, and matches a form token with `hmac.compare_digest`. A missing `Origin` is allowed through when the token matches. That is acceptable on loopback. It is the weakest of those checks, and it is not a hole by itself.
- Private files are created with `os.open(..., 0o600)`. On this machine SQLite's WAL and shared-memory sidecars for `checkpoints.db` inherit mode `0600` even with umask `022`, and `tests/integration/test_runtime.py` locks that in. The code never `chmod`s the sidecars itself. Keep that test.
- LangSmith tracing is forced off at import and again around every `invoke`.
- Coverage is branch coverage with a 90% floor, and `scripts/critical_modules.txt` lists the modules where a bug would skip an approval or drop a record.

## Suggested order

1. Remove `_SERVICES` and stop compiling a graph to read run status. Prune finished resumer threads.
2. Use one `/api/tags` parser for doctor and `decide()`.
3. On the run page, allow another resume after a recorded decision, and keep the real failure (type and message that do not include the request or the reply) instead of `"the resume failed"`.
4. Put the timestamp format, the id check, and the private-file creation in one module before another caller copies them.
5. Split `domains/finance.py` into reads and proposals, and split `cli/main.py` by command group, before phase 10.
6. When phase 10 adds the coder retry, thread `attempt` through `State` and `_ask_step`. Calling `needs_approval` alone will still ask the person every time.
7. Correct the status and the package tree in `docs/architecture.md`.
8. Collapse `*_more.py` files per module at a phase boundary, not in the middle of a feature.

No code was changed for this audit except this file.
