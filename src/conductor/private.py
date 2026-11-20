import errno
import os
import stat
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_dir(folder: Path) -> None:
    missing: list[Path] = []
    level = folder
    while not level.exists():
        missing.append(level)
        level = level.parent
    for level in reversed(missing):
        try:
            os.mkdir(level, DIR_MODE)
        except FileExistsError:
            continue
        os.chmod(level, DIR_MODE)
    if not folder.is_dir():
        raise NotADirectoryError(errno.ENOTDIR, "not a folder", str(folder))


def open_file(path: Path, flags: int) -> int:
    ensure_dir(path.parent)
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, FILE_MODE)
    except FileExistsError:
        if flags & os.O_EXCL:
            raise
        return os.open(path, flags)
    try:
        os.fchmod(descriptor, FILE_MODE)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def ensure_file(path: Path) -> None:
    os.close(open_file(path, os.O_RDONLY))


def open_to_others(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) & 0o077 != 0
