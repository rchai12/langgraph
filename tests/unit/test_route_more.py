from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.contracts import Contract, Escalation, FieldProblem, Route
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.decide import InvalidModelOutput, escalation_for
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.registry import Action, Domain, Registry, Rule
from conductor.routing.route import (
    CONFLICT_MESSAGE,
    Routed,
    route_fields,
    route_point,
    route_request,
)

RUN = "a" * 32
DECISION = "d" * 32
MODEL = "test-model:1b"


class PingArgs(Contract):
    target: str


class PingResult(Contract):
    ok: bool


PING = Action("ping", "Check that a host answers.", "tool", "ping", "read", PingArgs, PingResult)
LAB = Domain("lab", "Lab checks.", (PING,), (Rule("ping", ("ping",)),))


class NoModel:
    def model_info(self, name: str):
        raise AssertionError("the model was asked")

    def chat(self, request):
        raise AssertionError("the model was asked")


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: DECISION)


def ask(text: str, registry: Registry, model, log: EventLog):
    return route_request(text, registry, model=model, model_name=MODEL, log=log, run_id=RUN)


def test_one_domain_enumerates_itself_and_lists_domains_in_order() -> None:
    alone = Registry((demo.DOMAIN,))
    schema = route_point(alone).output.model_json_schema()
    assert schema["properties"]["domain"]["enum"] == ["demo", "unknown"]
    ordered = Registry((LAB, demo.DOMAIN))
    assert route_fields(ordered)["domains"] == (
        "- lab: Lab checks.\n- demo: A domain for tests: echo text, write a note, delegate a task."
    )


def test_a_request_of_2000_characters_routes_and_a_wide_conflict_keeps_20(tmp_path: Path) -> None:
    text = "demo: " + "x" * 1994
    assert len(text) == 2000
    found = ask(text, Registry((demo.DOMAIN,)), NoModel(), EventLog(tmp_path))
    assert found == Routed(
        Route(domain="demo", decided_by="rule", rule_id="demo.prefix"), "x" * 1994
    )
    domains = tuple(
        Domain(f"d{number:02d}", "A domain.", (PING,), (Rule("ping", ("ping",)),))
        for number in range(21)
    )
    wide = ask("please ping", Registry(domains), NoModel(), EventLog(tmp_path))
    assert isinstance(wide, Escalation)
    assert wide.detail == CONFLICT_MESSAGE
    assert wide.problems == tuple(
        FieldProblem(loc=f"d{number:02d}.ping", code="matched") for number in range(20)
    )


def test_a_failed_reply_is_the_escalation_and_a_script_error_passes(tmp_path: Path) -> None:
    registry = Registry((demo.DOMAIN, LAB))
    scripted = ScriptedModel([ScriptedReply("route", ModelReply(content='{"domain": "travel"}'))])
    found = ask("Is the printer up?", registry, scripted, EventLog(tmp_path))
    expected = escalation_for(
        InvalidModelOutput(DECISION, (FieldProblem(loc="domain", code="literal_error"),)),
        RUN,
    )
    assert found == expected
    assert isinstance(found, Escalation) and DECISION in found.detail
    missing = ScriptedModel([], info=ModelUnavailable("unreachable"))
    unavailable = ask("Is the printer up?", registry, missing, EventLog(tmp_path))
    assert unavailable == escalation_for(ModelUnavailable("unreachable"), RUN)
    with pytest.raises(ScriptError):
        ask("Is the printer up?", registry, ScriptedModel([]), EventLog(tmp_path))
