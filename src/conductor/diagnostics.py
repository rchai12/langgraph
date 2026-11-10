import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from conductor import domains
from conductor.config import Settings
from conductor.llm import tags
from conductor.mcp_client.check import ServerCheck, check_servers
from conductor.registry import Registry

MIN_PYTHON = (3, 12)


@dataclass(frozen=True)
class Check:
    status: Literal["ok", "FAIL", "SKIP"]
    name: str
    detail: str = ""

    @property
    def line(self) -> str:
        shown = f"{self.status:<5} {self.name}"
        if self.detail:
            return f"{shown}: {self.detail}"
        return shown


def python_version() -> tuple[int, int, int]:
    version = sys.version_info
    return (version[0], version[1], version[2])


def check_python() -> Check:
    version = python_version()
    name = f"python {version[0]}.{version[1]}.{version[2]}"
    if version >= MIN_PYTHON:
        return Check("ok", name)
    return Check("FAIL", name, "conductor needs Python 3.12 or newer")


def check_data_folder(folder: Path) -> Check:
    name = f"data folder {folder}"
    probe = folder / ".doctor-write-test"
    try:
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return Check("FAIL", name, "not writable")
    return Check("ok", name)


def check_ollama(host: str, model: str) -> list[Check]:
    ollama_name = f"ollama {host}"
    model_name = f"model {model}"
    try:
        listed = tags.fetch_models(host)
    except (tags.OllamaUnreachable, tags.OllamaBadAnswer) as error:
        return [
            Check("FAIL", ollama_name, str(error)),
            Check("SKIP", model_name, "needs ollama"),
        ]
    wanted = model if ":" in model else f"{model}:latest"
    if wanted not in listed:
        return [
            Check("ok", ollama_name),
            Check("FAIL", model_name, f"not pulled (run: ollama pull {model})"),
        ]
    digest = listed[wanted]
    if digest is None:
        return [
            Check("ok", ollama_name),
            Check("FAIL", model_name, "listed without a valid digest"),
        ]
    return [Check("ok", ollama_name), Check("ok", model_name, f"digest {digest[:12]}")]


def run_checks(settings: Settings) -> list[Check]:
    return [
        check_python(),
        check_data_folder(settings.data_dir),
        *check_ollama(settings.ollama_host, settings.model),
        *server_lines(settings),
    ]


def server_lines(settings: Settings) -> list[Check]:
    found = check_servers(Registry(domains.registered(settings)), settings)
    lines: list[Check] = []
    for item in found:
        lines.extend(_server_lines(item))
    return lines


def _server_lines(item: ServerCheck) -> list[Check]:
    name = f"server {item.server}"
    if item.tools is None:
        return [Check("FAIL", name, item.problems[0].message)]
    if item.problems:
        return [Check("FAIL", name, problem.text) for problem in item.problems]
    tools = _count(item.tools, "tool", "tools")
    actions = _count(item.actions, "action", "actions")
    detail = f"{tools}, {actions} checked"
    return [Check("ok", name, detail)]


def _count(count: int, singular: str, plural: str) -> str:
    word = singular if count == 1 else plural
    return f"{count} {word}"


def summary_line(checks: list[Check]) -> str:
    failed = sum(check.status == "FAIL" for check in checks)
    if failed == 0:
        return "All checks passed."
    if failed == 1:
        return "1 check failed."
    return f"{failed} checks failed."
