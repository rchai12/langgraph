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
