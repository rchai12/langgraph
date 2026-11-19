"""Run a phase spec's acceptance commands, or a guide's gates and searches, and print a digest.

Run it as: .venv/bin/python scripts/accept.py --phase ID [--guide]

Each row prints one line (the Sections table under check.py); full output goes to the log folder.
The script does not judge a row: compare each line with the table's "Must show".
"""

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from conductor.acceptance import accept, read_rows
from conductor.reports import PHASE_MESSAGE

ROOT = Path(__file__).resolve().parent.parent
_PHASE = re.compile(r"^[1-9][0-9]*[a-z]?$")


def run_shell(command: str, cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["/bin/zsh", "-c", command],
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return completed.returncode, completed.stdout


def phase_file(root: Path, phase: str, guide: bool) -> Path | None:
    letter = phase[-1] if phase[-1].isalpha() else ""
    number = phase[:-1] if letter else phase
    padded = f"{int(number):02d}{letter}"
    folder = root / "docs" / ("verification" if guide else "phases")
    matches = sorted(folder.glob(f"phase-{padded}-*.md"))
    if len(matches) == 1:
        return matches[0]
    return None


def main(
    argv: list[str] | None = None,
    run: Callable[[str, Path], tuple[int, str]] = run_shell,
) -> int:
    parser = argparse.ArgumentParser(description="Run a phase's acceptance commands.")
    parser.add_argument("--phase", required=True, help="Phase id, such as 9e.")
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Run the verification guide's Gates and Searches instead of the spec's Acceptance.",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="Log folder (default: conductor-accept-<id> in the temporary directory).",
    )
    options = parser.parse_args(argv)
    if _PHASE.fullmatch(options.phase) is None:
        print(f"Error: {PHASE_MESSAGE}", file=sys.stderr)
        return 2
    path = phase_file(options.root, options.phase, options.guide)
    if path is None:
        kind = "guide" if options.guide else "spec"
        print(f"Error: no {kind} for phase {options.phase}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    try:
        if options.guide:
            rows = read_rows(text, "Gates") + read_rows(text, "Searches")
        else:
            rows = read_rows(text, "Acceptance")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    log_dir = options.log_dir
    if log_dir is None:
        log_dir = Path(tempfile.gettempdir()) / f"conductor-accept-{options.phase}"

    def _run(command: str) -> tuple[int, str]:
        return run(command, options.root)

    for line in accept(rows, _run, log_dir):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
