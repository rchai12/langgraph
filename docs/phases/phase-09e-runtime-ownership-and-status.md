# Phase 9e: runtime ownership and status reads

## Goal

Remove the graph-services retention leak and read a saved run without building an
execution runtime. Preserve the existing approval and resume behavior, and refuse
malformed saved status safely. This implements audit findings 1 (graph ownership
and status polling) and the checkpoint-validation part of finding 5.

Decided with the owner (2026-11-17):
- Use a **graph-free checkpoint reader**, supporting Conductor's sequential graph
  and pinning its checkpoint-format assumptions with compatibility tests.
- A saved checkpoint whose displayed state cannot be read or validated yields a
  **generic 503** on the run page. A missing run remains 404.

Decided by the architect:
- Pass the event log explicitly to `start_run`, rather than storing services in
  a global, weak map, graph attribute or cache.
- Share one pure decoder between graph-backed and standalone status reads.
- Open existing checkpoints through SQLite's read-only URI and an explicit read
  transaction. Never initialize storage during a status read.
- Support the installed format 4 and fixed sequential graph only. Unknown formats,
  parallel work and sends are safely unavailable, not guessed or repaired.

## Read first

Read `AGENTS.md`, `docs/architecture.md` (supervisor graph, state/storage and privacy),
`docs/phase-conventions.md`, `docs/testing.md`, and the Phase 9d progress entry.
Inspect `graph/supervisor.py` (`build_graph`, `start_run`, `run_state`, `resume_run`),
`runtime.py` (`open_runtime`, `ask`, `state`), `web/app.py` (GET `/runs/{run_id}`),
and the five predecessor test files in the given patch below.

## Starting state

Phase 9d is built and independently verified: **N = 1006**. Planning baseline:
`fcd47b7d7027266826f1a680807a86c122ea5a16`. This phase's final spec and guide must
be committed before implementation; use that planning commit as the coder's
actual clean baseline. **Sections: cli,core.** No new dependency.

The architect collected 30 given cases in a fresh predecessor clone. On that
predecessor: 29 failed and 1 passed. The passing case is the existing invalid-id
web guard. Missing APIs were also represented by names-only stubs to check that
refusal tests do not pass on `NotImplementedError`. No feature was implemented.

## Scope

| Path | Change |
|---|---|
| `src/conductor/graph/status.py` | new critical decoder, existing display types/constants moved here |
| `src/conductor/graph/supervisor.py` | remove global owner, explicit log argument, status delegation; preserve nodes |
| `src/conductor/runtime.py` | pass the log in `ask`; new graph-free `read_state` |
| `src/conductor/web/app.py` | standalone reader and generic unavailable response on the run GET only |
| `scripts/critical_modules.txt`, `docs/testing.md` | exact given additions below |
| `tests/unit/test_checkpoint_status.py` | given, 14 cases |
| `tests/integration/test_graph_ownership.py` | given, 3 cases |
| `tests/integration/test_run_status.py` | given, 9 cases |
| `tests/e2e/test_web_run_status.py` | given, 4 cases |
| `tests/integration/test_supervisor.py`, `tests/integration/test_supervisor_more.py`, `tests/integration/test_answer_too_large.py`, `tests/unit/test_mcp_runner_more.py`, `tests/e2e/test_web_decide_more.py` | only the exact given migration edits below |
| `tests/unit/test_checkpoint_status_cases.py`, `tests/integration/test_run_status_cases.py`, `tests/e2e/test_web_run_status_cases.py` | coder-owned behavior/coverage cases |
| `docs/progress.md` | one Phase 9e entry |

All new unit/integration tests fall in `core`; `test_web_run_status*.py` also falls
in `core` under today's section patterns. `cli` is run first too to catch command
regressions. No section mapping change is needed. The verifier separately writes
`docs/reviews/phase-09e-runtime-ownership-and-status.md`.

## Out of scope

Background thread/error retention and shutdown (9f); another web Resume control
(9h); graph-node extraction and failure-code event changes (9k); general storage
helpers; new settings/dependencies; any schema migration or checkpoint rewrite;
new node scheduling, subgraphs, parallelism or model calls; cached status graphs;
changing commands, templates, prompts, approval policy, leases or retry rules.

## Dependencies

None new. Use the existing environment; do not install, recreate or upgrade it.

## Design

### Part 1: graph lifetime and public contracts

Move `NODES`, `RunStatus`, `RunError` and the frozen `RunState` dataclass unchanged
from `graph/supervisor.py` to `graph/status.py`. Re-export them from supervisor by
imports so existing callers retain the same names and class identity. `RunState`
keeps `run_id`, `status`, `approval_id=None`, `escalation_id=None`, `reply=None`,
`note=""`, `stopped_at=None`. Keep the existing NODES tuple and order.

Add `RunStateUnavailable(RunError)` in `graph/status.py`. Its raised message is
exactly `run <run_id> state is not available`. Missing runs raise `RunError` with
exactly `no run <run_id>`. Neither message includes checkpoint or library content.

Change the signature to:

```python
def start_run(graph: CompiledStateGraph, request: str, *, run_id: str, log: EventLog) -> RunState:
    ...
```

Keep request/duplicate-run validation and event ordering. Append RUN_STARTED to
that supplied log before invoking the graph. `runtime.ask` supplies `runtime.log`.
Remove `_SERVICES` and its assignments/lookups completely. No replacement module
owner, cache, weak map or graph attribute may hold Services or the start log.
The existing node closures already own their services for the graph's lifetime.

### Part 2: pure sequential checkpoint decoder

Add `checkpoint_state(saved: CheckpointTuple | None, run_id: str) -> RunState` in
`graph/status.py`. Validate `run_id` with `events.check_run_id` before examining
saved data, preserving its constant ValueError. `None` means a missing run.
Never mutate the checkpoint, writes, interrupt objects or nested values.

The relevant format is `saved.checkpoint['v'] == 4` (exact integer), a dict
`channel_values`, an empty/absent `pending_sends`, and `pending_writes` containing
triples `(task_id, channel, value)`. Ignore unrelated top-level metadata and
ordinary state values; do not revalidate the request, plan, route or tool results.
Their contents must never be printed in a refusal. This is a status projection,
not a second execution engine or a general LangGraph checkpoint reader.

The following rules fully define the projection:

1. A live target is a key `branch:to:<node>` in channel_values, or `__start__`
   before the first node. Its stored value is not a truth flag (normally None).
   Accept only the existing NODES or `__start__`; more than one target, an unknown
   branch target, a nonempty `pending_sends`, or malformed containers is unavailable.
2. Pending writes must belong to at most one non-null task. A task id is a string;
   LangGraph's null task id is the all-zero UUID. Null-task `__resume__` writes are
   bookkeeping and do not complete a task or decide an approval. Ignore
   `__scheduled__` and `__resume__` task bookkeeping. Reject unknown reserved
   channels, `__pregel_tasks` sends, malformed rows and multiple non-null task ids.
3. Ordinary writes to the existing State fields and `branch:to:<node>` are a
   completed task's output. `__no_writes__` also marks completion. For a completed
   task, consume the old live target, overlay ordinary state fields into a copy,
   and derive the next target from that task's branch writes. More than one next
   target is unavailable. These completed writes supersede stale `__interrupt__`
   and `__error__` entries for the same task. Do not return its old waiting id.
4. Otherwise a nonempty `__interrupt__` write must contain exactly one LangGraph
   `Interrupt`. Its value is a dict with exactly one key: `approval_id` at
   `wait_approval`, or `escalation_id` at `wait_escalation`. The value must be 32
   lowercase hex characters. Return waiting with only that reference set. Missing,
   mismatched, duplicate or malformed interrupts are unavailable. An `__error__`
   entry is opaque: never expose or inspect its exception text.
5. Without a live interrupt, a remaining target means stopped at that target,
   even when stale terminal fields exist. Do not infer waiting from State.pending
   or escalation_id alone. Busy is still a separate property of the web resumer.
6. With no target left, require status in `done`, `rejected`, `cancelled`. Reply
   is absent/None or a string of 1–2000 characters with nonblank content; `done`
   requires that string. Note is absent/None (normalize to empty) or a string.
   Do not coerce numbers, lists or booleans. Return only the terminal display
   fields; approval_id, escalation_id and stopped_at are None.

Unavailable format/shape/status raises `RunStateUnavailable` with the fixed
message. Do not use Pydantic exception text or arbitrary `str(error)`.

`run_state(graph, run_id)` keeps its signature, validates the id, obtains the
latest root checkpoint with `graph.checkpointer.get_tuple` and calls this decoder.
No graph invocation occurs. Normalize retrieval/deserialization failures to
RunStateUnavailable, preserving missing-run and bad-id distinctions. Keep
`runtime.state` as the compatibility wrapper and `resume_run`'s allowed stopped
nodes, decision lookup and policy revalidation unchanged. An unavailable state
must stop a resume before `_invoke` or any store decision lookup.

A pending successful node's next target is reported as stopped until the next
checkpoint is written. This intentionally closes the old KeyError window between
pending writes and checkpoint advancement. Read code never advances the graph.

### Part 3: read-only standalone access

Add `runtime.read_state(settings: Settings, run_id: str) -> RunState`.
Validate the id first. A missing checkpoints_path means missing run and creates
nothing: no parent directory, database, runs folder or store. Open an existing
path via `settings.checkpoints_path.as_uri() + '?mode=ro'`, with `uri=True` and
`check_same_thread=False`. Start a read transaction (`BEGIN`) so checkpoint and
pending-write SELECTs share one SQLite snapshot. Close the connection on every
success and failure. Do not cache a connection, graph, result or runtime.

Use SqliteSaver deserialization, not custom SQL decoding of its serialized blobs.
Its normal setup performs DDL; bypass setup for this existing-schema read by
setting the instance's `is_setup=True`. This phase supports the current
checkpoints/writes schema including task_path; an absent/incompatible schema is
unavailable, not initialized or migrated. Do not call `setup`, change journal
mode, touch schema/user_version or write checkpoint state. SQLite sidecar handling
is SQLite's own; do not use `immutable=1`, which could ignore a live WAL.

Read the latest root tuple using configurable thread_id=run_id and
checkpoint_ns="", then call checkpoint_state. Map SQLite/open/serde failures to
RunStateUnavailable; do not map a successfully read missing tuple to unavailable.
The decoder's own unavailable error passes through unchanged. No run lease is
needed or taken for this read. No call to `open_runtime`, `build_graph`, models,
registry, domain runner, Store, EventLog or ids.new_id is allowed on this path.

### Part 4: the run page

GET `/runs/{run_id}` keeps the current invalid-id 404 guard and calls
`runtime.read_state(settings, run_id)` directly. `RunStateUnavailable` maps to
503 and exact plain text `The run state is not available`; other RunError
(missing run) maps to 404 `Not found`. Do not print exception text. Keep all
middleware headers, escaping, links, refresh/busy/error presentation and existing
forms unchanged. GET must neither resume nor record a decision.

## Facts

Checked locally on 2026-11-17 from installed source and small synthetic spikes:

- Installed langgraph 1.2.20, langgraph-checkpoint 4.3.1, and SQLite saver 3.1.3.
  The base empty-checkpoint helper says v2, but **the actual supervisor writes v4**.
  The synthetic fixtures therefore use v4. Do not infer format from empty_checkpoint.
- Waiting runs store a `branch:to:wait_*` key plus an Interrupt in pending writes;
  stopped nodes store their branch and opaque `__error__` pending write; terminal
  checkpoints have status/reply and no live branch. Nodes return one destination.
- `put_writes` persists node output before the next checkpoint. `finish` uses
  `__no_writes__`. A synthetic echo run recorded all nine intermediate writes.
- SqliteSaver.get_tuple performs checkpoint and pending-write SELECTs and calls
  setup via cursor. An existing database can be read through an escaped URI
  containing spaces, # and ? with setup bypassed, without changing its main bytes.
- Existing direct start callers are the four test files in the patch and
  runtime.ask. One older web test patches open_runtime/state instead of the new
  standalone seam. All explicit migration edits are given below.
- The probe's independent stage table self-checks; its full restart harness was
  exercised against the existing execution reader to validate later assertions.
  On the predecessor the real probe reaches `FAILURES 2`, without stopping.

## Requirements

- **R1:** graphs own services only through their existing closures; releasing a
  graph releases services/models, with no replacement registry or cache.
- **R2:** start_run takes the explicit log; validation and RUN_STARTED order stay
  intact; all callers use the supplied log without weakening previous assertions.
- **R3:** checkpoint_state implements the sequential projection above, including
  pending output, stale interrupts, errors and safe format/shape refusal.
- **R4:** run_state/runtime.state share validated status and refuse unavailable
  state before resume can inspect a decision or invoke a node.
- **R5:** read_state opens only existing checkpoints read-only, uses a consistent
  SQLite snapshot, closes resources and constructs no execution services.
- **R6:** GET uses that reader, distinguishes generic 503 from missing 404, and
  preserves the page's security/presentation and read-only behavior.
- **R7:** given tests and migration edits stay exact; only Scope paths change;
  no later phase, dependency, schema change or real service is introduced.
- **R8:** all touched/new critical modules keep 100% line and branch coverage;
  append the exact Phase 9e progress entry and validate reports.

## Given edits

Apply this exact patch from the repository root (save outside the repository).
No other predecessor test edits are allowed. The patch also adds the critical
module to its list and documentation. It does not change any assertion or count.

```text
--- a/tests/integration/test_supervisor.py
+++ b/tests/integration/test_supervisor.py
@@ -90,7 +90,7 @@
         )

     def start(self, request: str) -> RunState:
-        return start_run(self.graph, request, run_id=RUN)
+        return start_run(self.graph, request, run_id=RUN, log=self.log)

     def resume(self) -> RunState:
         return resume_run(self.graph, self.store, RUN)
--- a/tests/integration/test_supervisor_more.py
+++ b/tests/integration/test_supervisor_more.py
@@ -86,7 +86,7 @@
         )

     def start(self, request: str) -> RunState:
-        return start_run(self.graph, request, run_id=RUN)
+        return start_run(self.graph, request, run_id=RUN, log=self.log)

     def resume(self) -> RunState:
         return resume_run(self.graph, self.store, RUN)
--- a/tests/integration/test_answer_too_large.py
+++ b/tests/integration/test_answer_too_large.py
@@ -47,7 +47,7 @@
         ),
         InMemorySaver(),
     )
-    state = start_run(graph, "demo: say hi", run_id=RUN)
+    state = start_run(graph, "demo: say hi", run_id=RUN, log=log)
     assert state.status == "waiting" and state.escalation_id is not None
     stored = store.escalation(state.escalation_id).escalation
     assert stored.kind == "answer_too_large"
--- a/tests/unit/test_mcp_runner_more.py
+++ b/tests/unit/test_mcp_runner_more.py
@@ -114,11 +114,12 @@

 def _start(folder: Path, registry: Registry, runner: object):
     store = Store(folder / "conductor.db")
+    log = EventLog(folder / "runs")
     graph = build_graph(
         Services(
             registry=registry,
             store=store,
-            log=EventLog(folder / "runs"),
+            log=log,
             model=ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))]),
             model_name="test-model:1b",
             runner=runner,  # type: ignore[arg-type]
@@ -126,7 +127,7 @@
         InMemorySaver(),
     )
     request = "lab: go" if registry.names == ("lab",) else "demo: hi"
-    return start_run(graph, request, run_id="f" * 32)
+    return start_run(graph, request, run_id="f" * 32, log=log)


 def _spend(outcome: ToolOutcome | McpUnavailable):
--- a/tests/e2e/test_web_decide_more.py
+++ b/tests/e2e/test_web_decide_more.py
@@ -1,4 +1,3 @@
-from contextlib import contextmanager
 from datetime import UTC, datetime
 from pathlib import Path

@@ -193,12 +192,7 @@
         "5" * 32: RunState(run_id="5" * 32, status="waiting", escalation_id="e" * 32),
     }

-    @contextmanager
-    def open_runtime(settings: object, *, model: object = None) -> object:
-        yield None
-
-    monkeypatch.setattr(runtime, "open_runtime", open_runtime)
-    monkeypatch.setattr(runtime, "state", lambda opened, run_id: states[run_id])
+    monkeypatch.setattr(runtime, "read_state", lambda settings, run_id: states[run_id])
     page = _page()
     done = page.get(f"/runs/{'1' * 32}").text
     assert "done" in done
--- a/scripts/critical_modules.txt
+++ b/scripts/critical_modules.txt
@@ -13,6 +13,7 @@
 planning/plan.py
 planning/answer.py
 graph/supervisor.py
+graph/status.py
 runtime.py
 mcp_client/client.py
 mcp_client/check.py
--- a/docs/testing.md
+++ b/docs/testing.md
@@ -39,6 +39,7 @@
 - `planning/plan.py` (the planner's schema from the registry, and every way planning escalates; Phase 5b)
 - `planning/answer.py` (the reply from the results, and every way it escalates; Phase 5b)
 - `graph/supervisor.py` (no step with a side effect runs without its own approval; Phase 5c)
+- `graph/status.py` (validated checkpoint status and safe refusals; Phase 9e)
 - `runtime.py` (one process per thread at a time, and private checkpoint files; Phase 5d)
 - `mcp_client/client.py` (what a tool server receives, and every way it can fail; Phase 6a)
 - `mcp_client/check.py` (a tool action runs only on the tool it says, and a `read` action only on a read-only tool; Phase 6b)
```

## Given tests

**30 cases** in four files, counting parameter rows. Copy each embedded file to
its named path exactly. Given APIs are imported inside checks so missing feature
names fail the check rather than break collection. No given file may be altered.

`tests/unit/test_checkpoint_status.py` — 14 cases:

```python
import copy
from importlib import import_module

import pytest
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.types import Interrupt

RUN = "a" * 32
APPROVAL = "b" * 32
ESCALATION = "c" * 32


def saved(values: dict, writes: list | None = None, version: int = 4) -> CheckpointTuple:
    return CheckpointTuple(
        {"configurable": {"thread_id": RUN}},
        {"v": version, "channel_values": values, "pending_sends": []},
        {},
        pending_writes=writes or [],
    )


def api():
    return import_module("conductor.graph.status")


@pytest.mark.parametrize("field", ["approval_id", "escalation_id"])
def test_valid_interrupt_is_waiting(field: str) -> None:
    module = api()
    value = APPROVAL if field == "approval_id" else ESCALATION
    node = "wait_approval" if field == "approval_id" else "wait_escalation"
    record = saved(
        {f"branch:to:{node}": None}, [("task", "__interrupt__", [Interrupt({field: value})])]
    )
    before = copy.deepcopy(record)
    assert module.checkpoint_state(record, RUN) == module.RunState(RUN, "waiting", **{field: value})
    assert record == before


def test_completed_pending_writes_override_an_old_interrupt() -> None:
    module = api()
    record = saved(
        {"branch:to:wait_approval": None},
        [
            ("task", "__interrupt__", [Interrupt({"approval_id": APPROVAL})]),
            ("task", "pending", None),
            ("task", "branch:to:ask_step", None),
        ],
    )
    assert module.checkpoint_state(record, RUN) == module.RunState(
        RUN, "stopped", stopped_at="ask_step"
    )


def test_finish_pending_no_writes_is_terminal() -> None:
    module = api()
    record = saved(
        {"branch:to:finish": None, "status": "done", "reply": "Done."},
        [("task", "__no_writes__", None)],
    )
    assert module.checkpoint_state(record, RUN) == module.RunState(RUN, "done", reply="Done.")


@pytest.mark.parametrize(
    "record",
    [
        saved({"status": "SYNTHETIC-SECRET"}),
        saved({"status": "done", "reply": 5}),
        saved({"status": "rejected", "note": ["SYNTHETIC-SECRET"]}),
        saved({"branch:to:wait_approval": None}, [("t", "__interrupt__", [Interrupt({})])]),
        saved(
            {"branch:to:wait_approval": None},
            [
                (
                    "t",
                    "__interrupt__",
                    [Interrupt({"approval_id": APPROVAL, "escalation_id": ESCALATION})],
                )
            ],
        ),
        saved(
            {"branch:to:wait_approval": None},
            [("t", "__interrupt__", [Interrupt({"approval_id": "B" * 32})])],
        ),
        saved({"branch:to:plan": None, "branch:to:answer": None}),
        saved({"status": "done", "reply": "Done."}, version=99),
        saved({"branch:to:plan": None}, [("t", "__pregel_tasks", "SYNTHETIC-SECRET")]),
        saved({"branch:to:plan": None}, [("t1", "status", "done"), ("t2", "status", "cancelled")]),
    ],
    ids=[
        "status",
        "reply",
        "note",
        "missing-id",
        "two-ids",
        "invalid-id",
        "parallel",
        "version",
        "task-send",
        "two-tasks",
    ],
)
def test_malformed_state_is_safely_refused(record: CheckpointTuple) -> None:
    module = api()
    with pytest.raises(module.RunStateUnavailable) as raised:
        module.checkpoint_state(record, RUN)
    assert str(raised.value) == f"run {RUN} state is not available"
    assert "SYNTHETIC-SECRET" not in str(raised.value)
```

`tests/integration/test_graph_ownership.py` — 3 cases:

```python
import gc
import itertools
import weakref
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor import clock, ids
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import Services, build_graph, start_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from conductor.runtime import DemoRunner
from conductor.store import Store

RUN = "a" * 32


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def make_graph(folder: Path):
    log = EventLog(folder / "runs")
    services = Services(
        Registry((demo.DOMAIN,)),
        Store(folder / "conductor.db"),
        log,
        ScriptedModel(
            [
                ScriptedReply(
                    "plan", ModelReply(content='{"steps":[{"action":"echo","args":{"text":"hi"}}]}')
                ),
                ScriptedReply("answer", ModelReply(content='{"reply":"Done."}')),
            ]
        ),
        "test-model",
        DemoRunner(),
    )
    return build_graph(services, InMemorySaver()), log, weakref.ref(services)


def test_services_are_released_with_the_graph(tmp_path: Path) -> None:
    graph, log, reference = make_graph(tmp_path)
    gc.collect()
    assert reference() is not None
    del graph
    gc.collect()
    assert reference() is None
    assert log.runs() == []


def test_start_records_through_the_explicit_log(tmp_path: Path) -> None:
    graph, log, _ = make_graph(tmp_path / "graph")
    supplied = EventLog(tmp_path / "start")
    found = start_run(graph, "demo: say hi", run_id=RUN, log=supplied)
    assert (found.status, found.reply) == ("done", "Done.")
    events = supplied.read(RUN)
    assert [(e.kind, e.payload) for e in events] == [
        (EventKind.RUN_STARTED, {"request": "demo: say hi"})
    ]
    assert EventKind.RUN_STARTED not in [e.kind for e in log.read(RUN)]


def test_many_graphs_do_not_retain_services(tmp_path: Path) -> None:
    references = []
    for index in range(12):
        graph, _, reference = make_graph(tmp_path / str(index))
        references.append(reference)
        del graph
    gc.collect()
    assert all(reference() is None for reference in references)
```

`tests/integration/test_run_status.py` — 9 cases:

```python
import itertools
from datetime import UTC, datetime

import pytest

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import answer_escalation, decide_approval
from conductor.graph.supervisor import RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError

NOTE = '{"steps":[{"action":"note","args":{"title":"Milk"}}]}'
ECHO = '{"steps":[{"action":"echo","args":{"text":"hi"}}]}'
REPLY = '{"reply":"Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def model(*rows: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(point, ModelReply(content=text)) for point, text in rows])


def forbid_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("status read constructed execution services")

    for name in (
        "open_runtime",
        "build_graph",
        "OllamaModel",
        "Store",
        "EventLog",
        "Registry",
        "DomainRunner",
    ):
        monkeypatch.setattr(runtime, name, forbidden)
    monkeypatch.setattr(ids, "new_id", forbidden)


def test_waiting_status_uses_only_checkpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
        expected = runtime.ask(opened, "demo: note Milk")
        opened.store.acquire(expected.run_id, "e" * 32)
    before = settings.checkpoints_path.read_bytes()
    forbid_execution(monkeypatch)
    for _ in range(12):
        assert runtime.read_state(settings, expected.run_id) == expected
    assert settings.checkpoints_path.read_bytes() == before


@pytest.mark.parametrize("terminal", ["done", "rejected", "cancelled"])
def test_terminal_status_survives_closed_runtime(terminal: str) -> None:
    settings = get_settings()
    if terminal == "done":
        with runtime.open_runtime(
            settings, model=model(("plan", ECHO), ("answer", REPLY))
        ) as opened:
            expected = runtime.ask(opened, "demo: say hi")
    elif terminal == "rejected":
        with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
            waiting = runtime.ask(opened, "demo: note Milk")
            decide_approval(
                opened.store,
                opened.registry,
                waiting.approval_id,
                "reject",
                channel="terminal",
                decided_by="owner",
                note="not today",
            )
            expected = runtime.resume(opened, waiting.run_id)
    else:
        with runtime.open_runtime(settings, model=model(("plan", '{"steps":[]}'))) as opened:
            waiting = runtime.ask(opened, "demo: do something")
            answer_escalation(
                opened.store,
                waiting.escalation_id,
                "cancel",
                channel="terminal",
                decided_by="owner",
            )
            expected = runtime.resume(opened, waiting.run_id)
    assert runtime.read_state(settings, expected.run_id) == expected
    assert expected.status == terminal


def test_missing_database_creates_nothing() -> None:
    settings = get_settings()
    with pytest.raises(RunError, match="^no run " + "f" * 32 + "$"):
        runtime.read_state(settings, "f" * 32)
    assert not settings.data_dir.exists()


def test_missing_run_leaves_existing_database_unchanged() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model(("plan", NOTE))) as opened:
        runtime.ask(opened, "demo: note Milk")
    before = settings.checkpoints_path.read_bytes()
    with pytest.raises(RunError, match="^no run " + "f" * 32 + "$"):
        runtime.read_state(settings, "f" * 32)
    assert settings.checkpoints_path.read_bytes() == before


def test_stopped_status_matches_the_execution_reader() -> None:
    settings = get_settings()
    with runtime.open_runtime(settings, model=model()) as opened:
        with pytest.raises(ScriptError):
            runtime.ask(opened, "demo: say hi")
        [run] = opened.log.runs()
        expected = runtime.state(opened, run.run_id)
    assert expected == RunState(run.run_id, "stopped", stopped_at="plan")
    assert runtime.read_state(settings, run.run_id) == expected


@pytest.mark.parametrize("contents", [b"not a sqlite database", b""])
def test_unreadable_checkpoint_database_is_safely_refused(contents: bytes) -> None:
    settings = get_settings()
    settings.data_dir.mkdir()
    settings.checkpoints_path.write_bytes(contents)
    with pytest.raises(RunError) as raised:
        runtime.read_state(settings, "f" * 32)
    assert type(raised.value).__name__ == "RunStateUnavailable"
    assert str(raised.value) == f"run {'f' * 32} state is not available"
    assert settings.checkpoints_path.read_bytes() == contents
```

`tests/e2e/test_web_run_status.py` — 4 cases:

```python
import itertools
from datetime import UTC, datetime
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.web.app import create_app

BASE = "http://127.0.0.1:8766"


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def test_run_page_does_not_open_an_execution_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    model = ScriptedModel(
        [
            ScriptedReply(
                "plan", ModelReply(content='{"steps":[{"action":"note","args":{"title":"Milk"}}]}')
            )
        ]
    )
    with runtime.open_runtime(settings, model=model) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("GET opened an execution runtime")

    monkeypatch.setattr(runtime, "open_runtime", forbidden)
    page = TestClient(create_app(settings), base_url=BASE)
    for _ in range(4):
        response = page.get(f"/runs/{waiting.run_id}")
        assert response.status_code == 200
        assert f"/approvals/{waiting.approval_id}" in response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("run_id", ["f" * 32, "nope"])
def test_missing_run_page_creates_no_storage(run_id: str) -> None:
    settings = get_settings()
    response = TestClient(create_app(settings), base_url=BASE).get(f"/runs/{run_id}")
    assert (response.status_code, response.text) == (404, "Not found")
    assert not settings.data_dir.exists()


def test_malformed_saved_state_is_a_generic_503(monkeypatch: pytest.MonkeyPatch) -> None:
    error_type = import_module("conductor.graph.status").RunStateUnavailable

    def unreadable(*args: object, **kwargs: object) -> None:
        raise error_type("SYNTHETIC-SECRET")

    monkeypatch.setattr(runtime, "read_state", unreadable)
    response = TestClient(create_app(get_settings()), base_url=BASE).get(f"/runs/{'f' * 32}")
    assert (response.status_code, response.text) == (503, "The run state is not available")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "SYNTHETIC-SECRET" not in response.text
```

## Tests to write

Use the named coder-owned files in Scope. Add behavioral assertions, not coverage
execution alone. Do not append to a given or predecessor file.

- Unit: missing tuple; invalid run ids; malformed containers/rows; unknown node,
  nonempty sends, boolean/wrong version; ignored null-task resume/scheduled writes;
  ordinary pending output (including __start__ -> route), terminal pending output,
  opaque errors, malformed/empty/multiple Interrupt objects, wrong waiter/id kind,
  nonhex ids, malformed reply/note, terminal references cleared, and input equality
  after both success and refusal. Each mutation of a base changes one field.
- Integration: compare saved format-4 checkpoints from the existing graph for
  waiting plan/step approvals, escalation, route/plan/answer/step stops, completion,
  rejection and cancellation with literal display expectations. Capture pending
  writes via a saver hook so each node's completed-but-uncheckpointed output is
  exercised; test an old interrupt alongside successful resume output. Reads
  themselves must not invoke, lease, renew, log or create ids.
- Integration: reading while another holder owns the lease; a data path containing
  spaces/#/?; absent run in an existing DB; corrupt serialized checkpoint/metadata;
  read/open/close exceptions; connection closure on both paths; BEGIN before both
  SELECTs; reading a live WAL without checkpointing or schema changes; no model or
  services constructed; no connection/cache retained across repeated reads.
- Integration: invalid request and duplicate start still produce no extra
  RUN_STARTED; normal runtime.ask puts RUN_STARTED first. After malformed state,
  resume must not inspect store decisions or invoke the graph.
- E2E: 503 for real stored malformed state, storage failures, escaping and headers
  on error/normal paths; no resume or decision on GET; existing busy refresh,
  last-error and terminal display behavior. Use fake resumers/ScriptedModel only.

## Rules for this phase

All project privacy, local-model, tracing-off and deterministic time/id rules
apply. No real Ollama/MCP server/finance data. No exception text from saved data.
Keep unchanged critical-module tests, leases, approval policy and node boundaries.
Only the given prior-test edits are exceptions to the ordinary no-test-edit rule.

## Acceptance

Run the baseline `.venv/bin/python scripts/check.py` before implementation; it must
show 1006 passed and end `All checks passed.`. Then before reporting:

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | at least 1036 passed; 0 failed/skipped/xfailed and no warnings summary; every Sections row has 0 failed; `tests (cli,core): passed`; final `All checks passed.` |
| `.venv/bin/python -m coverage report --include='*/conductor/graph/status.py,*/conductor/graph/supervisor.py,*/conductor/runtime.py,*/conductor/web/app.py' --fail-under=100` immediately after check.py | exit 0, all four modules measured, TOTAL 100% |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint_status.py tests/integration/test_graph_ownership.py tests/integration/test_run_status.py tests/e2e/test_web_run_status.py --no-cov` | exactly 30 passed |
| `git diff --check` | no output, exit 0 |
| `git diff --stat HEAD -- AGENTS.md pyproject.toml docs/architecture.md docs/roadmap.md docs/phases/phase-09e-runtime-ownership-and-status.md docs/verification/phase-09e-runtime-ownership-and-status.md src/conductor/web/jobs.py src/conductor/web/templates src/conductor/store.py src/conductor/policy.py src/conductor/llm` | no output |
| `git status --short --untracked-files=all` | only Scope paths (plus the review after verification) |
| `grep -c '^## Phase 9e: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 9e` after writing progress | `Reports OK.` |

### Searches

Run each independently. Both must print nothing (git grep exit 1 means no match,
not a failed gate). Search functionality was checked with planted scratch lines.

```sh
git grep --untracked -n -E '_SERVICES|WeakKeyDictionary|WeakValueDictionary' -- src/conductor/graph src/conductor/runtime.py
git grep --untracked -n -E 'StateGraph|CompiledStateGraph|build_graph|open_runtime|OllamaModel|DomainRunner|Registry|Store|EventLog' -- src/conductor/graph/status.py
```

The second search scopes the pure decoder, not runtime.py, which still legitimately
contains the execution runtime. Inspect read_state and the GET path for the R5
prohibitions; the behavioral tests must catch construction through aliases too.

## Report

Use `## Phase 9e: runtime ownership and status reads (YYYY-MM-DD)` and
`Tests: 1006 -> <actual passed> (given 30)`. List new public names, actual changed
path count and decisions/deviations. If stopped, use the first `Stopped:` follow-up
from the conventions. Provide the Sections table, last ten check.py lines, other
acceptance outcomes and requirement-to-test mapping. Do not commit or push.
