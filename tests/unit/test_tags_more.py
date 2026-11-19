import json

import pytest

from conductor.llm.tags import (
    MAX_BODY_BYTES,
    Listed,
    OllamaBadAnswer,
    TooLarge,
    fetch_model_names,
    fetch_models,
    parse_tags,
)
from tests.support import fake_ollama

A = "a" * 64


def test_a_failed_and_an_oversized_listing_are_refused() -> None:
    with fake_ollama() as (fake, host):
        fake.status = 500
        with pytest.raises(OllamaBadAnswer) as failed:
            fetch_models(host)
    assert (type(failed.value), str(failed.value)) == (OllamaBadAnswer, "unexpected answer")
    with fake_ollama() as (fake, host):
        fake.body = b" " * (MAX_BODY_BYTES + 1)
        with pytest.raises(TooLarge) as huge:
            fetch_models(host)
    assert str(huge.value) == "answer too large"


def test_names_skip_a_nameless_entry_and_list_a_duplicate_once() -> None:
    listed = [
        "x",
        {"name": "zeta:1", "digest": A},
        {"name": "alpha:1", "digest": A},
        {"name": "alpha:1", "digest": "b" * 64},
    ]
    with fake_ollama() as (fake, host):
        fake.body = json.dumps({"models": listed}).encode()
        assert fetch_model_names(host) == ["alpha:1", "zeta:1"]


def test_an_empty_name_is_skipped_and_repeated_capabilities_stay() -> None:
    body = json.dumps(
        {
            "models": [
                {"name": "", "digest": A},
                {"name": "m:1", "digest": A, "capabilities": ["b", "a", "b"]},
            ]
        }
    ).encode()
    assert parse_tags(body) == {"m:1": Listed("m:1", A, ("a", "b", "b"), None)}
    kept = json.dumps(
        {"models": [{"name": "m:1", "digest": "A" * 64, "capabilities": ["tools", "tools"]}]}
    ).encode()
    assert parse_tags(kept) == {"m:1": Listed("m:1", None, ("tools", "tools"), "no_digest")}


def test_an_answer_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(OllamaBadAnswer) as raised:
        parse_tags(b"[]")
    assert (type(raised.value), str(raised.value)) == (OllamaBadAnswer, "unexpected answer")
