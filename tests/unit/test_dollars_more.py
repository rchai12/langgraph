import json
from datetime import date
from pathlib import Path

import pytest

from conductor import clock
from conductor.contracts import Route
from conductor.domains import demo
from conductor.evals.cases import CaseFileError, load_cases
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import with_dollars
from conductor.planning.plan import Planned, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed

RUN = "a" * 32
CASE = '[[case]]\nid = "Bad"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'


@pytest.mark.parametrize(
    ("cents", "dollars"),
    [(-100, "-1.00"), (99, "0.99"), (-101, "-1.01")],
)
def test_amounts_near_a_whole_dollar(cents: int, dollars: str) -> None:
    assert with_dollars({"paid_cents": cents}) == {"paid_dollars": dollars}


def test_an_invalid_id_is_reported_before_an_invalid_today(tmp_path: Path) -> None:
    path = tmp_path / "cases.toml"
    path.write_text(CASE + 'today = "nope"\n')
    with pytest.raises(CaseFileError) as refused:
        load_cases(path, Registry((demo.DOMAIN,)))
    assert str(refused.value) == (
        f"{path}: case 1: id must be lowercase letters, digits, and dashes"
    )


def test_plan_request_plans_on_the_given_day_without_the_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unused() -> date:
        raise AssertionError("clock.today was called")

    monkeypatch.setattr(clock, "today", unused)
    reply = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=reply))])
    found = plan_request(
        Routed(Route(domain="demo", decided_by="rule", rule_id="demo.prefix"), "say hi"),
        Registry((demo.DOMAIN,)),
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path),
        run_id=RUN,
        today=date(2026, 11, 10),
    )
    assert isinstance(found, Planned)
    assert "Today is 2026-11-10, a Tuesday." in model.requests[0].system
