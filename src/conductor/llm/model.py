from dataclasses import dataclass
from typing import Literal, Protocol

from conductor.llm.points import ModelRequest

UnavailableCode = Literal["unreachable", "timeout", "http_error", "bad_answer", "not_installed"]


class ModelUnavailable(Exception):
    def __init__(self, code: UnavailableCode, status: int | None = None) -> None:
        self.code = code
        self.status = status
        if code == "http_error":
            text = f"model unavailable: http_error {status}"
        else:
            text = f"model unavailable: {code}"
        super().__init__(text)


@dataclass(frozen=True)
class ModelInfo:
    name: str
    digest: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ModelReply:
    content: str
    thinking: str = ""
    done_reason: str = "stop"
    total_ns: int = 0
    load_ns: int = 0
    prompt_tokens: int = 0
    prompt_ns: int = 0
    reply_tokens: int = 0
    reply_ns: int = 0


class Model(Protocol):
    def model_info(self, name: str) -> ModelInfo: ...

    def chat(self, request: ModelRequest) -> ModelReply: ...
