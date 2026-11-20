import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor import private

REAL_MKDIR = os.mkdir
REAL_OPEN = os.open


@contextmanager
def umask(value: int) -> Iterator[None]:
    previous = os.umask(value)
    try:
        yield
    finally:
        os.umask(previous)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_modes() -> None:
    assert (private.DIR_MODE, private.FILE_MODE) == (0o700, 0o600)


@pytest.mark.parametrize("mask", [0o022, 0o277], ids=["umask-022", "umask-277"])
def test_every_missing_folder_is_private(tmp_path: Path, mask: int) -> None:
    before = mode(tmp_path)
    with umask(mask):
        private.ensure_dir(tmp_path / "a" / "b" / "c")
    found = [mode(tmp_path / "a"), mode(tmp_path / "a" / "b"), mode(tmp_path / "a" / "b" / "c")]
    assert found == [0o700, 0o700, 0o700]
    assert mode(tmp_path) == before


@pytest.mark.parametrize("kept", [0o755, 0o750, 0o777], ids=["755", "750", "777"])
def test_an_existing_folder_keeps_its_mode(tmp_path: Path, kept: int) -> None:
    folder = tmp_path / "a"
    folder.mkdir()
    folder.chmod(kept)
    with umask(0o022):
        private.ensure_dir(folder)
        private.ensure_dir(folder / "b")
    assert (mode(folder), mode(folder / "b")) == (kept, 0o700)


def test_a_folder_made_meanwhile_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "a"

    def other_process_first(path, *args, **kwargs) -> None:
        REAL_MKDIR(path)
        os.chmod(path, 0o755)
        raise FileExistsError(path)

    monkeypatch.setattr(os, "mkdir", other_process_first)
    private.ensure_dir(folder)
    monkeypatch.undo()
    assert (folder.is_dir(), mode(folder)) == (True, 0o755)


@pytest.mark.parametrize("below", ["", "x"], ids=["itself", "below"])
def test_a_file_in_the_way_is_refused(tmp_path: Path, below: str) -> None:
    taken = tmp_path / "taken"
    taken.write_bytes(b"a file")
    with pytest.raises(NotADirectoryError):
        private.ensure_dir(taken / below if below else taken)
    assert taken.read_bytes() == b"a file"


@pytest.mark.parametrize("mask", [0o022, 0o277], ids=["umask-022", "umask-277"])
def test_a_new_file_is_private_and_empty(tmp_path: Path, mask: int) -> None:
    path = tmp_path / "a" / "b" / "f.db"
    with umask(mask):
        private.ensure_file(path)
    assert (mode(path), path.read_bytes()) == (0o600, b"")
    assert (mode(tmp_path / "a"), mode(tmp_path / "a" / "b")) == (0o700, 0o700)


def test_an_existing_file_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "f.db"
    path.write_bytes(b"keep")
    path.chmod(0o644)
    private.ensure_file(path)
    assert (mode(path), path.read_bytes()) == (0o644, b"keep")


def test_a_file_made_meanwhile_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "f.db"
    raced: list[str] = []

    def other_process_first(name, flags, *args, **kwargs) -> int:
        if flags & os.O_CREAT and not raced:
            raced.append("raced")
            made = REAL_OPEN(name, os.O_WRONLY | os.O_CREAT, 0o644)
            os.write(made, b"other")
            os.close(made)
            os.chmod(name, 0o644)
        return REAL_OPEN(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", other_process_first)
    private.ensure_file(path)
    monkeypatch.undo()
    assert (raced, mode(path), path.read_bytes()) == (["raced"], 0o644, b"other")


@pytest.mark.parametrize("mask", [0o022, 0o277], ids=["umask-022", "umask-277"])
def test_open_file_creates_a_private_file(tmp_path: Path, mask: int) -> None:
    path = tmp_path / "a" / "run.jsonl"
    with umask(mask):
        descriptor = private.open_file(path, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(descriptor, b"one\n")
    finally:
        os.close(descriptor)
    assert (mode(tmp_path / "a"), mode(path), path.read_bytes()) == (0o700, 0o600, b"one\n")


def test_open_file_appends_to_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(b"one\n")
    path.chmod(0o644)
    descriptor = private.open_file(path, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(descriptor, b"two\n")
    finally:
        os.close(descriptor)
    assert (mode(path), path.read_bytes()) == (0o644, b"one\ntwo\n")


def test_an_exclusive_open_refuses_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(b"first")
    with pytest.raises(FileExistsError):
        private.open_file(path, os.O_WRONLY | os.O_EXCL)
    assert path.read_bytes() == b"first"
