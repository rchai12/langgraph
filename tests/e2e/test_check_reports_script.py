import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_reports.py"

ENTRY = """## Phase 1: skeleton (2026-10-25)
- Tests: 0 -> 70 (given 65)
- New public names: None
- Changed files: 6
- Deviations:
  - None
- Follow-ups:
  - None
"""


def run_script(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_good_reports(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "progress.md").write_text(f"# Progress\n\n{ENTRY}", encoding="utf-8")
    done = run_script(tmp_path)
    assert (done.stdout, done.stderr, done.returncode) == ("Reports OK.\n", "", 0)


def test_one_problem(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "progress.md").write_text(
        f"# Progress\n\n{ENTRY.replace('(given 65)', '')}", encoding="utf-8"
    )
    done = run_script(tmp_path)
    assert done.stdout == (
        "docs/progress.md:4: expected `- Tests: <before> -> <after> (given <n>)`\n1 problem.\n"
    )
    assert done.returncode == 1


def test_two_problems(tmp_path: Path) -> None:
    done = run_script(tmp_path)
    assert done.stdout == "docs/progress.md:1: missing\n1 problem.\n"
    (tmp_path / "docs" / "reviews").mkdir(parents=True)
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n", encoding="utf-8")
    (tmp_path / "docs" / "reviews" / "phase-01-skeleton.md").write_text("# Review\n", "utf-8")
    (tmp_path / "docs" / "reviews" / "phase-02-x.md").write_text("# Review\n", "utf-8")
    done = run_script(tmp_path)
    assert done.stdout == (
        "docs/reviews/phase-01-skeleton.md:1: no spec docs/phases/phase-01-skeleton.md\n"
        "docs/reviews/phase-02-x.md:1: no spec docs/phases/phase-02-x.md\n"
        "2 problems.\n"
    )
    assert done.returncode == 1


def test_the_script_names_its_option() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0
    assert "--root" in done.stdout
