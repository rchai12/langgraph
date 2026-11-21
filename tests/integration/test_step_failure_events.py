import shlex
import sys
from pathlib import Path

import pytest

from conductor import domains
from conductor.config import get_settings
from conductor.events import EventKind
from conductor.graph.supervisor import StepFailed
from conductor.runtime import ask, open_runtime
from tests.integration.test_mcp_steps import FAKE, LAB, approve_all, model, plan
from tests.integration.test_supervisor_step_runs import (
    DELEGATE_PLAN,
    ECHO_PLAN,
    MIXED_PLAN,
    NOTE_PLAN,
    RUN,
    Runner,
    World,
    fixed,  # noqa: F401
)


def until_failed(world: World, request: str):
    state = world.start(request)
    while state.status == "waiting" and state.approval_id is not None:
        world.decide(state)
        state = world.resume()
    return state


def error_events(log) -> list[tuple[str | None, dict]]:
    return [(e.node, e.payload) for e in log.read(RUN) if e.kind == EventKind.ERROR]


@pytest.mark.parametrize(
    ("plan_text", "runner", "fields", "detail"),
    [
        (
            ECHO_PLAN,
            Runner(error=StepFailed(code="timeout")),
            {"code": "timeout", "effect": "read", "unknown_outcome": False},
            "step 1 demo.echo: the step failed (timeout)",
        ),
        (
            NOTE_PLAN,
            Runner(error=StepFailed(code="closed")),
            {"code": "closed", "effect": "write", "unknown_outcome": True},
            "step 1 demo.note: the step failed (closed)",
        ),
        (
            NOTE_PLAN,
            Runner(error=StepFailed(code="no_command")),
            {"code": "no_command", "effect": "write", "unknown_outcome": False},
            "step 1 demo.note: the step failed (no_command)",
        ),
        (
            NOTE_PLAN,
            Runner(error=StepFailed(code="too_large")),
            {"code": "too_large", "effect": "write", "unknown_outcome": True},
            "step 1 demo.note: the step failed (too_large)",
        ),
        (
            DELEGATE_PLAN,
            Runner(error=StepFailed()),
            {"code": None, "effect": "implement", "unknown_outcome": True},
            "step 1 demo.delegate: the step failed",
        ),
    ],
    ids=["read-timeout", "write-closed", "write-no-command", "write-too-large", "implement-bare"],
)
def test_the_error_event_names_the_cause_and_the_detail_is_unchanged(
    tmp_path: Path, plan_text: str, runner: Runner, fields: dict, detail: str
) -> None:
    world = World(tmp_path, [("plan", plan_text)], runner)
    state = until_failed(world, "demo: do it")
    stored = world.store.escalation(state.escalation_id).escalation
    assert (stored.kind, stored.detail, stored.problems) == ("tool_error", detail, ())
    assert error_events(world.log) == [
        ("run_step", {"step": 1, "error": "tool_error", **fields, "problems": []})
    ]


def test_a_result_that_does_not_fit_is_an_unknown_write(tmp_path: Path) -> None:
    world = World(tmp_path, [("plan", NOTE_PLAN)], Runner(output={"note_id": "x"}))
    state = until_failed(world, "demo: note")
    stored = world.store.escalation(state.escalation_id).escalation
    assert stored.detail == "step 1 demo.note: the result does not fit the action"
    assert error_events(world.log) == [
        (
            "run_step",
            {
                "step": 1,
                "error": "tool_error",
                "code": "invalid_result",
                "effect": "write",
                "unknown_outcome": True,
                "problems": [{"loc": "note_id", "code": "string_pattern_mismatch"}],
            },
        )
    ]


def test_an_earlier_step_keeps_its_result_when_a_later_write_fails(tmp_path: Path) -> None:
    class SecondFails(Runner):
        def run(self, action, args):
            if action.name == "note":
                raise StepFailed(code="timeout")
            return super().run(action, args)

    world = World(tmp_path, [("plan", MIXED_PLAN)], SecondFails())
    until_failed(world, "demo: both")
    kinds = [(e.kind, e.payload.get("step")) for e in world.log.read(RUN) if e.node == "run_step"]
    assert kinds == [
        (EventKind.TOOL_CALL, 1),
        (EventKind.TOOL_RESULT, 1),
        (EventKind.TOOL_CALL, 2),
        (EventKind.ERROR, 2),
    ]
    assert error_events(world.log)[0][1]["unknown_outcome"] is True


@pytest.fixture
def lab(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "2")
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))


@pytest.mark.usefixtures("lab")
def test_a_server_that_stops_records_an_unknown_write() -> None:
    with open_runtime(get_settings(), model=model(("plan", plan("stop", {})))) as runtime:
        failed = approve_all(runtime, ask(runtime, "lab: stop"))
        errors = [
            (event.node, event.payload)
            for event in runtime.log.read(failed.run_id)
            if event.kind == EventKind.ERROR
        ]
    assert errors == [
        (
            "run_step",
            {
                "step": 1,
                "error": "tool_error",
                "code": "closed",
                "effect": "write",
                "unknown_outcome": True,
                "problems": [],
            },
        )
    ]
