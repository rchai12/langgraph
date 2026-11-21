from pathlib import Path

import pytest

from tests.support import run


def test_an_open_folder_that_cannot_be_written_says_not_writable(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o555)
    try:
        result = run("doctor")
    finally:
        data.chmod(0o755)
    assert f"FAIL  data folder {data}: not writable" in result.stdout.splitlines()
    assert "chmod" not in result.stdout


def test_a_data_path_under_a_file_says_not_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "taken").write_bytes(b"a file")
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "taken" / "data"))
    result = run("doctor")
    line = f"FAIL  data folder {tmp_path / 'taken' / 'data'}: not writable"
    assert line in result.stdout.splitlines()
