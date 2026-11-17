# Verify Phase 9e: runtime ownership and status reads

Spec: `docs/phases/phase-09e-runtime-ownership-and-status.md`.
Follow `AGENTS.md`, `docs/phase-conventions.md` (For the verifier), and
`docs/ai-workflow.md`. This is an independent review: write only
`docs/reviews/phase-09e-runtime-ownership-and-status.md`.

## First: establish that the coder ran

Before expensive gates, inspect status, `git diff HEAD`, and all untracked files.
Require the new graph/status module, all four given test files and one Phase 9e
progress entry. The final spec and guide must be tracked and unchanged relative
to the committed planning baseline. Record that full commit. If there is no
implementation/progress entry, report the missing handoff without writing an
orphan review. If the coder stopped, follow the stopped-work procedure. Isolate
mixed scope before reviewing; never silently waive a scope failure.

The approved design is a graph-free reader, not a cached compiled graph. Its two
owner decisions are recorded in the spec. A generic 503 is intentional, while a
missing run stays 404. The tests below must not contact any real service.

## 1. Gates

N = 1006. Given count = 30. Sections = cli,core.
Run each command from the repository root in this order. Do not run concurrent
coverage producers; the coverage consumer immediately follows check.py.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | at least 1036 passed, no failed/skipped/xfailed or warnings summary; Sections all 0 failed; tests (cli,core) passed; final `All checks passed.` |
| `.venv/bin/python -m coverage report --include='*/conductor/graph/status.py,*/conductor/graph/supervisor.py,*/conductor/runtime.py,*/conductor/web/app.py' --fail-under=100` | all four modules measured, TOTAL 100%, exit 0 |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint_status.py tests/integration/test_graph_ownership.py tests/integration/test_run_status.py tests/e2e/test_web_run_status.py --no-cov` | exactly 30 passed |
| `git diff --check` | no output, exit 0 |
| `git diff --stat HEAD -- AGENTS.md pyproject.toml docs/architecture.md docs/roadmap.md docs/phases/phase-09e-runtime-ownership-and-status.md docs/verification/phase-09e-runtime-ownership-and-status.md src/conductor/web/jobs.py src/conductor/web/templates src/conductor/store.py src/conductor/policy.py src/conductor/llm` | no output |
| `git status --short --untracked-files=all` | only the spec's Scope paths; add only this review afterward |
| `grep -c '^## Phase 9e: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 9e` | `Reports OK.` before and after writing review |
| `.venv/bin/python <temporary-probe-path>` | both check lines start with ok; final `FAILURES 0` |

The guide's probe is saved outside the repository as described below. Compare
new given files byte-for-byte with the spec blocks and the five changed prior
tests against the exact patch. The critical list and testing-doc addition must
match their patch too. Do not treat an empty protected diff alone as a scope audit.

## 2. Requirement checklist

| Id | Evidence | Pass when |
|---|---|---|
| R1 | integration/test_graph_ownership.py: both service-release tests; probe ownership check; inspect module owners | GC releases services, graphs and models; no alternate global owner/cache/graph attribute |
| R2 | test_start_records_through_the_explicit_log; predecessor World.start callers; coder invalid/duplicate-start cases | explicit log is used, no extra start event on refusal, runtime.ask retains first-event order |
| R3 | all 14 test_checkpoint_status cases and coder cases | v4 sequential projection handles ordinary, error, interrupt, bookkeeping and completed pending output without mutation; unknown shapes fail safely |
| R4 | test_stopped_status_matches_the_execution_reader; coder resume refusal and status compatibility tests | run_state/state use the same decoder; corrupt state cannot reach store lookup or invoke |
| R5 | all 9 integration/test_run_status cases, coder SQLite lifecycle/snapshot/WAL tests and restart probe | no graph/services/lease/id/log side effects; existing-only consistent read and all connections closed |
| R6 | all 4 test_web_run_status cases, old test_web_runs and migrated terminal-display test | 404/503 distinction, generic safe text, headers and escaping retained, no GET decision/resume |
| R7 | complete status/diff/untracked audit and exact given patch/file comparison | only scoped paths and exact given migrations; no later-phase work or dependencies |
| R8 | critical coverage, progress entry, check_reports | all critical lines/branches covered by useful assertions and reports valid |

Inspect coder tests for every Tests to write bullet in the spec. A missing
compatibility test for pending output is a finding even if line coverage is 100%.
Use literal outcomes and actual reference ids; do not require a private helper
layout. Check that malformed-state tests vary one relevant field at a time.

## 3. Scope and safety inspection

- No `_SERVICES`, weak-map replacement or other process owner. Node closures
  retain Services normally until their graph can be collected.
- read_state must use an escaped read-only SQLite URI and BEGIN before tuple
  SELECTs. It must not use immutable=1, initialize SqliteSaver schema, change WAL
  mode or user_version, construct any execution services or hold a run lease.
- Status decoding must not execute a node or deserialize by a homemade alternate
  format. The SDK handles blobs; the pure decoder projects its typed tuple.
- Completed pending output supersedes a stale interrupt for the same task. An
  opaque pending error never becomes page/log text. Unknown sends/parallelism or
  formats must refuse rather than produce a plausible status.
- The graph-backed status path must not retain its old unchecked cast/KeyError
  route. A malformed state refuses before a resume reads an approval or invokes.
- Keep approval policy, stale-digest checks, lease behavior, stopped-node resume
  restrictions and node boundaries unchanged. No new status registry or store.
- App middleware continues to decorate both 404 and 503 responses. No library
  exception or synthetic secret from a fixture appears in the response.

## 4. Searches

Each command must print nothing. Exit 1 from git grep means no match; an invalid
command or unreadable path is not a clean result. Also inspect the R5 call path,
since a regex cannot prove absence of effects through aliases.

```sh
git grep --untracked -n -E '_SERVICES|WeakKeyDictionary|WeakValueDictionary' -- src/conductor/graph src/conductor/runtime.py
git grep --untracked -n -E 'StateGraph|CompiledStateGraph|build_graph|open_runtime|OllamaModel|DomainRunner|Registry|Store|EventLog' -- src/conductor/graph/status.py
```

## 5. Probe

Save the following as a fresh temporary file outside the repository, run it from
the repository root with `.venv/bin/python <path>`, then delete only that file.
`--oracle-only` checks its small independent plan/step/done table and prints
`FAILURES 0`. A harness/table self-check failure is a spec problem, not a product
finding. Each runtime check catches exceptions and reaches the final count.

This checks repeated runtime collection and two approvals across ten restart
cycles, with repeated status reads leaving event-log bytes unchanged. It uses
only synthetic demo runs and ScriptedModel, replacing time and ids. It does not
change a real data folder or use a real model/server. Its temporary environment
changes occur only in the probe process.

```python
import gc
import itertools
import os
import tempfile
import weakref
from datetime import UTC, datetime
from pathlib import Path

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply

FAILURES = 0
PHASES = ("plan", "step", "done")
EXPECTED_STATUS = {"plan": "waiting", "step": "waiting", "done": "done"}
assert tuple(EXPECTED_STATUS[phase] for phase in PHASES) == ("waiting", "waiting", "done")
assert len([phase for phase in PHASES if phase != "done"]) == 2


def section(label, body):
    global FAILURES
    try:
        assert body()
    except Exception as error:
        FAILURES += 1
        print(f"FAIL {label}: {type(error).__name__}")
    else:
        print(f"ok   {label}")


def scripted():
    return ScriptedModel(
        [
            ScriptedReply(
                "plan", ModelReply(content='{"steps":[{"action":"note","args":{"title":"Milk"}}]}')
            ),
            ScriptedReply("answer", ModelReply(content='{"reply":"Done."}')),
        ]
    )


def isolated(folder):
    for name in list(os.environ):
        if name.startswith("CONDUCTOR_"):
            del os.environ[name]
    os.environ["CONDUCTOR_DATA_DIR"] = str(folder)
    os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"
    os.environ["CONDUCTOR_DEMO"] = "true"


def ownership():
    with tempfile.TemporaryDirectory() as folder:
        isolated(Path(folder) / "data")
        references = []
        for _ in range(20):
            model = ScriptedModel([])
            with runtime.open_runtime(get_settings(), model=model) as opened:
                references.append(weakref.ref(opened.graph))
                references.append(weakref.ref(model))
            del opened, model
        gc.collect()
        return all(reference() is None for reference in references)


def restart_and_poll():
    read_state = runtime.read_state
    with tempfile.TemporaryDirectory() as folder:
        for trial in range(10):
            isolated(Path(folder) / str(trial))
            settings = get_settings()
            with runtime.open_runtime(settings, model=scripted()) as opened:
                waiting = runtime.ask(opened, "demo: note Milk")
            run_id = waiting.run_id
            for phase in PHASES:
                expected_status = EXPECTED_STATUS[phase]
                if phase != "done":
                    from conductor.store import Store

                    stored = Store(settings.db_path).pending()
                    assert len(stored) == 1 and stored[0].stage == phase
                    expected = RunState(run_id, expected_status, approval_id=stored[0].approval_id)
                else:
                    expected = RunState(run_id, expected_status, reply="Done.")
                before = {
                    path.name: path.read_bytes() for path in settings.runs_dir.glob("*.jsonl")
                }
                for _ in range(5):
                    assert read_state(settings, run_id) == expected
                after = {path.name: path.read_bytes() for path in settings.runs_dir.glob("*.jsonl")}
                assert after == before
                if phase != "done":
                    with runtime.open_runtime(
                        settings,
                        model=ScriptedModel(
                            [ScriptedReply("answer", ModelReply(content='{"reply":"Done."}'))]
                        ),
                    ) as opened:
                        decide_approval(
                            opened.store,
                            opened.registry,
                            expected.approval_id,
                            "approve",
                            channel="terminal",
                            decided_by="owner",
                        )
                        runtime.resume(opened, run_id)
        return True


if "--oracle-only" not in __import__("sys").argv:
    clock.now = lambda: datetime(2031, 1, 2, tzinfo=UTC)
    counter = itertools.count(1)
    ids.new_id = lambda: f"{next(counter):032x}"
    section("20 closed runtimes release their graphs and models", ownership)
    section("10 restart cycles retain two approvals and read-only status", restart_and_poll)
print(f"FAILURES {FAILURES}")
```

## 6. Spot checks

Do these only in an isolated scratch copy of the reviewed bytes. Link the existing
venv and set PYTHONPATH to the copy's src. First run the deciding test unmodified
and see it pass. Change the named single behavior, run its full node id with
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<node id>' --no-cov -vv`,
then restore the exact saved bytes. Record the concrete old/new expression used;
private layouts may differ. Confirm the reviewed tree never changed.

| # | Function and one-expression mutation | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | build_graph: add `globals()['_SPOT_OWNER'] = services` before return | `tests/integration/test_graph_ownership.py::test_services_are_released_with_the_graph` | weak reference is None after GC | Services remains alive |
| S2 | start_run: omit the supplied log's RUN_STARTED append | `tests/integration/test_graph_ownership.py::test_start_records_through_the_explicit_log` | one RUN_STARTED in supplied log | supplied run is missing |
| S3 | checkpoint_state: let the old interrupt take precedence over successful pending output | `tests/unit/test_checkpoint_status.py::test_completed_pending_writes_override_an_old_interrupt` | stopped at ask_step | waiting on old approval |
| S4 | checkpoint_state: disable the format-version refusal | `tests/unit/test_checkpoint_status.py::test_malformed_state_is_safely_refused[version]` | RunStateUnavailable | version 99 returns done |
| S5 | checkpoint_state: accept uppercase ids in an interrupt | `tests/unit/test_checkpoint_status.py::test_malformed_state_is_safely_refused[invalid-id]` | RunStateUnavailable | B repeated 32 times is accepted |
| S6 | read_state: insert `open_runtime(settings).__enter__()` before the read | `tests/integration/test_run_status.py::test_waiting_status_uses_only_checkpoints` | 12 reads succeed | forbidden execution construction |
| S7 | run GET: change unavailable response code 503 to 404 | `tests/e2e/test_web_run_status.py::test_malformed_saved_state_is_a_generic_503` | 503 with generic text | 404 |

Trace mutations through all guards. For S4 and S5, disable the complete relevant
version/id validation rather than change an unused parallel check. Do not count
collection/setup errors as caught mutations. An unexpected failure mode needs
investigation and a note; a surviving mutation may expose a weak test. Judge
whether it is a spec/test issue or an implementation defect and explain why.
Do not alter given tests or spec requirements to force a mutation result.

## 7. Reasonable variations

Private helpers and local copies of dictionaries are allowed. Re-export syntax
may use explicit aliases to keep Ruff satisfied. Decoder guard ordering may vary
when all bad shapes still produce the same safe error; invalid run-id validation
must happen first. No timing/memory-size threshold is required: weak references
and object/service-construction assertions provide deterministic evidence.

A failed read-only lookup on an existing incompatible database is 503 rather than
an implicit schema upgrade. SQLite may maintain its own WAL/shared-memory sidecar
lifecycle; do not demand byte identity of volatile sidecars while a writer runs.
The main tests still require no main-database/schema/log changes from reads.

## 8. Verdict and progress

Write the exact review head and findings format from phase-conventions, headed
`# Review: Phase 9e`. Include concise gate/Sections/coverage, scope, probe and spot
results, one requirement/location/expected/observed line per finding, and required
Parts that needed a repair / Built beyond the spec lines. Do not repair code.
For FAIL, send requirement, observation and required result back to the coder.
Run `.venv/bin/python scripts/check_reports.py --phase 9e`; require `Reports OK.`.
A PASS applies only to the reviewed bytes and the recorded planning baseline.
