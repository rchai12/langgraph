from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.contracts import Escalation, FieldProblem
from conductor.events import EventLog
from conductor.llm.decide import InvalidModelOutput, escalation_for
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError
from conductor.planning.answer import RESULTS_MESSAGE, Answered, StepOutcome, answer_request
from conductor.routing.route import REQUEST_MESSAGE

RUN = "a" * 32
DECISION = "d" * 32
MODEL = "test-model:1b"
ONE = (StepOutcome(step=1, action="demo.echo", output={"text": "hi"}),)


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 9, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: DECISION)


def answer(request: str, results, model, log: EventLog):
    return answer_request(request, results, model=model, model_name=MODEL, log=log, run_id=RUN)


def test_a_full_request_and_eight_results_reach_the_model_and_the_request_is_first(
    tmp_path: Path,
) -> None:
    results = tuple(
        StepOutcome(step=number, action="demo.echo", output={"text": "hi"})
        for number in range(1, 9)
    )
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Done."}'))])
    found = answer("x" * 2000, results, model, EventLog(tmp_path))
    assert found == Answered("Done.", DECISION)
    assert '"request": "' + "x" * 2000 + '"' in model.requests[0].user
    with pytest.raises(ValueError) as raised:
        answer("y" * 2001, (), ScriptedModel([]), EventLog(tmp_path))
    assert str(raised.value) == REQUEST_MESSAGE
    assert str(raised.value) != RESULTS_MESSAGE


def test_an_invalid_reply_is_the_escalation_and_a_script_error_passes(tmp_path: Path) -> None:
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": 1}'))])
    found = answer("Echo hi", ONE, model, EventLog(tmp_path))
    expected = escalation_for(
        InvalidModelOutput(DECISION, (FieldProblem(loc="reply", code="string_type"),)),
        RUN,
    )
    assert found == expected
    with pytest.raises(ScriptError):
        answer("Echo hi", ONE, ScriptedModel([]), EventLog(tmp_path))


def test_a_reply_of_2000_characters_is_kept_and_2001_is_too_long(tmp_path: Path) -> None:
    kept = "x" + " " * 1999
    model = ScriptedModel(
        [ScriptedReply("answer", ModelReply(content='{"reply": "' + kept + '"}'))]
    )
    assert answer("Echo hi", ONE, model, EventLog(tmp_path)) == Answered(kept, DECISION)
    longer = ScriptedModel(
        [ScriptedReply("answer", ModelReply(content='{"reply": "' + "y" * 2001 + '"}'))]
    )
    found = answer("Echo hi", ONE, longer, EventLog(tmp_path))
    assert isinstance(found, Escalation)
    assert found.problems == (FieldProblem(loc="reply", code="string_too_long"),)
