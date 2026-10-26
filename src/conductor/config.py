from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
OLLAMA_HOST_MESSAGE = "must be an http address on this machine (127.0.0.1, localhost, or ::1)"
MODEL_MESSAGE = "must not be empty"


class SettingsError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONDUCTOR_")

    data_dir: Path = Path("data")
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "qwen3.8:27b"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"


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
    if problems:
        raise SettingsError("; ".join(problems))
    return settings
