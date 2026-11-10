from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from conductor import clock
from conductor.contracts import Route
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.prompts import load_template
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.plan import plan_fields, plan_point, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed

BY_RULE = Route(domain="demo", decided_by="rule", rule_id="demo.prefix")
ECHO_PLAN = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
PLAN_V1_SHA256 = "098b7cb36ec194b4fc187f2cdeb9066936df7d6bcfc0fcb5a781f90429a72c0c"


def test_today_is_the_local_day_of_now(monkeypatch: pytest.MonkeyPatch) -> None:
    moment = datetime(2031, 3, 4, 3, 30, tzinfo=UTC)
    monkeypatch.setattr(clock, "now", lambda: moment)
    assert clock.today() == moment.astimezone().date()
    later = datetime(2031, 3, 4, 23, 30, tzinfo=timezone(timedelta(hours=-6)))
    monkeypatch.setattr(clock, "now", lambda: later)
    assert clock.today() == later.astimezone().date()


@pytest.mark.parametrize(
    ("day", "weekday"),
    [
        (date(2026, 11, 9), "Monday"),
        (date(2026, 11, 10), "Tuesday"),
        (date(2026, 11, 11), "Wednesday"),
        (date(2026, 11, 12), "Thursday"),
        (date(2026, 11, 13), "Friday"),
        (date(2026, 11, 14), "Saturday"),
        (date(2026, 11, 15), "Sunday"),
    ],
)
def test_plan_fields_name_today_and_its_weekday(
    monkeypatch: pytest.MonkeyPatch, day: date, weekday: str
) -> None:
    monkeypatch.setattr(clock, "today", lambda: day)
    fields = plan_fields(demo.DOMAIN)
    assert (fields["today"], fields["weekday"]) == (day.isoformat(), weekday)


def test_the_plan_point_uses_plan_v2_and_keeps_v1() -> None:
    assert plan_point(demo.DOMAIN).template == "plan.v2"
    assert load_template("plan.v1").sha256 == PLAN_V1_SHA256
    assert load_template("plan.v2").fields == (
        "actions",
        "description",
        "domain",
        "today",
        "weekday",
    )


def test_each_plan_request_reads_today_again(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    days = iter([date(2026, 12, 31), date(2027, 1, 1)])
    monkeypatch.setattr(clock, "today", lambda: next(days))
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=ECHO_PLAN))] * 2)
    for run_id in ("a" * 32, "b" * 32):
        plan_request(
            Routed(BY_RULE, "demo: say hi"),
            Registry((demo.DOMAIN,)),
            model=model,
            model_name="test-model:1b",
            log=EventLog(tmp_path),
            run_id=run_id,
        )
    systems = [request.system for request in model.requests]
    assert "Today is 2026-12-31, a Thursday.\n" in systems[0]
    assert "Today is 2027-01-01, a Friday.\n" in systems[1]
