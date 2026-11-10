import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from conductor import clock
from conductor.config import get_settings
from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import answer_escalation, decide_approval
from conductor.domains import demo
from conductor.registry import Registry
from conductor.store import Store
from conductor.web.app import SECURITY_HEADERS, create_app

FIRST = "1" * 32
SECOND = "2" * 32
RUN = "a" * 32
BASE = "http://127.0.0.1:8766"


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 10, 0, tzinfo=UTC))


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


@pytest.fixture
def page() -> TestClient:
    return TestClient(create_app(get_settings()), base_url=BASE)


def add(db: Store, approval_id: str, args: dict, hour: int, stage: str = "step") -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args=args)
    db.add_request(
        ApprovalRequest(
            approval_id=approval_id,
            run_id=RUN,
            stage=stage,
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, hour, 0, tzinfo=UTC),
        )
    )


def shown(args: dict) -> str:
    return str(escape(json.dumps(args, ensure_ascii=False, sort_keys=True)))


def test_an_empty_home_page(db: Store, page: TestClient) -> None:
    response = page.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "No pending approvals." in response.text
    assert "No open escalations." in response.text
    assert "<script" not in response.text


def test_the_home_page_lists_what_waits_oldest_first(db: Store, page: TestClient) -> None:
    add(db, SECOND, {"title": "Bread"}, 9)
    add(db, FIRST, {"title": "Milk"}, 10, stage="plan")
    raised = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    text = page.get("/").text
    assert text.index(f'<a href="/approvals/{SECOND}">{SECOND}</a>') < text.index(
        f'<a href="/approvals/{FIRST}">{FIRST}</a>'
    )
    assert "2026-11-09T09:00:00Z" in text and "demo.note" in text
    assert f'<a href="/escalations/{raised.escalation_id}">{raised.escalation_id}</a>' in text
    assert "model_unavailable" in text
    assert "No pending approvals." not in text


def test_a_pending_approval(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "Milk", "tags": ["home"]}, 9)
    text = page.get(f"/approvals/{FIRST}").text
    for part in (
        FIRST,
        "step",
        "pending",
        f"run {RUN}",
        "requested 2026-11-09T09:00:00Z",
        "1. demo.note",
        "write",
        shown({"title": "Milk", "tags": ["home"]}),
    ):
        assert part in text


def test_a_decided_approval_shows_who_decided_and_the_edit(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "Milk"}, 9)
    decide_approval(
        db,
        Registry((demo.DOMAIN,)),
        FIRST,
        "edit",
        channel="terminal",
        decided_by="owner",
        note="fewer",
        edited_args={"title": "Eggs"},
    )
    text = page.get(f"/approvals/{FIRST}").text
    assert "edited by owner (terminal) at 2026-11-09T10:00:00Z" in text
    assert f"edited args: {shown({'title': 'Eggs'})}" in text
    assert "note: fewer" in text


def test_an_escalation_and_its_answer(db: Store, page: TestClient) -> None:
    raised = db.add_escalation(
        Escalation(
            kind="invalid_plan",
            detail="decision 3: the plan does not fit the registry",
            run_id=RUN,
            problems=(FieldProblem(loc="steps.0.args.title", code="string_too_short"),),
        )
    )
    path = f"/escalations/{raised.escalation_id}"
    before = page.get(path).text
    for part in ("invalid_plan", "open", f"run {RUN}", "the plan does not fit the registry"):
        assert part in before
    assert "steps.0.args.title: string_too_short" in before
    answer_escalation(
        db, raised.escalation_id, "cancel", channel="terminal", decided_by="owner", note="later"
    )
    after = page.get(path).text
    assert "cancel by owner (terminal) at 2026-11-09T10:00:00Z" in after
    assert "note: later" in after


@pytest.mark.parametrize(
    "path", [f"/approvals/{'9' * 32}", f"/escalations/{'9' * 32}", "/approvals/not-an-id"]
)
def test_what_is_not_there(db: Store, page: TestClient, path: str) -> None:
    response = page.get(path)
    assert (response.status_code, response.text) == (404, "Not found")


def test_text_from_a_request_is_escaped(db: Store, page: TestClient) -> None:
    add(db, FIRST, {"title": "<script>alert(1)</script>"}, 9)
    text = page.get(f"/approvals/{FIRST}").text
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:8765", "localhost"])
def test_only_this_server_by_name_is_answered(db: Store, host: str) -> None:
    client = TestClient(create_app(get_settings()), base_url=f"http://{host}")
    response = client.get("/")
    assert (response.status_code, response.text) == (400, "Bad host")
    assert response.headers["x-frame-options"] == "DENY"


def test_localhost_by_port_is_answered(db: Store) -> None:
    client = TestClient(create_app(get_settings()), base_url="http://localhost:8766")
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("path", ["/", f"/approvals/{'9' * 32}"])
def test_every_answer_carries_the_security_headers(db: Store, page: TestClient, path: str) -> None:
    response = page.get(path)
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "server" not in response.headers


def test_the_headers(db: Store) -> None:
    assert SECURITY_HEADERS == {
        "content-security-policy": (
            "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        ),
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "cache-control": "no-store",
    }


@pytest.mark.parametrize(
    ("method", "path"), [("post", "/"), ("get", "/docs"), ("get", "/openapi.json")]
)
def test_nothing_else_is_served(db: Store, page: TestClient, method: str, path: str) -> None:
    assert getattr(page, method)(path).status_code in (404, 405)


def test_a_store_that_cannot_be_read(tmp_path: Path, page: TestClient) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "conductor.db").write_text("not a database")
    response = page.get("/")
    assert (response.status_code, response.text) == (503, "The store is not available")
