from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor import runtime
from conductor.config import get_settings
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.decisions import parse_json_object
from conductor.graph.supervisor import RunState
from conductor.store import Store
from conductor.web.app import FORM_COOKIE, create_app

FIRST = "1" * 32
RUN = "a" * 32
BASE = "http://127.0.0.1:8766"
COOKIE = "ab" * 32


class FakeResumer:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, run_id: str) -> bool:
        return False

    def error(self, run_id: str) -> str | None:
        return None


@pytest.fixture
def db(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "conductor.db")


def _add(db: Store) -> None:
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


def _page(resumer: FakeResumer | None = None) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=resumer or FakeResumer()), base_url=BASE)


def test_parse_json_object_keeps_only_objects() -> None:
    assert parse_json_object("{}") == {}
    assert parse_json_object("[]") is None
    assert parse_json_object('"x"') is None
    assert parse_json_object('{"a": Infinity}') is None
    assert parse_json_object('{"a": -Infinity}') is None


def test_a_valid_cookie_is_kept_and_the_forms_carry_it(db: Store) -> None:
    _add(db)
    page = _page()
    page.cookies.set(FORM_COOKIE, COOKIE)
    response = page.get(f"/approvals/{FIRST}")
    assert "set-cookie" not in response.headers
    assert f'name="token" value="{COOKIE}"' in response.text


def test_a_bad_token_does_not_open_the_store(db: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _add(db)
    page = _page()
    page.get(f"/approvals/{FIRST}")

    class _Closed:
        def __init__(self, path: object) -> None:
            raise AssertionError("the store was opened")

    monkeypatch.setattr("conductor.web.app.Store", _Closed)
    response = page.post(
        f"/approvals/{FIRST}/approve",
        data={"token": "0" * 64},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert (response.status_code, response.text) == (403, "Bad form token")
    escalation = page.post(
        f"/escalations/{'9' * 32}/retry",
        data={"token": "0" * 64},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert (escalation.status_code, escalation.text) == (403, "Bad form token")


def test_an_unknown_action_is_refused_and_a_broken_store_is_unavailable(
    db: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add(db)
    page = _page()
    sent = page.get(f"/approvals/{FIRST}").text.split('name="token" value="')[1].split('"')[0]
    refused = page.post(
        f"/approvals/{FIRST}/approve",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert "no action demo.note" in refused.text
    assert db.approval(FIRST).decision is None
    (tmp_path / "data" / "conductor.db").write_text("not a database")
    failed = page.post(
        f"/approvals/{FIRST}/approve",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert (failed.status_code, failed.text) == (503, "The store is not available")


def test_a_second_decision_links_back_to_the_request(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    _add(db)
    resumer = FakeResumer()
    page = _page(resumer)
    sent = page.get(f"/approvals/{FIRST}").text.split('name="token" value="')[1].split('"')[0]
    assert (
        page.post(
            f"/approvals/{FIRST}/approve",
            data={"token": sent},
            headers={"origin": BASE},
            follow_redirects=False,
        ).status_code
        == 303
    )
    again = page.post(
        f"/approvals/{FIRST}/reject",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert again.status_code == 409
    assert f'href="/approvals/{FIRST}"' in again.text
    assert resumer.started == [RUN]


def test_a_refused_edit_and_a_conflict_start_no_extra_resume(
    db: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    _add(db)
    resumer = FakeResumer()
    page = _page(resumer)
    sent = page.get(f"/approvals/{FIRST}").text.split('name="token" value="')[1].split('"')[0]
    bad = page.post(
        f"/approvals/{FIRST}/edit",
        data={"token": sent, "args": "[1]"},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert bad.status_code == 400
    assert resumer.started == []
    page.post(
        f"/approvals/{FIRST}/approve",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    again = page.post(
        f"/approvals/{FIRST}/reject",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert again.status_code == 409
    assert resumer.started == [RUN]


def test_finished_runs_show_their_line(monkeypatch: pytest.MonkeyPatch) -> None:
    states = {
        "1" * 32: RunState(run_id="1" * 32, status="done", reply="<script>alert(1)</script>"),
        "2" * 32: RunState(run_id="2" * 32, status="rejected", note="not today"),
        "3" * 32: RunState(run_id="3" * 32, status="cancelled"),
        "4" * 32: RunState(run_id="4" * 32, status="stopped", stopped_at="answer"),
        "5" * 32: RunState(run_id="5" * 32, status="waiting", escalation_id="e" * 32),
    }

    @contextmanager
    def open_runtime(settings: object, *, model: object = None) -> object:
        yield None

    monkeypatch.setattr(runtime, "open_runtime", open_runtime)
    monkeypatch.setattr(runtime, "state", lambda opened, run_id: states[run_id])
    page = _page()
    done = page.get(f"/runs/{'1' * 32}").text
    assert "done" in done
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in done
    assert "<script>" not in done
    assert "refresh" not in done
    rejected = page.get(f"/runs/{'2' * 32}").text
    assert "rejected" in rejected and "not today" in rejected
    assert "cancelled" in page.get(f"/runs/{'3' * 32}").text
    stopped = page.get(f"/runs/{'4' * 32}").text
    assert "stopped" in stopped and "answer" in stopped
    waiting = page.get(f"/runs/{'5' * 32}").text
    assert f'<a href="/escalations/{"e" * 32}">' in waiting
    assert "refresh" not in waiting
