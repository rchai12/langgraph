import itertools
import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from conductor import clock, ids, runtime
from conductor.config import get_settings
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run


def ID(n: int) -> str:
    return f"{n:032x}"


NOTE_PLAN = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
REPLY = '{"reply": "Done."}'
WHEN = "2026-11-09T09:00:00Z"


def plan_block(approval: int, run_id: int, stage: str = "plan") -> str:
    return (
        f"approval {ID(approval)}  {stage}  pending\n"
        f"run {ID(run_id)}  requested {WHEN}\n"
        '  1. demo.note  write  {"body": "", "tags": [], "title": "Milk"}\n'
        f"Next: conductor approvals approve {ID(approval)} (or reject, or edit --args)\n"
    )


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """What the model answers in the next command; each command opens a new runtime."""
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


@pytest.mark.usefixtures("demo_on")
def test_a_read_only_request_is_answered(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN), ("answer", REPLY)]
    result = run("ask", "demo: say hi")
    assert (result.exit_code, result.stdout, result.stderr) == (
        0,
        f"run {ID(2)}  done\nDone.\n",
        "",
    )


@pytest.mark.usefixtures("demo_on")
def test_each_decision_resumes_the_run(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    asked = run("ask", "demo: note Milk")
    assert (asked.exit_code, asked.stdout) == (0, plan_block(4, 2))
    plan = run("approvals", "approve", ID(4), "--yes")
    assert (plan.exit_code, plan.stdout) == (0, f"Approved {ID(4)}.\n" + plan_block(6, 2, "step"))
    replies[:] = [("answer", REPLY)]
    step = run("approvals", "approve", ID(6), "--yes")
    assert (step.exit_code, step.stdout) == (
        0,
        f"Approved {ID(6)}.\nrun {ID(2)}  done\nDone.\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_a_rejection_ends_the_run(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    result = run("approvals", "reject", ID(4), "--note", "not now")
    assert (result.exit_code, result.stdout) == (
        0,
        f"Rejected {ID(4)}.\nrun {ID(2)}  rejected\nnote: not now\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_no_resume_only_records_and_resume_continues(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    recorded = run("approvals", "approve", ID(4), "--yes", "--no-resume")
    assert (recorded.exit_code, recorded.stdout) == (0, f"Approved {ID(4)}.\n")
    resumed = run("resume", ID(2))
    assert (resumed.exit_code, resumed.stdout) == (0, plan_block(7, 2, "step"))


def test_an_escalation_and_its_answers(replies: list) -> None:
    asked = run("ask", "Say hi back to me")
    assert (asked.exit_code, asked.stdout) == (
        0,
        f"escalation {ID(3)}  unknown_route  open\n"
        f"run {ID(2)}  raised {WHEN}\n"
        "no domains are registered\n"
        f"Next: conductor escalations retry {ID(3)} (or cancel)\n",
    )
    retried = run("escalations", "retry", ID(3), "--yes")
    assert retried.exit_code == 0
    assert retried.stdout.startswith(f"Retry recorded for {ID(3)}.\nescalation {ID(5)}  ")
    cancelled = run("escalations", "cancel", ID(5))
    assert (cancelled.exit_code, cancelled.stdout) == (
        0,
        f"Cancelled {ID(5)}.\nrun {ID(2)}  cancelled\n",
    )


@pytest.mark.usefixtures("demo_on")
def test_json_output(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    asked = run("ask", "demo: note Milk", "--json")
    assert json.loads(asked.stdout) == {
        "run_id": ID(2),
        "status": "waiting",
        "approval_id": ID(4),
        "escalation_id": None,
        "reply": None,
        "note": "",
        "stopped_at": None,
    }
    run("approvals", "reject", ID(4), "--no-resume")
    resumed = run("resume", ID(2), "--json")
    assert json.loads(resumed.stdout)["status"] == "rejected"


@pytest.mark.usefixtures("demo_on")
def test_a_busy_run_keeps_the_decision_and_says_why(replies: list) -> None:
    replies[:] = [("plan", NOTE_PLAN)]
    run("ask", "demo: note Milk")
    with runtime.open_runtime(get_settings()) as opened:
        opened.store.acquire(ID(2), "9" * 32)
    result = run("approvals", "approve", ID(4), "--yes")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        f"Approved {ID(4)}.\n",
        f"Error: run {ID(2)} is busy\n",
    )


@pytest.mark.usefixtures("demo_on")
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("ask", "   "), "Error: a request must have 1 to 2000 characters\n"),
        (("resume", "9" * 32), f"Error: no run {'9' * 32}\n"),
    ],
)
def test_errors(replies: list, args: tuple[str, ...], message: str) -> None:
    result = run(*args)
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", message)


@pytest.mark.usefixtures("demo_on")
def test_a_finished_run_is_not_resumed(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN), ("answer", REPLY)]
    run("ask", "demo: say hi")
    result = run("resume", ID(2))
    assert (result.exit_code, result.stderr) == (1, f"Error: run {ID(2)} is not waiting\n")


@pytest.mark.usefixtures("demo_on")
def test_a_run_stopped_at_a_model_call_is_resumed(replies: list) -> None:
    replies[:] = [("plan", ECHO_PLAN)]
    stopped = run("ask", "demo: say hi")
    assert stopped.exit_code == 1 and stopped.exception is not None
    replies[:] = [("answer", REPLY)]
    resumed = run("resume", ID(2))
    assert (resumed.exit_code, resumed.stdout) == (0, f"run {ID(2)}  done\nDone.\n")
