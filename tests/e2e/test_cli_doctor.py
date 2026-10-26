from pathlib import Path

import pytest

from conductor import diagnostics
from tests.support import fake_ollama, run

HOST_REFUSED = (
    "Error: CONDUCTOR_OLLAMA_HOST: must be an http address on this machine "
    "(127.0.0.1, localhost, or ::1)\n"
)


@pytest.fixture(autouse=True)
def python_3_12_13(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def test_everything_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with fake_ollama() as (fake, host):
        fake.models("nomic-embed-text:latest", "qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout == (
        "ok    python 3.12.13\n"
        f"ok    data folder {tmp_path / 'data'}\n"
        f"ok    ollama {host}\n"
        "ok    model qwen3.8:27b\n"
        "All checks passed.\n"
    )
    assert result.stderr == ""
    assert result.exit_code == 0
    assert fake.paths == ["/api/tags"]
    assert (tmp_path / "data").stat().st_mode & 0o777 == 0o700
    assert list((tmp_path / "data").iterdir()) == []


def test_ollama_not_running(tmp_path: Path) -> None:
    result = run("doctor")
    assert result.stdout == (
        "ok    python 3.12.13\n"
        f"ok    data folder {tmp_path / 'data'}\n"
        "FAIL  ollama http://127.0.0.1:9: not reachable\n"
        "SKIP  model qwen3.8:27b: needs ollama\n"
        "1 check failed.\n"
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b"<html>not ollama</html>"),
        (500, b'{"models": []}'),
        (200, b'{"models": "qwen3.8:27b"}'),
        (200, b'{"models": [{"model": "qwen3.8:27b"}]}'),
    ],
)
def test_something_else_answering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: int, body: bytes
) -> None:
    with fake_ollama() as (fake, host):
        fake.status = status
        fake.body = body
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"FAIL  ollama {host}: unexpected answer",
        "SKIP  model qwen3.8:27b: needs ollama",
        "1 check failed.",
    ]
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("model", "pulled", "line"),
    [
        (
            "qwen3.8:27b",
            ["qwen3-coder:30b"],
            "FAIL  model qwen3.8:27b: not pulled (run: ollama pull qwen3.8:27b)",
        ),
        ("qwen3-coder", ["qwen3-coder:latest"], "ok    model qwen3-coder"),
        (
            "qwen3-coder",
            ["qwen3-coder:30b"],
            "FAIL  model qwen3-coder: not pulled (run: ollama pull qwen3-coder)",
        ),
    ],
)
def test_the_model_must_be_pulled(
    monkeypatch: pytest.MonkeyPatch, model: str, pulled: list[str], line: str
) -> None:
    with fake_ollama() as (fake, host):
        fake.models(*pulled)
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("CONDUCTOR_MODEL", model)
        result = run("doctor")
    assert result.stdout.splitlines()[3] == line
    assert result.exit_code == (0 if line.startswith("ok") else 1)


def test_a_proxy_in_the_environment_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_ollama() as (fake, host):
        fake.models("qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"ok    ollama {host}",
        "ok    model qwen3.8:27b",
        "All checks passed.",
    ]


def test_old_python_and_a_data_folder_that_cannot_be_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 11, 9))
    (tmp_path / "taken").write_text("a file, not a folder", encoding="utf-8")
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "taken" / "data"))
    result = run("doctor")
    assert result.stdout == (
        "FAIL  python 3.11.9: conductor needs Python 3.12 or newer\n"
        f"FAIL  data folder {tmp_path / 'taken' / 'data'}: not writable\n"
        "FAIL  ollama http://127.0.0.1:9: not reachable\n"
        "SKIP  model qwen3.8:27b: needs ollama\n"
        "3 checks failed.\n"
    )
    assert result.exit_code == 1


def test_settings_that_point_elsewhere_stop_before_any_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://10.0.0.5:11434")
    result = run("doctor")
    assert result.stdout == ""
    assert result.stderr == HOST_REFUSED
    assert result.exit_code == 1
    assert not (tmp_path / "data").exists()
