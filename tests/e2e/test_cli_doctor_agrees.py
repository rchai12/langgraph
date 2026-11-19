import json

import pytest

from conductor.llm.model import ModelUnavailable
from conductor.llm.ollama import OllamaModel
from tests.raw_http import answer, raw_server
from tests.support import fake_ollama, run

A = "a" * 64
QWEN = {"name": "qwen3.8:27b", "digest": A}
JUNK = [{"name": "junk:1"}, "x", {"model": "m"}]


def run_outcome(host: str, model: str) -> str:
    try:
        OllamaModel(host, timeout=5).model_info(model)
    except ModelUnavailable as error:
        return error.code
    return "ok"


@pytest.mark.parametrize(
    ("model", "models", "line", "outcome"),
    [
        ("qwen3.8:27b", [*JUNK, QWEN], "ok    model qwen3.8:27b: digest aaaaaaaaaaaa", "ok"),
        (
            "qwen3.8:27b",
            [{"name": "qwen3.8:27b", "digest": "A" * 64}],
            "FAIL  model qwen3.8:27b: listed without a valid digest",
            "bad_answer",
        ),
        (
            "qwen3.8:27b",
            [{**QWEN, "capabilities": ["thinking", 2]}],
            "FAIL  model qwen3.8:27b: listed with invalid capabilities",
            "bad_answer",
        ),
        (
            "qwen3.8:27b",
            [QWEN, {**QWEN, "digest": "b" * 64}],
            "FAIL  model qwen3.8:27b: listed more than once",
            "bad_answer",
        ),
        ("plain", [{"name": "plain", "digest": A}], "ok    model plain: digest aaaaaaaaaaaa", "ok"),
    ],
    ids=["junk", "no-digest", "bad-capabilities", "duplicate", "untagged"],
)
def test_doctor_and_a_run_agree_on_the_model(
    monkeypatch: pytest.MonkeyPatch, model: str, models: list[object], line: str, outcome: str
) -> None:
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": models}).encode()
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("CONDUCTOR_MODEL", model)
        result = run("doctor")
        found = run_outcome(host, model)
    assert (result.stdout.splitlines()[3], found) == (line, outcome)
    assert result.exit_code == (0 if outcome == "ok" else 1)


def test_doctor_names_an_answer_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_ollama() as (fake, host):
        fake.body = b" " * (1_048_576 + 1)
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"FAIL  ollama {host}: answer too large",
        "SKIP  model qwen3.8:27b: needs ollama",
        "1 check failed.",
    ]
    assert result.exit_code == 1


def test_doctor_survives_a_broken_chunked_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = answer(b'5\r\n{"mod', "Transfer-Encoding: chunked")
    with raw_server(sent) as host:
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"FAIL  ollama {host}: unexpected answer",
        "SKIP  model qwen3.8:27b: needs ollama",
        "1 check failed.",
    ]
    assert result.exit_code == 1
