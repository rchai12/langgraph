from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import Field, JsonValue, field_validator

from conductor.contracts import Contract, Escalation
from conductor.contracts.base import ActionName, JsonObject
from conductor.contracts.plans import MAX_STEPS
from conductor.events import EventLog
from conductor.llm.decide import InvalidModelOutput, decide, escalation_for
from conductor.llm.model import Model, ModelUnavailable
from conductor.llm.points import DecisionPoint
from conductor.routing.route import REQUEST_MESSAGE

RESULTS_MESSAGE = "an answer needs 1 to 8 step results"
BLANK_MESSAGE = "the reply is blank"
ANSWER_REPLY_TOKENS = 6144
ANSWER_CONTEXT_TOKENS = 16384
ANSWER_INPUT_BYTES = 24_000


class StepOutcome(Contract):
    step: int = Field(ge=1, le=MAX_STEPS)
    action: ActionName
    output: JsonObject


class AnswerInputs(Contract):
    request: str = Field(min_length=1, max_length=2000)
    results: tuple[StepOutcome, ...] = Field(min_length=1, max_length=MAX_STEPS)


class AnswerOutput(Contract):
    reply: str = Field(min_length=1, max_length=2000)

    @field_validator("reply")
    @classmethod
    def _not_blank(cls, reply: str) -> str:
        if reply.strip() == "":
            raise ValueError(BLANK_MESSAGE)
        return reply


ANSWER_POINT = DecisionPoint(
    name="answer",
    template="answer.v1",
    inputs=AnswerInputs,
    output=AnswerOutput,
    think=True,
    max_reply_tokens=ANSWER_REPLY_TOKENS,
    context_tokens=ANSWER_CONTEXT_TOKENS,
)


@dataclass(frozen=True)
class Answered:
    reply: str
    decision_id: str


def with_dollars(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [with_dollars(item) for item in value]
    if isinstance(value, dict):
        converted: dict[str, JsonValue] = {}
        for key, item in value.items():
            name, _, suffix = key.rpartition("_")
            if suffix == "cents" and name and type(item) is int and f"{name}_dollars" not in value:
                converted[f"{name}_dollars"] = _dollar_string(item)
            else:
                converted[key] = with_dollars(item)
        return converted
    return value


def _dollar_string(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    amount = abs(cents)
    return f"{sign}{amount // 100}.{amount % 100:02d}"


def answer_request(
    request: str,
    results: Sequence[StepOutcome],
    *,
    model: Model,
    model_name: str,
    log: EventLog,
    run_id: str,
) -> Answered | Escalation:
    if not request.strip() or len(request) > 2000:
        raise ValueError(REQUEST_MESSAGE)
    if len(results) < 1 or len(results) > MAX_STEPS:
        raise ValueError(RESULTS_MESSAGE)
    inputs = AnswerInputs(
        request=request,
        results=tuple(
            item.model_copy(update={"output": cast(JsonObject, with_dollars(item.output))})
            for item in results
        ),
    )
    size = len(inputs.model_dump_json(indent=2).encode("utf-8"))
    if size > ANSWER_INPUT_BYTES:
        return Escalation(
            kind="answer_too_large",
            detail=(
                f"the step results are {size} bytes, more than {ANSWER_INPUT_BYTES}; ask for less"
            ),
            run_id=run_id,
        )
    try:
        decision = decide(
            ANSWER_POINT,
            inputs,
            fields={},
            model=model,
            model_name=model_name,
            log=log,
            run_id=run_id,
            node="answer",
        )
    except (InvalidModelOutput, ModelUnavailable) as error:
        return escalation_for(error, run_id)
    return Answered(decision.output.reply, decision.decision_id)
