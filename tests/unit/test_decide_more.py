from dataclasses import replace
from pathlib import Path

import pytest

from conductor.contracts import Contract, Escalation, FieldProblem
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.decide import InvalidModelOutput, decide, escalation_for
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply, ScriptError

RUN = "a" * 32
MODEL = "test-model:1b"


def run(model, log: EventLog, *, point=demo.PICK):
    return decide(
        point,
        demo.PickInputs(request="x"),
        fields=demo.pick_fields(),
        model=model,
        model_name=MODEL,
        log=log,
        run_id=RUN,
    )


def test_the_request_is_on_disk_when_chat_is_called(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    seen: list[EventKind] = []

    class ReadingModel:
        def model_info(self, name: str) -> ModelInfo:
            return replace(SCRIPTED_INFO, name=name)

        def chat(self, request: object) -> ModelReply:
            seen.extend(event.kind for event in log.read(RUN))
            return ModelReply(content='{"action": "echo"}')

    decision = run(ReadingModel(), log)
    assert seen == [EventKind.MODEL_REQUEST]
    assert decision.output == demo.PickOutput(action="echo")


def test_a_script_error_leaves_only_the_request(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    model = ScriptedModel([], info=SCRIPTED_INFO)
    with pytest.raises(ScriptError):
        run(model, log)
    events = log.read(RUN)
    assert [event.kind for event in events] == [EventKind.MODEL_REQUEST]


def test_any_done_reason_but_stop_is_cut_off_without_parsing(tmp_path: Path) -> None:
    cases = (("length", "not json"), ("load", '{"action": "echo"}'))
    for done_reason, content in cases:
        log = EventLog(tmp_path / done_reason)
        model = ScriptedModel(
            [ScriptedReply("demo_pick", ModelReply(content=content, done_reason=done_reason))]
        )
        with pytest.raises(InvalidModelOutput) as raised:
            run(model, log)
        assert raised.value.problems == (FieldProblem(loc="reply", code="cut_off"),)


class TwoNumbers(Contract):
    a: int
    b: int


def test_two_bad_fields_are_both_reported(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    point = replace(demo.PICK, output=TwoNumbers)
    model = ScriptedModel([ScriptedReply("demo_pick", ModelReply(content='{"a": "1", "b": "2"}'))])
    with pytest.raises(InvalidModelOutput) as raised:
        run(model, log, point=point)
    assert raised.value.problems == (
        FieldProblem(loc="a", code="int_type"),
        FieldProblem(loc="b", code="int_type"),
    )


def test_a_timeout_is_logged_with_no_status(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    down = ModelUnavailable("timeout")
    model = ScriptedModel([ScriptedReply("demo_pick", down)])
    with pytest.raises(ModelUnavailable) as raised:
        run(model, log)
    assert raised.value is down
    error = log.read(RUN)[-1]
    assert error.kind == EventKind.ERROR
    assert error.payload["code"] == "timeout"
    assert error.payload["status"] is None


def test_a_failing_reply_is_asked_once(tmp_path: Path) -> None:
    log = EventLog(tmp_path)

    class CountingModel:
        def __init__(self) -> None:
            self.calls = 0

        def model_info(self, name: str) -> ModelInfo:
            return replace(SCRIPTED_INFO, name=name)

        def chat(self, request: object) -> ModelReply:
            self.calls += 1
            return ModelReply(content="not json")

    model = CountingModel()
    with pytest.raises(InvalidModelOutput):
        run(model, log)
    assert model.calls == 1


def test_every_unavailable_code_escalates_within_the_detail_limit() -> None:
    errors = (
        ModelUnavailable("unreachable"),
        ModelUnavailable("timeout"),
        ModelUnavailable("http_error", 503),
        ModelUnavailable("bad_answer"),
        ModelUnavailable("not_installed"),
    )
    for error in errors:
        escalation = escalation_for(error, RUN)
        assert len(escalation.detail) <= 500
        assert escalation.kind == "model_unavailable"
        assert Escalation.from_json(escalation.model_dump_json()) == escalation
