from pathlib import Path

import pytest

from conductor.config import SettingsError, get_settings

HOST_REFUSED = (
    "CONDUCTOR_OLLAMA_HOST: must be an http address on this machine (127.0.0.1, localhost, or ::1)"
)


def test_the_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CONDUCTOR_DATA_DIR")
    monkeypatch.delenv("CONDUCTOR_OLLAMA_HOST")
    settings = get_settings()
    assert settings.data_dir == tmp_path / "data"
    assert settings.runs_dir == tmp_path / "data" / "runs"
    assert settings.ollama_host == "http://127.0.0.1:11434"
    assert settings.model == "qwen3.8:27b"


def test_a_relative_data_folder_is_made_absolute_without_resolving_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", "agent/../data")
    monkeypatch.setenv("CONDUCTOR_MODEL", "qwen3-coder:30b")
    settings = get_settings()
    assert settings.data_dir == tmp_path / "agent" / ".." / "data"
    assert settings.model == "qwen3-coder:30b"


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://[::1]:11434/", "http://[::1]:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
    ],
)
def test_a_host_on_this_machine_is_kept_without_a_trailing_slash(
    monkeypatch: pytest.MonkeyPatch, given: str, kept: str
) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", given)
    assert get_settings().ollama_host == kept


@pytest.mark.parametrize(
    "host",
    [
        "http://10.0.0.5:11434",
        "https://127.0.0.1:11434",
        "http://localhost.example.com:11434",
        "http://127.0.0.1@example.com:11434",
        "127.0.0.1:11434",
    ],
)
def test_a_host_elsewhere_is_refused(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == HOST_REFUSED


def test_every_problem_is_named_in_field_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL", "   ")
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://192.168.1.20:11434")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == f"{HOST_REFUSED}; CONDUCTOR_MODEL: must not be empty"
