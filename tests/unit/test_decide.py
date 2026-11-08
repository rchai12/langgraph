from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.contracts import Escalation, FieldProblem
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.decide import (
    INVALID_OUTPUT_MESSAGE,
    Decision,
    InvalidModelOutput,
    decide,
    escalation_for,
)
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import build_request
from conductor.llm.prompts import PromptError, load_template
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply

RUN = "a" * 32
DECISION = "d" * 32
MODEL = "test-model:1b"
PLAIN = ModelInfo(name="plain:latest", digest="b" * 64, capabilities=("completion",))


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 8, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: DECISION)


def run(model, log: EventLog, *, point=demo.PICK, node: str | None = "route"):
    return decide(
        point,
        demo.PickInputs(request="Please repeat: hello"),
        fields=demo.pick_fields(),
        model=model,
        model_name=MODEL,
        log=log,
        run_id=RUN,
        node=node,
    )


def body(think: bool) -> dict[str, object]:
    built = build_request(
        demo.PICK,
        demo.PickInputs(request="Please repeat: hello"),
        model=MODEL,
        fields=demo.pick_fields(),
    )
    return replace(built, think=think).body()


def scripted(content: str, **reply: object) -> ScriptedModel:
    return ScriptedModel([ScriptedReply("demo_pick", ModelReply(content=content, **reply))])


def test_a_decision(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    model = scripted('{"action": "echo"}', thinking="It asks to repeat.")
    decision = run(model, log)
    assert decision == Decision(decision_id=DECISION, output=demo.PickOutput(action="echo"))
    assert [request.think for request in model.requests] == [True]
    events = log.read(RUN)
    assert [(event.kind, event.node) for event in events] == [
        (EventKind.MODEL_REQUEST, "route"),
        (EventKind.MODEL_REPLY, "route"),
    ]
    assert events[0].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "template": "demo_pick.v1",
        "template_sha256": load_template("demo_pick.v1").sha256,
        "model": MODEL,
        "model_listed_as": MODEL,
        "digest": SCRIPTED_INFO.digest,
        "think_requested": True,
        "think": True,
        "body": body(True),
    }
    assert events[1].payload == {
        "decision_id": DECISION,
        "content": '{"action": "echo"}',
        "thinking": "It asks to repeat.",
        "done_reason": "stop",
        "total_ns": 0,
        "load_ns": 0,
        "prompt_tokens": 0,
        "prompt_ns": 0,
        "reply_tokens": 0,
        "reply_ns": 0,
    }


@pytest.mark.parametrize(
    ("wanted", "capabilities", "sent"),
    [
        (True, ("completion", "thinking"), True),
        (True, ("completion",), False),
        (False, ("completion", "thinking"), False),
        (False, (), False),
    ],
)
def test_thinking_needs_the_point_and_the_model(
    tmp_path: Path, wanted: bool, capabilities: tuple[str, ...], sent: bool
) -> None:
    log = EventLog(tmp_path)
    info = replace(PLAIN, capabilities=capabilities)
    model = ScriptedModel(
        [ScriptedReply("demo_pick", ModelReply(content='{"action": "none"}'))], info=info
    )
    run(model, log, point=replace(demo.PICK, think=wanted))
    assert model.requests[0].think is sent
    payload = log.read(RUN)[0].payload
    assert (payload["think_requested"], payload["think"]) == (wanted, sent)
    assert (payload["model_listed_as"], payload["digest"]) == ("plain:latest", "b" * 64)


@pytest.mark.parametrize(
    ("content", "done_reason", "problems"),
    [
        ('{"action": "send"}', "stop", [("action", "literal_error")]),
        ("not json", "stop", [("", "json_invalid")]),
        ('["echo"]', "stop", [("", "model_type")]),
        ('{"action": "echo", "extra": 1}', "stop", [("extra", "extra_forbidden")]),
        ("{}", "stop", [("action", "missing")]),
        ('{"action": "echo"}', "length", [("reply", "cut_off")]),
    ],
)
def test_a_reply_that_does_not_fit_raises(
    tmp_path: Path, content: str, done_reason: str, problems: list[tuple[str, str]]
) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(InvalidModelOutput) as raised:
        run(scripted(content, done_reason=done_reason), log)
    expected = tuple(FieldProblem(loc=loc, code=code) for loc, code in problems)
    assert (raised.value.decision_id, raised.value.problems) == (DECISION, expected)
    assert str(raised.value) == INVALID_OUTPUT_MESSAGE
    events = log.read(RUN)
    assert [event.kind for event in events] == [
        EventKind.MODEL_REQUEST,
        EventKind.MODEL_REPLY,
        EventKind.ERROR,
    ]
    assert events[1].payload["content"] == content
    assert events[2].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "invalid_model_output",
        "problems": [{"loc": loc, "code": code} for loc, code in problems],
    }


def test_no_reply_value_reaches_the_error(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(InvalidModelOutput) as raised:
        run(scripted('{"action": "SYNTHETIC-SECRET"}'), log)
    assert "SYNTHETIC-SECRET" not in str(raised.value)
    assert "SYNTHETIC-SECRET" not in repr(raised.value.problems)
    assert "SYNTHETIC-SECRET" not in repr(log.read(RUN)[-1].payload)


def test_a_model_that_is_not_installed(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    missing = ModelUnavailable("not_installed")
    with pytest.raises(ModelUnavailable) as raised:
        run(ScriptedModel([], info=missing), log, node=None)
    assert raised.value is missing
    [event] = log.read(RUN)
    assert (event.kind, event.node) == (EventKind.ERROR, None)
    assert event.payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "model_unavailable",
        "code": "not_installed",
        "status": None,
    }


def test_a_model_that_fails_while_answering(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    down = ModelUnavailable("http_error", 500)
    with pytest.raises(ModelUnavailable) as raised:
        run(ScriptedModel([ScriptedReply("demo_pick", down)]), log)
    assert raised.value is down
    events = log.read(RUN)
    assert [event.kind for event in events] == [EventKind.MODEL_REQUEST, EventKind.ERROR]
    assert events[1].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "model_unavailable",
        "code": "http_error",
        "status": 500,
    }


class SwappedModel:
    """Lists a new digest each time it is asked, as if the model were pulled again."""

    def __init__(self) -> None:
        self.digests = iter(["1" * 64, "2" * 64])

    def model_info(self, name: str) -> ModelInfo:
        return ModelInfo(name=name, digest=next(self.digests), capabilities=())

    def chat(self, request) -> ModelReply:
        return ModelReply(content='{"action": "note"}')


def test_the_digest_is_read_for_every_decision(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    model = SwappedModel()
    run(model, log)
    run(model, log)
    requests = [event for event in log.read(RUN) if event.kind == EventKind.MODEL_REQUEST]
    assert [event.payload["digest"] for event in requests] == ["1" * 64, "2" * 64]


def test_a_prompt_error_is_raised_before_anything_is_logged(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(PromptError):
        decide(
            demo.PICK,
            demo.PickInputs(request="x"),
            fields={},
            model=scripted('{"action": "echo"}'),
            model_name=MODEL,
            log=log,
            run_id=RUN,
        )
    assert log.runs() == []


def test_an_escalation_for_invalid_output() -> None:
    problems = (FieldProblem(loc="action", code="literal_error"),)
    escalation = escalation_for(InvalidModelOutput(DECISION, problems), RUN)
    assert escalation == Escalation(
        kind="invalid_model_output",
        detail=f"decision {DECISION}: {INVALID_OUTPUT_MESSAGE}",
        run_id=RUN,
        problems=problems,
    )


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (
            ModelUnavailable("unreachable"),
            "model unavailable: unreachable; retry when Ollama answers",
        ),
        (
            ModelUnavailable("http_error", 503),
            "model unavailable: http_error 503; retry when Ollama answers",
        ),
    ],
)
def test_an_escalation_for_a_model_that_is_unavailable(
    error: ModelUnavailable, detail: str
) -> None:
    assert escalation_for(error, RUN) == Escalation(
        kind="model_unavailable", detail=detail, run_id=RUN
    )
