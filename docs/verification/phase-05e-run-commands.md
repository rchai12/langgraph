# Verify Phase 5e: the run commands

Spec: `docs/phases/phase-05e-run-commands.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 5e` on your own report.

The coder added `RESUMABLE_STOPS` to `conductor.graph.supervisor`, added `ask` and `resume` to `conductor.cli.main` and resuming to its five decision commands, replaced the three 4c test files with the given versions (`--no-resume` only), copied `tests/e2e/test_cli_ask.py` and `tests/integration/test_resume_stopped.py` (16 tests), and wrote `tests/e2e/test_cli_ask_more.py`.

## 1. Gates

N is `542`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 558 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/cli/main.py,*/conductor/graph/supervisor.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/e2e/test_cli_ask.py tests/integration/test_resume_stopped.py --no-cov` | exactly `16 passed` |
| each of `tests/e2e/test_cli_approvals.py`, `tests/e2e/test_cli_escalations.py`, `tests/e2e/test_cli_approvals_more.py` against the spec's block (save the block, then `diff`) | no output; and `git diff HEAD` of them shows `--no-resume` added to decision commands and nothing else besides line wrapping |
| `.venv/bin/python scripts/check_reports.py --phase 5e` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/runtime.py src/conductor/decisions.py src/conductor/store.py src/conductor/policy.py src/conductor/routing src/conductor/planning src/conductor/contracts tests/unit tests/integration/test_supervisor.py tests/integration/test_runtime.py tests/support.py` | no output |
| `git diff HEAD -- src/conductor/graph/supervisor.py` | only `RESUMABLE_STOPS` and the stopped branch of `resume_run` |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) (langgraph|conductor\.llm|conductor\.graph(\.supervisor)? import [^R])" -- src/conductor/cli`
2. `git grep --untracked -n -E "Registry\(|from conductor\.runtime import|start_run|resume_run" -- src/conductor/cli`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files, including the three replaced 4c files, equal the spec's blocks.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_resumable_stops`, `test_a_run_stopped_at_a_model_call_runs_that_node_again` (three nodes), `test_a_run_stopped_at_a_step_stays_stopped`; probe "a run stopped at answer resumes to done ..." | pass; ok |
| R2 | `test_a_read_only_request_is_answered`, `test_json_output`, `test_a_finished_run_is_not_resumed`; the coder's `--json` and settings tests | pass |
| R3 | `test_each_decision_resumes_the_run`, `test_an_escalation_and_its_answers`, `test_a_rejection_ends_the_run`; the coder's stopped, no-note, and problems tests; read the block function: it calls the 4c `_request_block` and `_escalation_block` | pass; the same |
| R4 | the three edited 4c files; the coder's edit and declined-prompt tests | pass |
| R5 | `test_no_resume_only_records_and_resume_continues`; the coder's retry and cancel tests; probe "every run reaches its end through ask, the decision commands, and resume" | pass; ok |
| R6 | `test_a_busy_run_keeps_the_decision_and_says_why`; the coder's busy rejection test | pass |
| R7 | `test_errors`; the coder's 2001-character test | pass |
| R8 | searches 1 and 2 | no output |
| R9 | the coverage gate | as in the Gates |
| R10 | the 4c-files gate; the full check | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It replaces `runtime.open_runtime` with one that gives each command a `ScriptedModel` and plays 120 random demo runs through `CliRunner`: `ask`, then each approval decided with or without `--no-resume` (and `resume` after it), rejecting some. Its line readers check themselves on known text first; a stop at those `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 5e. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from typer.testing import CliRunner

from conductor import runtime
from conductor.cli.main import app
from conductor.config import get_settings
from conductor.events import EventKind
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


for key in list(os.environ):
    if key.startswith("CONDUCTOR_") or "TRACING" in key:
        del os.environ[key]
os.environ["CONDUCTOR_DEMO"] = "true"
os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"
rng = random.Random(31)
cli = CliRunner()
queue: list[tuple[str, str]] = []
real_open = runtime.open_runtime


@contextmanager
def scripted(settings, *, model=None):
    answers = [ScriptedReply(p, ModelReply(content=c)) for p, c in queue]
    queue.clear()
    with real_open(settings, model=ScriptedModel(answers)) as opened:
        yield opened


runtime.open_runtime = scripted
NEXT = re.compile(r"^Next: conductor (approvals approve|escalations retry) ([0-9a-f]{32}) ")
DONE = re.compile(r"^run ([0-9a-f]{32})  (done|rejected|cancelled)$")


def next_id(text: str) -> tuple[str, str] | None:
    for line in text.splitlines():
        found = NEXT.match(line)
        if found:
            return found.group(1), found.group(2)
    return None


def final(text: str) -> str | None:
    for line in text.splitlines():
        found = DONE.match(line)
        if found:
            return found.group(2)
    return None


# The probe's readers check themselves on known text first.
assert next_id("x\nNext: conductor approvals approve " + "a" * 32 + " (or reject)\n") == (
    "approvals approve",
    "a" * 32,
)
assert final("Approved x.\nrun " + "b" * 32 + "  done\nDone.\n") == "done"
assert next_id("run " + "b" * 32 + "  done\n") is None

ARGS = {"echo": {"text": "hi"}, "note": {"title": "Milk"}, "delegate": {"task": "tidy"}}
ok_flow = True
ok_once = True
ok_json = True
ok_next = True
seen: dict[str, int] = {}
for _scenario in range(120):
    os.environ["CONDUCTOR_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "data")
    actions = [rng.choice(["echo", "note", "delegate"]) for _ in range(rng.randint(1, 3))]
    plan = json.dumps({"steps": [{"action": a, "args": ARGS[a]} for a in actions]})
    queue[:] = [("plan", plan), ("answer", '{"reply": "Done."}')]
    out = cli.invoke(app, ["ask", "demo: do it"])
    ok_flow &= out.exit_code == 0
    decisions = 0
    for _ in range(12):
        status = final(out.stdout)
        if status is not None:
            seen[status] = seen.get(status, 0) + 1
            break
        found = next_id(out.stdout)
        if found is None:
            ok_flow = False
            break
        _, approval_id = found
        with real_open(get_settings(), model=ScriptedModel([])) as opened:
            pending = [r.approval_id for r in opened.store.pending()]
        ok_next &= pending == [approval_id]
        queue[:] = [("answer", '{"reply": "Done."}')]
        verdict = rng.choice(["approve", "approve", "approve", "reject"])
        args = ["approvals", verdict, approval_id] + (["--yes"] if verdict == "approve" else [])
        if rng.random() < 0.3:
            recorded = cli.invoke(app, [*args, "--no-resume"])
            ok_flow &= recorded.exit_code == 0 and len(recorded.stdout.splitlines()) == 1
            queue[:] = [("answer", '{"reply": "Done."}')]
            run_id = re.search(r"run ([0-9a-f]{32})", out.stdout).group(1)
            out = cli.invoke(app, ["resume", run_id])
        else:
            out = cli.invoke(app, args)
            word = "Approved" if verdict == "approve" else "Rejected"
            ok_flow &= out.stdout.startswith(f"{word} {approval_id}.")
        ok_flow &= out.exit_code == 0
        decisions += 1
    else:
        ok_flow = False
    with real_open(get_settings(), model=ScriptedModel([])) as opened:
        [summary] = opened.log.runs()
        events = opened.log.read(summary.run_id)
        results = [e.payload["step"] for e in events if e.kind == EventKind.TOOL_RESULT]
        ok_once &= len(results) == len(set(results))
        again = cli.invoke(app, ["resume", summary.run_id, "--json"])
        ok_json &= (again.exit_code, again.stdout, again.stderr) == (
            1,
            "",
            f"Error: run {summary.run_id} is not waiting\n",
        )
check(f"every run reaches its end through ask, the decision commands, and resume ({seen})", ok_flow)
check("every Next line names exactly the one pending approval", ok_next)
check("no step ran twice", ok_once)
check("resuming a finished run is refused on stderr, also with --json", ok_json)

# A stopped run resumes only at a model node.
os.environ["CONDUCTOR_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "data")
queue[:] = [("plan", json.dumps({"steps": [{"action": "echo", "args": ARGS["echo"]}]}))]
stopped = cli.invoke(app, ["ask", "demo: say hi"])
with real_open(get_settings(), model=ScriptedModel([])) as opened:
    [summary] = opened.log.runs()
queue[:] = [("answer", '{"reply": "Done."}')]
again = cli.invoke(app, ["resume", summary.run_id])
check(
    "a run stopped at answer resumes to done, without running its step again",
    stopped.exit_code == 1 and again.stdout == f"run {summary.run_id}  done\nDone.\n",
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The new test file covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `run_step` added to `RESUMABLE_STOPS` | `test_a_run_stopped_at_a_step_stays_stopped` | `cannot be resumed`, one call | the step runs again |
| 2 | the stopped branch of `resume_run` removed (resumable stops refused as in 5d) | `test_a_run_stopped_at_a_model_call_runs_that_node_again`, `plan` | `done` | `cannot be resumed` |
| 3 | `approve` does not resume | `test_each_decision_resumes_the_run` | the step block after `Approved` | only `Approved` |
| 4 | `--no-resume` ignored (`approve`) | `test_no_resume_only_records_and_resume_continues` | one line | the step block too |
| 5 | the resume error swallowed after a recorded decision (exit 0) | `test_a_busy_run_keeps_the_decision_and_says_why` | exit 1, the busy error | exit 0 |
| 6 | the decision commands keep building `Registry(domains.DOMAINS)` | `test_each_decision_resumes_the_run` (demo on, `DOMAINS` empty) | `Approved` | `no action demo.note` |
| 7 | the `Next:` line left out of the approval block | `test_a_rejection_ends_the_run`'s `ask`, or `test_each_decision_resumes_the_run` | the pinned block | without `Next:` |
| 8 | `runtime.open_runtime` imported by name (`from conductor.runtime import open_runtime`) | any test of `tests/e2e/test_cli_ask.py` | passes | `ScriptError` or a real Ollama call refused |

Reasonable variations that are correct: one private helper that opens the runtime and maps the errors; one that prints the state block; the decision commands sharing a private "record, then resume" helper; `dataclasses.asdict` or an explicit dict for `--json` with the same keys.

## 6. Project rules

- Searches 1 and 2.
- `cli/main.py` has no decision logic: it parses, calls `runtime` or `decisions`, and prints; it never compares verdicts, statuses beyond choosing the block, or digests.
- Every error is one `Error:` line on stderr; after a recorded decision, the recorded line stays on stdout.
- No test or probe opens a connection beyond 127.0.0.1; models are scripted.

## 7. Out of scope

Each must be absent: resuming stops at any node but `route`, `plan`, or `answer`, streaming or progress output, colours, an interactive shell, `runs status`, changes to `runtime`, `decisions`, `store`, `policy`, routing, planning, contracts, or the existing `list`, `show`, `doctor`, and `runs` commands, the approvals page.

## 8. Progress log

The entry exists, headed `## Phase 5e: the run commands (...)`, with `Tests: 542 -> <passed> (given 16)`, and each deviation it lists is real and justified.
