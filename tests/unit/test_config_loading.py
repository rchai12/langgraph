import pytest
from pydantic import ValidationError

from conductor import config
from conductor.config import Settings, SettingsError, get_settings

MCP_REFUSED = "CONDUCTOR_MCP: must map server names to command lines"


def test_a_construction_failure_reports_only_its_own_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP", "notjson")
    monkeypatch.setenv("CONDUCTOR_MODEL", "   ")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == MCP_REFUSED


def test_a_host_elsewhere_with_a_trailing_slash_is_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://10.0.0.5:11434/")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == f"CONDUCTOR_OLLAMA_HOST: {config.OLLAMA_HOST_MESSAGE}"


def test_problems_list_a_bad_server_then_a_name_that_is_not_a_setting() -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(mcp={"bank": 1}, nope=2)
    assert config.validation_problems(raised.value) == [
        MCP_REFUSED,
        "CONDUCTOR_NOPE: is not a setting",
    ]
