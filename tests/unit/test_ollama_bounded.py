import json

import pytest

from conductor.domains import demo
from conductor.llm import tags
from conductor.llm.model import ModelInfo, ModelUnavailable
from conductor.llm.ollama import OllamaModel
from conductor.llm.points import build_request
from tests.raw_http import answer, raw_server
from tests.support import fake_ollama

A = "a" * 64
PLAIN = {"name": "plain:latest", "digest": A}
TOO_BIG = b" " * (1_048_576 + 1)


def request():
    return build_request(
        demo.PICK, demo.PickInputs(request="x"), model="qwen3.8:27b", fields=demo.pick_fields()
    )


def unavailable(call) -> ModelUnavailable:
    with pytest.raises(ModelUnavailable) as raised:
        call()
    return raised.value


def test_an_unrelated_bad_entry_does_not_hide_the_model() -> None:
    junk = [{"name": "junk:1"}, "x", {"name": "q:7b", "digest": "b" * 64, "capabilities": 1}]
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": [*junk, PLAIN]}).encode()
        info = OllamaModel(host, timeout=5).model_info("plain")
    assert info == ModelInfo("plain:latest", A, ())


@pytest.mark.parametrize(
    "models",
    [[PLAIN, PLAIN], [{**PLAIN, "capabilities": "thinking"}]],
    ids=["duplicate", "caps-text"],
)
def test_a_bad_entry_for_the_model_is_a_bad_answer(models: list[object]) -> None:
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": models}).encode()
        error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    assert (error.code, str(error)) == ("bad_answer", "model unavailable: bad_answer")


@pytest.mark.parametrize("where", ["tags", "chat", "tags without a length"])
def test_an_answer_over_the_cap_is_too_large(where: str) -> None:
    if where == "tags without a length":
        with raw_server(answer(TOO_BIG, "Content-Type: application/json")) as host:
            error = unavailable(lambda: OllamaModel(host, timeout=5).model_info("plain"))
    else:
        with fake_ollama() as (fake, host):
            fake.body = TOO_BIG
            fake.chat_body = TOO_BIG
            model = OllamaModel(host, timeout=5)
            if where == "tags":
                error = unavailable(lambda: model.model_info("plain"))
            else:
                error = unavailable(lambda: model.chat(request()))
    assert (error.code, error.status, str(error)) == (
        "too_large",
        None,
        "model unavailable: too_large",
    )


def test_an_answer_of_exactly_the_cap_is_read() -> None:
    listing = json.dumps({"models": [PLAIN]}).encode()
    with fake_ollama() as (fake, host):
        fake.body = listing + b" " * (tags.MAX_BODY_BYTES - len(listing))
        info = OllamaModel(host, timeout=5).model_info("plain")
    assert info == ModelInfo("plain:latest", A, ())


class _Recorder:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def open(self, _request: object, timeout: float) -> object:
        self.timeouts.append(timeout)
        raise ConnectionResetError


def test_each_caller_keeps_its_own_timeout() -> None:
    model = OllamaModel("http://127.0.0.1:9", timeout=7)
    recorder = _Recorder()
    model._opener = recorder
    unavailable(lambda: model.model_info("plain"))
    assert recorder.timeouts == [7]
    assert tags.fetch_models.__kwdefaults__ == {"timeout": 3.0}
