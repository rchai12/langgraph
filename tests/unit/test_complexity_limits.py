"""The complexity limits hold in the files Phase 9w refactors (Phase 9x turns them on for all)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIMITS = [
    "--select",
    "C901,PLR0911,PLR0912,PLR0915",
    "--config",
    "lint.mccabe.max-complexity = 10",
    "--config",
    "lint.pylint.max-returns = 6",
    "--config",
    "lint.pylint.max-branches = 12",
    "--config",
    "lint.pylint.max-statements = 50",
]
FILES = [
    "src/conductor/reports.py",
    "src/conductor/spotcheck.py",
    "src/conductor/registry.py",
    "src/conductor/cli/common.py",
    "src/conductor/routing/route.py",
]


def findings(path: str) -> list[str]:
    command = [sys.executable, "-m", "ruff", "check", "--no-cache", *LIMITS]
    command += ["--output-format", "concise", path]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return [line.split(": ", 1)[1] for line in done.stdout.splitlines() if line.startswith(path)]


@pytest.mark.parametrize("path", FILES, ids=[Path(path).stem for path in FILES])
def test_no_function_is_over_the_limits(path: str) -> None:
    assert findings(path) == []
