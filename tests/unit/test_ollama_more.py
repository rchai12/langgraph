import json
from http.client import IncompleteRead
from urllib.error import URLError

import pytest

from conductor.domains import demo
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.ollama import OllamaModel
from conductor.llm.points import build_request
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from tests.support import fake_ollama

PLAIN = {"name": "plain:latest", "digest": "a" * 64}
GOOD = {"done": True, "done_reason": "stop", "message": {"content": "{}"}}
BAD = "model unavailable: bad_answer"


def request(text: str = "x"):
    return build_request(
        demo.PICK, demo.PickInputs(request=text), model="qwen3.8:27b", fields=demo.pick_fields()
    )


def unavailable(call) -> ModelUnavailable:
    with pytest.raises(ModelUnavailable) as raised:
        call()
    return raised.value


def text(call) -> str:
    return str(unavailable(call))


def test_a_tags_404_is_an_http_error() -> None:
    with fake_ollama() as (fake, host):
        fake.status = 404
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert (error.code, error.status, str(error)) == (
        "http_error",
        404,
        "model unavailable: http_error 404",
    )


class _Raises:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    def open(self, request: object, timeout: float) -> object:
        raise self._error


def test_opener_errors_keep_their_codes() -> None:
    model = OllamaModel("http://127.0.0.1:9", timeout=5)
    cases = [
        (URLError(TimeoutError()), "timeout"),
        (ConnectionResetError(), "unreachable"),
        (IncompleteRead(b""), "bad_answer"),
    ]
    for error, code in cases:
        model._opener = _Raises(error)
        raised = unavailable(lambda: model.chat(request()))
        assert (raised.code, str(raised)) == (code, f"model unavailable: {code}")


def test_a_tagged_name_does_not_match_latest_and_bad_tags_are_refused() -> None:
    with fake_ollama() as (fake, host):
        model = OllamaModel(host, timeout=5)
        fake.body = json.dumps({"models": [PLAIN]}).encode()
        missing = unavailable(lambda: model.model_info("plain:7b"))
        assert (missing.code, str(missing)) == (
            "not_installed",
            "model unavailable: not_installed",
        )
        fake.body = json.dumps({"models": "x"}).encode()
        assert text(lambda: model.model_info("plain")) == BAD
        fake.body = json.dumps({"models": [{"name": 3, "digest": "a" * 64}]}).encode()
        assert text(lambda: model.model_info("plain")) == BAD


def test_counts_thinking_and_the_done_reason() -> None:
    with fake_ollama() as (fake, host):
        model = OllamaModel(host, timeout=5)
        for answer in (
            {**GOOD, "eval_count": True},
            {**GOOD, "eval_count": -1},
            {**GOOD, "done_reason": 7},
        ):
            fake.answer(**answer)
            assert text(lambda: model.chat(request())) == BAD
        fake.answer(**{**GOOD, "message": {"content": "{}", "thinking": None}})
        assert model.chat(request()).thinking == ""


def test_a_body_that_is_not_utf8() -> None:
    with fake_ollama() as (fake, host):
        fake.chat_body = b"\xff"
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request()))
    assert str(error) == BAD


def test_the_post_body_keeps_non_ascii_text() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(**GOOD)
        built = request("Résumé")
        OllamaModel(host, timeout=5).chat(built)
    body = fake.posts[0][2]
    assert "Résumé".encode() in body
    assert b"\\u00e9" not in body


def test_the_script_keeps_its_own_copy_and_uses_up_a_wrong_point() -> None:
    echo = ModelReply(content='{"action": "echo"}')
    replies = [ScriptedReply("other", echo)]
    model = ScriptedModel(replies)
    replies.clear()
    assert model.remaining == 1
    with pytest.raises(ScriptError) as raised:
        model.chat(request())
    assert str(raised.value) == "scripted reply 1 is for other, not demo_pick"
    assert model.remaining == 0


def test_answers_outside_the_documented_shape() -> None:
    with fake_ollama() as (fake, host):
        model = OllamaModel(host, timeout=5)
        fake.chat_body = b"[]"
        assert text(lambda: model.chat(request())) == BAD
        shapes = (
            {"models": ["x"]},
            {"models": [{"name": "plain:latest", "digest": 1}]},
            {
                "models": [
                    {"name": "plain:latest", "digest": "a" * 64, "capabilities": ["thinking", 1]}
                ]
            },
        )
        for shape in shapes:
            fake.body = json.dumps(shape).encode()
            assert text(lambda: model.model_info("plain")) == BAD
        fake.answer(**{**GOOD, "message": {"content": "{}", "thinking": 1}})
        assert text(lambda: model.chat(request())) == BAD
