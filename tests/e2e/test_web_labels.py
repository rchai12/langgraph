from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.store import Store
from conductor.web.app import create_app

FIRST = "1" * 32


class Quiet:
    def start(self, run_id: str) -> None:
        pass

    def running(self, run_id: str) -> bool:
        return False

    def error(self, run_id: str) -> str | None:
        return None


@pytest.fixture
def page(tmp_path: Path) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=Quiet()), base_url="http://127.0.0.1:8766")


def add(tmp_path: Path, stage: str) -> Store:
    db = Store(tmp_path / "data" / "conductor.db")
    step = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id="a" * 32,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )
    return db


def buttons(text: str) -> list[str]:
    return [part.split("</button>")[0] for part in text.split('<button type="submit">')[1:]]


@pytest.mark.parametrize(
    ("stage", "labels"),
    [("step", ["Approve", "Reject", "Edit and approve"]), ("plan", ["Approve", "Reject"])],
)
def test_each_approval_form_says_what_it_does(
    tmp_path: Path, page: TestClient, stage: str, labels: list[str]
) -> None:
    add(tmp_path, stage)
    text = page.get(f"/approvals/{FIRST}").text
    assert buttons(text) == labels
    assert '<label for="note-approve">Note</label>' in text


def test_each_escalation_form_says_what_it_does(tmp_path: Path, page: TestClient) -> None:
    db = add(tmp_path, "step")
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id="a" * 32)
    )
    text = page.get(f"/escalations/{raised.escalation_id}").text
    assert buttons(text) == ["Retry", "Cancel"]
