import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from string import Template
from typing import Any

from conductor.contracts import Contract
from conductor.llm.prompts import PromptError, load_template

SEED = 7
CONTEXT_TOKENS = 8192
MIN_CONTEXT_TOKENS = 8192
MAX_CONTEXT_TOKENS = 32768
MAX_REPLY_TOKENS = 8192
SCHEMA_INTRO = "Answer with one JSON object that matches this JSON schema:"
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


@dataclass(frozen=True)
class DecisionPoint:
    name: str
    template: str
    inputs: type[Contract]
    output: type[Contract]
    think: bool = True
    max_reply_tokens: int = 1024
    context_tokens: int = CONTEXT_TOKENS


@dataclass(frozen=True)
class ModelRequest:
    point: str
    template: str
    template_sha256: str
    model: str
    system: str
    user: str
    schema: dict[str, Any]
    think: bool
    options: dict[str, int]

    def body(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
            ],
            "format": json.loads(json.dumps(self.schema)),
            "options": dict(self.options),
            "think": self.think,
            "stream": False,
        }


def _is_contract(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, Contract)


def build_request(
    point: DecisionPoint,
    inputs: Contract,
    *,
    model: str,
    fields: Mapping[str, str],
) -> ModelRequest:
    if _NAME.fullmatch(point.name) is None:
        raise PromptError(f"point {point.name}: not a valid name")
    if not _is_contract(point.inputs):
        raise PromptError(f"point {point.name}: inputs must be a Contract")
    if not _is_contract(point.output):
        raise PromptError(f"point {point.name}: output must be a Contract")
    if type(point.think) is not bool:
        raise PromptError(f"point {point.name}: think must be true or false")
    tokens = point.max_reply_tokens
    if type(tokens) is not int or not 1 <= tokens <= MAX_REPLY_TOKENS:
        raise PromptError(f"point {point.name}: max_reply_tokens must be 1 to {MAX_REPLY_TOKENS}")
    context = point.context_tokens
    if type(context) is not int or not MIN_CONTEXT_TOKENS <= context <= MAX_CONTEXT_TOKENS:
        message = (
            f"point {point.name}: context_tokens must be "
            f"{MIN_CONTEXT_TOKENS} to {MAX_CONTEXT_TOKENS}"
        )
        raise PromptError(message)
    if type(inputs) is not point.inputs:
        raise PromptError(f"point {point.name}: inputs do not match")
    template = load_template(point.template)
    if set(fields) != set(template.fields):
        raise PromptError(f"prompt {template.name}: fields do not match")
    if any(not isinstance(value, str) for value in fields.values()):
        raise PromptError(f"prompt {template.name}: field values must be text")
    schema = point.output.model_json_schema()
    filled = Template(template.text).substitute(fields).rstrip()
    system = f"{filled}\n\n{SCHEMA_INTRO}\n{json.dumps(schema, indent=2)}"
    return ModelRequest(
        point=point.name,
        template=template.name,
        template_sha256=template.sha256,
        model=model,
        system=system,
        user=inputs.model_dump_json(indent=2),
        schema=schema,
        think=point.think,
        options={
            "temperature": 0,
            "seed": SEED,
            "num_ctx": context,
            "num_predict": point.max_reply_tokens,
        },
    )
