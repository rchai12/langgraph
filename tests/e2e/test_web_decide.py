import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from conductor import clock
from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.store import Store
from conductor.web.app import FORM_COOKIE, create_app

FIRST = "1" * 32
RUN = "a" * 32
BASE = "http://127.0.0.1:8766"


class FakeResumer:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, run_id: str) -> bool:
        return False

    def error(self, run_id: str) -> str | None:
        return None


@pytest.fixture(autouse=True)
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 10, 0, tzinfo=UTC))


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


@pytest.fixture
def resumer() -> FakeResumer:
    return FakeResumer()


@pytest.fixture
def page(resumer: FakeResumer) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)


def add(db: Store, stage: str = "step", args: dict | None = None) -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args=args or {"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id=RUN,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )


def token(page: TestClient, path: str) -> str:
    """Open the page the form is on, as a browser would, and read its form token."""
    response = page.get(path)
    found = re.search(r'name="token" value="([0-9a-f]{64})"', response.text)
    assert found is not None
    assert page.cookies[FORM_COOKIE] == found.group(1)
    return found.group(1)


def post(page: TestClient, path: str, form: dict, origin: str | None = BASE):
    headers = {} if origin is None else {"origin": origin}
    return page.post(path, data=form, headers=headers, follow_redirects=False)


def test_a_pending_step_has_its_forms(db: Store, page: TestClient) -> None:
    add(db, args={"title": "<b>Milk</b>"})
    response = page.get(f"/approvals/{FIRST}")
    text = response.text
    for action in ("approve", "reject", "edit"):
        assert f'<form method="post" action="/approvals/{FIRST}/{action}">' in text
    assert str(escape(json.dumps({"title": "<b>Milk</b>"}, sort_keys=True))) in text
    cookie = response.headers["set-cookie"]
    assert f"{FORM_COOKIE}=" in cookie
    for flag in ("HttpOnly", "Path=/", "SameSite=strict"):
        assert flag in cookie


def test_a_plan_cannot_be_edited_and_a_decided_request_has_no_forms(
    db: Store, page: TestClient
) -> None:
    add(db, stage="plan")
    text = page.get(f"/approvals/{FIRST}").text
    assert f'action="/approvals/{FIRST}/approve"' in text
    assert f'action="/approvals/{FIRST}/edit"' not in text
    post(page, f"/approvals/{FIRST}/reject", {"token": token(page, f"/approvals/{FIRST}")})
    assert "<form" not in page.get(f"/approvals/{FIRST}").text


def test_approve_records_from_the_web_and_resumes(
    db: Store, page: TestClient, resumer: FakeResumer
) -> None:
    add(db)
    response = post(
        page, f"/approvals/{FIRST}/approve", {"token": token(page, f"/approvals/{FIRST}")}
    )
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{RUN}")
    decision = db.approval(FIRST).decision
    assert (decision.verdict, decision.channel, decision.decided_by) == ("approve", "web", "owner")
    assert resumer.started == [RUN]


def test_an_edit_carries_its_note_and_arguments(db: Store, page: TestClient) -> None:
    add(db)
    form = {
        "token": token(page, f"/approvals/{FIRST}"),
        "args": '{"title": "Eggs"}',
        "note": "fewer",
    }
    assert post(page, f"/approvals/{FIRST}/edit", form).status_code == 303
    decision = db.approval(FIRST).decision
    assert (decision.verdict, decision.edited_args, decision.note) == (
        "edit",
        {"title": "Eggs"},
        "fewer",
    )


@pytest.mark.parametrize("args", ["[1]", "not json", '{"title": NaN}'])
def test_edited_arguments_must_be_a_json_object(
    db: Store, page: TestClient, resumer: FakeResumer, args: str
) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "args": args}
    response = post(page, f"/approvals/{FIRST}/edit", form)
    assert response.status_code == 400
    assert "The arguments must be a JSON object." in response.text
    assert (db.approval(FIRST).decision, resumer.started) == (None, [])


def test_an_edit_the_action_refuses_lists_its_problems(db: Store, page: TestClient) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "args": '{"title": ""}'}
    response = post(page, f"/approvals/{FIRST}/edit", form)
    assert response.status_code == 400
    assert "decision refused: invalid_edit" in response.text
    assert "title: string_too_short" in response.text
    assert db.approval(FIRST).decision is None


@pytest.mark.parametrize("sent", [None, "0" * 64, "short"])
def test_a_form_without_its_token_is_refused(
    db: Store, page: TestClient, resumer: FakeResumer, sent: str | None
) -> None:
    add(db)
    token(page, f"/approvals/{FIRST}")
    form = {} if sent is None else {"token": sent}
    response = post(page, f"/approvals/{FIRST}/approve", form)
    assert (response.status_code, response.text) == (403, "Bad form token")
    assert response.headers["x-frame-options"] == "DENY"
    assert (db.approval(FIRST).decision, resumer.started) == (None, [])


def test_a_token_without_its_cookie_is_refused(db: Store, page: TestClient) -> None:
    add(db)
    sent = token(page, f"/approvals/{FIRST}")
    page.cookies.clear()
    response = post(page, f"/approvals/{FIRST}/approve", {"token": sent})
    assert (response.status_code, response.text) == (403, "Bad form token")


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        ("http://evil.example", 403),
        ("http://127.0.0.1:8765", 403),
        ("http://localhost:8766", 303),
        (None, 303),
    ],
)
def test_the_origin_of_a_form(db: Store, page: TestClient, origin: str | None, status: int) -> None:
    add(db)
    response = post(
        page, f"/approvals/{FIRST}/approve", {"token": token(page, f"/approvals/{FIRST}")}, origin
    )
    assert response.status_code == status
    if status == 403:
        assert response.text == "Bad origin"
        assert db.approval(FIRST).decision is None


def test_a_second_decision_is_refused(db: Store, page: TestClient, resumer: FakeResumer) -> None:
    add(db)
    sent = token(page, f"/approvals/{FIRST}")
    post(page, f"/approvals/{FIRST}/approve", {"token": sent})
    again = post(page, f"/approvals/{FIRST}/reject", {"token": sent})
    assert again.status_code == 409
    assert f"approval {FIRST} is already decided" in again.text
    assert db.approval(FIRST).decision.verdict == "approve"
    assert resumer.started == [RUN]


def test_a_note_too_long_is_refused(db: Store, page: TestClient) -> None:
    add(db)
    form = {"token": token(page, f"/approvals/{FIRST}"), "note": "x" * 501}
    response = post(page, f"/approvals/{FIRST}/reject", form)
    assert response.status_code == 400
    assert "note must be at most 500 characters" in response.text


@pytest.mark.parametrize("answer", ["retry", "cancel"])
def test_an_escalation_is_answered_from_the_web(
    db: Store, page: TestClient, resumer: FakeResumer, answer: str
) -> None:
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    path = f"/escalations/{raised.escalation_id}"
    assert f'<form method="post" action="{path}/{answer}">' in page.get(path).text
    response = post(page, f"{path}/{answer}", {"token": token(page, path), "note": "ok"})
    assert (response.status_code, response.headers["location"]) == (303, f"/runs/{RUN}")
    stored = db.escalation(raised.escalation_id).answer
    assert (stored.answer, stored.channel, stored.note) == (answer, "web", "ok")
    assert resumer.started == [RUN]


@pytest.mark.parametrize(
    "path",
    [f"/approvals/{'9' * 32}/approve", "/approvals/nope/approve", f"/escalations/{'9' * 32}/retry"],
)
def test_deciding_what_is_not_there(db: Store, page: TestClient, path: str) -> None:
    add(db)
    response = post(page, path, {"token": token(page, f"/approvals/{FIRST}")})
    assert (response.status_code, response.text) == (404, "Not found")
