from collections.abc import Sequence
from dataclasses import dataclass, replace

from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import ModelRequest

SCRIPTED_INFO = ModelInfo(name="scripted", digest="0" * 64, capabilities=("completion", "thinking"))


class ScriptError(Exception):
    pass


@dataclass(frozen=True)
class ScriptedReply:
    point: str
    reply: ModelReply | ModelUnavailable


class ScriptedModel:
    def __init__(
        self,
        replies: Sequence[ScriptedReply],
        *,
        info: ModelInfo | ModelUnavailable = SCRIPTED_INFO,
    ) -> None:
        self._replies = list(replies)
        self._next = 0
        self._info = info
        self.requests: list[ModelRequest] = []

    @property
    def remaining(self) -> int:
        return len(self._replies) - self._next

    def model_info(self, name: str) -> ModelInfo:
        if isinstance(self._info, ModelUnavailable):
            raise self._info
        if self._info is SCRIPTED_INFO:
            return replace(SCRIPTED_INFO, name=name)
        return self._info

    def chat(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        if self._next >= len(self._replies):
            raise ScriptError(f"no scripted reply left for {request.point}")
        scripted = self._replies[self._next]
        self._next += 1
        if scripted.point != request.point:
            raise ScriptError(
                f"scripted reply {self._next} is for {scripted.point}, not {request.point}"
            )
        if isinstance(scripted.reply, ModelUnavailable):
            raise scripted.reply
        return scripted.reply
