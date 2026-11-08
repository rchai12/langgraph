from collections.abc import Mapping
from dataclasses import dataclass, replace

from pydantic import ValidationError

from conductor import ids
from conductor.contracts import Contract, Escalation, FieldProblem, problems_from
from conductor.events import EventKind, EventLog
from conductor.llm.model import Model, ModelUnavailable
from conductor.llm.points import DecisionPoint, build_request

INVALID_OUTPUT_MESSAGE = "the model's reply does not fit the decision point"
RETRY_HINT = "retry when Ollama answers"


class InvalidModelOutput(Exception):
    def __init__(self, decision_id: str, problems: tuple[FieldProblem, ...]) -> None:
        self.decision_id = decision_id
        self.problems = problems
        super().__init__(INVALID_OUTPUT_MESSAGE)


@dataclass(frozen=True)
class Decision:
    decision_id: str
    output: Contract


def decide(
    point: DecisionPoint,
    inputs: Contract,
    *,
    fields: Mapping[str, str],
    model: Model,
    model_name: str,
    log: EventLog,
    run_id: str,
    node: str | None = None,
) -> Decision:
    request = build_request(point, inputs, model=model_name, fields=fields)
    decision_id = ids.new_id()
    try:
        info = model.model_info(model_name)
    except ModelUnavailable as error:
        _log_unavailable(log, run_id, node, decision_id, point.name, error)
        raise
    think = point.think and "thinking" in info.capabilities
    sent = replace(request, think=think)
    log.append(
        run_id,
        EventKind.MODEL_REQUEST,
        node=node,
        payload={
            "decision_id": decision_id,
            "point": point.name,
            "template": sent.template,
            "template_sha256": sent.template_sha256,
            "model": model_name,
            "model_listed_as": info.name,
            "digest": info.digest,
            "think_requested": point.think,
            "think": sent.think,
            "body": sent.body(),
        },
    )
    try:
        reply = model.chat(sent)
    except ModelUnavailable as error:
        _log_unavailable(log, run_id, node, decision_id, point.name, error)
        raise
    log.append(
        run_id,
        EventKind.MODEL_REPLY,
        node=node,
        payload={
            "decision_id": decision_id,
            "content": reply.content,
            "thinking": reply.thinking,
            "done_reason": reply.done_reason,
            "total_ns": reply.total_ns,
            "load_ns": reply.load_ns,
            "prompt_tokens": reply.prompt_tokens,
            "prompt_ns": reply.prompt_ns,
            "reply_tokens": reply.reply_tokens,
            "reply_ns": reply.reply_ns,
        },
    )
    if reply.done_reason != "stop":
        problems = (FieldProblem(loc="reply", code="cut_off"),)
    else:
        try:
            output = point.output.from_json(reply.content)
        except ValidationError as error:
            problems = problems_from(error)
        else:
            return Decision(decision_id, output)
    log.append(
        run_id,
        EventKind.ERROR,
        node=node,
        payload={
            "decision_id": decision_id,
            "point": point.name,
            "error": "invalid_model_output",
            "problems": [{"loc": problem.loc, "code": problem.code} for problem in problems],
        },
    )
    raise InvalidModelOutput(decision_id, problems)


def escalation_for(error: InvalidModelOutput | ModelUnavailable, run_id: str) -> Escalation:
    if isinstance(error, InvalidModelOutput):
        return Escalation(
            kind="invalid_model_output",
            detail=f"decision {error.decision_id}: {INVALID_OUTPUT_MESSAGE}",
            run_id=run_id,
            problems=error.problems,
        )
    return Escalation(
        kind="model_unavailable",
        detail=f"{error}; {RETRY_HINT}",
        run_id=run_id,
    )


def _log_unavailable(
    log: EventLog,
    run_id: str,
    node: str | None,
    decision_id: str,
    point: str,
    error: ModelUnavailable,
) -> None:
    log.append(
        run_id,
        EventKind.ERROR,
        node=node,
        payload={
            "decision_id": decision_id,
            "point": point,
            "error": "model_unavailable",
            "code": error.code,
            "status": error.status,
        },
    )
