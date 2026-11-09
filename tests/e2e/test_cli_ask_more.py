import itertools
import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from conductor import clock, ids, runtime
from conductor.cli.main import app
from conductor.config import get_settings
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.store import Store
from tests.support import run, runner

NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
REPLY = '{"reply": "Done."}'


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    queue: list[tuple[str, str]] = []
    real = runtime.open_runtime

    @contextmanager
    def scripted(settings, *, model=None):
        answers = [ScriptedReply(point, ModelReply(content=text)) for point, text in queue]
        queue.clear()
        with real(settings, model=ScriptedModel(answers)) as opened:
            yield opened

    monkeypatch.setattr(runtime, "open_runtime", scripted)
    return queue


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")


def pending() -> object:
    return Store(get_settings().db_path).pending()[0]


@pytest.mark.usefixtures("demo_on")
def test_resume_json_of_a_waiting_run_and_a_bad_demo_setting(
    replies: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    request = pending()
    run("approvals", "approve", request.approval_id, "--yes", "--no-resume")
    resumed = run("resume", request.run_id, "--json")
    assert resumed.exit_code == 0
    body = json.loads(resumed.stdout)
    assert body["status"] == "waiting" and body["run_id"] == request.run_id
    assert body["approval_id"] not in (None, request.approval_id)
    monkeypatch.setenv("CONDUCTOR_DEMO", "yes")
    refused = run("ask", "demo: say hi")
    assert (refused.exit_code, refused.stdout, refused.stderr) == (
        1,
        "",
        "Error: CONDUCTOR_DEMO: must be true or false\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_stopped_plain_rejection_and_escalation_problems(
    replies: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stopped(opened: object, run_id: str) -> RunState:
        return RunState(run_id=run_id, status="stopped", stopped_at="plan")

    real_resume = runtime.resume
    monkeypatch.setattr(runtime, "resume", stopped)
    shown = run("resume", "a" * 32)
    monkeypatch.setattr(runtime, "resume", real_resume)
    assert (shown.exit_code, shown.stdout) == (0, f"run {'a' * 32}  stopped at plan\n")

    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    request = pending()
    rejected = run("approvals", "reject", request.approval_id)
    assert rejected.stdout == f"Rejected {request.approval_id}.\nrun {request.run_id}  rejected\n"
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    noted = pending()
    with_note = run("approvals", "reject", noted.approval_id, "--note", "not now")
    assert with_note.stdout == (
        f"Rejected {noted.approval_id}.\nrun {noted.run_id}  rejected\nnote: not now\n"
    )

    replies[:] = [("plan", '{"steps": [{"action": "missing"}]}')]
    asked = run("ask", "demo: say hi")
    assert asked.exit_code == 0
    head, _, tail = asked.stdout.partition("Next:")
    assert "\n  " in head
    assert tail.startswith(" conductor escalations retry ")


@pytest.mark.usefixtures("demo_on")
def test_an_edit_resumes_with_the_new_arguments_and_a_decline_waits(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    plan = pending()
    run("approvals", "approve", plan.approval_id, "--yes")
    step = pending()
    replies[:] = [("answer", REPLY)]
    edited = run("approvals", "edit", step.approval_id, "--args", '{"title": "Bread"}', "--yes")
    assert edited.exit_code == 0
    calls = [
        event
        for event in EventLog(get_settings().runs_dir).read(plan.run_id)
        if event.kind == EventKind.TOOL_CALL
    ]
    assert calls[-1].payload["args"]["title"] == "Bread"

    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    waiting = pending()
    declined = runner.invoke(app, ["approvals", "approve", waiting.approval_id], input="n\n")
    assert declined.exit_code == 0
    assert declined.stdout.endswith("Nothing recorded.\n")
    assert Store(get_settings().db_path).approval(waiting.approval_id).decision is None
    assert Store(get_settings().db_path).pending()


def test_retry_without_resume_and_cancel_that_resumes(replies: list) -> None:
    run("ask", "Say hi back to me")
    first = Store(get_settings().db_path).open_escalations()[0]
    recorded = run("escalations", "retry", first.escalation_id, "--yes", "--no-resume")
    assert (recorded.exit_code, recorded.stdout) == (
        0,
        f"Retry recorded for {first.escalation_id}.\n",
    )
    run("ask", "Book a flight to Lisbon")
    second = Store(get_settings().db_path).open_escalations()[0]
    cancelled = run("escalations", "cancel", second.escalation_id)
    assert cancelled.stdout == (
        f"Cancelled {second.escalation_id}.\nrun {second.escalation.run_id}  cancelled\n"
    )


@pytest.mark.usefixtures("demo_on")
def test_a_busy_reject_keeps_the_rejection(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    request = pending()
    with runtime.open_runtime(get_settings()) as opened:
        opened.store.acquire(request.run_id, "9" * 32)
    result = run("approvals", "reject", request.approval_id, "--note", "no")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        f"Rejected {request.approval_id}.\n",
        f"Error: run {request.run_id} is busy\n",
    )
    decision = Store(get_settings().db_path).approval(request.approval_id).decision
    assert decision is not None and decision.verdict == "reject"


def test_a_request_of_2001_characters_is_refused(replies: list) -> None:
    result = run("ask", "y" * 2001)
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        "Error: a request must have 1 to 2000 characters\n",
    )
    assert "Traceback" not in (result.output or "")
    assert isinstance(result.exception, SystemExit)
