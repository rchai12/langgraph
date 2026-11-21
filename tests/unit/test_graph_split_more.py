from pathlib import Path

import pytest

from conductor.graph import steps
from conductor.graph.supervisor import StepFailed
from tests.integration.test_supervisor_more import (  # noqa: F401
    NOTE_PLAN,
    Runner,
    World,
    fixed,
)


@pytest.mark.parametrize(
    ("effect", "code", "unknown"),
    [("propose", "no_result", True), ("read", "tool_error", False)],
    ids=["propose-no-result", "read-tool-error"],
)
def test_a_propose_without_a_result_and_a_failed_read(
    effect: str, code: str, unknown: bool
) -> None:
    assert steps.failure_fields(effect, code) == {
        "code": code,
        "effect": effect,
        "unknown_outcome": unknown,
    }


def test_a_retried_write_waits_for_a_new_step_approval(tmp_path: Path) -> None:
    runner = Runner(error=StepFailed(code="timeout"))
    world = World(tmp_path, [("plan", NOTE_PLAN)], runner)
    state = world.start("demo: note Milk")
    while state.status == "waiting" and state.approval_id is not None:
        world.decide(state)
        state = world.resume()
    world.answer(state, "retry")
    waiting = world.resume()
    [pending] = world.store.pending()
    assert (waiting.status, pending.stage, len(runner.calls)) == ("waiting", "step", 1)
