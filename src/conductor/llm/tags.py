import json
import urllib.error
import urllib.request


class OllamaUnreachable(Exception):
    pass


class OllamaBadAnswer(Exception):
    pass


def fetch_model_names(host: str, *, timeout: float = 3.0) -> list[str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"{host}/api/tags")
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        raise OllamaBadAnswer("unexpected answer") from error
    except OSError as error:
        raise OllamaUnreachable("not reachable") from error
    return _names(body)


def _names(body: bytes) -> list[str]:
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaBadAnswer("unexpected answer") from error
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise OllamaBadAnswer("unexpected answer")
    names: list[str] = []
    for entry in data["models"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise OllamaBadAnswer("unexpected answer")
        names.append(entry["name"])
    return sorted(names)
