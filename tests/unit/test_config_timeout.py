import pytest

from conductor.config import SettingsError, get_settings

TIMEOUT_REFUSED = "CONDUCTOR_MODEL_TIMEOUT: must be whole seconds from 1 to 3600"


def test_the_default_timeout() -> None:
    settings = get_settings()
    assert (settings.model_timeout, settings.model_timeout_seconds) == ("300", 300)


@pytest.mark.parametrize(("given", "seconds"), [("1", 1), ("3600", 3600)])
def test_a_timeout_in_range(monkeypatch: pytest.MonkeyPatch, given: str, seconds: int) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", given)
    assert get_settings().model_timeout_seconds == seconds


@pytest.mark.parametrize("given", [" 30 ", "30.0", "0", "3601", "0300"])
def test_a_timeout_out_of_range_or_not_whole(monkeypatch: pytest.MonkeyPatch, given: str) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", given)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == TIMEOUT_REFUSED


def test_the_timeout_problem_comes_last(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL", "")
    monkeypatch.setenv("CONDUCTOR_MODEL_TIMEOUT", "fast")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == f"CONDUCTOR_MODEL: must not be empty; {TIMEOUT_REFUSED}"
