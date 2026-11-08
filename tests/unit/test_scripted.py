from dataclasses import replace

import pytest

from conductor.domains import demo
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import build_request
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply, ScriptError

ECHO = ModelReply(content='{"action": "echo"}')
NOTE = ModelReply(content='{"action": "note"}', thinking="A note.")


def request(point: str = "demo_pick"):
    built = build_request(
        demo.PICK, demo.PickInputs(request="x"), model="test-model:1b", fields=demo.pick_fields()
    )
    return replace(built, point=point)


def test_replies_come_in_order() -> None:
    model = ScriptedModel([ScriptedReply("demo_pick", ECHO), ScriptedReply("demo_pick", NOTE)])
    assert model.remaining == 2
    first, second = request(), request()
    assert model.chat(first) is ECHO
    assert model.chat(second) is NOTE
    assert model.remaining == 0
    assert model.requests == [first, second]


def test_a_reply_for_another_point() -> None:
    model = ScriptedModel([ScriptedReply("demo_pick", ECHO), ScriptedReply("route", NOTE)])
    model.chat(request())
    with pytest.raises(ScriptError) as raised:
        model.chat(request())
    assert str(raised.value) == "scripted reply 2 is for route, not demo_pick"


def test_no_reply_left() -> None:
    model = ScriptedModel([])
    with pytest.raises(ScriptError) as raised:
        model.chat(request())
    assert str(raised.value) == "no scripted reply left for demo_pick"


def test_a_scripted_failure_is_raised_in_its_turn() -> None:
    down = ModelUnavailable("unreachable")
    model = ScriptedModel([ScriptedReply("demo_pick", down), ScriptedReply("demo_pick", ECHO)])
    with pytest.raises(ModelUnavailable) as raised:
        model.chat(request())
    assert raised.value is down
    assert model.chat(request()) is ECHO
    assert len(model.requests) == 2


def test_the_model_info() -> None:
    assert SCRIPTED_INFO == ModelInfo(
        name="scripted", digest="0" * 64, capabilities=("completion", "thinking")
    )
    assert ScriptedModel([]).model_info("qwen3.8:27b") == replace(SCRIPTED_INFO, name="qwen3.8:27b")
    plain = ModelInfo(name="plain:latest", digest="a" * 64, capabilities=("completion",))
    assert ScriptedModel([], info=plain).model_info("plain") == plain
    missing = ModelUnavailable("not_installed")
    with pytest.raises(ModelUnavailable) as raised:
        ScriptedModel([], info=missing).model_info("plain")
    assert raised.value is missing
