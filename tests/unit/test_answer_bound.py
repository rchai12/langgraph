from pathlib import Path

import pytest

from conductor.contracts import Escalation
from conductor.events import EventLog, RunNotFound
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import (
    ANSWER_INPUT_BYTES,
    Answered,
    AnswerInputs,
    StepOutcome,
    answer_request,
)

RUN = "a" * 32
REQUEST = "Say hi back"


def results(text: str) -> tuple[StepOutcome, ...]:
    return (StepOutcome(step=1, action="demo.echo", output={"text": text}),)


def sized(total: int, char: str = "x") -> tuple[StepOutcome, ...]:
    """Results whose answer message is exactly `total` bytes, padded with `char`."""
    base = len(
        AnswerInputs(request=REQUEST, results=results("")).model_dump_json(indent=2).encode()
    )
    count, rest = divmod(total - base, len(char.encode()))
    made = results(char * count + "x" * rest)
    assert (
        len(AnswerInputs(request=REQUEST, results=made).model_dump_json(indent=2).encode()) == total
    )
    return made


def ask(tmp_path: Path, made: tuple[StepOutcome, ...]) -> tuple[ScriptedModel, object]:
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Hi."}'))])
    found = answer_request(
        REQUEST,
        made,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    return model, found


def test_the_bound_is_24000_bytes() -> None:
    assert ANSWER_INPUT_BYTES == 24_000


def test_results_at_the_bound_are_answered(tmp_path: Path) -> None:
    model, found = ask(tmp_path, sized(24_000))
    assert isinstance(found, Answered)
    assert found.reply == "Hi."
    assert len(model.requests[0].user.encode()) == 24_000


@pytest.mark.parametrize(("total", "char"), [(24_001, "x"), (24_002, "é"), (30_000, "x")])
def test_results_past_the_bound_escalate_without_asking(
    tmp_path: Path, total: int, char: str
) -> None:
    model, found = ask(tmp_path, sized(total, char))
    assert found == Escalation(
        kind="answer_too_large",
        detail=f"the step results are {total} bytes, more than 24000; ask for less",
        run_id=RUN,
    )
    assert model.requests == []
    with pytest.raises(RunNotFound):
        EventLog(tmp_path).read(RUN)
