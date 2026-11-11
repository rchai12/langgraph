import json
from datetime import date
from pathlib import Path

import pytest

from conductor import clock
from conductor.domains import demo, finance
from conductor.evals.cases import CaseFileError, EvalCase, load_cases
from conductor.evals.run import run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.plan import plan_fields
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
CASE = '[[case]]\nid = "say-hi"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'
FINANCE = Path(__file__).resolve().parents[2] / "evals" / "cases" / "finance.toml"


@pytest.fixture(autouse=True)
def another_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: date(2031, 1, 1))


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.toml"
    path.write_text(text)
    return path


def test_a_case_may_name_its_today(tmp_path: Path) -> None:
    found = load_cases(write(tmp_path, CASE + "today = 2026-11-10\n"), REGISTRY)
    assert found == (
        EvalCase("say-hi", "demo: say hi", "demo", ("echo",), None, date(2026, 11, 10)),
    )
    assert load_cases(write(tmp_path, CASE), REGISTRY)[0].today is None


@pytest.mark.parametrize(
    "value",
    ['"2026-11-10"', "2026-11-10T09:00:00", "2026-11-10T09:00:00Z", "20261110", "09:00:00"],
    ids=["text", "local-datetime", "datetime", "number", "time"],
)
def test_today_must_be_a_date(tmp_path: Path, value: str) -> None:
    with pytest.raises(CaseFileError) as refused:
        load_cases(write(tmp_path, CASE + f"today = {value}\n"), REGISTRY)
    assert str(refused.value) == (
        f"{tmp_path / 'cases.toml'}: case 1: today must be a date such as 2026-11-10"
    )


def test_plan_fields_take_a_given_day() -> None:
    fields = plan_fields(demo.DOMAIN, today=date(2026, 11, 10))
    assert (fields["today"], fields["weekday"]) == ("2026-11-10", "Tuesday")
    fields = plan_fields(demo.DOMAIN)
    assert (fields["today"], fields["weekday"]) == ("2031-01-01", "Wednesday")


@pytest.mark.parametrize(
    ("today", "line"),
    [
        (date(2026, 11, 10), "Today is 2026-11-10, a Tuesday."),
        (None, "Today is 2031-01-01, a Wednesday."),
    ],
    ids=["given", "clock"],
)
def test_each_run_plans_on_the_case_day(tmp_path: Path, today: date | None, line: str) -> None:
    reply = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=reply))] * 2)
    case = EvalCase("say-hi", "demo: say hi", "demo", ("echo",), None, today)
    found = run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=2,
    )
    assert found.plan_ok == 2
    assert [line in request.system for request in model.requests] == [True, True]


def test_the_finance_cases_load_and_plan_on_one_day() -> None:
    found = load_cases(FINANCE, Registry((finance.DOMAIN,)))
    assert len(found) == 24
    assert {case.today for case in found} == {date(2026, 11, 10)}
    assert {case.route for case in found} == {"finance", "escalate"}
