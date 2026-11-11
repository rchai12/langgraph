"""Run one spot-check row against code that exists, and restore the file.

Run from the repository root with the project's interpreter:

    .venv/bin/python .claude/skills/phase-architect/spot.py \
        --file src/conductor/x.py --old 'exact text' --new 'broken text' \
        --test 'tests/unit/test_x.py::test_name[case]' [--root <clone>]

The old text must occur exactly once. The test runs with -vv, no bytecode, and no coverage,
and with PYTHONPATH=<root>/src, so a clone's own source is used. The file is restored and
every __pycache__ under src, tests, and scripts is removed, whatever the outcome. The exit
code is 0 when the test failed (the row works) and 1 when it passed or the edit could not
be made.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--file", required=True)
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--test", required=True)
    given = parser.parse_args()
    root = Path(given.root).resolve()
    path = root / given.file
    original = path.read_text()
    count = original.count(given.old)
    if count != 1:
        print(f"the old text occurs {count} times in {given.file}; it must occur once")
        return 1
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(root / "src")}
    command = [sys.executable, "-m", "pytest", "-q", "-vv", "--no-cov", "-p", "no:cacheprovider"]
    path.write_text(original.replace(given.old, given.new))
    try:
        run = subprocess.run(
            [*command, given.test], cwd=root, env=env, capture_output=True, text=True
        )
    finally:
        path.write_text(original)
        for folder in ("src", "tests", "scripts"):
            for cache in (root / folder).rglob("__pycache__"):
                shutil.rmtree(cache, ignore_errors=True)
    lines = run.stdout.splitlines()
    for line in [line for line in lines if line.startswith("E ")][:12]:
        print(line)
    print(lines[-1] if lines else "no output")
    if run.returncode == 0:
        print("the test still passes: this row cannot fail as written")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
