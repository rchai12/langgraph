# Verify Phase 5d: the runtime

Spec: `docs/phases/phase-05d-runtime.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 5d` on your own report.

The coder added `langgraph-checkpoint-sqlite` and installed it, added `demo`, `demo_on`, and `checkpoints_path` to the settings, added the `stopped` status to `conductor.graph.supervisor`, created `conductor.runtime` (critical), copied `tests/integration/test_runtime.py` (12 tests), and wrote `tests/integration/test_runtime_more.py`.

## 1. Gates

N is `523`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 535 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `runtime.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/runtime.py,*/conductor/graph/*.py,*/conductor/config.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/integration/test_runtime.py --no-cov -W error` | exactly `12 passed` |
| `.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph-checkpoint-sqlite'))"` | `3.1.2` or a later `3.1.x` |
| `.venv/bin/python scripts/check_reports.py --phase 5d` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/contracts src/conductor/policy.py src/conductor/store.py src/conductor/decisions.py src/conductor/routing src/conductor/planning src/conductor/domains src/conductor/events.py src/conductor/llm src/conductor/cli tests/unit tests/e2e tests/support.py tests/integration/test_supervisor.py` | no output |
| `git diff HEAD -- pyproject.toml` | exactly one added line, `"langgraph-checkpoint-sqlite>=3.1.2,<3.2",` |
| `git diff HEAD -- src/conductor/graph/supervisor.py` | only the `stopped` status: `RunStatus`, `RunState.stopped_at`, `run_state`, and `resume_run`'s first check |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/runtime.py | grep -v -E "^[^:]+:[0-9]+:from conductor(\.config|\.contracts|\.domains|\.events|\.graph\.supervisor|\.llm\.model|\.llm\.ollama|\.registry|\.store)? import "`
2. `git grep --untracked -n -E "get_settings|urllib|langchain|langsmith|from conductor\.domains import DOMAINS" -- src/conductor/runtime.py`
3. `git grep --untracked -n -E "SqliteSaver|checkpoint\.sqlite" -- src | grep -v "^src/conductor/runtime.py:"`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given file equals the spec's block; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_settings`, `test_the_demo_setting_is_true_or_false`; the version gate | pass |
| R2 | `test_a_run_survives_a_restart_in_private_files`; the coder's umask, existing-file, and closed-connection tests; probe "every file under the data folder is 0600 ..."; read `open_runtime` against the Design's steps | pass; ok; in that order |
| R3 | `test_without_the_demo_setting_no_domain_is_registered`, `test_the_demo_runner`; the coder's `DOMAINS`, `NoRunner`, and `OllamaModel` tests; probe "without CONDUCTOR_DEMO the registry is exactly DOMAINS" | pass; ok |
| R4 | `test_a_busy_run_is_refused`, `test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step`, `test_a_run_that_raises_releases_its_lease_and_stops`; the coder's lease-free tests; probe "of six resumes at once ..." | pass; ok |
| R5 | `test_a_lost_lease_stops_the_run_before_its_step_runs`, the renewal count of the lease test; the coder's `answer` test | pass |
| R6 | `test_a_run_survives_a_restart_in_private_files`; the coder's `state` test; probe "a run waits, survives two restarts, and finishes in a third process" | pass; ok |
| R7 | `test_a_run_that_raises_releases_its_lease_and_stops`; the coder's `route` test; probe "a run that raises stops where it was ..." | pass; ok |
| R8 | searches 1 to 3 | no output |
| R9 | the message checks in the given and the coder's tests; read every `RunError(` in `runtime.py` and the graph's new one | constant texts plus ids and node names |
| R10 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It works in its own temporary data folder with `CONDUCTOR_DEMO=true`; it passes one run through three separate processes, races six runtimes in threads to resume the same decided step, and stops runs at `plan` and at `answer`. Its event counter checks itself on the finished run before the race; a stop at that `assert` is the probe's fault: report it under "For the architect", not as a finding. Run it twice; a race check that fails even once is a finding.

```python
"""Independent probe for Phase 5d. Run from the repository root with .venv/bin/python."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


folder = Path(tempfile.mkdtemp())
for key in list(os.environ):
    if key.startswith("CONDUCTOR_") or "TRACING" in key:
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(folder / "data")
os.environ["CONDUCTOR_DEMO"] = "true"
os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"

STEP = """
import json, sys
from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import ask, open_runtime, resume
replies = [ScriptedReply(p, ModelReply(content=c)) for p, c in json.loads(sys.argv[2])]
with open_runtime(get_settings(), model=ScriptedModel(replies)) as runtime:
    if sys.argv[1] == "ask":
        found = ask(runtime, "demo: note Milk")
    else:
        run_id, approval_id = sys.argv[3], sys.argv[4]
        decide_approval(runtime.store, runtime.registry, approval_id, "approve",
                        channel="terminal", decided_by="owner")
        found = resume(runtime, run_id)
    print(json.dumps({"holder": runtime.holder, "status": found.status, "run_id": found.run_id,
                      "approval_id": found.approval_id, "reply": found.reply}))
"""
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'


def process(*args: str) -> dict:
    done = subprocess.run(
        [sys.executable, "-c", STEP, *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        return {"error": done.stderr[-300:]}
    return json.loads(done.stdout)


# 1. one run through three processes
a = process("ask", json.dumps([["plan", NOTE_PLAN]]))
b = process("resume", "[]", a.get("run_id", ""), a.get("approval_id") or "")
c = process(
    "resume",
    json.dumps([["answer", '{"reply": "Done."}']]),
    a.get("run_id", ""),
    b.get("approval_id") or "",
)
check(
    "a run waits, survives two restarts, and finishes in a third process",
    (a.get("status"), b.get("status"), c.get("status"), c.get("reply"))
    == ("waiting", "waiting", "done", "Done.")
    and len({a.get("holder"), b.get("holder"), c.get("holder")}) == 3,
)

# 2. every file private
data = folder / "data"
modes = {p.name: stat.S_IMODE(p.stat().st_mode) for p in data.rglob("*") if p.is_file()}
check(
    f"every file under the data folder is 0600 and the folder 0700 ({sorted(modes)})",
    "checkpoints.db" in modes
    and all(m == 0o600 for m in modes.values())
    and stat.S_IMODE(data.stat().st_mode) == 0o700,
)

# In-process from here on.
from conductor import domains  # noqa: E402
from conductor.config import get_settings  # noqa: E402
from conductor.decisions import decide_approval  # noqa: E402
from conductor.events import EventKind  # noqa: E402
from conductor.graph.supervisor import RunError  # noqa: E402
from conductor.llm.model import ModelReply  # noqa: E402
from conductor.llm.scripted import ScriptedModel, ScriptedReply  # noqa: E402
from conductor.runtime import ask, open_runtime, resume, state  # noqa: E402


def results_of(log, run_id: str) -> int:
    return sum(e.kind == EventKind.TOOL_RESULT for e in log.read(run_id))


# The probe's counter checks itself on the finished run first.
with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
    assert results_of(runtime.log, a["run_id"]) == 1

# 3. six resumes of the same decided step at once
os.environ["CONDUCTOR_DATA_DIR"] = str(folder / "race")
answer = [ScriptedReply("answer", ModelReply(content='{"reply": "Done."}'))]
with open_runtime(
    get_settings(), model=ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE_PLAN))])
) as runtime:
    first = ask(runtime, "demo: note Milk")
    decide_approval(
        runtime.store,
        runtime.registry,
        first.approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )
    second = resume(runtime, first.run_id)
    decide_approval(
        runtime.store,
        runtime.registry,
        second.approval_id,
        "approve",
        channel="terminal",
        decided_by="owner",
    )
outcomes: list[str] = []
barrier = threading.Barrier(6)


def racer() -> None:
    with open_runtime(get_settings(), model=ScriptedModel(list(answer))) as mine:
        barrier.wait()
        try:
            outcomes.append(resume(mine, first.run_id).status)
        except RunError as error:
            outcomes.append(str(error).split(" ", 2)[2])


threads = [threading.Thread(target=racer) for _ in range(6)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
    ran = results_of(runtime.log, first.run_id)
    final = state(runtime, first.run_id).status
check(
    f"of six resumes at once, one runs the step and the rest are refused ({sorted(outcomes)})",
    outcomes.count("done") == 1
    and all(o in ("done", "is busy", "is not waiting") for o in outcomes)
    and ran == 1
    and final == "done",
)

# 4. a run that raises stops, frees its lease, and is never resumed
ok = True
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
for point in ("plan", "answer"):
    os.environ["CONDUCTOR_DATA_DIR"] = str(folder / f"stops-{point}")
    replies = [] if point == "plan" else [ScriptedReply("plan", ModelReply(content=ECHO_PLAN))]
    with open_runtime(get_settings(), model=ScriptedModel(replies)) as runtime:
        try:
            ask(runtime, "demo: say hi")
            ok = False
        except RunError:
            ok = False
        except Exception:
            pass
        [summary] = runtime.log.runs()
        run_id = summary.run_id
        stopped = state(runtime, run_id)
        ok &= (stopped.status, stopped.stopped_at) == ("stopped", point)
        try:
            resume(runtime, run_id)
            ok = False
        except RunError as error:
            ok &= str(error) == f"run {run_id} stopped at {point} and cannot be resumed"
        runtime.store.acquire(run_id, "8" * 32)
check("a run that raises stops where it was, frees its lease, and cannot be resumed", ok)

# 5. without the demo setting nothing is registered
os.environ["CONDUCTOR_DEMO"] = "false"
with open_runtime(get_settings(), model=ScriptedModel([])) as runtime:
    check(
        "without CONDUCTOR_DEMO the registry is exactly DOMAINS",
        runtime.registry.names == tuple(d.name for d in domains.DOMAINS),
    )

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The new test file covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `checkpoints.db` left for `sqlite3.connect` to create (`open_runtime`) | the coder's umask test | `0o600` | `0o644` |
| 2 | the lease not released when `start_run` raises (`ask`) | `test_a_run_that_raises_releases_its_lease_and_stops` | `acquire` by `OTHER` succeeds | `LeaseHeld` |
| 3 | `resume` without its lease (calls `resume_run` directly) | `test_a_busy_run_is_refused` | `is busy` | the run goes on |
| 4 | no renewal before a step (only before `chat`) | `test_a_lost_lease_stops_the_run_before_its_step_runs` | `lost its lease`, no `TOOL_RESULT` | the step runs |
| 5 | no renewal before `chat` (only before a step) | `test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step` | three renewals | one |
| 6 | the demo domain added whatever the setting (`open_runtime`) | `test_without_the_demo_setting_no_domain_is_registered` | `()` | `("demo",)` |
| 7 | the stopped check removed from `run_state` (both layers: `run_state` and `resume_run`'s first check) | `test_a_run_that_raises_releases_its_lease_and_stops` | `stopped` at `plan` | a `KeyError` or another status |
| 8 | the connection not closed (`open_runtime`) | the coder's closed-connection test | `ProgrammingError` | a result |

Reasonable variations that are correct: the leased model and runner as small private classes holding a reference to the runtime's current run; `contextlib.ExitStack` in `open_runtime`; the release in a `finally` with the `LeaseLost` mapping around both; `Runtime` with `slots=True`.

## 6. Project rules

- Searches 1 to 3.
- No model call and no step runs for a run without a lease renewed by this runtime just before it (read the leased wrappers and every call path to `chat` and `run`).
- Every file the runtime makes is `0600` and every folder `0700`; nothing is written outside the data folder.
- The demo runner touches no file and no network; no test or probe opens a connection beyond 127.0.0.1.

## 7. Out of scope

Each must be absent: any command (`ask`, `resume`, resuming from the approvals or escalations commands), resuming or repairing a stopped run, a lease timer or renewal during a model call, MCP, real domains, graph changes beyond `stopped`, changes to contracts, `policy`, `store`, `decisions`, routing, planning, or `cli`, WAL settings, migrations, deleting checkpoints.

## 8. Progress log

The entry exists, headed `## Phase 5d: the runtime (...)`, with `Tests: 523 -> <passed> (given 12)`, and each deviation it lists is real and justified.
