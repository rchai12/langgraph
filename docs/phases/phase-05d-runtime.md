# Phase 5d: the runtime

## Goal

What turns the 5c graph into something a process can run, stop, and pick up again, without any command yet (the commands are 5e):

- `conductor.runtime` (critical): **one place that opens everything** a run needs from the settings: `checkpoints.db` through LangGraph's `SqliteSaver`, the store, the event log, the registry, the model, and the step runner. The terminal (5e) and the approvals page (Phase 7) will both call it;
- the **thread lease** (4b) held around every start and resume, and **renewed before every model call and every step**, so two processes can never run the same thread at once;
- a **demo setting**, `CONDUCTOR_DEMO`, that registers the demo domain with an in-process runner, so the whole loop can be tried by hand before real domains exist;
- runs that **stopped** inside a node (an exception, a crash, a lost lease) are reported as stopped and are never resumed.

Decided with the owner (2026-11-09): Phase 5d is split into **5d (this runtime) and 5e (`conductor ask`, `conductor resume`, and deciding then resuming in the approvals and escalations commands)**; the demo is **a setting**, not a flag; a run whose lease another process holds **fails at once** (`is busy`). For 5e: a decision command records and then resumes; `ask` and `resume` print text, exit 0 for every state reached, and take `--json`.

Decided by the architect for this phase, within those answers: a stopped run cannot be resumed in 5d, because resuming would run its node again from the first line, and a `run_step` that stopped after its runner was called would run the step a second time on one approval. Recovering stopped runs is a later phase.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("State, threads, and storage", "Approvals and escalations")
- `src/conductor/graph/supervisor.py` (5c), `src/conductor/store.py` (leases), `src/conductor/config.py`, `src/conductor/llm/ollama.py`, `src/conductor/domains/__init__.py`, `src/conductor/domains/demo.py`, `tests/conftest.py` (`isolated_settings`)

## Starting state

Phase 5c is built and verified, and everything is committed: N is `523`. **Sections: core.** `langgraph-checkpoint-sqlite` is not installed.

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | add `"langgraph-checkpoint-sqlite>=3.1.2,<3.2",` to `dependencies`, after `langgraph`; then run `.venv/bin/python -m pip install -e ".[dev]"` once |
| `src/conductor/config.py` | the field `demo`, its check, and the properties `demo_on` and `checkpoints_path` (Part 1) |
| `src/conductor/graph/supervisor.py` | the `stopped` status (Part 3) |
| `src/conductor/runtime.py` | the runtime (Part 2, critical) |
| `scripts/critical_modules.txt` | add the line `runtime.py` after `graph/supervisor.py` |
| `docs/testing.md` | under "Critical modules", add `` - `runtime.py` (one process per thread at a time, and private checkpoint files; Phase 5d) `` after the `graph/supervisor.py` line |
| `tests/integration/test_runtime.py` | given |
| `tests/integration/test_runtime_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Every command: `conductor ask`, `conductor resume`, and resuming from the approvals and escalations commands (5e).
- Resuming or repairing a stopped run; undoing a step; renewing the lease on a timer or during a model call.
- MCP and real runners (Phase 6); real domains (Phase 9).
- Changes to the graph other than the `stopped` status; to contracts, `policy`, `store`, `decisions`, routing, or planning; new event or escalation kinds.
- WAL settings, vacuuming, migrations, or deleting old checkpoints.

## Dependencies

`langgraph-checkpoint-sqlite>=3.1.2,<3.2` (3.1.2 is current; it also installs `aiosqlite` and `sqlite-vec`, which the project does not use). Only `langgraph.checkpoint.sqlite.SqliteSaver`, over the standard library's `sqlite3`, is used; `AsyncSqliteSaver` and the vector store are not.

## Design

```python
# conductor/config.py: added
DEMO_MESSAGE = "must be true or false"
class Settings(BaseSettings):
    ...
    demo: str = "false"               # after decided_by; must be exactly "true" or "false"

    @property
    def demo_on(self) -> bool: ...     # demo == "true"

    @property
    def checkpoints_path(self) -> Path: ...   # data_dir / "checkpoints.db"
```

A `demo` that is not exactly `true` or `false` adds the problem `CONDUCTOR_DEMO: must be true or false` after the `decided_by` problem.

```python
# conductor/graph/supervisor.py: changed
RunStatus = Literal["waiting", "done", "rejected", "cancelled", "stopped"]

@dataclass(frozen=True)
class RunState:
    ...                                # the 5c fields, unchanged
    stopped_at: str | None = None      # the node a stopped run stopped in
```

```python
# conductor/runtime.py (critical)
DEMO_SUMMARY = "the demo agent does no work"

class DemoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...

class NoRunner:
    def run(self, action: Action, args: Contract) -> dict[str, JsonValue]: ...   # raises StepFailed()

@dataclass(frozen=True)
class Runtime:
    graph: CompiledStateGraph
    store: Store
    log: EventLog
    registry: Registry
    holder: str                        # this runtime's lease holder id

@contextmanager
def open_runtime(settings: Settings, *, model: Model | None = None) -> Iterator[Runtime]: ...
def ask(runtime: Runtime, request: str) -> RunState: ...
def resume(runtime: Runtime, run_id: str) -> RunState: ...
def state(runtime: Runtime, run_id: str) -> RunState: ...
```

`DemoRunner.run` returns, by action name: `echo` → `{"text": args.text}`; `note` → `{"note_id": ids.new_id()}` (nothing is written); `delegate` → `{"summary": DEMO_SUMMARY}`. It never touches a file or the network.

`open_runtime` does, in order:

1. creates `settings.data_dir` with mode `0700` if it is missing (`parents=True`);
2. creates `checkpoints.db` with `os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o600)` when it does not exist, then opens it with `sqlite3.connect(path, check_same_thread=False)` and builds `SqliteSaver(connection)`;
3. opens `Store(settings.db_path)` and `EventLog(settings.runs_dir)`;
4. builds the registry from `domains.DOMAINS` (read through the module, `from conductor import domains`), with `demo.DOMAIN` added at the end when `settings.demo_on`, and picks `DemoRunner()` when `settings.demo_on`, `NoRunner()` otherwise;
5. uses `model`, or `OllamaModel(settings.ollama_host, timeout=settings.model_timeout_seconds)` when none is given;
6. takes `holder = ids.new_id()`;
7. builds the graph with `build_graph(Services(registry, store, log, <the model, leased>, settings.model, <the runner, leased>), saver)`;
8. yields the `Runtime`, and closes the SQLite connection when the block ends, also on an exception.

"Leased" means wrapped so that `chat` and `run` first call `store.renew(<the current run id>, holder)`; `model_info` is passed straight through. The current run id is the one `ask` or `resume` is working on.

| Function | Does |
|---|---|
| `ask` | `run_id = ids.new_id()`; `store.acquire(run_id, holder)`; `start_run(graph, request, run_id=run_id)`; the lease is released afterwards, also on an exception |
| `resume` | `store.acquire(run_id, holder)` (`LeaseHeld` → `RunError(f"run {run_id} is busy")`, nothing else done); `resume_run(graph, store, run_id)`; the lease is released afterwards, also on an exception |
| `state` | `run_state(graph, run_id)`, without a lease |

A `LeaseLost`, from a renewal inside the run or from the release, becomes `RunError(f"run {run_id} lost its lease")`. Any other exception passes through after the release.

`run_state` (5c) returns `RunState(run_id, "stopped", stopped_at=snapshot.next[0])` when the snapshot has no interrupts but a next node; `resume_run` refuses a stopped run first, with `RunError(f"run {run_id} stopped at {node} and cannot be resumed")`.

## Facts about LangGraph's SQLite checkpointer

Found on 2026-11-09 with langgraph 1.2.20, langgraph-checkpoint 4.3.1, langgraph-checkpoint-sqlite 3.1.2:

- `SqliteSaver(sqlite3.connect(path, check_same_thread=False))` creates the tables `checkpoints` and `writes` on first use, and **switches the file to WAL**: `checkpoints.db-wal` and `checkpoints.db-shm` exist while a connection is open and are removed when the last one closes.
- With umask `022` and the file made `0600` first, **the `-wal` and `-shm` files are `0600` too** (they take the database's mode). Without the `os.open` step, `sqlite3.connect` would make the database `0644`.
- A thread interrupted in one process is found by `get_state` in another, with its `next` node and interrupt values, and `Command(resume=...)` there finishes it. A second connection reads while the first is open.
- JSON-only state gives no warning under `warnings.simplefilter("error")`.
- **A node that raises leaves the thread with `next` = that node, no interrupts, and the error on its task**; `invoke(None, config)` would run that node again from its first line. Hence the `stopped` status and the refusal.
- `Store.renew` succeeds for the holder whose row it still is, even after the 600 seconds, and fails with `LeaseLost` once another holder has acquired it; renewing before every model call and step therefore stops a run at its next call after another process took over. A single model call can last up to `CONDUCTOR_MODEL_TIMEOUT` (at most 3600 seconds), longer than a lease; then another process may start a model call for the same thread, but no step runs without a successful renewal first.

## Requirements

### Part 1: the settings and the dependency

- **R1.** `langgraph-checkpoint-sqlite` is added as under Scope and installed. `Settings.demo`, `demo_on`, `checkpoints_path`, and the `CONDUCTOR_DEMO` problem are as under Design.

### Part 2: the runtime (critical)

- **R2.** `open_runtime` does the Design's steps in that order; `checkpoints.db`, its `-wal` and `-shm` files, and the data folder are private (`0600`, `0700`) whatever the umask; the connection is closed when the block ends.
- **R3.** The registry is `domains.DOMAINS` read when `open_runtime` runs, plus `demo.DOMAIN` only when `demo_on`; `DemoRunner` and `NoRunner` behave as under Design.
- **R4.** `ask` and `resume` hold the run's lease, under the runtime's `holder`, for exactly the time of their call; a lease held by another holder makes `resume` fail with `is busy` before it reads or writes anything else; the lease is released on every way out.
- **R5.** Every `chat` and every step `run` first renews the lease of the current run; a `LeaseLost` stops the run where it is and becomes `lost its lease`; no step runs after a failed renewal.
- **R6.** `state` reports a run without taking its lease; a run started by one runtime is found, waiting at the same place, by a runtime opened later (another process).

### Part 3: stopped runs

- **R7.** `run_state` and `resume_run` treat a run with a next node and no interrupt as stopped, as under Design; nothing in 5d resumes a stopped run.

### Part 4: the rules

- **R8.** `runtime.py` imports from the project only `conductor` (for `domains` and `ids`), `conductor.config`, `conductor.contracts`, `conductor.domains`, `conductor.events`, `conductor.graph.supervisor`, `conductor.llm.model`, `conductor.llm.ollama`, `conductor.registry`, and `conductor.store`; from libraries only the standard library, `pydantic`, and `langgraph` (`SqliteSaver`, and the compiled graph's type). It reads settings only from the `Settings` it is given.
- **R9.** Every `RunError` message is constant text plus the run id or node name.
- **R10.** `runtime.py` reaches 100% of lines and branches and joins the critical modules; `graph/supervisor.py` stays at 100%.

## Given tests

12 tests in `tests/integration/test_runtime.py`. Do not change them; if one fails, the code is wrong. They open real runtimes on files under the test's data folder (`isolated_settings`), with `ScriptedModel`.

```python
import itertools
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, domains, ids
from conductor.config import SettingsError, get_settings
from conductor.decisions import decide_approval
from conductor.domains import demo
from conductor.events import EventKind
from conductor.graph.supervisor import RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import DEMO_SUMMARY, DemoRunner, Runtime, ask, open_runtime, resume, state
from conductor.store import Store

START = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
NOW = [START]
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
REPLY = '{"reply": "Done."}'
OTHER = "9" * 32


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    NOW[0] = START
    monkeypatch.setattr(clock, "now", lambda: NOW[0])
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def scripted(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies])


def approve(runtime: Runtime, approval_id: str) -> None:
    decide_approval(
        runtime.store,
        runtime.registry,
        approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert (settings.demo, settings.demo_on) == ("false", False)
    assert settings.checkpoints_path == tmp_path / "data" / "checkpoints.db"
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    assert get_settings().demo_on is True


@pytest.mark.parametrize("value", ["yes", "True"])
def test_the_demo_setting_is_true_or_false(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == "CONDUCTOR_DEMO: must be true or false"


def test_without_the_demo_setting_no_domain_is_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", ())
    with open_runtime(get_settings(), model=scripted()) as runtime:
        assert runtime.registry.names == ()
        found = ask(runtime, "demo: echo hi")
        assert found.status == "waiting" and found.escalation_id is not None
        assert runtime.store.escalation(found.escalation_id).escalation.detail == (
            "no domains are registered"
        )


@pytest.mark.usefixtures("demo_on")
def test_a_run_survives_a_restart_in_private_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with open_runtime(get_settings(), model=scripted(("plan", NOTE_PLAN))) as first:
        assert first.registry.names == ("demo",)
        waiting = ask(first, "demo: note Milk")
        assert waiting.status == "waiting" and waiting.approval_id is not None
        assert {p.name: mode(p) for p in data.iterdir() if p.name.startswith("checkpoints")} == {
            name: 0o600 for name in ("checkpoints.db", "checkpoints.db-shm", "checkpoints.db-wal")
        }
        approve(first, waiting.approval_id)
    with open_runtime(get_settings(), model=scripted(("answer", REPLY))) as second:
        assert second.holder != first.holder
        assert state(second, waiting.run_id) == waiting
        step = resume(second, waiting.run_id)
        assert step.status == "waiting" and step.approval_id != waiting.approval_id
        approve(second, step.approval_id)
        assert resume(second, waiting.run_id) == RunState(
            run_id=waiting.run_id, status="done", reply="Done."
        )
    assert mode(data / "checkpoints.db") == 0o600


@pytest.mark.parametrize(
    ("action", "args", "output"),
    [
        ("echo", demo.EchoArgs(text="hi"), {"text": "hi"}),
        ("note", demo.NoteArgs(title="Milk"), {"note_id": "1".rjust(32, "0")}),
        ("delegate", demo.DelegateArgs(task="tidy"), {"summary": DEMO_SUMMARY}),
    ],
)
def test_the_demo_runner(action: str, args: object, output: dict) -> None:
    found = DemoRunner().run(next(a for a in demo.DOMAIN.actions if a.name == action), args)
    assert found == output
    assert DEMO_SUMMARY == "the demo agent does no work"


@pytest.mark.usefixtures("demo_on")
def test_a_busy_run_is_refused(tmp_path: Path) -> None:
    with open_runtime(get_settings(), model=scripted(("plan", NOTE_PLAN))) as runtime:
        waiting = ask(runtime, "demo: note Milk")
        approve(runtime, waiting.approval_id)
        runtime.store.acquire(waiting.run_id, OTHER)
        with pytest.raises(RunError) as raised:
            resume(runtime, waiting.run_id)
        assert str(raised.value) == f"run {waiting.run_id} is busy"
        assert state(runtime, waiting.run_id) == waiting


@pytest.mark.usefixtures("demo_on")
def test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renewals: list[tuple[str, str]] = []
    real = Store.renew

    def spy(self: Store, thread_id: str, holder: str):
        renewals.append((thread_id, holder))
        return real(self, thread_id, holder)

    monkeypatch.setattr(Store, "renew", spy)
    model = scripted(("plan", ECHO_PLAN), ("answer", REPLY))
    with open_runtime(get_settings(), model=model) as runtime:
        done = ask(runtime, "demo: say hi")
        assert done.status == "done"
        assert renewals == [(done.run_id, runtime.holder)] * 3
        runtime.store.acquire(done.run_id, OTHER)


@pytest.mark.usefixtures("demo_on")
def test_a_run_that_raises_releases_its_lease_and_stops(tmp_path: Path) -> None:
    with open_runtime(get_settings(), model=scripted()) as runtime:
        with pytest.raises(Exception, match="no scripted reply left for plan"):
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        stopped = state(runtime, run.run_id)
        assert stopped == RunState(run_id=run.run_id, status="stopped", stopped_at="plan")
        runtime.store.acquire(run.run_id, OTHER)
        runtime.store.release(run.run_id, OTHER)
        with pytest.raises(RunError) as raised:
            resume(runtime, run.run_id)
        assert str(raised.value) == f"run {run.run_id} stopped at plan and cannot be resumed"


class StealingModel(ScriptedModel):
    """Answers like ScriptedModel, then calls `steal` (set by the test) after each chat."""

    steal = None

    def chat(self, request):
        reply = super().chat(request)
        if self.steal is not None:
            self.steal()
        return reply


@pytest.mark.usefixtures("demo_on")
def test_a_lost_lease_stops_the_run_before_its_step_runs(tmp_path: Path) -> None:
    model = StealingModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))])
    with open_runtime(get_settings(), model=model) as runtime:

        def steal() -> None:
            NOW[0] = START + timedelta(seconds=601)
            [run] = runtime.log.runs()
            runtime.store.acquire(run.run_id, OTHER)

        model.steal = steal
        with pytest.raises(RunError) as raised:
            ask(runtime, "demo: say hi")
        [run] = runtime.log.runs()
        assert str(raised.value) == f"run {run.run_id} lost its lease"
        assert EventKind.TOOL_RESULT not in [e.kind for e in runtime.log.read(run.run_id)]
        assert state(runtime, run.run_id) == RunState(
            run_id=run.run_id, status="stopped", stopped_at="run_step"
        )
```

## Tests to write

In `tests/integration/test_runtime_more.py`, each with its deciding input:

- R2: with umask `0o022` (set and restored in the test), a new data folder is `0700` and `checkpoints.db` `0600`; an existing `checkpoints.db` is opened, not replaced (its checkpoints remain); the connection is closed after the block (a query on it raises `sqlite3.ProgrammingError`), also when the block raises.
- R3: `domains.DOMAINS` replaced by a test domain is used (with and without the demo setting, which adds `demo` after it); `NoRunner().run` raises `StepFailed`; without `model`, the model is an `OllamaModel` on the settings' host (the run reaches the closed port of `isolated_settings` and escalates as `model_unavailable`, with a request that needs the classifier).
- R4: after `ask` raises `ValueError` (a blank request), the lease is free; `resume` of an unknown run gives `no run ...` and leaves no lease.
- R5: a renewal that fails before the answer (the lease taken during the step) gives `lost its lease`, and the run is stopped at `answer`.
- R6: `state` of a run whose lease another holder has is still answered.
- R7: a run stopped at `route` (a `ScriptError` from the classifier) reports `stopped_at` `route`.
- R9: the messages of `is busy`, `lost its lease`, and `stopped at` are exactly as under Design.

## Rules for this phase

- **Private files** (`AGENTS.md` rule 6, `docs/architecture.md`): every file the runtime makes is `0600`, every folder `0700`.
- **One process per thread**: no model call and no step happens for a run without a lease renewed by this runtime just before it.
- **Side effects need approval** (`AGENTS.md` rule 7): unchanged from 5c; a stopped `run_step` is never run again without a new approval (it is not resumed at all).
- **Network**: only `OllamaModel` on the configured loopback host; the demo runner touches nothing.
- **Critical module**: `runtime.py` joins `scripts/critical_modules.txt` and `docs/testing.md`.
- **Synthetic data only**; earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 12 = 535 passed; `critical coverage` passed (it now includes `runtime.py`);
- the given file: `.venv/bin/python -m pytest tests/integration/test_runtime.py --no-cov -W error`, exactly `12 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/*.py,*/conductor/config.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 5d`, after the progress entry: `Reports OK.`;
- `.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph-checkpoint-sqlite'))"` prints `3.1.2` or a later `3.1.x`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/runtime.py | grep -v -E "^[^:]+:[0-9]+:from conductor(\.config|\.contracts|\.domains|\.events|\.graph\.supervisor|\.llm\.model|\.llm\.ollama|\.registry|\.store)? import "`
  - `git grep --untracked -n -E "get_settings|urllib|langchain|langsmith|from conductor\.domains import DOMAINS" -- src/conductor/runtime.py`
  - `git grep --untracked -n -E "SqliteSaver|checkpoint\.sqlite" -- src | grep -v "^src/conductor/runtime.py:"`
- `git diff --stat HEAD -- src/conductor/contracts src/conductor/policy.py src/conductor/store.py src/conductor/decisions.py src/conductor/routing src/conductor/planning src/conductor/domains src/conductor/events.py src/conductor/llm src/conductor/cli tests/unit tests/e2e tests/support.py tests/integration/test_supervisor.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 5d: the runtime (YYYY-MM-DD)`, with `Tests: 523 -> <passed> (given 12)`.
