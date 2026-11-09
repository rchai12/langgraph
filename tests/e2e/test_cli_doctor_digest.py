import json
from pathlib import Path

import pytest

from conductor import diagnostics
from tests.support import fake_ollama, run


@pytest.fixture(autouse=True)
def python_3_12_13(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "qwen3.8:27b"},
        {"name": "qwen3.8:27b", "digest": "sha256:" + "a" * 64},
    ],
)
def test_a_model_listed_without_a_valid_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entry: dict[str, str]
) -> None:
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": [entry]}).encode()
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"ok    ollama {host}",
        "FAIL  model qwen3.8:27b: listed without a valid digest",
        "1 check failed.",
    ]
    assert result.exit_code == 1
