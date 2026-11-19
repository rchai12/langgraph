"""Run one spot check: test passes, change one exact text, test again, restore the module.

Run it as: .venv/bin/python scripts/spot_check.py MODULE --old TEXT --new TEXT --test ID \
    [--row S1] --root SCRATCH_COPY

MODULE is relative to --root and must be under its src/. Run it against an isolated scratch copy
of the reviewed bytes (docs/ai-workflow.md); the test imports that copy's src through PYTHONPATH.
It prints one line: `S1 fails: <first failure line>`, `S1 passes`, `S1 no test ran`, or an error.
"""

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from conductor.spotcheck import SpotError, spot_check

ROOT = Path(__file__).resolve().parent.parent


def run_pytest(test: str, cwd: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(cwd / "src")
    command = [
        sys.executable,
        "-m",
        "pytest",
        test,
        "-q",
        "--tb=line",
        "--no-cov",
        "-p",
        "no:cacheprovider",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return completed.returncode, completed.stdout


def main(
    argv: list[str] | None = None,
    run: Callable[[str, Path], tuple[int, str]] = run_pytest,
) -> int:
    parser = argparse.ArgumentParser(description="Run one spot check and restore the module.")
    parser.add_argument("module", help="Module path relative to --root.")
    parser.add_argument("--old", required=True, help="Text that must match exactly once.")
    parser.add_argument("--new", required=True, help="Replacement text.")
    parser.add_argument("--test", required=True, help="Full pytest node id to run.")
    parser.add_argument("--row", help="Spot-check row label, printed before the verdict.")
    parser.add_argument("--root", type=Path, required=True, help="Scratch copy to work in.")
    options = parser.parse_args(argv)
    root = options.root.resolve()
    if root == ROOT:
        print("Error: run spot checks in a scratch copy, not the repository", file=sys.stderr)
        return 2
    module = (root / options.module).resolve()
    if not module.is_relative_to(root / "src") or not module.is_file():
        print("Error: the module must be a file under src/", file=sys.stderr)
        return 2

    def _run() -> tuple[int, str]:
        return run(options.test, root)

    try:
        found = spot_check(module, options.old, options.new, _run)
    except SpotError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"{options.row} {found}" if options.row else found)
    return 0 if found.startswith("fails") else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
