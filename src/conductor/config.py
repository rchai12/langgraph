import re
import shlex
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
OLLAMA_HOST_MESSAGE = "must be an http address on this machine (127.0.0.1, localhost, or ::1)"
MODEL_MESSAGE = "must not be empty"
TIMEOUT_MESSAGE = "must be whole seconds from 1 to 3600"
DECIDED_BY_MESSAGE = "must be a lowercase name of up to 32 characters"
DEMO_MESSAGE = "must be true or false"
MCP_TIMEOUT_MESSAGE = "must be whole seconds from 1 to 600"
MCP_COMMAND_MESSAGE = "must be a command line"
MCP_NAME_MESSAGE = "not a server name"
MCP_MAPPING_MESSAGE = "must map server names to command lines"

_SERVER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class SettingsError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONDUCTOR_", env_nested_delimiter="__")

    data_dir: Path = Path("data")
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "qwen3.8:27b"
    model_timeout: str = "300"
    decided_by: str = "owner"
    demo: str = "false"
    mcp_timeout: str = "60"
    mcp: dict[str, str] = {}

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "conductor.db"

    @property
    def checkpoints_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def demo_on(self) -> bool:
        return self.demo == "true"

    @property
    def model_timeout_seconds(self) -> int:
        return int(self.model_timeout)

    @property
    def mcp_timeout_seconds(self) -> int:
        return int(self.mcp_timeout)

    def mcp_command(self, name: str) -> tuple[str, ...] | None:
        line = self.mcp.get(name)
        if line is None:
            return None
        return tuple(shlex.split(line))


def get_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError:
        raise SettingsError(f"CONDUCTOR_MCP: {MCP_MAPPING_MESSAGE}") from None
    settings.data_dir = settings.data_dir.absolute()
    problems: list[str] = []
    parsed = urlsplit(settings.ollama_host)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        problems.append(f"CONDUCTOR_OLLAMA_HOST: {OLLAMA_HOST_MESSAGE}")
    else:
        settings.ollama_host = settings.ollama_host.rstrip("/")
    if settings.model.strip() == "":
        problems.append(f"CONDUCTOR_MODEL: {MODEL_MESSAGE}")
    timeout = settings.model_timeout
    if re.fullmatch(r"^[1-9][0-9]{0,3}$", timeout) is None or int(timeout) > 3600:
        problems.append(f"CONDUCTOR_MODEL_TIMEOUT: {TIMEOUT_MESSAGE}")
    if re.fullmatch(r"^[a-z][a-z0-9_]{0,31}$", settings.decided_by) is None:
        problems.append(f"CONDUCTOR_DECIDED_BY: {DECIDED_BY_MESSAGE}")
    if settings.demo not in ("true", "false"):
        problems.append(f"CONDUCTOR_DEMO: {DEMO_MESSAGE}")
    if (
        re.fullmatch(r"^[1-9][0-9]{0,2}$", settings.mcp_timeout) is None
        or int(settings.mcp_timeout) > 600
    ):
        problems.append(f"CONDUCTOR_MCP_TIMEOUT: {MCP_TIMEOUT_MESSAGE}")
    for key in sorted(settings.mcp):
        label = f"CONDUCTOR_MCP__{key.upper()}"
        if _SERVER_NAME.fullmatch(key) is None:
            problems.append(f"{label}: {MCP_NAME_MESSAGE}")
        try:
            parts = shlex.split(settings.mcp[key])
        except ValueError:
            parts = ()
        if not parts:
            problems.append(f"{label}: {MCP_COMMAND_MESSAGE}")
    if problems:
        raise SettingsError("; ".join(problems))
    return settings
