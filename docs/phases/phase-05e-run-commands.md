# Phase 5e: the run commands

## Corrections (2026-11-09, after the first review)

The first attempt failed on two mistakes in this spec, not in the code:

- `tests/e2e/test_cli_ask.py` numbered the plan approval `...03`; `decide()` takes the plan's decision id first, so it is `...04`, and every later id moves by one (the `--no-resume` test's step approval is `...07`, since that command also opens a runtime). The file below is corrected.
- Two 5d tests still required a run stopped at `plan` or `route` to be refused, which R1 changes. Both get a given edit (Scope), so they check that such a resume runs the node again.

The code already written for this phase stays; apply the corrected given file and the two edits, then run Acceptance again.

## Goal

The whole loop from the terminal, closing Phase 5:

- `conductor ask "<request>"` starts a run and prints where it stopped: the reply, or the approval or escalation to decide, with the command that decides it;
- `conductor resume <run_id>` continues a run;
- `approvals approve | reject | edit` and `escalations retry | cancel` **record, then resume the run** and print where it stopped next, unless `--no-resume`;
- a run that stopped inside `route`, `plan`, or `answer` (a Ctrl-C or an error during a model call) can be resumed, since those nodes change nothing outside.

Decided with the owner (2026-11-09, with 5d): a decision command records then resumes; `ask` and `resume` print text, exit 0 for every state reached, and take `--json`; a run leased by another process fails at once. Decided for 5e: when the resume after a recorded decision fails, the command **prints both** (the recorded line on stdout, the error on stderr) and **exits 1**; decision commands take **`--no-resume`**; a waiting run prints **the full request or escalation block and the next command**; runs stopped at **`route`, `plan`, or `answer` can be resumed**, any other stopped run stays refused.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Approvals and escalations")
- `src/conductor/cli/main.py` (4c: how commands print and fail), `src/conductor/runtime.py` (5d), `src/conductor/graph/supervisor.py`, `tests/support.py` (`run`, `runner`), the 4c tests in `tests/e2e/`

## Starting state

Phase 5d is built and verified, and everything is committed: N is `542`. **Sections: cli, core.** No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/graph/supervisor.py` | `RESUMABLE_STOPS` and the resume of such a run (Part 1) |
| `src/conductor/cli/main.py` | `ask`, `resume`, and resuming in the five decision commands (Parts 2 and 3) |
| `tests/e2e/test_cli_approvals.py`, `tests/e2e/test_cli_escalations.py`, `tests/e2e/test_cli_approvals_more.py` | given edits: every decision command these tests run gets `--no-resume`, since their requests belong to runs that have no checkpoint; nothing else changes (the files are given in full below) |
| `tests/e2e/test_cli_ask.py`, `tests/integration/test_resume_stopped.py` | given |
| `tests/integration/test_runtime.py` | given edit: in `test_a_run_that_raises_releases_its_lease_and_stops`, the last three lines (the `pytest.raises(RunError)` block and its message check) become the four lines below |
| `tests/integration/test_runtime_more.py` | given edit: in `test_run_errors_name_the_run_and_the_node`, the last three lines (the `pytest.raises(RunError) as stopped` block and its message check) become the three lines below |
| `tests/e2e/test_cli_ask_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The edit to `tests/integration/test_runtime.py`:

```python
        with pytest.raises(Exception, match="no scripted reply left for plan"):
            resume(runtime, run.run_id)
        assert state(runtime, run.run_id) == stopped
        runtime.store.acquire(run.run_id, OTHER)
```

The edit to `tests/integration/test_runtime_more.py`:

```python
        with pytest.raises(ScriptError):
            resume(runtime, run.run_id)
        assert state(runtime, run.run_id).stopped_at == "route"
```

## Out of scope

- Resuming a run stopped at any node but `route`, `plan`, or `answer`; undoing a step.
- Streaming the model's output, progress lines, colours, an interactive shell, `conductor runs status`, listing runs by status.
- Changes to `conductor.runtime`, `decisions`, `store`, `policy`, routing, planning, contracts, or the existing `list`, `show`, `doctor`, and `runs` commands.
- The approvals page (Phase 7).

## Dependencies

None new.

## Design

```python
# conductor/graph/supervisor.py: added
RESUMABLE_STOPS = ("route", "plan", "answer")
```

`resume_run` of a stopped run: when `stopped_at` is in `RESUMABLE_STOPS`, it invokes with `None` (LangGraph runs the stopped node again from its first line) and returns `run_state`; otherwise it raises the 5d message, `run <id> stopped at <node> and cannot be resumed`.

The commands (every arguments object as `json.dumps(args, ensure_ascii=False, sort_keys=True)`, every time `%Y-%m-%dT%H:%M:%SZ`, as in 4c):

| Command | Does | Prints (stdout) |
|---|---|---|
| `ask <request> [--json]` | `runtime.ask` | the state block (below); with `--json`, `json.dumps(dataclasses.asdict(state), indent=2)` |
| `resume <run_id> [--json]` | `runtime.resume` | the same |
| `approvals approve <id> [--note T] [--yes] [--no-resume]` | as in 4c, then, unless `--no-resume`, `runtime.resume` of the request's `run_id` | `Approved <id>.`, then the state block |
| `approvals reject <id> [--note T] [--no-resume]` | the same | `Rejected <id>.`, then the state block |
| `approvals edit <id> --args JSON [--note T] [--yes] [--no-resume]` | the same | `Approved <id> with edited arguments.`, then the state block |
| `escalations retry <id> [--note T] [--yes] [--no-resume]` | as in 4c, then, unless `--no-resume`, `runtime.resume` of the escalation's `run_id` | `Retry recorded for <id>.`, then the state block |
| `escalations cancel <id> [--note T] [--no-resume]` | the same | `Cancelled <id>.`, then the state block |

Every one of these commands opens `runtime.open_runtime(settings)`, read through the module (`from conductor import runtime`) so tests can replace it, and uses that runtime's `store` and `registry` (the registry therefore includes the demo domain when `CONDUCTOR_DEMO` is on). A declined prompt still prints `Nothing recorded.`, exits 0, and resumes nothing.

The state block, by status:

| Status | Lines |
|---|---|
| `waiting`, at an approval | the 4c request block of `store.approval(id)`, then `Next: conductor approvals approve <id> (or reject, or edit --args)` |
| `waiting`, at an escalation | the 4c escalation block of `store.escalation(id)`, then `Next: conductor escalations retry <id> (or cancel)` |
| `done` | `run <run_id>  done`, then the reply |
| `rejected` | `run <run_id>  rejected`, then `note: <note>` when the note is not empty |
| `cancelled` | `run <run_id>  cancelled` |
| `stopped` | `run <run_id>  stopped at <node>` |

Errors are one `Error: <message>` line on stderr and exit 1, as in 4c: `SettingsError`, `ValueError` (a request `route_request` refuses), `RunError`, and `StoreError`, plus the 4c errors of the decision commands before anything is recorded. After a decision is recorded, a `RunError` or `StoreError` from the resume is printed the same way, after the recorded line, and the command exits 1; the decision stays recorded. Any other exception (a model or runner fault inside the run) is not caught: the run is left stopped where it was.

## Facts

- The 4c tests decide on requests added straight to the store, for a run id with no checkpoint; resuming them would print `Error: no run ...` and exit 1. Hence `--no-resume` in those tests, the only change to them.
- LangGraph runs a stopped node again from its first line when invoked with `None` (5d's spike). `route`, `plan`, and `answer` do nothing before their model call that changes anything outside the run: their only effects are the model's events, which are logged again with a new decision id. `run_step` runs its runner; `ask_plan`, `ask_step`, and `record_escalation` add rows to the store, so running them again would add a second request or escalation.
- In the given tests, ids come from a counter in the order they are taken: `open_runtime` takes the holder id first, then `ask` the run id; then, in the graph, each `decide()` takes a decision id before its reply, and policy, store, and runner take request, escalation, and note ids as they go. Each command, `--no-resume` ones included, opens a new runtime and so takes a new holder id. For `demo: note Milk`: holder `01`, run `02`, plan decision `03`, plan approval `04`.

## Requirements

### Part 1: resuming a stopped model call

- **R1.** `RESUMABLE_STOPS` and `resume_run` are as under Design; a stopped run at any other node is refused as in 5d; a resumed stop at `answer` does not run any step again.

### Part 2: `ask` and `resume`

- **R2.** `conductor ask <request>` and `conductor resume <run_id>` open the runtime, call `runtime.ask` and `runtime.resume`, and print the state block, or the `--json` object, as under Design; they exit 0 for every status they print.
- **R3.** The state block is exactly as under Design for every status; the request and escalation blocks are the 4c ones (`_request_block`, `_escalation_block`), not copies.

### Part 3: deciding, then resuming

- **R4.** The five decision commands open the runtime and decide through `decide_approval` and `answer_escalation` with its `store` and `registry`, exactly as in 4c otherwise (the prompts, `--yes`, `--note`, `--args`, the messages).
- **R5.** After the recorded line, they resume the run of the request or escalation and print its state block, unless `--no-resume`, which prints only the recorded line.
- **R6.** A failed resume after a recorded decision prints the recorded line on stdout, the error on stderr, and exits 1, with the decision kept.

### Part 4: the rules

- **R7.** Errors are reported as under Design; no traceback for those; no request, reply, or argument text in a message.
- **R8.** `cli/main.py` reaches the graph only through `conductor.runtime`: it imports neither `conductor.graph` (except `RunError`, `RunState` from `conductor.graph.supervisor`), nor `langgraph`, nor `conductor.llm`, and builds no `Registry` itself any more.
- **R9.** `cli/main.py` and `graph/supervisor.py` stay at 100% of lines and branches.
- **R10.** The three 4c test files equal the given blocks below (the only change is `--no-resume`); every earlier test passes.

## Given tests

16 new tests in two files (counting each parameter set), and the three edited 4c files. Do not change them; if one fails, the code is wrong.

`tests/e2e/test_cli_ask.py` (11 tests)

```python
import itertools
import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run


def ID(n: int) -> str:
    return f"{n:032x}"


NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'
WHEN = "2026-11-09T09:00:00Z"


def plan_block(approval: int, run_id: int, stage: str = "plan") -> str:
    return (
        f"approval {ID(approval)}  {stage}  pending\n"
        f"run {ID(run_id)}  requested {WHEN}\n"
        '  1. demo.note  write  {"body": "", "tags": [], "title": "Milk"}\n'
        f"Next: conductor approvals approve {ID(approval)} (or reject, or edit --args)\n"
    )


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """What the model answers in the next command; each command opens a new runtime."""
    queue: list[tuple[str, str]] = []
    real = runtime.open_runtime

    @contextmanager
    def scripted(settings, *, model=None):
        answers = [ScriptedReply(point, ModelReply(content=text)) for point, text in queue]
        queue.clear()
        with real(settings, model=ScriptedModel(answers)) as opened:
            yield opened

    monkeypatch.setattr(runtime, "open_runtime", scripted)
    return queue


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


@pytest.mark.usefixtures("demo_on")
def test_a_read_only_request_is_answered(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN), ("answer", REPLY)]
    result = run("ask", "demo: say hi")
    assert (result.exit_code, result.stdout, result.stderr) == (
        0,
        f"run {ID(2)}  done\nDone.\n",
        "",
    )


@pytest.mark.usefixtures("demo_on")
def test_each_decision_resumes_the_run(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    asked = run("ask", "demo: note Milk")
    assert (asked.exit_code, asked.stdout) == (0, plan_block(4, 2))
    plan = run("approvals", "approve", ID(4), "--yes")
    assert (plan.exit_code, plan.stdout) == (0, f"Approved {ID(4)}.\n" + plan_block(6, 2, "step"))
    replies[:] = [("answer", REPLY)]
    step = run("approvals", "approve", ID(6), "--yes")
    assert (step.exit_code, step.stdout) == (
        0,
        f"Approved {ID(6)}.\nrun {ID(2)}  done\nDone.\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_a_rejection_ends_the_run(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    result = run("approvals", "reject", ID(4), "--note", "not now")
    assert (result.exit_code, result.stdout) == (
        0,
        f"Rejected {ID(4)}.\nrun {ID(2)}  rejected\nnote: not now\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_no_resume_only_records_and_resume_continues(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    recorded = run("approvals", "approve", ID(4), "--yes", "--no-resume")
    assert (recorded.exit_code, recorded.stdout) == (0, f"Approved {ID(4)}.\n")
    resumed = run("resume", ID(2))
    assert (resumed.exit_code, resumed.stdout) == (0, plan_block(7, 2, "step"))


def test_an_escalation_and_its_answers(replies: list) -> None:
    asked = run("ask", "Say hi back to me")
    assert (asked.exit_code, asked.stdout) == (
        0,
        f"escalation {ID(3)}  unknown_route  open\n"
        f"run {ID(2)}  raised {WHEN}\n"
        "no domains are registered\n"
        f"Next: conductor escalations retry {ID(3)} (or cancel)\n",
    )
    retried = run("escalations", "retry", ID(3), "--yes")
    assert retried.exit_code == 0
    assert retried.stdout.startswith(f"Retry recorded for {ID(3)}.\nescalation {ID(5)}  ")
    cancelled = run("escalations", "cancel", ID(5))
    assert (cancelled.exit_code, cancelled.stdout) == (
        0,
        f"Cancelled {ID(5)}.\nrun {ID(2)}  cancelled\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_json_output(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    asked = run("ask", "demo: note Milk", "--json")
    assert json.loads(asked.stdout) == {
        "run_id": ID(2),
        "status": "waiting",
        "approval_id": ID(4),
        "escalation_id": None,
        "reply": None,
        "note": "",
        "stopped_at": None,
    }
    run("approvals", "reject", ID(4), "--no-resume")
    resumed = run("resume", ID(2), "--json")
    assert json.loads(resumed.stdout)["status"] == "rejected"


@pytest.mark.usefixtures("demo_on")
def test_a_busy_run_keeps_the_decision_and_says_why(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    with runtime.open_runtime(get_settings()) as opened:
        opened.store.acquire(ID(2), "9" * 32)
    result = run("approvals", "approve", ID(4), "--yes")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        f"Approved {ID(4)}.\n",
        f"Error: run {ID(2)} is busy\n",
    )


@pytest.mark.usefixtures("demo_on")
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("ask", "   "), "Error: a request must have 1 to 2000 characters\n"),
        (("resume", "9" * 32), f"Error: no run {'9' * 32}\n"),
    ],
)
def test_errors(replies: list, args: tuple[str, ...], message: str) -> None:
    result = run(*args)
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", message)


@pytest.mark.usefixtures("demo_on")
def test_a_finished_run_is_not_resumed(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN), ("answer", REPLY)]
    run("ask", "demo: say hi")
    result = run("resume", ID(2))
    assert (result.exit_code, result.stderr) == (1, f"Error: run {ID(2)} is not waiting\n")


@pytest.mark.usefixtures("demo_on")
def test_a_run_stopped_at_a_model_call_is_resumed(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN)]
    stopped = run("ask", "demo: say hi")
    assert stopped.exit_code == 1 and stopped.exception is not None
    replies[:] = [("answer", REPLY)]
    resumed = run("resume", ID(2))
    assert (resumed.exit_code, resumed.stdout) == (0, f"run {ID(2)}  done\nDone.\n")
```

`tests/integration/test_resume_stopped.py` (5 tests)

```python
import itertools
from datetime import UTC, datetime

import pytest

from conductor import clock, ids
from conductor.config import get_settings
from conductor.events import EventKind
from conductor.graph.supervisor import RESUMABLE_STOPS, RunError, RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.runtime import DemoRunner, ask, open_runtime, resume, state

ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def model(*replies: tuple[str, str]) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies])


def test_the_resumable_stops() -> None:
    assert RESUMABLE_STOPS == ("route", "plan", "answer")


@pytest.mark.parametrize(
    ("request_text", "first", "then", "node"),
    [
        ("Say hi back to me", [], [("route", '{"domain": "demo"}'), ("plan", ECHO_PLAN)], "route"),
        ("demo: say hi", [], [("plan", ECHO_PLAN)], "plan"),
        ("demo: say hi", [("plan", ECHO_PLAN)], [], "answer"),
    ],
)
def test_a_run_stopped_at_a_model_call_runs_that_node_again(
    request_text: str, first: list, then: list, node: str
) -> None:
    with open_runtime(get_settings(), model=model(*first)) as one:
        with pytest.raises(Exception, match="no scripted reply left"):
            ask(one, request_text)
        [summary] = one.log.runs()
        assert state(one, summary.run_id).stopped_at == node
    with open_runtime(get_settings(), model=model(*then, ("answer", REPLY))) as two:
        assert resume(two, summary.run_id) == RunState(
            run_id=summary.run_id, status="done", reply="Done."
        )
        results = [e for e in two.log.read(summary.run_id) if e.kind == EventKind.TOOL_RESULT]
        assert len(results) == 1


def test_a_run_stopped_at_a_step_stays_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def broken(self, action, args):
        calls.append(action.name)
        raise RuntimeError("the runner broke")

    monkeypatch.setattr(DemoRunner, "run", broken)
    with open_runtime(get_settings(), model=model(("plan", ECHO_PLAN))) as opened:
        with pytest.raises(RuntimeError):
            ask(opened, "demo: say hi")
        [summary] = opened.log.runs()
        assert state(opened, summary.run_id).stopped_at == "run_step"
        with pytest.raises(RunError) as raised:
            resume(opened, summary.run_id)
        assert str(raised.value) == (
            f"run {summary.run_id} stopped at run_step and cannot be resumed"
        )
    assert calls == ["echo"]
```

The edited `tests/e2e/test_cli_approvals.py` (replace the file with this)

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, domains
from conductor.cli.main import app
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.domains import demo
from conductor.store import Store
from tests.support import run, runner

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
FIRST, SECOND = "1" * 32, "2" * 32
RUN = "a" * 32
ECHO = PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"})
NOTE = PlannedStep(number=2, action="demo.note", effect="write", args={"title": "Café", "tags": []})


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setattr(clock, "now", lambda: AT)
    monkeypatch.setattr(domains, "DOMAINS", (demo.DOMAIN,))
    return Store(tmp_path / "data" / "conductor.db")


def add(db: Store, approval_id: str, stage: str, steps, hour: int) -> ApprovalRequest:
    request = ApprovalRequest(
        approval_id=approval_id,
        run_id=RUN,
        stage=stage,
        steps=steps,
        args_sha256=steps_digest(steps),
        requested_at=datetime(2026, 11, 8, hour, 0, tzinfo=UTC),
    )
    db.add_request(request)
    return request


def note_request(db: Store) -> ApprovalRequest:
    return add(db, FIRST, "step", (NOTE.model_copy(update={"number": 1}),), 9)


SHOWN = (
    f"approval {FIRST}  step  pending\n"
    f"run {RUN}  requested 2026-11-08T09:00:00Z\n"
    '  1. demo.note  write  {"tags": [], "title": "Café"}\n'
)


def test_nothing_pending(db: Store) -> None:
    result = run("approvals", "list")
    assert (result.exit_code, result.stdout) == (0, "No pending approvals.\n")


def test_the_pending_list(db: Store) -> None:
    second = add(db, SECOND, "plan", (ECHO, NOTE), 8)
    first = note_request(db)
    result = run("approvals", "list")
    assert result.stdout == (
        f"{SECOND}  2026-11-08T08:00:00Z  plan  demo.echo, demo.note\n"
        f"{FIRST}  2026-11-08T09:00:00Z  step  demo.note\n"
    )
    listed = json.loads(run("approvals", "list", "--json").stdout)
    assert listed == [second.model_dump(mode="json"), first.model_dump(mode="json")]


def test_show_a_pending_request(db: Store) -> None:
    request = note_request(db)
    assert run("approvals", "show", FIRST).stdout == SHOWN
    shown = json.loads(run("approvals", "show", FIRST, "--json").stdout)
    assert shown == {"request": request.model_dump(mode="json"), "decision": None}


def test_show_a_decided_request(db: Store) -> None:
    note_request(db)
    edit = run(
        "approvals",
        "edit",
        "--no-resume",
        FIRST,
        "--args",
        '{"title": "Eggs"}',
        "--note",
        "fewer",
        "--yes",
    )
    assert (edit.exit_code, edit.stdout) == (0, f"Approved {FIRST} with edited arguments.\n")
    assert run("approvals", "show", FIRST).stdout == (
        f"approval {FIRST}  step  edited by owner (terminal) at 2026-11-08T10:00:00Z\n"
        f"run {RUN}  requested 2026-11-08T09:00:00Z\n"
        '  1. demo.note  write  {"tags": [], "title": "Café"}\n'
        'edited args: {"title": "Eggs"}\n'
        "note: fewer\n"
    )


def test_approve_asks_first(db: Store) -> None:
    note_request(db)
    result = runner.invoke(app, ["approvals", "approve", "--no-resume", FIRST], input="y\n")
    assert result.exit_code == 0
    assert result.stdout == SHOWN + "Approve? [y/N]: y\n" + f"Approved {FIRST}.\n"
    assert db.approval(FIRST).decision.verdict == "approve"


def test_approve_can_be_declined(db: Store) -> None:
    note_request(db)
    result = runner.invoke(app, ["approvals", "approve", "--no-resume", FIRST], input="n\n")
    assert result.exit_code == 0
    assert result.stdout.endswith("Approve? [y/N]: n\nNothing recorded.\n")
    assert db.approval(FIRST).decision is None


def test_approve_with_yes_and_reject_do_not_ask(db: Store) -> None:
    note_request(db)
    add(db, SECOND, "plan", (ECHO, NOTE), 8)
    approved = run("approvals", "approve", "--no-resume", FIRST, "--yes")
    rejected = run("approvals", "reject", "--no-resume", SECOND, "--note", "not today")
    assert (approved.stdout, rejected.stdout) == (f"Approved {FIRST}.\n", f"Rejected {SECOND}.\n")
    decision = db.approval(SECOND).decision
    assert (decision.verdict, decision.note) == ("reject", "not today")


def test_an_edit_shows_the_new_arguments_before_asking(db: Store) -> None:
    note_request(db)
    result = runner.invoke(
        app, ["approvals", "edit", "--no-resume", FIRST, "--args", '{"title": "Eggs"}'], input="y\n"
    )
    assert result.stdout == (
        SHOWN
        + 'edited args: {"title": "Eggs"}\n'
        + "Approve with these arguments? [y/N]: y\n"
        + f"Approved {FIRST} with edited arguments.\n"
    )


def test_an_edit_that_does_not_fit(db: Store) -> None:
    note_request(db)
    result = run(
        "approvals",
        "edit",
        "--no-resume",
        FIRST,
        "--args",
        '{"title": "", "tags": ["Home"]}',
        "--yes",
    )
    assert result.exit_code == 1
    assert result.stderr == (
        "Error: decision refused: invalid_edit\n"
        "  title: string_too_short\n"
        "  tags.0: string_pattern_mismatch\n"
    )
    assert db.approval(FIRST).decision is None


@pytest.mark.parametrize("given", ["[1]", "not json", '{"title": NaN}'])
def test_edit_arguments_must_be_a_json_object(db: Store, given: str) -> None:
    note_request(db)
    result = run("approvals", "edit", "--no-resume", FIRST, "--args", given, "--yes")
    assert (result.exit_code, result.stderr) == (1, "Error: --args must be a JSON object\n")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("show", "9" * 32), f"Error: no approval {'9' * 32}\n"),
        (
            ("approve", "--no-resume", FIRST, "--yes"),
            f"Error: approval {FIRST} is already decided\n",
        ),
        (
            ("reject", "--no-resume", FIRST, "--note", "x" * 501),
            "Error: note must be at most 500 characters\n",
        ),
    ],
)
def test_errors(db: Store, args: tuple[str, ...], message: str) -> None:
    note_request(db)
    run("approvals", "reject", "--no-resume", FIRST)
    result = run("approvals", *args)
    assert (result.exit_code, result.stderr) == (1, message)


def test_an_action_that_is_not_registered(db: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    note_request(db)
    monkeypatch.setattr(domains, "DOMAINS", ())
    result = run("approvals", "approve", "--no-resume", FIRST, "--yes")
    assert (result.exit_code, result.stderr) == (1, "Error: no action demo.note\n")
    assert db.approval(FIRST).decision is None
```

The edited `tests/e2e/test_cli_escalations.py` (replace the file with this)

```python
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.cli.main import app
from conductor.contracts import Escalation, FieldProblem
from conductor.store import Store
from tests.support import run, runner

START = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIRST, SECOND = f"{1:032x}", f"{2:032x}"
RUN = "a" * 32
INVALID = Escalation(
    kind="invalid_model_output",
    detail=f"decision {'d' * 32}: the model's reply does not fit the decision point",
    run_id=RUN,
    problems=(FieldProblem(loc="action", code="literal_error"),),
)
DOWN = Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    times = iter([START, START + timedelta(minutes=5), START + timedelta(hours=1)])
    monkeypatch.setattr(clock, "now", lambda: next(times))
    numbers = iter(range(1, 10))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(numbers):032x}")
    store = Store(tmp_path / "data" / "conductor.db")
    store.add_escalation(INVALID)
    store.add_escalation(DOWN)
    return store


def test_the_open_escalations(db: Store) -> None:
    assert run("escalations", "list").stdout == (
        f"{FIRST}  2026-11-08T09:00:00Z  invalid_model_output  run {RUN}\n"
        f"{SECOND}  2026-11-08T09:05:00Z  model_unavailable  run {RUN}\n"
    )
    listed = json.loads(run("escalations", "list", "--json").stdout)
    assert [entry["escalation_id"] for entry in listed] == [FIRST, SECOND]
    assert listed[0] == {
        "escalation_id": FIRST,
        "raised_at": "2026-11-08T09:00:00Z",
        "escalation": INVALID.model_dump(mode="json"),
        "answer": None,
    }


def test_nothing_open(tmp_path: Path) -> None:
    result = run("escalations", "list")
    assert (result.exit_code, result.stdout) == (0, "No open escalations.\n")


def test_show_an_escalation(db: Store) -> None:
    assert run("escalations", "show", FIRST).stdout == (
        f"escalation {FIRST}  invalid_model_output  open\n"
        f"run {RUN}  raised 2026-11-08T09:00:00Z\n"
        f"decision {'d' * 32}: the model's reply does not fit the decision point\n"
        "  action: literal_error\n"
    )


def test_retry_asks_first(db: Store) -> None:
    result = runner.invoke(
        app, ["escalations", "retry", "--no-resume", SECOND, "--note", "back up"], input="y\n"
    )
    assert result.exit_code == 0
    assert result.stdout.endswith("Retry? [y/N]: y\n" + f"Retry recorded for {SECOND}.\n")
    assert run("escalations", "show", SECOND).stdout == (
        f"escalation {SECOND}  model_unavailable  "
        "retry by owner (terminal) at 2026-11-08T10:00:00Z\n"
        f"run {RUN}  raised 2026-11-08T09:05:00Z\n"
        "model unavailable: timeout\n"
        "note: back up\n"
    )
    assert [e.escalation_id for e in db.open_escalations()] == [FIRST]


def test_cancel_does_not_ask(db: Store) -> None:
    result = run("escalations", "cancel", "--no-resume", FIRST)
    assert (result.exit_code, result.stdout) == (0, f"Cancelled {FIRST}.\n")
    again = run("escalations", "retry", "--no-resume", FIRST, "--yes")
    assert (again.exit_code, again.stderr) == (
        1,
        f"Error: escalation {FIRST} is already answered\n",
    )
```

The edited `tests/e2e/test_cli_approvals_more.py` (replace the file with this)

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, domains
from conductor.cli.main import app
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.domains import demo
from conductor.store import Store
from tests.support import run, runner

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
FIRST = "1" * 32
RUN = "a" * 32
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Café", "tags": []})


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setattr(clock, "now", lambda: AT)
    monkeypatch.setattr(domains, "DOMAINS", (demo.DOMAIN,))
    store = Store(tmp_path / "data" / "conductor.db")
    store.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id=RUN,
            stage="step",
            steps=(NOTE,),
            args_sha256=steps_digest((NOTE,)),
            requested_at=datetime(2026, 11, 8, 9, 0, tzinfo=UTC),
        )
    )
    return store


def test_show_json_includes_an_answer(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    answered = run(
        "escalations", "retry", "--no-resume", raised.escalation_id, "--note", "back up", "--yes"
    )
    assert answered.exit_code == 0
    shown = json.loads(run("escalations", "show", raised.escalation_id, "--json").stdout)
    stored = db.escalation(raised.escalation_id).answer
    assert stored is not None
    assert shown["answer"] == stored.model_dump(mode="json")


def test_a_declined_retry_records_nothing(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    result = runner.invoke(
        app, ["escalations", "retry", "--no-resume", raised.escalation_id], input="n\n"
    )
    assert result.exit_code == 0
    assert result.stdout.endswith("Retry? [y/N]: n\nNothing recorded.\n")
    assert [item.escalation_id for item in db.open_escalations()] == [raised.escalation_id]


def test_a_declined_edit_records_nothing(db: Store) -> None:
    result = runner.invoke(
        app, ["approvals", "edit", "--no-resume", FIRST, "--args", '{"title": "Eggs"}'], input="n\n"
    )
    assert result.exit_code == 0
    assert result.stdout.endswith(
        'edited args: {"title": "Eggs"}\n'
        "Approve with these arguments? [y/N]: n\n"
        "Nothing recorded.\n"
    )
    assert db.approval(FIRST).decision is None


def test_infinity_is_refused_and_an_empty_object_is_judged(db: Store) -> None:
    refused = run(
        "approvals", "edit", "--no-resume", FIRST, "--args", '{"title": Infinity}', "--yes"
    )
    assert (refused.exit_code, refused.stderr) == (1, "Error: --args must be a JSON object\n")
    assert db.approval(FIRST).decision is None
    judged = run("approvals", "edit", "--no-resume", FIRST, "--args", "{}", "--yes")
    assert judged.exit_code == 1
    assert judged.stderr.startswith("Error: decision refused:")
    assert "--args must be a JSON object" not in judged.stderr
    assert db.approval(FIRST).decision is None


def test_a_bad_decided_by_prints_the_settings_error(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", "Owner")
    result = run("approvals", "approve", "--no-resume", FIRST, "--yes")
    assert result.exit_code == 1
    assert result.stderr == (
        "Error: CONDUCTOR_DECIDED_BY: must be a lowercase name of up to 32 characters\n"
    )
    assert db.approval(FIRST).decision is None


def test_an_approval_without_a_note_shows_who_approved(db: Store) -> None:
    assert run("approvals", "approve", "--no-resume", FIRST, "--yes").exit_code == 0
    assert run("approvals", "show", FIRST).stdout == (
        f"approval {FIRST}  step  approved by owner (terminal) at 2026-11-08T10:00:00Z\n"
        f"run {RUN}  requested 2026-11-08T09:00:00Z\n"
        '  1. demo.note  write  {"tags": [], "title": "Café"}\n'
    )
    shown = json.loads(run("approvals", "show", FIRST, "--json").stdout)
    decision = db.approval(FIRST).decision
    assert decision is not None
    assert shown["decision"] == decision.model_dump(mode="json")


def test_a_cancellation_without_a_note_shows_who_cancelled(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    assert run("escalations", "cancel", "--no-resume", raised.escalation_id).exit_code == 0
    assert run("escalations", "show", raised.escalation_id).stdout == (
        f"escalation {raised.escalation_id}  model_unavailable  "
        "cancel by owner (terminal) at 2026-11-08T10:00:00Z\n"
        f"run {RUN}  raised 2026-11-08T10:00:00Z\n"
        "model unavailable: timeout\n"
    )
```

## Tests to write

In `tests/e2e/test_cli_ask_more.py`, each with its deciding input:

- R2: `resume --json` of a waiting run; `ask` with a bad `CONDUCTOR_DEMO` prints the settings error and exits 1.
- R3: a `stopped` state prints `run <id>  stopped at <node>` (replace `runtime.resume` with a function that returns one; no command reaches it otherwise); a rejection with no note prints only `run <id>  rejected`; an escalation block that lists problems (an invalid planner reply) keeps them before its `Next:` line.
- R4: `approvals edit --yes` resumes and runs the step with the edited arguments (the note's title in the `TOOL_CALL` event); a declined `approve` prompt prints `Nothing recorded.` and leaves the run waiting.
- R5: `escalations retry --no-resume` prints only `Retry recorded for <id>.`; `escalations cancel` without `--no-resume` prints the `cancelled` block.
- R6: a `reject` whose resume finds the run busy prints `Rejected <id>.` and the busy error, exits 1, and the rejection is recorded.
- R7: an `ask` whose request is 2001 characters prints the request error with no traceback.

## Rules for this phase

- **`cli` is thin** (`AGENTS.md`): parse, call `runtime` or `decisions`, print. No decision logic and no graph code in `cli/main.py`.
- **Side effects need approval** (`AGENTS.md` rule 7): a resumed stop never runs a step again; only `route`, `plan`, and `answer` are resumed.
- **Synthetic data only**: tests run under the test's data folder with `ScriptedModel`.
- Earlier tests stay unchanged, except the given edits.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 16 = 558 passed;
- the given files: `.venv/bin/python -m pytest tests/e2e/test_cli_ask.py tests/integration/test_resume_stopped.py --no-cov`, exactly `16 passed`; and `.venv/bin/python -m pytest tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py tests/e2e/test_cli_approvals_more.py --no-cov` passes;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/cli/main.py,*/conductor/graph/supervisor.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 5e`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) (langgraph|conductor\.llm|conductor\.graph(\.supervisor)? import [^R])" -- src/conductor/cli`
  - `git grep --untracked -n -E "Registry\(|from conductor\.runtime import|start_run|resume_run" -- src/conductor/cli`
- `git diff --stat HEAD -- src/conductor/runtime.py src/conductor/decisions.py src/conductor/store.py src/conductor/policy.py src/conductor/routing src/conductor/planning src/conductor/contracts tests/unit tests/integration/test_supervisor.py tests/support.py` prints nothing; `git diff HEAD -- tests/integration/test_runtime.py tests/integration/test_runtime_more.py` shows only the two given edits.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 5e: the run commands (YYYY-MM-DD)`, with `Tests: 542 -> <passed> (given 16)`.
