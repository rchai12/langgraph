from pathlib import Path

import pytest
from pydantic import ValidationError

from conductor import config
from conductor.config import Settings, SettingsError, get_settings

MCP_REFUSED = "CONDUCTOR_MCP: must map server names to command lines"
MESSAGES = {
    "data_dir": "must be a folder path",
    "ollama_host": "must be an http address on this machine (127.0.0.1, localhost, or ::1)",
    "model": "must not be empty",
    "model_timeout": "must be whole seconds from 1 to 3600",
    "decided_by": "must be a lowercase name of up to 32 characters",
    "demo": "must be true or false",
    "mcp_timeout": "must be whole seconds from 1 to 600",
    "web_port": "must be a port from 1024 to 65535",
    "mcp": "must map server names to command lines",
}
NEW_VALUES = {
    "data_dir": Path("/elsewhere"),
    "ollama_host": "http://127.0.0.1:1",
    "model": "other:1b",
    "model_timeout": "5",
    "decided_by": "someone",
    "demo": "true",
    "mcp_timeout": "5",
    "web_port": "9999",
    "mcp": {"bank": "bank serve"},
}


def problems_of(**values: object) -> list[str]:
    with pytest.raises(ValidationError) as raised:
        Settings(**values)
    return config.validation_problems(raised.value)


def refused(monkeypatch: pytest.MonkeyPatch, **env: str) -> str:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert type(raised.value) is SettingsError
    assert (raised.value.__cause__, raised.value.__suppress_context__) == (None, True)
    return str(raised.value)


@pytest.mark.parametrize("field", list(NEW_VALUES))
def test_a_loaded_setting_cannot_be_reassigned(field: str) -> None:
    settings = get_settings()
    before = getattr(settings, field)
    with pytest.raises(ValidationError) as raised:
        setattr(settings, field, NEW_VALUES[field])
    assert [error["type"] for error in raised.value.errors()] == ["frozen_instance"]
    assert getattr(settings, field) == before


@pytest.mark.parametrize(
    "env", [{}, {"CONDUCTOR_MCP__LEDGER": "ledger serve"}], ids=["default", "one server"]
)
def test_the_server_mapping_is_read_only(monkeypatch: pytest.MonkeyPatch, env: dict) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = get_settings()
    before = dict(settings.mcp)
    with pytest.raises(TypeError):
        settings.mcp["bank"] = "bank serve"
    with pytest.raises(TypeError):
        del settings.mcp["ledger"]
    assert (dict(settings.mcp), settings.mcp == before) == (before, True)


@pytest.mark.parametrize(
    ("env", "servers"),
    [
        (
            {"CONDUCTOR_MCP": '{"bank": "bank serve"}', "CONDUCTOR_MCP__LEDGER": "ledger serve"},
            {"bank": "bank serve", "ledger": "ledger serve"},
        ),
        ({"CONDUCTOR_MCP": "null"}, {}),
    ],
    ids=["json and one name merge", "null is none"],
)
def test_the_server_mapping_is_read_as_today(
    monkeypatch: pytest.MonkeyPatch, env: dict, servers: dict
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert dict(get_settings().mcp) == servers


def test_settings_are_normalised_before_they_are_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", "agent/../data")
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://[::1]:11434/")
    settings = get_settings()
    assert (settings.data_dir, settings.ollama_host) == (
        tmp_path / "agent" / ".." / "data",
        "http://[::1]:11434",
    )
    with pytest.raises(ValidationError):
        settings.ollama_host = "http://[::1]:11434/"


@pytest.mark.parametrize("value", ["notjson", '{"bank": ', "[1"], ids=["word", "cut", "list"])
def test_mcp_text_that_is_not_json_names_the_mcp_setting(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    assert refused(monkeypatch, CONDUCTOR_MCP=value) == MCP_REFUSED


@pytest.mark.parametrize(
    "env",
    [
        {"CONDUCTOR_MCP": "[1]"},
        {"CONDUCTOR_MCP": '"bank serve"'},
        {"CONDUCTOR_MCP__LEDGER__BIN": "ledger"},
    ],
    ids=["list", "text", "nested name"],
)
def test_an_mcp_value_of_the_wrong_shape_names_the_mcp_setting(
    monkeypatch: pytest.MonkeyPatch, env: dict
) -> None:
    assert refused(monkeypatch, **env) == MCP_REFUSED


@pytest.mark.parametrize("field", list(MESSAGES))
def test_a_validation_error_names_the_field_that_failed(field: str) -> None:
    assert problems_of(**{field: 1}) == [f"CONDUCTOR_{field.upper()}: {MESSAGES[field]}"]


def test_problems_follow_field_order_once_each() -> None:
    found = problems_of(mcp={"bank": 1, "ledger": 2}, web_port=7, model=3)
    assert found == [
        "CONDUCTOR_MODEL: must not be empty",
        "CONDUCTOR_WEB_PORT: must be a port from 1024 to 65535",
        MCP_REFUSED,
    ]


def test_a_name_that_is_not_a_setting_is_reported_as_such() -> None:
    assert problems_of(nope=1) == ["CONDUCTOR_NOPE: is not a setting"]


def test_every_setting_has_its_message() -> None:
    assert list(config.FIELD_MESSAGES) == list(Settings.model_fields)
    assert config.FIELD_MESSAGES == MESSAGES
    assert (config.DATA_DIR_MESSAGE, config.NOT_A_SETTING_MESSAGE) == (
        "must be a folder path",
        "is not a setting",
    )


def test_only_the_server_mapping_is_decoded_from_json() -> None:
    plain = {
        name: field.annotation
        for name, field in Settings.model_fields.items()
        if field.annotation not in (str, Path)
    }
    assert list(plain) == ["mcp"]
