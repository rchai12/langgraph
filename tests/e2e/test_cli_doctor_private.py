import os
import stat
from pathlib import Path

import pytest

from conductor import diagnostics
from tests.support import run


@pytest.fixture(autouse=True)
def python_3_12_13(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.parametrize("loose", [0o755, 0o750, 0o701, 0o707], ids=["755", "750", "701", "707"])
def test_an_existing_folder_open_to_others_fails(tmp_path: Path, loose: int) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(loose)
    result = run("doctor")
    assert result.stdout == (
        "ok    python 3.12.13\n"
        f"FAIL  data folder {data}: open to other users (run: chmod 700 {data})\n"
        "FAIL  ollama http://127.0.0.1:9: not reachable\n"
        "SKIP  model qwen3.8:27b: needs ollama\n"
        "2 checks failed.\n"
    )
    assert result.exit_code == 1
    assert (mode(data), list(data.iterdir())) == (loose, [])


def test_a_private_existing_folder_passes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o700)
    result = run("doctor")
    assert result.stdout.splitlines()[1] == f"ok    data folder {data}"
    assert mode(data) == 0o700


def test_a_new_folder_and_its_parents_are_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = tmp_path / "x" / "y" / "data"
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(data))
    previous = os.umask(0o022)
    try:
        result = run("doctor")
    finally:
        os.umask(previous)
    assert result.stdout.splitlines()[1] == f"ok    data folder {data}"
    found = [mode(tmp_path / "x"), mode(tmp_path / "x" / "y"), mode(data)]
    assert found == [0o700, 0o700, 0o700]
