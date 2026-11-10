from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import clock
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.points import build_request
from conductor.llm.prompts import PromptError
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import (
    ANSWER_INPUT_BYTES,
    RESULTS_MESSAGE,
    AnswerInputs,
    StepOutcome,
    answer_request,
)
from conductor.planning.plan import plan_fields

RUN = "a" * 32
REQUEST = "Say hi back"


def test_a_late_offset_just_after_midnight_is_the_local_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moment = datetime(2031, 3, 4, 0, 30, tzinfo=timezone(timedelta(hours=14)))
    monkeypatch.setattr(clock, "now", lambda: moment)
    assert clock.today() == moment.astimezone().date()
    assert clock.today() != moment.date()


def test_plan_fields_reads_today_once_and_leap_day_is_tuesday(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def counted() -> date:
        nonlocal calls
        calls += 1
        return date(2028, 2, 29)

    monkeypatch.setattr(clock, "today", counted)
    fields = plan_fields(demo.DOMAIN)
    assert calls == 1
    assert (fields["today"], fields["weekday"]) == ("2028-02-29", "Tuesday")


def test_both_caps_at_8192_are_sent_and_a_missing_context_is_refused() -> None:
    point = replace(demo.PICK, context_tokens=8192, max_reply_tokens=8192)
    sent = build_request(point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields())
    assert (sent.options["num_ctx"], sent.options["num_predict"]) == (8192, 8192)
    with pytest.raises(PromptError) as raised:
        build_request(
            replace(demo.PICK, context_tokens=None),
            demo.PickInputs(request="x"),
            model="m",
            fields=demo.pick_fields(),
        )
    assert str(raised.value) == "point demo_pick: context_tokens must be 8192 to 32768"


def test_no_results_are_refused_and_two_results_together_escalate(tmp_path: Path) -> None:
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Hi."}'))])
    with pytest.raises(ValueError) as raised:
        answer_request(
            REQUEST,
            (),
            model=model,
            model_name="test-model:1b",
            log=EventLog(tmp_path),
            run_id=RUN,
        )
    assert str(raised.value) == RESULTS_MESSAGE
    text = "x" * 12_000
    made = (
        StepOutcome(step=1, action="demo.echo", output={"text": text}),
        StepOutcome(step=2, action="demo.echo", output={"text": text}),
    )
    alone = len(
        AnswerInputs(request=REQUEST, results=(made[0],)).model_dump_json(indent=2).encode()
    )
    both = len(AnswerInputs(request=REQUEST, results=made).model_dump_json(indent=2).encode())
    assert alone < ANSWER_INPUT_BYTES < both
    found = answer_request(
        REQUEST,
        made,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    assert found.kind == "answer_too_large"
    assert found.detail == f"the step results are {both} bytes, more than 24000; ask for less"
    assert model.requests == []
