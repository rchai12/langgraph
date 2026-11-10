import json
from pathlib import Path

import pytest

from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.run import CaseResult, case_line, overall_line, run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
ECHO = EvalCase(
    id="say-hi",
    request="Say hi back to me",
    route="demo",
    plan=("echo",),
    args=({"text": "hi"},),
)
ROUTE = '{"domain": "demo"}'


def plan(*steps: tuple[str, dict]) -> str:
    return json.dumps({"steps": [{"action": a, "args": args} for a, args in steps]})


def scripted(*replies) -> ScriptedModel:
    made = []
    for point, content, seconds in replies:
        reply = (
            content
            if isinstance(content, ModelUnavailable)
            else ModelReply(content=content, total_ns=int(seconds * 1e9))
        )
        made.append(ScriptedReply(point, reply))
    return ScriptedModel(made)


def run(case: EvalCase, model: ScriptedModel, tmp_path: Path, runs: int) -> CaseResult:
    return run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=runs,
    )


def test_three_runs_that_agree(tmp_path: Path) -> None:
    replies = [("route", ROUTE, 1.0), ("plan", plan(("echo", {"text": "hi"})), 2.0)] * 3
    result = run(ECHO, scripted(*replies), tmp_path, 3)
    assert result == CaseResult(
        case_id="say-hi",
        runs=3,
        consistent=3,
        route_ok=3,
        plan_ok=3,
        args_ok=3,
        valid=3,
        escalated=0,
        unavailable=0,
        seconds=(3.0, 3.0, 3.0),
    )
    assert case_line(result) == (
        "say-hi  consistent 3/3  route 3/3  plan 3/3  args 3/3  valid 3/3  escalated 0/3"
        "  p50 3.00s  p95 3.00s"
    )


def test_runs_that_disagree(tmp_path: Path) -> None:
    replies = [
        ("route", ROUTE, 1.0),
        ("plan", plan(("echo", {"text": "hi"})), 1.0),
        ("route", ROUTE, 1.0),
        ("plan", plan(("echo", {"text": "Hi!"})), 3.0),
        ("route", '{"domain": "unknown"}', 0.5),
        ("route", ROUTE, 1.0),
        ("plan", plan(("note", {"title": "hi"})), 2.0),
    ]
    result = run(ECHO, scripted(*replies), tmp_path, 4)
    assert (result.consistent, result.route_ok, result.plan_ok, result.args_ok) == (1, 3, 2, 1)
    assert (result.valid, result.escalated, result.unavailable) == (4, 1, 0)
    assert result.seconds == (2.0, 4.0, 0.5, 3.0)
    assert case_line(result).endswith("p50 2.00s  p95 4.00s")


def test_an_invalid_reply_and_an_unavailable_model(tmp_path: Path) -> None:
    replies = [
        ("route", ROUTE, 1.0),
        ("plan", '{"steps": [{"action": "send", "args": {}}]}', 1.0),
        ("route", ModelUnavailable("timeout"), 0),
    ]
    result = run(ECHO, scripted(*replies), tmp_path, 2)
    assert (result.valid, result.escalated, result.unavailable) == (1, 2, 1)
    assert (result.route_ok, result.plan_ok) == (1, 0)


def test_a_case_that_expects_escalations(tmp_path: Path) -> None:
    no_domain = EvalCase(id="weather", request="Weather in Lisbon?", route="escalate")
    result = run(no_domain, scripted(("route", '{"domain": "unknown"}', 1.0)), tmp_path, 1)
    assert (result.route_ok, result.plan_ok, result.args_ok, result.escalated) == (1, 1, None, 1)
    nothing_fits = EvalCase(id="table", request="demo: book a table", route="demo", plan="escalate")
    result = run(nothing_fits, scripted(("plan", '{"steps": []}', 1.0)), tmp_path, 1)
    assert (result.route_ok, result.plan_ok, result.escalated) == (1, 1, 1)
    assert "args -" in case_line(result)


def test_a_rule_route_asks_the_model_only_to_plan(tmp_path: Path) -> None:
    case = EvalCase(id="prefixed", request="demo: say hi", route="demo", plan=("echo",))
    model = scripted(("plan", plan(("echo", {"text": "hi"})), 1.5))
    result = run(case, model, tmp_path, 1)
    assert (result.consistent, result.plan_ok, result.seconds) == (1, 1, (1.5,))
    assert [request.point for request in model.requests] == ["plan"]


def test_the_overall_line(tmp_path: Path) -> None:
    first = CaseResult("a", 2, 2, 2, 2, 2, 2, 0, 0, (1.0, 2.0))
    second = CaseResult("b", 2, 1, 2, 1, None, 1, 1, 1, (3.0, 4.0))
    assert overall_line((first, second)) == (
        "overall  2 cases  consistent 3/4  route 4/4  plan 3/4  args 2/2  valid 3/4"
        "  escalated 1/4  p50 2.00s  p95 4.00s"
    )


@pytest.mark.parametrize("runs", [0, 101])
def test_runs_are_1_to_100(tmp_path: Path, runs: int) -> None:
    with pytest.raises(ValueError) as raised:
        run(ECHO, scripted(), tmp_path, runs)
    assert str(raised.value) == "runs must be 1 to 100"
