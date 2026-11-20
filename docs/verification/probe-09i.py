"""Probe for Phase 9i: private storage primitives and the doctor's data-folder check.

The oracle is built from this file's own tables (the spec's Part 1 and Part 3), never from the
code under test. Each trial gets its own temporary folder. Run from the repository root with
.venv/bin/python docs/verification/probe-09i.py. The last line is FAILURES <n>.
"""

import os
import random
import stat
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

failures = 0
rng = random.Random(9)


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def section(label: str, body: Callable[[], bool]) -> None:
    try:
        ok = body()
    except Exception as error:  # noqa: BLE001
        print(f"     {label}: raised {type(error).__name__}")
        ok = False
    check(label, ok)


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables, written from the spec.
NEW_DIR = 0o700
NEW_FILE = 0o600
OTHERS = 0o077
MASKS = (0o022, 0o077, 0o277, 0o002)
KEPT_DIRS = (0o700, 0o755, 0o750, 0o711)
KEPT_FILES = (0o600, 0o644, 0o640)


def want_levels(existing: list[int], depth: int) -> list[int]:
    """Existing levels keep their mode; every level made by the call is 0700."""
    return existing + [NEW_DIR] * (depth - len(existing))


def want_doctor(folder_mode: int, folder: str) -> tuple[str, str]:
    if folder_mode & OTHERS:
        return ("FAIL", f"open to other users (run: chmod 700 {folder})")
    return ("ok", "")


assert want_levels([0o755], 3) == [0o755, 0o700, 0o700]
assert want_levels([], 2) == [0o700, 0o700]
assert want_doctor(0o700, "/d") == ("ok", "")
assert want_doctor(0o701, "/d") == ("FAIL", "open to other users (run: chmod 700 /d)")
assert want_doctor(0o740, "/d")[0] == "FAIL"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def one_tree() -> bool:
    from conductor import private

    top = Path(tempfile.mkdtemp())
    depth = rng.randint(1, 4)
    kept = rng.randint(0, depth)
    chain = [top]
    for index in range(depth):
        chain.append(chain[-1] / f"l{index}")
    existing = []
    for level in chain[1 : kept + 1]:
        level.mkdir()
        chosen = rng.choice(KEPT_DIRS)
        level.chmod(chosen)
        existing.append(chosen)
    use = rng.choice(["dir", "file", "open"])
    target = chain[-1] / "f"
    file_mode = None
    if use != "dir" and kept == depth and rng.random() < 0.5:
        file_mode = rng.choice(KEPT_FILES)
        target.write_bytes(b"old")
        target.chmod(file_mode)
    previous = os.umask(rng.choice(MASKS))
    try:
        if use == "dir":
            private.ensure_dir(chain[-1])
        elif use == "file":
            private.ensure_file(target)
        else:
            os.close(private.open_file(target, os.O_WRONLY | os.O_APPEND))
    finally:
        os.umask(previous)
    ok = [mode(level) for level in chain[1:]] == want_levels(existing, depth)
    if use != "dir":
        want_file = (NEW_FILE, b"") if file_mode is None else (file_mode, b"old")
        ok &= (mode(target), target.read_bytes()) == want_file
    return ok


def check_trees() -> bool:
    return all(one_tree() for _ in range(200))


def check_doctor() -> bool:
    from conductor import diagnostics

    agree = True
    for trial in range(100):
        folder = Path(tempfile.mkdtemp()) / "data"
        folder.mkdir()
        chosen = 0o700 | rng.randint(0, 0o77) if trial else 0o701
        folder.chmod(chosen)
        found = diagnostics.check_data_folder(folder)
        want = want_doctor(chosen, str(folder))
        agree &= (found.status, found.detail) == want
        agree &= mode(folder) == chosen and list(folder.iterdir()) == []
    missing = Path(tempfile.mkdtemp()) / "a" / "data"
    found = diagnostics.check_data_folder(missing)
    agree &= (found.status, found.detail) == ("ok", "")
    return agree and [mode(missing.parent), mode(missing)] == [NEW_DIR, NEW_DIR]


def one_race(top: Path) -> bool:
    from conductor import private

    target = top / "a" / "b" / "c" / "f.db"
    barrier = threading.Barrier(8)
    errors: list[str] = []

    def work(make_file: bool) -> None:
        barrier.wait()
        try:
            if make_file:
                private.ensure_file(target)
            else:
                private.ensure_dir(target.parent)
        except Exception as error:  # noqa: BLE001
            errors.append(type(error).__name__)

    threads = [threading.Thread(target=work, args=(n % 2 == 1,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        return False
    levels = [mode(top / "a"), mode(top / "a" / "b"), mode(target.parent), mode(target)]
    return levels == [NEW_DIR, NEW_DIR, NEW_DIR, NEW_FILE]


def check_threads() -> bool:
    return all(one_race(Path(tempfile.mkdtemp())) for _ in range(20))


previous_mask = os.umask(0o022)
try:
    section("200 random trees: new levels 0700, new files 0600, existing kept", check_trees)
    section("100 random folder modes: doctor fails exactly when others have a bit", check_doctor)
    section("8 threads creating one path at once all succeed, all private", check_threads)
finally:
    os.umask(previous_mask)

print(f"FAILURES {failures}")
