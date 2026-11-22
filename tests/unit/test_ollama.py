import json
import socket
from http.client import IncompleteRead
from urllib.error import URLError

import pytest

from conductor.domains import demo
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.ollama import OllamaModel
from conductor.llm.points import build_request
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from tests.support import fake_ollama

QWEN = {"name": "qwen3.8:27b", "digest": "4" * 64, "capabilities": ["thinking", "completion"]}
PLAIN = {"name": "plain:latest", "digest": "a" * 64}
TAGS = json.dumps({"models": [QWEN, PLAIN]}).encode()


def request():
    return build_request(
        demo.PICK,
        demo.PickInputs(request="Please repeat: hello"),
        model="qwen3.8:27b",
        fields=demo.pick_fields(),
    )


def unavailable(call) -> ModelUnavailable:
    with pytest.raises(ModelUnavailable) as raised:
        call()
    return raised.value


def test_the_model_info_is_read_from_the_tags() -> None:
    with fake_ollama() as (fake, host):
        fake.body = TAGS
        model = OllamaModel(host, timeout=5)
        assert model.model_info("qwen3.8:27b") == ModelInfo(
            name="qwen3.8:27b", digest="4" * 64, capabilities=("completion", "thinking")
        )
        assert model.model_info("plain") == ModelInfo(
            name="plain:latest", digest="a" * 64, capabilities=()
        )
    assert fake.paths == ["/api/tags", "/api/tags"]


@pytest.mark.parametrize("name", ["qwen3.8", "qwen3.8:7b"])
def test_a_model_that_is_not_installed(name: str) -> None:
    with fake_ollama() as (fake, host):
        fake.body = TAGS
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info(name))
    assert (error.code, error.status, str(error)) == (
        "not_installed",
        None,
        "model unavailable: not_installed",
    )


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"models": [{**PLAIN, "digest": "a" * 63}]}).encode(),
        json.dumps({"models": [QWEN, {**PLAIN, "capabilities": "thinking"}]}).encode(),
    ],
)
def test_tags_that_do_not_fit(body: bytes) -> None:
    with fake_ollama() as (fake, host):
        fake.body = body
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert str(error) == "model unavailable: bad_answer"


def test_tags_with_an_http_error() -> None:
    with fake_ollama() as (fake, host):
        fake.status = 500
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert (error.code, error.status, str(error)) == (
        "http_error",
        500,
        "model unavailable: http_error 500",
    )


def test_the_chat_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "synthetic-key")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    with fake_ollama() as (fake, host):
        fake.answer(done=True, done_reason="stop", message={"role": "assistant", "content": "{}"})
        OllamaModel(host, timeout=5).chat(request())
    [(path, headers, body)] = fake.posts
    assert path == "/api/chat"
    assert json.loads(body) == request().body()
    assert headers["content-type"] == "application/json"
    assert "authorization" not in headers


def test_a_chat_answer_becomes_a_reply() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(
            model="qwen3.8:27b",
            done=True,
            done_reason="stop",
            message={"role": "assistant", "content": '{"action": "echo"}', "thinking": "Hm."},
            total_duration=900,
            load_duration=100,
            prompt_eval_count=40,
            prompt_eval_duration=300,
            prompt_eval_cached_count=0,
            eval_count=6,
            eval_duration=500,
        )
        reply = OllamaModel(host, timeout=5).chat(request())
    assert reply == ModelReply(
        content='{"action": "echo"}',
        thinking="Hm.",
        done_reason="stop",
        total_ns=900,
        load_ns=100,
        prompt_tokens=40,
        prompt_ns=300,
        reply_tokens=6,
        reply_ns=500,
    )


def test_a_short_chat_answer_gets_defaults() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(done=True, done_reason="length", message={"content": '{"act'})
        reply = OllamaModel(host, timeout=5).chat(request())
    assert reply == ModelReply(content='{"act', done_reason="length")
    assert (reply.thinking, reply.total_ns, reply.reply_tokens) == ("", 0, 0)


@pytest.mark.parametrize(
    ("status", "code", "text"),
    [
        (404, "not_installed", "model unavailable: not_installed"),
        (400, "http_error", "model unavailable: http_error 400"),
    ],
)
def test_a_chat_http_error(status: int, code: str, text: str) -> None:
    with fake_ollama() as (fake, host):
        fake.chat_status = status
        fake.answer(error="model 'qwen3.8:27b' not found")
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request()))
    assert (error.code, str(error)) == (code, text)


GOOD = {"done": True, "done_reason": "stop", "message": {"content": "{}"}}


@pytest.mark.parametrize(
    "answer",
    [
        {**GOOD, "done": False},
        {"done": True, "done_reason": "stop"},
        {**GOOD, "message": {"content": None}},
        {**GOOD, "eval_count": "6"},
    ],
)
def test_a_chat_answer_that_does_not_fit(answer: dict[str, object]) -> None:
    with fake_ollama() as (fake, host):
        fake.answer(**answer)
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request()))
    assert str(error) == "model unavailable: bad_answer"


def test_nothing_listening() -> None:
    model = OllamaModel("http://127.0.0.1:9", timeout=5)
    assert str(unavailable(lambda: model.chat(request()))) == "model unavailable: unreachable"
    assert str(unavailable(lambda: model.model_info("plain"))) == "model unavailable: unreachable"


def test_a_silent_server_times_out() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        model = OllamaModel(f"http://127.0.0.1:{port}", timeout=0.3)
        error = unavailable(lambda: model.chat(request()))
    finally:
        listener.close()
    assert (error.code, str(error)) == ("timeout", "model unavailable: timeout")


BAD = "model unavailable: bad_answer"


def request_moved(text: str = "x"):
    return build_request(
        demo.PICK, demo.PickInputs(request=text), model="qwen3.8:27b", fields=demo.pick_fields()
    )


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

    def open(self, _request: object, timeout: float) -> object:  # noqa: ARG002
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
        raised = unavailable(lambda: model.chat(request_moved()))
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
        fake.body = json.dumps({"models": [PLAIN, PLAIN]}).encode()
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
            assert text(lambda: model.chat(request_moved())) == BAD
        fake.answer(**{**GOOD, "message": {"content": "{}", "thinking": None}})
        assert model.chat(request_moved()).thinking == ""


def test_a_body_that_is_not_utf8() -> None:
    with fake_ollama() as (fake, host):
        fake.chat_body = b"\xff"
        error = unavailable(lambda: OllamaModel(host, timeout=5).chat(request_moved()))
    assert str(error) == BAD


def test_the_post_body_keeps_non_ascii_text() -> None:
    with fake_ollama() as (fake, host):
        fake.answer(**GOOD)
        built = request_moved("Résumé")
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
        model.chat(request_moved())
    assert str(raised.value) == "scripted reply 1 is for other, not demo_pick"
    assert model.remaining == 0


def test_answers_outside_the_documented_shape() -> None:
    with fake_ollama() as (fake, host):
        model = OllamaModel(host, timeout=5)
        fake.chat_body = b"[]"
        assert text(lambda: model.chat(request_moved())) == BAD
        shapes = (
            {"models": [{"name": "plain:latest"}]},
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
        assert text(lambda: model.chat(request_moved())) == BAD
