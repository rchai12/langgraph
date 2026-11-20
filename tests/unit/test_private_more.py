import os
import stat
from pathlib import Path

import pytest

from conductor import private


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_failed_fchmod_closes_the_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[int] = []
    real_open = os.open

    def remember(name: str, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = real_open(name, flags, *args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "open", remember)
    monkeypatch.setattr(os, "fchmod", refuse)
    with pytest.raises(PermissionError):
        private.open_file(tmp_path / "new", os.O_WRONLY)
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_an_exclusive_open_creates_a_private_file(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    descriptor = private.open_file(path, os.O_WRONLY | os.O_EXCL)
    try:
        os.write(descriptor, b"body")
    finally:
        os.close(descriptor)
    assert (mode(path), path.read_bytes()) == (0o600, b"body")


@pytest.mark.parametrize(
    ("kept", "open_bits"),
    [(0o700, False), (0o600, False), (0o710, True), (0o704, True)],
    ids=["700", "600", "710", "704"],
)
def test_open_to_others_reads_group_and_other_bits(
    tmp_path: Path, kept: int, open_bits: bool
) -> None:
    path = tmp_path / "kept"
    path.mkdir()
    path.chmod(kept)
    assert private.open_to_others(path) is open_bits
