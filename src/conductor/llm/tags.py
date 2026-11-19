import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPException
from typing import Literal, Protocol

_DIGEST = re.compile(r"^[0-9a-f]{64}$")

MAX_BODY_BYTES = 1_048_576
UNEXPECTED_MESSAGE = "unexpected answer"
UNREACHABLE_MESSAGE = "not reachable"
TOO_LARGE_MESSAGE = "answer too large"

Problem = Literal["no_digest", "bad_capabilities", "duplicate"]


class OllamaUnreachable(Exception):
    pass


class OllamaBadAnswer(Exception):
    pass


class TooLarge(OllamaBadAnswer):
    def __init__(self) -> None:
        super().__init__(TOO_LARGE_MESSAGE)


@dataclass(frozen=True)
class Listed:
    name: str
    digest: str | None
    capabilities: tuple[str, ...]
    problem: Problem | None


class _Body(Protocol):
    def read(self, amount: int) -> bytes: ...


def fetch_model_names(host: str, *, timeout: float = 3.0) -> list[str]:
    return sorted(fetch_models(host, timeout=timeout))


def fetch_models(host: str, *, timeout: float = 3.0) -> dict[str, Listed]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"{host}/api/tags")
    try:
        with opener.open(request, timeout=timeout) as response:
            body = read_capped(response)
    except urllib.error.HTTPError as error:
        raise OllamaBadAnswer(UNEXPECTED_MESSAGE) from error
    except HTTPException as error:
        raise OllamaBadAnswer(UNEXPECTED_MESSAGE) from error
    except OSError as error:
        raise OllamaUnreachable(UNREACHABLE_MESSAGE) from error
    return parse_tags(body)


def parse_tags(body: bytes) -> dict[str, Listed]:
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaBadAnswer(UNEXPECTED_MESSAGE) from error
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise OllamaBadAnswer(UNEXPECTED_MESSAGE)
    listed: dict[str, Listed] = {}
    for entry in data["models"]:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or name == "":
            continue
        if name in listed:
            listed[name] = Listed(name, None, (), "duplicate")
            continue
        listed[name] = _one(name, entry)
    return listed


def find_model(listed: dict[str, Listed], name: str) -> Listed | None:
    found = listed.get(name)
    if found is not None:
        return found
    if ":" not in name:
        return listed.get(f"{name}:latest")
    return None


def read_capped(response: _Body, limit: int = MAX_BODY_BYTES) -> bytes:
    body = response.read(limit + 1)
    if len(body) > limit:
        raise TooLarge()
    return body


def _capabilities(entry: dict[str, object]) -> tuple[str, ...] | None:
    if "capabilities" not in entry:
        return ()
    raw = entry["capabilities"]
    if not isinstance(raw, list) or any(not isinstance(part, str) for part in raw):
        return None
    return tuple(sorted(raw))


def _one(name: str, entry: dict[str, object]) -> Listed:
    digest = entry.get("digest")
    capabilities = _capabilities(entry)
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        return Listed(name, None, () if capabilities is None else capabilities, "no_digest")
    if capabilities is None:
        return Listed(name, digest, (), "bad_capabilities")
    return Listed(name, digest, capabilities, None)
