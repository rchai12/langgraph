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
