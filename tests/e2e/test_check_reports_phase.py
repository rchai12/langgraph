import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_reports.py"


def run_script(root: Path, phase: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--phase", phase],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_phase_option(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-05a-routing.md").write_text("# Phase 5a\n")
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n")
    missing = run_script(tmp_path, "5a")
    assert (missing.stdout, missing.stderr, missing.returncode) == (
        "docs/progress.md:1: no progress entry for Phase 5a\n1 problem.\n",
        "",
        1,
    )
    bad = run_script(tmp_path, "5A")
    assert (bad.stdout, bad.stderr, bad.returncode) == (
        "",
        "Error: phase must be a phase id such as 5a\n",
        2,
    )
