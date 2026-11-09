# Phase 4c: the approvals and escalations commands

## Goal

The person's side of Phase 4, in the terminal:

- `conductor.decisions` (critical): `decide_approval` and `answer_escalation`, the one sequence that every channel uses (the terminal now, the approvals page in Phase 7): read what is stored, refuse what is already decided, build the decision, let `policy.apply_decision` judge it, and record it only when it is accepted;
- `conductor approvals list | show | approve | reject | edit` and `conductor escalations list | show | retry | cancel`, thin commands over the store and `decisions`;
- the setting `CONDUCTOR_DECIDED_BY` (default `owner`), recorded with every decision.

Recording a decision does not resume anything yet: the graph that waits on these decisions is Phase 5.

Decided with the owner (2026-11-08): who decided is **a setting**, default `owner`; `approve`, `edit`, and `retry` **show what they will allow and ask** `y/N`, unless `--yes`; `reject` and `cancel` never ask, since they only stop things; edited arguments come as **`--args` JSON**; `list` and `show` take **`--json`**, which prints the stored contracts.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Approve", "Approvals and escalations")
- `src/conductor/policy.py` (4a), `src/conductor/store.py` (4b), `src/conductor/contracts/approvals.py`, `src/conductor/cli/main.py` (how commands report errors), `src/conductor/config.py`, `tests/support.py` (`run`, `runner`)

## Starting state

Phase 4b is built, its progress entry written, its review PASS, and all committed: N is `378`. **Sections: cli, core.** No `decisions.py` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/decisions.py` | `NOTE_MESSAGE`, `decide_approval`, `answer_escalation` (Part 1, critical) |
| `src/conductor/cli/main.py` | the `approvals` and `escalations` command groups (Part 2) |
| `src/conductor/config.py` | the field `decided_by` and its check (Part 3) |
| `scripts/critical_modules.txt` | add the line `decisions.py` after `store.py` |
| `docs/testing.md` | under "Critical modules", add `` - `decisions.py` (a decision is recorded only after the policy accepts it; Phase 4c) `` after the `store.py` line |
| `tests/unit/test_decisions.py`, `tests/e2e/test_cli_approvals.py`, `tests/e2e/test_cli_escalations.py` | given |
| `tests/unit/test_decisions_more.py`, `tests/e2e/test_cli_approvals_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Resuming a thread, leases, `interrupt`, events (Phase 5); the approvals page (Phase 7).
- Opening an editor, `--args-file`, approving several requests at once, deleting or listing decided requests, filters.
- Escalation answers other than `retry` and `cancel`.
- Changes to `policy.py`, `store.py`, any contract, or the existing commands.

## Dependencies

None new.

## Design

```python
# conductor/decisions.py
NOTE_MESSAGE = "note must be at most 500 characters"

def decide_approval(
    store: Store,
    registry: Registry,
    approval_id: str,
    verdict: Verdict,
    *,
    channel: Channel,
    decided_by: str,
    note: str = "",
    edited_args: dict[str, Any] | None = None,
) -> Approved | Rejected: ...

def answer_escalation(
    store: Store,
    escalation_id: str,
    answer: Answer,
    *,
    channel: Channel,
    decided_by: str,
    note: str = "",
) -> StoredEscalation: ...
```

```python
# conductor/config.py: added
DECIDED_BY_MESSAGE = "must be a lowercase name of up to 32 characters"
class Settings(BaseSettings):
    ...
    decided_by: str = "owner"      # after model_timeout; checked against ^[a-z][a-z0-9_]{0,31}$
```

The commands (every time is written `%Y-%m-%dT%H:%M:%SZ`; every arguments object as `json.dumps(args, ensure_ascii=False, sort_keys=True)`):

| Command | Prints (stdout) |
|---|---|
| `approvals list [--json]` | `No pending approvals.`, or one line per pending request, oldest first: `<approval_id>  <requested_at>  <stage>  <actions joined by ", ">`. With `--json`: `json.dumps([request.model_dump(mode="json"), ...], ensure_ascii=False, indent=2)` |
| `approvals show <id> [--json]` | the request block (below). With `--json`: `{"request": ..., "decision": ... or null}`, the same way |
| `approvals approve <id> [--note T] [--yes]` | unless `--yes`: the request block, then the prompt `Approve?`; then `Approved <id>.`, or `Nothing recorded.` when declined |
| `approvals reject <id> [--note T]` | `Rejected <id>.` (never asks) |
| `approvals edit <id> --args JSON [--note T] [--yes]` | unless `--yes`: the request block, `edited args: <args>`, then the prompt `Approve with these arguments?`; then `Approved <id> with edited arguments.`, or `Nothing recorded.` |
| `escalations list [--json]` | `No open escalations.`, or one line per open escalation, oldest first: `<escalation_id>  <raised_at>  <kind>  run <run_id>`. With `--json`: a list of `{"escalation_id", "raised_at", "escalation", "answer"}` |
| `escalations show <id> [--json]` | the escalation block (below); `--json` as one such object |
| `escalations retry <id> [--note T] [--yes]` | unless `--yes`: the escalation block, then the prompt `Retry?`; then `Retry recorded for <id>.`, or `Nothing recorded.` |
| `escalations cancel <id> [--note T]` | `Cancelled <id>.` (never asks) |

The request block, one line each:

```text
approval <approval_id>  <stage>  <status>
run <run_id>  requested <requested_at>
  <number>. <action>  <effect>  <args>              (one line per step)
edited args: <edited_args>                          (only for a recorded edit)
note: <note>                                        (only when a recorded decision has a note)
```

`<status>` is `pending`, or `<approved|rejected|edited> by <decided_by> (<channel>) at <decided_at>`.

The escalation block:

```text
escalation <escalation_id>  <kind>  <status>
run <run_id>  raised <raised_at>
<detail>
  <loc>: <code>                                     (one line per problem)
note: <note>                                        (only when an answer has a note)
```

`<status>` is `open`, or `<retry|cancel> by <decided_by> (<channel>) at <answered_at>`.

Prompts are `typer.confirm(<text>, default=False)`, so they read `Approve? [y/N]: `. Every error is one line on stderr, `Error: <message>`, and exit code 1: `SettingsError`, `StoreError`, `NotFound`, `AlreadyDecided`, `NotRegistered`, `ValueError` from `decisions` (the note), and `DecisionRefused`, whose problems follow as `  <loc>: <code>`, one per line. A declined prompt exits 0.

## Requirements

### Part 1: decisions (critical)

- **R1.** `decide_approval` checks `note` first (more than 500 characters gives `ValueError(NOTE_MESSAGE)`), then reads `store.approval(approval_id)` (`NotFound` passes through), then refuses a request that has a decision with `AlreadyDecided(f"approval {id} is already decided")`, all before the policy is asked.
- **R2.** It then builds `ApprovalDecision(approval_id, verdict, args_sha256=<the stored request's>, edited_args, note, channel, decided_by, decided_at=clock.now())`, calls `policy.apply_decision(request, decision, registry)` (a `DecisionRefused` or `NotRegistered` passes through and nothing is recorded), and only then `store.record_decision(decision)`; it returns the policy's outcome. An `AlreadyDecided` from the store (another channel was first) passes through.
- **R3.** `answer_escalation` checks the note the same way, reads `store.escalation(escalation_id)` and refuses an answered one with `AlreadyDecided(f"escalation {id} is already answered")` before building anything, then builds `EscalationAnswer(..., answered_at=clock.now())` and returns `store.answer(answer)`.
- **R4.** `decisions.py` imports only the standard library, `conductor.contracts.approvals`, `conductor.policy`, `conductor.registry`, `conductor.store`, and `clock` as a module; it never writes to the store before `apply_decision` has returned.

### Part 2: the commands

- **R5.** Every command reads settings through `get_settings()`, opens `Store(settings.db_path)`, and decides nothing itself: `approve`, `reject`, and `edit` call `decide_approval`; `retry` and `cancel` call `answer_escalation`; both with `channel="terminal"` and `decided_by=settings.decided_by`. The registry is `Registry(domains.DOMAINS)`, read through the module (`from conductor import domains`) when the command runs, so tests can replace it.
- **R6.** The output is exactly as under Design, text and `--json`.
- **R7.** `approve`, `edit`, and `retry` show their block and ask unless `--yes`; a declined prompt prints `Nothing recorded.`, records nothing, and exits 0. `reject` and `cancel` never ask.
- **R8.** `edit --args` must parse as a JSON object with `json.loads` and `parse_constant` refusing `NaN`, `Infinity`, and `-Infinity`; anything else gives `Error: --args must be a JSON object` before the store is opened.
- **R9.** Errors are reported as under Design: one `Error:` line (plus a refused edit's problem lines) on stderr, exit 1, no traceback, and no request, argument, or library text in the message.

### Part 3: the setting

- **R10.** `Settings.decided_by` (`CONDUCTOR_DECIDED_BY`) defaults to `owner`; a value that does not fully match `^[a-z][a-z0-9_]{0,31}$` adds the problem `CONDUCTOR_DECIDED_BY: must be a lowercase name of up to 32 characters` after the timeout's.

## Given tests

33 tests in three files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_decisions.py` (12 tests)

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.config import SettingsError, get_settings
from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import NOTE_MESSAGE, answer_escalation, decide_approval
from conductor.domains import demo
from conductor.policy import Approved, DecisionRefused, Rejected
from conductor.registry import Registry
from conductor.store import AlreadyDecided, NotFound, Store

AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
REGISTRY = Registry((demo.DOMAIN,))
NOTE = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
ID = "1" * 32


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setattr(clock, "now", lambda: AT)
    store = Store(tmp_path / "conductor.db")
    store.add_request(
        ApprovalRequest(
            approval_id=ID,
            run_id="a" * 32,
            stage="step",
            steps=(NOTE,),
            args_sha256=steps_digest((NOTE,)),
            requested_at=datetime(2026, 11, 8, 9, 0, tzinfo=UTC),
        )
    )
    return store


def decide(db: Store, verdict: str, **options: object):
    return decide_approval(
        db, REGISTRY, ID, verdict, channel="terminal", decided_by="owner", **options
    )


def test_an_approval_is_checked_then_recorded(db: Store) -> None:
    assert decide(db, "approve") == Approved(args=demo.NoteArgs(title="Milk"), edited=False)
    decision = db.approval(ID).decision
    assert decision is not None
    assert (decision.verdict, decision.channel, decision.decided_by, decision.decided_at) == (
        "approve",
        "terminal",
        "owner",
        AT,
    )
    assert decision.args_sha256 == steps_digest((NOTE,))
    assert db.pending() == []


def test_an_edit_and_a_rejection(db: Store, tmp_path: Path) -> None:
    outcome = decide(db, "edit", edited_args={"title": "Eggs"}, note="fewer")
    assert outcome == Approved(args=demo.NoteArgs(title="Eggs"), edited=True)
    stored = db.approval(ID).decision
    assert stored is not None and (stored.edited_args, stored.note) == ({"title": "Eggs"}, "fewer")
    other = Store(tmp_path / "other.db")
    other.add_request(db.approval(ID).request)
    assert decide(other, "reject", note="not now") == Rejected(note="not now")


def test_a_refused_edit_records_nothing(db: Store) -> None:
    with pytest.raises(DecisionRefused) as raised:
        decide(db, "edit", edited_args={"title": ""})
    assert raised.value.problems == (FieldProblem(loc="title", code="string_too_short"),)
    assert db.approval(ID).decision is None


def test_a_decided_request_is_refused_before_the_policy(db: Store) -> None:
    decide(db, "reject")
    with pytest.raises(AlreadyDecided) as raised:
        decide(db, "edit", edited_args={"title": ""})
    assert str(raised.value) == f"approval {ID} is already decided"


def test_an_unknown_request(db: Store) -> None:
    with pytest.raises(NotFound):
        decide_approval(db, REGISTRY, "9" * 32, "approve", channel="web", decided_by="owner")


def test_a_note_that_is_too_long(db: Store) -> None:
    with pytest.raises(ValueError) as raised:
        decide(db, "reject", note="x" * 501)
    assert str(raised.value) == NOTE_MESSAGE == "note must be at most 500 characters"
    assert db.approval(ID).decision is None


def test_an_escalation_is_answered_once(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id="a" * 32)
    )
    stored = answer_escalation(
        db, raised.escalation_id, "retry", note="back up", channel="web", decided_by="owner"
    )
    assert stored.answer is not None
    assert (stored.answer.answer, stored.answer.note, stored.answer.answered_at) == (
        "retry",
        "back up",
        AT,
    )
    with pytest.raises(AlreadyDecided):
        answer_escalation(db, raised.escalation_id, "cancel", channel="web", decided_by="owner")
    with pytest.raises(ValueError):
        answer_escalation(
            db, raised.escalation_id, "cancel", note="y" * 501, channel="web", decided_by="owner"
        )


def test_who_decides_is_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().decided_by == "owner"
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", "house_admin")
    assert get_settings().decided_by == "house_admin"


@pytest.mark.parametrize("label", ["", "Owner", "the owner", "x" * 33])
def test_a_bad_label_is_refused(monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", label)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == (
        "CONDUCTOR_DECIDED_BY: must be a lowercase name of up to 32 characters"
    )
```

`tests/e2e/test_cli_approvals.py` (16 tests)

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
        "approvals", "edit", FIRST, "--args", '{"title": "Eggs"}', "--note", "fewer", "--yes"
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
    result = runner.invoke(app, ["approvals", "approve", FIRST], input="y\n")
    assert result.exit_code == 0
    assert result.stdout == SHOWN + "Approve? [y/N]: y\n" + f"Approved {FIRST}.\n"
    assert db.approval(FIRST).decision.verdict == "approve"


def test_approve_can_be_declined(db: Store) -> None:
    note_request(db)
    result = runner.invoke(app, ["approvals", "approve", FIRST], input="n\n")
    assert result.exit_code == 0
    assert result.stdout.endswith("Approve? [y/N]: n\nNothing recorded.\n")
    assert db.approval(FIRST).decision is None


def test_approve_with_yes_and_reject_do_not_ask(db: Store) -> None:
    note_request(db)
    add(db, SECOND, "plan", (ECHO, NOTE), 8)
    approved = run("approvals", "approve", FIRST, "--yes")
    rejected = run("approvals", "reject", SECOND, "--note", "not today")
    assert (approved.stdout, rejected.stdout) == (f"Approved {FIRST}.\n", f"Rejected {SECOND}.\n")
    decision = db.approval(SECOND).decision
    assert (decision.verdict, decision.note) == ("reject", "not today")


def test_an_edit_shows_the_new_arguments_before_asking(db: Store) -> None:
    note_request(db)
    result = runner.invoke(
        app, ["approvals", "edit", FIRST, "--args", '{"title": "Eggs"}'], input="y\n"
    )
    assert result.stdout == (
        SHOWN
        + 'edited args: {"title": "Eggs"}\n'
        + "Approve with these arguments? [y/N]: y\n"
        + f"Approved {FIRST} with edited arguments.\n"
    )


def test_an_edit_that_does_not_fit(db: Store) -> None:
    note_request(db)
    result = run("approvals", "edit", FIRST, "--args", '{"title": "", "tags": ["Home"]}', "--yes")
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
    result = run("approvals", "edit", FIRST, "--args", given, "--yes")
    assert (result.exit_code, result.stderr) == (1, "Error: --args must be a JSON object\n")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("show", "9" * 32), f"Error: no approval {'9' * 32}\n"),
        (("approve", FIRST, "--yes"), f"Error: approval {FIRST} is already decided\n"),
        (("reject", FIRST, "--note", "x" * 501), "Error: note must be at most 500 characters\n"),
    ],
)
def test_errors(db: Store, args: tuple[str, ...], message: str) -> None:
    note_request(db)
    run("approvals", "reject", FIRST)
    result = run("approvals", *args)
    assert (result.exit_code, result.stderr) == (1, message)


def test_an_action_that_is_not_registered(db: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    note_request(db)
    monkeypatch.setattr(domains, "DOMAINS", ())
    result = run("approvals", "approve", FIRST, "--yes")
    assert (result.exit_code, result.stderr) == (1, "Error: no action demo.note\n")
    assert db.approval(FIRST).decision is None
```

`tests/e2e/test_cli_escalations.py` (5 tests)

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
    result = runner.invoke(app, ["escalations", "retry", SECOND, "--note", "back up"], input="y\n")
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
    result = run("escalations", "cancel", FIRST)
    assert (result.exit_code, result.stdout) == (0, f"Cancelled {FIRST}.\n")
    again = run("escalations", "retry", FIRST, "--yes")
    assert (again.exit_code, again.stderr) == (
        1,
        f"Error: escalation {FIRST} is already answered\n",
    )
```

## Tests to write

In `tests/unit/test_decisions_more.py` (unit, for `decisions.py`), each with its deciding input:

- R1: a note of exactly 500 characters is accepted, and the note is checked before the store is read (an unknown id with a 501-character note gives the note's `ValueError`).
- R2: a store whose `record_decision` raises `AlreadyDecided` (another channel was first; replace the method) passes it through.
- R2: a `NotRegistered` from the policy (an empty registry) records nothing.
- R3: an unknown escalation gives `NotFound`; an answered one is refused before `clock.now` is read (replace it with a function that fails).
- R4: `decide_approval` with an edit the policy refuses leaves `store.pending()` unchanged.

And in `tests/e2e/test_cli_approvals_more.py` (cli):

- R6: `escalations show --json` for an answered escalation includes the answer as its contract's JSON.
- R7: `escalations retry` declined prints `Nothing recorded.` and leaves it open.
- R8: `--args` of `{"title": Infinity}` is refused; `{}` is accepted as an object (and then judged by the policy).
- R9: `approvals approve` with `CONDUCTOR_DECIDED_BY=Owner` prints the settings error and records nothing.

`decisions.py` reaches 100% of lines and branches (critical).

## Rules for this phase

- **Critical module**: `decisions.py` joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **Side effects need approval** (`AGENTS.md` rule 7): nothing is recorded as approved unless `policy.apply_decision` returned `Approved`; a refused edit stays pending.
- **`cli` is thin** (`AGENTS.md`): parse, call `decisions` or the store, print. No verdict logic in `cli/main.py`.
- **Synthetic data only**: tests build their stores under `tmp_path`.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 33 = 411 passed; `critical coverage` passed (it now includes `decisions.py`);
- the given files: `.venv/bin/python -m pytest tests/unit/test_decisions.py tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py --no-cov`, exactly `33 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry, and `docs/progress.md` has an entry headed `## Phase 4c: the approvals and escalations commands (...)` (the checker does not yet require one before the review exists: check it yourself);
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/decisions.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|typing|conductor\.contracts\.approvals|conductor\.policy|conductor\.registry|conductor\.store|conductor import clock)( |$)"`
  - `git grep --untracked -n -E "apply_decision|record_decision|\.answer\(|ApprovalDecision\(|EscalationAnswer\(" -- src/conductor/cli`
  - `git grep --untracked -n -E "from conductor\.domains import DOMAINS" -- src/conductor/cli`
- `git diff --stat HEAD -- tests/unit tests/e2e/test_cli_doctor.py tests/e2e/test_cli_runs.py tests/support.py src/conductor/policy.py src/conductor/store.py src/conductor/contracts` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 4c: the approvals and escalations commands (YYYY-MM-DD)`, with `Tests: 378 -> <passed> (given 33)`.
