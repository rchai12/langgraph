import json
import re
import urllib.error
import urllib.request
from http.client import HTTPException

from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import ModelRequest

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
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
        return _info(self._read("/api/tags"), name)

    def chat(self, request: ModelRequest) -> ModelReply:
        payload = json.dumps(request.body(), ensure_ascii=False).encode("utf-8")
        return _reply(self._read("/api/chat", payload))

    def _read(self, path: str, payload: bytes | None = None) -> bytes:
        headers = {} if payload is None else {"Content-Type": "application/json"}
        outgoing = urllib.request.Request(f"{self._host}{path}", data=payload, headers=headers)
        try:
            with self._opener.open(outgoing, timeout=self._timeout) as response:
                return response.read()
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


def _info(body: bytes, name: str) -> ModelInfo:
    models = _object(body).get("models")
    if not isinstance(models, list):
        raise ModelUnavailable("bad_answer")
    entries = [_entry(item) for item in models]
    found = _find(entries, name)
    if found is None:
        raise ModelUnavailable("not_installed")
    model_name, digest, capabilities = found
    return ModelInfo(model_name, digest, capabilities)


def _entry(item: object) -> tuple[str, str, tuple[str, ...]]:
    if not isinstance(item, dict):
        raise ModelUnavailable("bad_answer")
    name = item.get("name")
    digest = item.get("digest")
    if (
        not isinstance(name, str)
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
    ):
        raise ModelUnavailable("bad_answer")
    return name, digest, _capabilities(item)


def _capabilities(item: dict[str, object]) -> tuple[str, ...]:
    if "capabilities" not in item:
        return ()
    raw = item["capabilities"]
    if not isinstance(raw, list) or any(not isinstance(part, str) for part in raw):
        raise ModelUnavailable("bad_answer")
    return tuple(sorted(raw))


def _find(
    entries: list[tuple[str, str, tuple[str, ...]]], name: str
) -> tuple[str, str, tuple[str, ...]] | None:
    latest = None if ":" in name else f"{name}:latest"
    found: tuple[str, str, tuple[str, ...]] | None = None
    for model_name, digest, capabilities in entries:
        if model_name == name:
            return model_name, digest, capabilities
        if model_name == latest:
            found = (model_name, digest, capabilities)
    return found


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
