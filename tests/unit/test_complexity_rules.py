"""Ruff's complexity rules are on at explicit limits, and nothing in the tree is over them."""

import subprocess
import sys
import tomllib
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
    "src/conductor/config.py",
    "src/conductor/evals/report.py",
    "src/conductor/web/app.py",
    "scripts/check.py",
    "tests/integration/test_run_status_cases.py",
]


def findings(path: str) -> list[str]:
    command = [sys.executable, "-m", "ruff", "check", "--no-cache", *LIMITS]
    command += ["--output-format", "concise", path]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return [line for line in done.stdout.splitlines() if ": C901 " in line or ": PLR09" in line]


@pytest.mark.parametrize("path", FILES, ids=[Path(path).stem for path in FILES])
def test_no_function_is_over_the_limits(path: str) -> None:
    assert findings(path) == []


def test_nothing_in_the_tree_is_over_the_limits() -> None:
    assert findings(".") == []


def test_pyproject_turns_the_rules_on_at_the_limits() -> None:
    settings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert settings["tool"]["ruff"]["lint"] == {
        "select": ["E", "F", "I", "B", "UP", "ARG", "C901", "PLR0911", "PLR0912", "PLR0915"],
        "mccabe": {"max-complexity": 10},
        "pylint": {"max-returns": 6, "max-branches": 12, "max-statements": 50},
    }
