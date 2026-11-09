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
    answered = run("escalations", "retry", raised.escalation_id, "--note", "back up", "--yes")
    assert answered.exit_code == 0
    shown = json.loads(run("escalations", "show", raised.escalation_id, "--json").stdout)
    stored = db.escalation(raised.escalation_id).answer
    assert stored is not None
    assert shown["answer"] == stored.model_dump(mode="json")


def test_a_declined_retry_records_nothing(db: Store) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    result = runner.invoke(app, ["escalations", "retry", raised.escalation_id], input="n\n")
    assert result.exit_code == 0
    assert result.stdout.endswith("Retry? [y/N]: n\nNothing recorded.\n")
    assert [item.escalation_id for item in db.open_escalations()] == [raised.escalation_id]


def test_a_declined_edit_records_nothing(db: Store) -> None:
    result = runner.invoke(
        app, ["approvals", "edit", FIRST, "--args", '{"title": "Eggs"}'], input="n\n"
    )
    assert result.exit_code == 0
    assert result.stdout.endswith(
        'edited args: {"title": "Eggs"}\n'
        "Approve with these arguments? [y/N]: n\n"
        "Nothing recorded.\n"
    )
    assert db.approval(FIRST).decision is None


def test_infinity_is_refused_and_an_empty_object_is_judged(db: Store) -> None:
    refused = run("approvals", "edit", FIRST, "--args", '{"title": Infinity}', "--yes")
    assert (refused.exit_code, refused.stderr) == (1, "Error: --args must be a JSON object\n")
    assert db.approval(FIRST).decision is None
    judged = run("approvals", "edit", FIRST, "--args", "{}", "--yes")
    assert judged.exit_code == 1
    assert judged.stderr.startswith("Error: decision refused:")
    assert "--args must be a JSON object" not in judged.stderr
    assert db.approval(FIRST).decision is None


def test_a_bad_decided_by_prints_the_settings_error(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DECIDED_BY", "Owner")
    result = run("approvals", "approve", FIRST, "--yes")
    assert result.exit_code == 1
    assert result.stderr == (
        "Error: CONDUCTOR_DECIDED_BY: must be a lowercase name of up to 32 characters\n"
    )
    assert db.approval(FIRST).decision is None


def test_an_approval_without_a_note_shows_who_approved(db: Store) -> None:
    assert run("approvals", "approve", FIRST, "--yes").exit_code == 0
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
    assert run("escalations", "cancel", raised.escalation_id).exit_code == 0
    assert run("escalations", "show", raised.escalation_id).stdout == (
        f"escalation {raised.escalation_id}  model_unavailable  "
        "cancel by owner (terminal) at 2026-11-08T10:00:00Z\n"
        f"run {RUN}  raised 2026-11-08T10:00:00Z\n"
        "model unavailable: timeout\n"
    )
