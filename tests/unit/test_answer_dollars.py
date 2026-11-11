import copy
from pathlib import Path

import pytest

from conductor.contracts import Escalation
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import (
    ANSWER_INPUT_BYTES,
    Answered,
    AnswerInputs,
    StepOutcome,
    answer_request,
    with_dollars,
)

RUN = "a" * 32
REQUEST = "What is our net worth?"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ({"amount_cents": -4210}, {"amount_dollars": "-42.10"}),
        ({"amount_cents": 0}, {"amount_dollars": "0.00"}),
        ({"amount_cents": 5}, {"amount_dollars": "0.05"}),
        ({"amount_cents": -5}, {"amount_dollars": "-0.05"}),
        ({"net_worth_cents": 123456}, {"net_worth_dollars": "1234.56"}),
        ({"big_cents": 100000000000001}, {"big_dollars": "1000000000000.01"}),
        (
            {"lines": [{"spent_cents": 4210, "label": "Groceries"}], "summary": {"net_cents": -1}},
            {
                "lines": [{"spent_dollars": "42.10", "label": "Groceries"}],
                "summary": {"net_dollars": "-0.01"},
            },
        ),
        ([{"bills_cents": -1299}, 7, "x"], [{"bills_dollars": "-12.99"}, 7, "x"]),
        ({"flag_cents": True}, {"flag_cents": True}),
        ({"rate_cents": 1.5}, {"rate_cents": 1.5}),
        ({"text_cents": "4210"}, {"text_cents": "4210"}),
        ({"none_cents": None}, {"none_cents": None}),
        ({"cents": 4210, "_cents": 4210}, {"cents": 4210, "_cents": 4210}),
        ({"amount_cents_total": 4210}, {"amount_cents_total": 4210}),
        (
            {"amount_cents": 4210, "amount_dollars": "set"},
            {"amount_cents": 4210, "amount_dollars": "set"},
        ),
        (4210, 4210),
    ],
    ids=[
        "negative",
        "zero",
        "five-cents",
        "minus-five-cents",
        "thousands",
        "large",
        "nested",
        "list",
        "bool",
        "float",
        "text",
        "null",
        "no-prefix",
        "inner-cents",
        "dollars-already",
        "scalar",
    ],
)
def test_cents_become_dollars(given: object, expected: object) -> None:
    assert with_dollars(given) == expected


def test_the_keys_keep_their_order_and_the_input_is_unchanged() -> None:
    given = {"a": 1, "x_cents": 250, "b": [{"y_cents": -3, "c": 2}]}
    kept = copy.deepcopy(given)
    found = with_dollars(given)
    assert list(found) == ["a", "x_dollars", "b"]
    assert list(found["b"][0]) == ["y_dollars", "c"]
    assert given == kept


def ask(tmp_path: Path, output: dict) -> tuple[ScriptedModel, object]:
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Done."}'))])
    found = answer_request(
        REQUEST,
        (StepOutcome(step=1, action="finance.get_balances", output=output),),
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path),
        run_id=RUN,
    )
    return model, found


def test_the_answer_reads_dollars(tmp_path: Path) -> None:
    output = {
        "accounts": [{"name": "Sample Checking", "balance_cents": -4210}],
        "net_worth_cents": 123456,
    }
    model, found = ask(tmp_path, output)
    sent = model.requests[0].user
    assert isinstance(found, Answered)
    assert '"balance_dollars": "-42.10"' in sent
    assert '"net_worth_dollars": "1234.56"' in sent
    assert "_cents" not in sent


def size(output: dict) -> int:
    inputs = AnswerInputs(
        request=REQUEST,
        results=(StepOutcome(step=1, action="finance.get_balances", output=output),),
    )
    return len(inputs.model_dump_json(indent=2).encode())


def test_the_bound_is_measured_on_the_dollars(tmp_path: Path) -> None:
    # "a_cents": 1000 becomes "a_dollars": "10.00", five bytes longer.
    pad = "x" * (ANSWER_INPUT_BYTES + 1 - size({"text": "", "a_dollars": "10.00"}))
    assert size({"text": pad, "a_dollars": "10.00"}) == ANSWER_INPUT_BYTES + 1
    assert size({"text": pad, "a_cents": 1000}) == ANSWER_INPUT_BYTES - 4
    model, found = ask(tmp_path, {"text": pad, "a_cents": 1000})
    assert found == Escalation(
        kind="answer_too_large",
        detail="the step results are 24001 bytes, more than 24000; ask for less",
        run_id=RUN,
    )
    assert model.requests == []
