from dataclasses import replace

import pytest

from conductor.domains import demo
from conductor.llm.points import (
    CONTEXT_TOKENS,
    MAX_CONTEXT_TOKENS,
    MIN_CONTEXT_TOKENS,
    build_request,
)
from conductor.llm.prompts import PromptError
from conductor.planning.answer import (
    ANSWER_CONTEXT_TOKENS,
    ANSWER_POINT,
    ANSWER_REPLY_TOKENS,
    AnswerInputs,
    StepOutcome,
)


def pick(point=demo.PICK):
    return build_request(point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields())


def test_a_point_keeps_the_default_context() -> None:
    assert (demo.PICK.context_tokens, CONTEXT_TOKENS) == (8192, 8192)
    assert pick().options["num_ctx"] == 8192


def test_the_answer_point_has_a_larger_context() -> None:
    assert (ANSWER_CONTEXT_TOKENS, ANSWER_REPLY_TOKENS) == (16384, 6144)
    results = (StepOutcome(step=1, action="demo.echo", output={"text": "hi"}),)
    request = build_request(
        ANSWER_POINT, AnswerInputs(request="Say hi", results=results), model="m", fields={}
    )
    assert request.options == {
        "temperature": 0,
        "seed": 7,
        "num_ctx": 16384,
        "num_predict": 6144,
    }


@pytest.mark.parametrize("tokens", [MIN_CONTEXT_TOKENS, 16384, MAX_CONTEXT_TOKENS])
def test_a_context_in_range_is_sent(tokens: int) -> None:
    assert pick(replace(demo.PICK, context_tokens=tokens)).options["num_ctx"] == tokens


@pytest.mark.parametrize("tokens", [8191, 32769, 0, True, "16384", 16384.0])
def test_a_context_out_of_range_is_refused(tokens: object) -> None:
    with pytest.raises(PromptError) as raised:
        pick(replace(demo.PICK, context_tokens=tokens))
    assert str(raised.value) == "point demo_pick: context_tokens must be 8192 to 32768"


def test_the_reply_cap_is_checked_before_the_context() -> None:
    with pytest.raises(PromptError) as raised:
        pick(replace(demo.PICK, max_reply_tokens=0, context_tokens=0))
    assert str(raised.value) == "point demo_pick: max_reply_tokens must be 1 to 8192"
