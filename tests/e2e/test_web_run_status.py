import itertools
from datetime import UTC, datetime
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.web.app import create_app

BASE = "http://127.0.0.1:8766"


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def test_run_page_does_not_open_an_execution_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    model = ScriptedModel(
        [
            ScriptedReply(
                "plan", ModelReply(content='{"steps":[{"action":"note","args":{"title":"Milk"}}]}')
            )
        ]
    )
    with runtime.open_runtime(settings, model=model) as opened:
        waiting = runtime.ask(opened, "demo: note Milk")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("GET opened an execution runtime")

    monkeypatch.setattr(runtime, "open_runtime", forbidden)
    page = TestClient(create_app(settings), base_url=BASE)
    for _ in range(4):
        response = page.get(f"/runs/{waiting.run_id}")
        assert response.status_code == 200
        assert f"/approvals/{waiting.approval_id}" in response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("run_id", ["f" * 32, "nope"])
def test_missing_run_page_creates_no_storage(run_id: str) -> None:
    settings = get_settings()
    response = TestClient(create_app(settings), base_url=BASE).get(f"/runs/{run_id}")
    assert (response.status_code, response.text) == (404, "Not found")
    assert not settings.data_dir.exists()


def test_malformed_saved_state_is_a_generic_503(monkeypatch: pytest.MonkeyPatch) -> None:
    error_type = import_module("conductor.graph.status").RunStateUnavailable

    def unreadable(*args: object, **kwargs: object) -> None:
        raise error_type("SYNTHETIC-SECRET")

    monkeypatch.setattr(runtime, "read_state", unreadable)
    response = TestClient(create_app(get_settings()), base_url=BASE).get(f"/runs/{'f' * 32}")
    assert (response.status_code, response.text) == (503, "The run state is not available")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "SYNTHETIC-SECRET" not in response.text
