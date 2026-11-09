import json

import pytest

from conductor.llm.tags import fetch_models
from tests.support import fake_ollama, run


def test_a_bad_digest_is_missing_and_a_latest_tag_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with fake_ollama() as (fake, host):
        fake.body = json.dumps(
            {
                "models": [
                    {"name": "plain:latest"},
                    {"name": "numbered:latest", "digest": 1},
                    {"name": "upper:latest", "digest": "A" * 64},
                ]
            }
        ).encode()
        found = fetch_models(host)
    assert found == {"plain:latest": None, "numbered:latest": None, "upper:latest": None}
    digest = "cd" * 32
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": [{"name": "coder:latest", "digest": digest}]}).encode()
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("CONDUCTOR_MODEL", "coder")
        result = run("doctor")
    assert f"ok    model coder: digest {digest[:12]}" in result.stdout.splitlines()
    assert result.exit_code == 0
