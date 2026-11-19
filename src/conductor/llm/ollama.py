import json
import urllib.error
import urllib.request
from http.client import HTTPException
from typing import cast

from conductor.llm import tags
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import ModelRequest
from conductor.llm.tags import TooLarge

_COUNTS = (
    ("total_duration", "total_ns"),
    ("load_duration", "load_ns"),
    ("prompt_eval_count", "prompt_tokens"),
    ("prompt_eval_duration", "prompt_ns"),
    ("eval_count", "reply_tokens"),
    ("eval_duration", "reply_ns"),
)


class OllamaModel:
    def __init__(self, host: str, *, timeout: float) -> None:
        self._host = host
        self._timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def model_info(self, name: str) -> ModelInfo:
        try:
            listed = tags.parse_tags(self._read("/api/tags"))
        except tags.OllamaBadAnswer:
            raise ModelUnavailable("bad_answer") from None
        found = tags.find_model(listed, name)
        if found is None:
            raise ModelUnavailable("not_installed")
        if found.problem is not None:
            raise ModelUnavailable("bad_answer")
        return ModelInfo(found.name, cast(str, found.digest), found.capabilities)

    def chat(self, request: ModelRequest) -> ModelReply:
        payload = json.dumps(request.body(), ensure_ascii=False).encode("utf-8")
        return _reply(self._read("/api/chat", payload))

    def _read(self, path: str, payload: bytes | None = None) -> bytes:
        headers = {} if payload is None else {"Content-Type": "application/json"}
        outgoing = urllib.request.Request(f"{self._host}{path}", data=payload, headers=headers)
        try:
            with self._opener.open(outgoing, timeout=self._timeout) as response:
                return tags.read_capped(response)
        except TooLarge:
            raise ModelUnavailable("too_large") from None
        except urllib.error.HTTPError as error:
            if path == "/api/chat" and error.code == 404:
                raise ModelUnavailable("not_installed") from None
            raise ModelUnavailable("http_error", error.code) from None
        except TimeoutError:
            raise ModelUnavailable("timeout") from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise ModelUnavailable("timeout") from None
            raise ModelUnavailable("unreachable") from None
        except OSError:
            raise ModelUnavailable("unreachable") from None
        except HTTPException:
            raise ModelUnavailable("bad_answer") from None


def _object(body: bytes) -> dict[str, object]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ModelUnavailable("bad_answer") from None
    if not isinstance(data, dict):
        raise ModelUnavailable("bad_answer")
    return data


def _reply(body: bytes) -> ModelReply:
    data = _object(body)
    if data.get("done") is not True:
        raise ModelUnavailable("bad_answer")
    reason = data.get("done_reason")
    if not isinstance(reason, str):
        raise ModelUnavailable("bad_answer")
    message = data.get("message")
    if not isinstance(message, dict):
        raise ModelUnavailable("bad_answer")
    content = message.get("content")
    if not isinstance(content, str):
        raise ModelUnavailable("bad_answer")
    return ModelReply(
        content=content,
        thinking=_thinking(message),
        done_reason=reason,
        **_counts(data),
    )


def _thinking(message: dict[str, object]) -> str:
    if "thinking" not in message or message["thinking"] is None:
        return ""
    thinking = message["thinking"]
    if not isinstance(thinking, str):
        raise ModelUnavailable("bad_answer")
    return thinking


def _counts(data: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source, target in _COUNTS:
        if source not in data:
            counts[target] = 0
            continue
        value = data[source]
        if type(value) is not int or value < 0:
            raise ModelUnavailable("bad_answer")
        counts[target] = value
    return counts
