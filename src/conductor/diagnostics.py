import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from conductor.config import Settings
from conductor.llm import tags

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
        names = tags.fetch_model_names(host)
    except (tags.OllamaUnreachable, tags.OllamaBadAnswer) as error:
        return [
            Check("FAIL", ollama_name, str(error)),
            Check("SKIP", model_name, "needs ollama"),
        ]
    wanted = model if ":" in model else f"{model}:latest"
    if wanted in names:
        return [Check("ok", ollama_name), Check("ok", model_name)]
    return [
        Check("ok", ollama_name),
        Check("FAIL", model_name, f"not pulled (run: ollama pull {model})"),
    ]


def run_checks(settings: Settings) -> list[Check]:
    return [
        check_python(),
        check_data_folder(settings.data_dir),
        *check_ollama(settings.ollama_host, settings.model),
    ]


def summary_line(checks: list[Check]) -> str:
    failed = sum(check.status == "FAIL" for check in checks)
    if failed == 0:
        return "All checks passed."
    if failed == 1:
        return "1 check failed."
    return f"{failed} checks failed."
