from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor import clock
from conductor.config import get_settings
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.graph.status import RunStateUnavailable
from conductor.store import Store
from conductor.web import app as web_app
from conductor.web.app import create_app

BASE = "http://127.0.0.1:8766"
TOKEN = "ab" * 32
APPROVAL = "1" * 32
RUN = "a" * 32


class Recorder:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, _run_id: str) -> bool:
        return False

    def error(self, _run_id: str) -> str | None:
        return None


@pytest.fixture(autouse=True)
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 10, 0, tzinfo=UTC))


def client(resumer: Recorder) -> TestClient:
    found = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    found.cookies.set("conductor_form", TOKEN)
    return found


def add_approval(tmp_path: Path) -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
    Store(tmp_path / "data" / "conductor.db").add_request(
        ApprovalRequest(
            approval_id=APPROVAL,
            run_id=RUN,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )


def test_a_second_approve_is_a_conflict_and_starts_nothing(tmp_path: Path) -> None:
    add_approval(tmp_path)
    resumer = Recorder()
    page = client(resumer)
    first = page.post(
        f"/approvals/{APPROVAL}/approve", data={"token": TOKEN}, follow_redirects=False
    )
    second = page.post(
        f"/approvals/{APPROVAL}/approve", data={"token": TOKEN}, follow_redirects=False
    )
    assert (first.status_code, first.headers["location"]) == (303, f"/runs/{RUN}")
    assert second.status_code == 409
    assert resumer.started == [RUN]


def test_a_bad_edit_is_refused_before_the_store_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_path: object) -> None:
        raise AssertionError("the store was opened")

    monkeypatch.setattr(web_app, "Store", refuse)
    resumer = Recorder()
    found = client(resumer).post(
        f"/approvals/{APPROVAL}/edit", data={"token": TOKEN, "args": "{bad"}
    )
    assert found.status_code == 400
    assert "The arguments must be a JSON object." in found.text
    assert resumer.started == []


def test_an_unavailable_run_state_is_a_503_on_the_page_and_the_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_settings: object, _run_id: str) -> None:
        raise RunStateUnavailable("no state")

    monkeypatch.setattr(web_app.runtime, "read_state", unavailable)
    resumer = Recorder()
    page = client(resumer)
    shown = page.get(f"/runs/{RUN}")
    posted = page.post(f"/runs/{RUN}/resume", data={"token": TOKEN})
    for found in (shown, posted):
        assert (found.status_code, found.text) == (503, "The run state is not available")
    assert resumer.started == []
