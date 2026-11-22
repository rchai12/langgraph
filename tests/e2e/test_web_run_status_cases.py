import itertools
import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.web import app as web_app
from conductor.web.app import create_app

BASE = "http://127.0.0.1:8766"
NOTE = '{"steps":[{"action":"note","args":{"title":"Milk"}}]}'
ECHO = '{"steps":[{"action":"echo","args":{"text":"hi"}}]}'
REPLY = '{"reply":"1 < 2 & 3"}'


class Still:
    def __init__(self, *, busy: bool = False, error: str | None = None) -> None:
        self.busy = busy
        self.last = error
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)

    def running(self, _run_id: str) -> bool:
        return self.busy

    def error(self, _run_id: str) -> str | None:
        return self.last


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def page_for(resumer: Still | None = None) -> TestClient:
    return TestClient(create_app(get_settings(), resumer=resumer or Still()), base_url=BASE)


def test_a_stored_malformed_run_is_a_generic_503() -> None:
    settings = get_settings()
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE))])
    with runtime.open_runtime(settings, model=model) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
    connection = sqlite3.connect(settings.checkpoints_path)
    connection.execute("UPDATE checkpoints SET checkpoint = ?", (b"SYNTHETIC-SECRET",))
    connection.commit()
    connection.close()
    response = page_for().get(f"/runs/{waiting.run_id}")
    assert (response.status_code, response.text) == (503, "The run state is not available")
    assert "SYNTHETIC-SECRET" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"

    settings.checkpoints_path.write_bytes(b"not a sqlite database")
    failed = page_for().get(f"/runs/{waiting.run_id}")
    assert (failed.status_code, failed.text) == (503, "The run state is not available")
    assert failed.headers["x-content-type-options"] == "nosniff"


def test_a_done_page_escapes_and_a_get_does_not_decide(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    model = ScriptedModel(
        [
            ScriptedReply("plan", ModelReply(content=ECHO)),
            ScriptedReply("answer", ModelReply(content=REPLY)),
        ]
    )
    with runtime.open_runtime(settings, model=model) as opened:
        done = runtime.ask(opened, "demo: say hi")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GET resumed or recorded a decision")

    monkeypatch.setattr(runtime, "resume", forbidden)
    monkeypatch.setattr(web_app, "decide_approval", forbidden)
    monkeypatch.setattr(web_app, "answer_escalation", forbidden)
    resumer = Still(error="a < b")
    response = page_for(resumer).get(f"/runs/{done.run_id}")
    assert response.status_code == 200
    assert "done" in response.text
    assert "1 &lt; 2 &amp; 3" in response.text
    assert "1 < 2 & 3" not in response.text
    assert "a &lt; b" in response.text
    assert resumer.started == []
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "same-origin"


def test_busy_refresh_last_error_and_a_stopped_node() -> None:
    settings = get_settings()
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=NOTE))])
    with runtime.open_runtime(settings, model=model) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")
    busy = page_for(Still(busy=True, error=f"run {waiting.run_id} is busy"))
    text = busy.get(f"/runs/{waiting.run_id}").text
    assert '<meta http-equiv="refresh" content="5">' in text
    assert "busy" in text
    assert f"The last resume failed: run {waiting.run_id} is busy" in text

    model = ScriptedModel([])
    with runtime.open_runtime(settings, model=model) as opened:
        before = {item.run_id for item in opened.log.runs()}
        with pytest.raises(ScriptError):
            runtime.ask(opened, "demo: say hi")
        [run] = [item for item in opened.log.runs() if item.run_id not in before]
    stopped = page_for().get(f"/runs/{run.run_id}").text
    assert "stopped" in stopped
    assert "plan" in stopped
