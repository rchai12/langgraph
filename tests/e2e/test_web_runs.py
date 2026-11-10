from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conductor import runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.web.app import create_app
from conductor.web.jobs import Resumer

BASE = "http://127.0.0.1:8766"
NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'


class StillResuming:
    def __init__(self, *, busy: bool = False, error: str | None = None) -> None:
        self.busy = busy
        self.last = error

    def start(self, run_id: str) -> None:
        pass

    def running(self, run_id: str) -> bool:
        return self.busy

    def error(self, run_id: str) -> str | None:
        return self.last


@pytest.fixture(autouse=True)
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def waiting_run() -> runtime.RunState:
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE_PLAN))])
    with runtime.open_runtime(get_settings(), model=model) as opened:
        return runtime.ask(opened, "demo: note Milk")


def test_a_waiting_run_links_to_what_it_waits_for() -> None:
    state = waiting_run()
    page = TestClient(create_app(get_settings(), resumer=StillResuming()), base_url=BASE)
    text = page.get(f"/runs/{state.run_id}").text
    assert f'<a href="/approvals/{state.approval_id}">' in text
    assert "waiting" in text
    assert "refresh" not in text


def test_a_busy_run_refreshes_itself() -> None:
    state = waiting_run()
    page = TestClient(create_app(get_settings(), resumer=StillResuming(busy=True)), base_url=BASE)
    text = page.get(f"/runs/{state.run_id}").text
    assert '<meta http-equiv="refresh" content="5">' in text
    assert "busy" in text


def test_the_last_resume_error_is_shown() -> None:
    state = waiting_run()
    resumer = StillResuming(error=f"run {state.run_id} is busy")
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    assert (
        f"The last resume failed: run {state.run_id} is busy"
        in page.get(f"/runs/{state.run_id}").text
    )


@pytest.mark.parametrize("run_id", ["9" * 32, "nope"])
def test_a_run_that_is_not_there(run_id: str) -> None:
    page = TestClient(create_app(get_settings(), resumer=StillResuming()), base_url=BASE)
    response = page.get(f"/runs/{run_id}")
    assert (response.status_code, response.text) == (404, "Not found")


def test_a_decision_resumes_the_run_in_the_background(tmp_path: Path) -> None:
    state = waiting_run()
    resumer = Resumer(get_settings())
    page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
    form_page = page.get(f"/approvals/{state.approval_id}").text
    sent = form_page.split('name="token" value="')[1].split('"')[0]
    response = page.post(
        f"/approvals/{state.approval_id}/approve",
        data={"token": sent},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    assert response.status_code == 303
    resumer.join(state.run_id, timeout=30)
    assert (resumer.running(state.run_id), resumer.error(state.run_id)) == (False, None)
    with runtime.open_runtime(get_settings()) as opened:
        after = runtime.state(opened, state.run_id)
        request = opened.store.approval(after.approval_id).request
    assert (after.status, request.stage) == ("waiting", "step")
    text = page.get(f"/runs/{state.run_id}").text
    assert f'<a href="/approvals/{after.approval_id}">' in text


def test_a_resume_that_fails_is_recorded_not_raised() -> None:
    resumer = Resumer(get_settings())
    resumer.start("9" * 32)
    resumer.join("9" * 32, timeout=30)
    assert resumer.error("9" * 32) == f"no run {'9' * 32}"
