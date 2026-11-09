import json
import re
import urllib.error
import urllib.request

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class OllamaUnreachable(Exception):
    pass


class OllamaBadAnswer(Exception):
    pass


def fetch_model_names(host: str, *, timeout: float = 3.0) -> list[str]:
    return sorted(fetch_models(host, timeout=timeout))


def fetch_models(host: str, *, timeout: float = 3.0) -> dict[str, str | None]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"{host}/api/tags")
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        raise OllamaBadAnswer("unexpected answer") from error
    except OSError as error:
        raise OllamaUnreachable("not reachable") from error
    return _models(body)


def _models(body: bytes) -> dict[str, str | None]:
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaBadAnswer("unexpected answer") from error
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise OllamaBadAnswer("unexpected answer")
    listed: dict[str, str | None] = {}
    for entry in data["models"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise OllamaBadAnswer("unexpected answer")
        digest = entry.get("digest")
        if isinstance(digest, str) and _DIGEST.fullmatch(digest):
            listed[entry["name"]] = digest
        else:
            listed[entry["name"]] = None
    return listed
