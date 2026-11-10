import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor import clock
from conductor.config import get_settings
from conductor.contracts import Escalation
from conductor.contracts.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    PlannedStep,
    steps_digest,
)
from conductor.store import Store
from conductor.web.app import SECURITY_HEADERS, create_app

FIRST = "1" * 32
RUN = "a" * 32
MARKUP = "<img src=x onerror=1>"
ESCAPED = "&lt;img src=x onerror=1&gt;"
BASE = "http://127.0.0.1:8766"


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


@pytest.fixture
def page() -> TestClient:
    return TestClient(create_app(get_settings()), base_url=BASE)


def _request(app: object, headers: list[tuple[bytes, bytes]]) -> tuple[int, bytes]:
    status: list[int] = []
    body = bytearray()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        kind = message["type"]
        if kind == "http.response.start":
            status.append(int(message["status"]))  # type: ignore[arg-type]
        elif kind == "http.response.body":
            body.extend(message.get("body", b""))  # type: ignore[arg-type]

    async def once() -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8766),
        }
        await app(scope, receive, send)  # type: ignore[operator]

    asyncio.run(once())
    return status[0], bytes(body)


def _plan(db: Store) -> None:
    steps = (
        PlannedStep(number=1, action="demo.echo", effect="read", args={"text": "hi"}),
        PlannedStep(number=2, action="demo.note", effect="write", args={"title": "Milk"}),
    )
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id=RUN,
            stage="plan",
            steps=steps,
            args_sha256=steps_digest(steps),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )


def test_two_host_headers_are_refused_and_localhost_is_answered(db: Store) -> None:
    app = create_app(get_settings())
    status, body = _request(app, [(b"host", b"127.0.0.1:8766"), (b"host", b"localhost:8766")])
    assert (status, body) == (400, b"Bad host")
    client = TestClient(app, base_url="http://localhost:8766")
    assert client.get("/").status_code == 200


def test_a_lifespan_message_reaches_the_app() -> None:
    app = create_app(get_settings())
    seen: list[str] = []

    async def receive() -> dict[str, str]:
        return {"type": "lifespan.startup" if not seen else "lifespan.shutdown"}

    async def send(message: dict[str, object]) -> None:
        seen.append(str(message["type"]))

    async def once() -> None:
        scope = {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}
        await app(scope, receive, send)  # type: ignore[operator]

    asyncio.run(once())
    assert seen == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_post_and_a_broken_store_carry_every_header(
    db: Store, page: TestClient, tmp_path: Path
) -> None:
    posted = page.post("/")
    assert posted.status_code == 405
    for name, value in SECURITY_HEADERS.items():
        assert posted.headers[name] == value
    (tmp_path / "data" / "conductor.db").write_text("not a database")
    failed = page.get("/")
    assert failed.status_code == 503
    for name, value in SECURITY_HEADERS.items():
        assert failed.headers[name] == value


def test_a_plan_shows_both_steps_and_escalations_are_oldest_first(
    db: Store, page: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plan(db)
    text = page.get(f"/approvals/{FIRST}").text
    assert text.index("1. demo.echo") < text.index("2. demo.note")
    current = {"at": datetime(2026, 11, 9, 8, 0, tzinfo=UTC)}
    monkeypatch.setattr(clock, "now", lambda: current["at"])
    current["at"] = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    older = db.add_escalation(Escalation(kind="tool_error", detail="the tool failed", run_id=RUN))
    current["at"] = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)
    newer = db.add_escalation(
        Escalation(kind="model_unavailable", detail="model unavailable: timeout", run_id=RUN)
    )
    home = page.get("/").text
    assert home.index(older.escalation_id) < home.index(newer.escalation_id)
    assert "2026-11-09T08:00:00Z" in home and "2026-11-09T11:00:00Z" in home
    assert "No open escalations." not in home


def _unsafe(text: str) -> bool:
    return (
        "<script" in text.lower()
        or "http://" in text
        or "https://" in text
        or re.search(r"<[^>]*\son[a-z]+=", text) is not None
    )


def test_a_note_a_detail_and_an_action_are_escaped(
    db: Store, page: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    step = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=FIRST,
            run_id=RUN,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )
    db.record_decision(
        ApprovalDecision(
            approval_id=FIRST,
            verdict="reject",
            args_sha256=steps_digest((step,)),
            note=MARKUP,
            channel="terminal",
            decided_by="owner",
            decided_at=datetime(2026, 11, 9, 10, 0, tzinfo=UTC),
        )
    )
    raised = db.add_escalation(Escalation(kind="tool_error", detail=MARKUP, run_id=RUN))
    note_page = page.get(f"/approvals/{FIRST}").text
    detail_page = page.get(f"/escalations/{raised.escalation_id}").text
    assert f"note: {ESCAPED}" in note_page
    assert ESCAPED in detail_page
    assert MARKUP not in note_page and MARKUP not in detail_page
    assert not _unsafe(note_page) and not _unsafe(detail_page)

    class _Step:
        action = MARKUP

    class _Row:
        approval_id = "b" * 32
        requested_at = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
        stage = "step"
        steps = (_Step(),)

    class _FakeStore:
        def __init__(self, path: object) -> None:
            pass

        def pending(self) -> list[_Row]:
            return [_Row()]

        def open_escalations(self) -> list[object]:
            return []

    monkeypatch.setattr("conductor.web.app.Store", _FakeStore)
    home = page.get("/").text
    assert ESCAPED in home
    assert MARKUP not in home
    assert not _unsafe(home)


@pytest.mark.parametrize("path", [f"/approvals/{'A' * 32}", f"/escalations/{'A' * 32}"])
def test_a_capital_id_is_not_found_without_opening_the_store(
    page: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    class _Closed:
        def __init__(self, path: object) -> None:
            raise AssertionError("the store was opened")

    monkeypatch.setattr("conductor.web.app.Store", _Closed)
    response = page.get(path)
    assert (response.status_code, response.text) == (404, "Not found")
