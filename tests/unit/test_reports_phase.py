from pathlib import Path

import pytest

from conductor.reports import PHASE_MESSAGE, Problem, check_reports

ENTRY = """## Phase 5a: routing (2026-11-09)
- Tests: 423 -> 460 (given 37)
- New public names: None
- Changed files: 12
- Deviations:
  - None
- Follow-ups:
  - None
"""


def repository(root: Path, *, spec: bool, entry: bool) -> Path:
    (root / "docs" / "phases").mkdir(parents=True)
    if spec:
        (root / "docs" / "phases" / "phase-05a-routing.md").write_text("# Phase 5a\n")
    (root / "docs" / "progress.md").write_text("# Progress\n\n" + (ENTRY if entry else ""))
    return root


@pytest.mark.parametrize(
    ("spec", "entry", "problems"),
    [
        (True, True, []),
        (True, False, [Problem("docs/progress.md", 1, "no progress entry for Phase 5a")]),
        (False, True, [Problem("docs/phases", 1, "no spec for Phase 5a")]),
    ],
)
def test_a_phase_needs_its_spec_and_its_entry(
    tmp_path: Path, spec: bool, entry: bool, problems: list[Problem]
) -> None:
    root = repository(tmp_path, spec=spec, entry=entry)
    assert check_reports(root, phase="5a") == problems
    assert check_reports(root) == []


@pytest.mark.parametrize("phase", ["05a", "5A"])
def test_a_phase_id_is_checked(tmp_path: Path, phase: str) -> None:
    root = repository(tmp_path, spec=True, entry=True)
    with pytest.raises(ValueError) as raised:
        check_reports(root, phase=phase)
    assert str(raised.value) == PHASE_MESSAGE == "phase must be a phase id such as 5a"


ENTRY_moved = """## Phase 5: routing (2026-11-09)
- Tests: 1 -> 2 (given 1)
- New public names: None
- Changed files: 1
- Deviations:
  - None
- Follow-ups:
  - None
"""


def test_neither_spec_nor_entry_names_the_spec_first(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n", encoding="utf-8")
    assert check_reports(tmp_path, phase="5a") == [
        Problem("docs/phases", 1, "no spec for Phase 5a"),
        Problem("docs/progress.md", 1, "no progress entry for Phase 5a"),
    ]


def test_phase_5_matches_a_zero_padded_spec(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-05-x.md").write_text("# Phase 5\n", encoding="utf-8")
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n\n" + ENTRY_moved, encoding="utf-8")
    assert check_reports(tmp_path, phase="5") == []


def test_an_empty_phase_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as raised:
        check_reports(tmp_path, phase="")
    assert str(raised.value) == PHASE_MESSAGE


def test_a_malformed_entry_is_also_a_missing_entry(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-05a-routing.md").write_text(
        "# Phase 5a\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "progress.md").write_text(
        "# Progress\n\n## Phase 5a: routing (2026-11-09)\n- Tests: wrong\n",
        encoding="utf-8",
    )
    assert check_reports(tmp_path, phase="5a") == [
        Problem(
            "docs/progress.md",
            4,
            "expected `- Tests: <before> -> <after> (given <n>)`",
        ),
        Problem("docs/progress.md", 1, "no progress entry for Phase 5a"),
    ]
