import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError as EnvironmentSettingsError

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
WEB_PORT_MESSAGE = "must be a port from 1024 to 65535"
DATA_DIR_MESSAGE = "must be a folder path"
NOT_A_SETTING_MESSAGE = "is not a setting"

_SERVER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class SettingsError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONDUCTOR_", env_nested_delimiter="__", frozen=True
    )

    data_dir: Path = Path("data")
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "qwen3.8:27b"
    model_timeout: str = "300"
    decided_by: str = "owner"
    demo: str = "false"
    mcp_timeout: str = "60"
    web_port: str = "8766"
    mcp: Mapping[str, str] = Field(default_factory=dict, validate_default=True)

    @field_validator("mcp", mode="after")
    @classmethod
    def _read_only(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

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

    @property
    def web_port_number(self) -> int:
        return int(self.web_port)

    def mcp_command(self, name: str) -> tuple[str, ...] | None:
        line = self.mcp.get(name)
        if line is None:
            return None
        return tuple(shlex.split(line))


FIELD_MESSAGES = {
    "data_dir": DATA_DIR_MESSAGE,
    "ollama_host": OLLAMA_HOST_MESSAGE,
    "model": MODEL_MESSAGE,
    "model_timeout": TIMEOUT_MESSAGE,
    "decided_by": DECIDED_BY_MESSAGE,
    "demo": DEMO_MESSAGE,
    "mcp_timeout": MCP_TIMEOUT_MESSAGE,
    "web_port": WEB_PORT_MESSAGE,
    "mcp": MCP_MAPPING_MESSAGE,
}


def validation_problems(error: ValidationError) -> list[str]:
    """One constant line per failing field, from the error locations only."""
    names = {str(item["loc"][0]) for item in error.errors()}
    known = [
        f"CONDUCTOR_{name.upper()}: {FIELD_MESSAGES[name]}"
        for name in FIELD_MESSAGES
        if name in names
    ]
    other = [
        f"CONDUCTOR_{name.upper()}: {NOT_A_SETTING_MESSAGE}"
        for name in sorted(names - set(FIELD_MESSAGES))
    ]
    return known + other


def _bad_number(value: str, pattern: str, limit: int) -> bool:
    return re.fullmatch(pattern, value) is None or int(value) > limit


def _setting_problems(settings: Settings) -> list[str]:
    parsed = urlsplit(settings.ollama_host)
    rows = (
        (
            "CONDUCTOR_OLLAMA_HOST",
            OLLAMA_HOST_MESSAGE,
            parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS,
        ),
        ("CONDUCTOR_MODEL", MODEL_MESSAGE, settings.model.strip() == ""),
        (
            "CONDUCTOR_MODEL_TIMEOUT",
            TIMEOUT_MESSAGE,
            _bad_number(settings.model_timeout, r"^[1-9][0-9]{0,3}$", 3600),
        ),
        (
            "CONDUCTOR_DECIDED_BY",
            DECIDED_BY_MESSAGE,
            re.fullmatch(r"^[a-z][a-z0-9_]{0,31}$", settings.decided_by) is None,
        ),
        ("CONDUCTOR_DEMO", DEMO_MESSAGE, settings.demo not in ("true", "false")),
        (
            "CONDUCTOR_MCP_TIMEOUT",
            MCP_TIMEOUT_MESSAGE,
            _bad_number(settings.mcp_timeout, r"^[1-9][0-9]{0,2}$", 600),
        ),
        (
            "CONDUCTOR_WEB_PORT",
            WEB_PORT_MESSAGE,
            _bad_number(settings.web_port, r"^[1-9][0-9]{3,4}$", 65535),
        ),
    )
    return [f"{label}: {message}" for label, message, bad in rows if bad]


def _mcp_problems(mcp: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    for key in sorted(mcp):
        label = f"CONDUCTOR_MCP__{key.upper()}"
        if _SERVER_NAME.fullmatch(key) is None:
            problems.append(f"{label}: {MCP_NAME_MESSAGE}")
        try:
            parts = shlex.split(mcp[key])
        except ValueError:
            parts = ()
        if not parts:
            problems.append(f"{label}: {MCP_COMMAND_MESSAGE}")
    return problems


def get_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError as error:
        raise SettingsError("; ".join(validation_problems(error))) from None
    except EnvironmentSettingsError:
        raise SettingsError(f"CONDUCTOR_MCP: {MCP_MAPPING_MESSAGE}") from None
    problems = _setting_problems(settings) + _mcp_problems(settings.mcp)
    if problems:
        raise SettingsError("; ".join(problems))
    return settings.model_copy(
        update={
            "data_dir": settings.data_dir.absolute(),
            "ollama_host": settings.ollama_host.rstrip("/"),
        }
    )
