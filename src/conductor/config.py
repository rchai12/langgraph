import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
OLLAMA_HOST_MESSAGE = "must be an http address on this machine (127.0.0.1, localhost, or ::1)"
MODEL_MESSAGE = "must not be empty"
TIMEOUT_MESSAGE = "must be whole seconds from 1 to 3600"


class SettingsError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONDUCTOR_")

    data_dir: Path = Path("data")
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "qwen3.8:27b"
    model_timeout: str = "300"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "conductor.db"

    @property
    def model_timeout_seconds(self) -> int:
        return int(self.model_timeout)


def get_settings() -> Settings:
    settings = Settings()
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
    if problems:
        raise SettingsError("; ".join(problems))
    return settings
