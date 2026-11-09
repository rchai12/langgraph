from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, ids, plancheck
from conductor.contracts import Escalation, FieldProblem, Plan, Route
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.decide import escalation_for
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.plancheck import PlanRejected
from conductor.planning.plan import Planned, plan_fields, plan_point, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed

RUN = "a" * 32
DECISION = "d" * 32
MODEL = "test-model:1b"
SECRET = "SYNTHETIC-SECRET"
DEMO = Registry((demo.DOMAIN,))
BY_RULE = Route(domain="demo", decided_by="rule", rule_id="demo.prefix")


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: DECISION)


def ask(content: str, log: EventLog, request: str = "Echo hello") -> Planned | Escalation:
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=content))])
    return plan_request(
        Routed(BY_RULE, request), DEMO, model=model, model_name=MODEL, log=log, run_id=RUN
    )


def test_fields_list_every_action_and_the_union_keeps_declaration_order() -> None:
    assert plan_fields(demo.DOMAIN) == {
        "domain": "demo",
        "description": "A domain for tests: echo text, write a note, delegate a task.",
        "actions": (
            "- echo: Repeat the text back.\n"
            "- note: Write a note with a title, a body, and tags.\n"
            "- delegate: Hand a task to the demo agent."
        ),
    }
    note, echo = demo.DOMAIN.actions[1], demo.DOMAIN.actions[0]
    domain = replace(demo.DOMAIN, actions=(note, echo))
    one_of = plan_point(domain).output.model_json_schema()["properties"]["steps"]["items"]["oneOf"]
    assert [item["$ref"] for item in one_of] == ["#/$defs/note_step", "#/$defs/echo_step"]


def test_a_script_error_passes_and_an_unreachable_model_escalates(tmp_path: Path) -> None:
    routed = Routed(BY_RULE, "Echo hello")
    with pytest.raises(ScriptError):
        plan_request(
            routed,
            DEMO,
            model=ScriptedModel([]),
            model_name=MODEL,
            log=EventLog(tmp_path),
            run_id=RUN,
        )
    found = plan_request(
        routed,
        DEMO,
        model=ScriptedModel([], info=ModelUnavailable("unreachable")),
        model_name=MODEL,
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    assert found == escalation_for(ModelUnavailable("unreachable"), RUN)
    assert isinstance(found, Escalation)
    assert found.kind == "model_unavailable"


def test_omitted_arguments_keep_their_defaults_and_eight_steps_plan(tmp_path: Path) -> None:
    found = ask(
        '{"steps": [{"action": "note", "args": {"title": "Milk"}},'
        ' {"action": "delegate", "args": {"task": "Sweep the step"}}]}',
        EventLog(tmp_path),
    )
    assert isinstance(found, Planned)
    assert [(step.action, step.args) for step in found.plan.steps] == [
        ("demo.note", {"title": "Milk", "body": "", "tags": []}),
        ("demo.delegate", {"task": "Sweep the step", "max_minutes": 10}),
    ]
    steps = ", ".join(['{"action": "echo", "args": {"text": "hi"}}'] * 8)
    eight = ask('{"steps": [' + steps + "]}", EventLog(tmp_path))
    assert isinstance(eight, Planned)
    assert len(eight.plan.steps) == 8
    assert [step.number for step in eight.steps] == list(range(1, 9))


def test_a_secret_stays_out_of_every_escalation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(plan: Plan, route: Route, registry: Registry) -> None:
        raise PlanRejected((FieldProblem(loc="steps.0.action", code="unknown_action"),))

    monkeypatch.setattr(plancheck, "check_plan", refuse)
    request = f"Please {SECRET}"
    replies = [
        f'{{"steps": [{{"action": "echo", "args": {{"text": "hi", "x": "{SECRET}"}}}}]}}',
        '{"steps": []}',
        f'{{"steps": [{{"action": "echo", "args": {{"text": "{SECRET}"}}}}]}}',
    ]
    for content in replies:
        found = ask(content, EventLog(tmp_path), request)
        assert isinstance(found, Escalation)
        assert SECRET not in found.model_dump_json()


def test_the_model_is_shown_the_stripped_request(tmp_path: Path) -> None:
    content = '{"steps": [{"action": "echo", "args": {"text": "hi"}}]}'
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=content))])
    found = plan_request(
        Routed(BY_RULE, "say hello"),
        DEMO,
        model=model,
        model_name=MODEL,
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    assert isinstance(found, Planned)
    assert model.requests[0].user == '{\n  "request": "say hello"\n}'
