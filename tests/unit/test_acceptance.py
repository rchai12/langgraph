import pytest

from conductor.acceptance import HEADING_MESSAGE, Row, accept, digest, read_rows

SPEC = """# Phase 4z: invented

## Acceptance

Run the baseline `.venv/bin/python scripts/check.py` first.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | `All checks passed.` |
| `grep -c '^## Phase 4z: ' docs/progress.md` | `1` |
| plain words, no command | nothing |
| `git grep -n -E 'a\\|b' -- src` | no output |

### Searches

```sh
git grep --untracked -n -E 'one' -- src

git grep --untracked -n -E 'two' -- src
```

## Report

| Command | Must show |
|---|---|
| `echo not acceptance` | ignored |
"""

GUIDE = """# Verify Phase 4z: invented

## 1. Gates

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | passed |
| G2 | `git status --short` | Scope |

## 4. Searches

```sh
git grep --untracked -n -E 'one' -- src
```
"""


def test_spec_rows_are_table_commands_then_fenced_searches() -> None:
    assert read_rows(SPEC, "Acceptance") == [
        Row("A1", ".venv/bin/python scripts/check.py --first core"),
        Row("A2", "grep -c '^## Phase 4z: ' docs/progress.md"),
        Row("A3", "git grep -n -E 'a|b' -- src"),
        Row("Q1", "git grep --untracked -n -E 'one' -- src"),
        Row("Q2", "git grep --untracked -n -E 'two' -- src"),
    ]


def test_guide_headings_may_carry_a_number_and_rows_keep_their_labels() -> None:
    assert read_rows(GUIDE, "Gates") == [
        Row("G1", ".venv/bin/python scripts/check.py --first core"),
        Row("G2", "git status --short"),
    ]
    assert read_rows(GUIDE, "Searches") == [Row("Q1", "git grep --untracked -n -E 'one' -- src")]


def test_a_missing_heading_is_refused() -> None:
    with pytest.raises(ValueError) as caught:
        read_rows(GUIDE, "Acceptance")
    assert str(caught.value) == f"{HEADING_MESSAGE}: Acceptance"


def test_check_rows_show_the_last_line_and_the_sections_table() -> None:
    output = (
        "== lint\nAll good\nSections:\n  core      10 passed    0 failed    0 skipped\n"
        "  cli        2 passed    0 failed    0 skipped\nSummary:\n  lint: passed\n\n"
        "All checks passed.\n"
    )
    row = Row("A1", ".venv/bin/python scripts/check.py --first core")
    assert digest(row, output, 0) == [
        "A1: All checks passed.",
        "  Sections:",
        "    core      10 passed    0 failed    0 skipped",
        "    cli        2 passed    0 failed    0 skipped",
    ]


def test_long_details_are_cut_with_a_count_of_hidden_lines() -> None:
    output = "\n".join(f"src/x.py:{number}: match" for number in range(1, 24))
    lines = digest(Row("Q1", "git grep -n x -- src"), output, 0)
    assert lines[0] == "Q1: 23 lines"
    assert lines[1] == "  src/x.py:1: match"
    assert lines[20] == "  src/x.py:20: match"
    assert lines[21] == "  ... 3 more lines in the log"
    assert len(lines) == 22


@pytest.mark.parametrize(
    ("command", "output", "code", "expected"),
    [
        ("git grep -n x -- src", "", 1, ["Q1: empty"]),
        ("git grep -n x -- src", "fatal: bad\n", 128, ["Q1: 1 line (exit 128)", "  fatal: bad"]),
        ("git status --short", " M a.py\n?? b.py\n", 0, ["Q1: 2 lines", "   M a.py", "  ?? b.py"]),
        ("git diff --check", "", 0, ["Q1: empty"]),
        ("grep -c x docs/progress.md", "0\n", 1, ["Q1: 0 (exit 1)"]),
        ("true", "", 0, ["Q1: empty"]),
        (".venv/bin/python -m pytest a.py", "x\n\n30 passed in 1s\n", 0, ["Q1: 30 passed in 1s"]),
    ],
    ids=["grep-empty", "grep-error", "status", "diff-empty", "exit-code", "silent", "last-line"],
)
def test_digest_heads(command: str, output: str, code: int, expected: list[str]) -> None:
    assert digest(Row("Q1", command), output, code) == expected


def test_accept_runs_each_row_in_order_and_logs_its_output(tmp_path) -> None:
    seen: list[str] = []

    def run(command: str) -> tuple[int, str]:
        seen.append(command)
        return 0, f"out of {command}\n"

    rows = [Row("A1", "echo one"), Row("Q1", "git grep -n x -- src")]
    log_dir = tmp_path / "logs"
    lines = accept(rows, run, log_dir)
    assert seen == ["echo one", "git grep -n x -- src"]
    assert lines == [
        "A1: out of echo one",
        "Q1: 1 line",
        "  out of git grep -n x -- src",
        f"Logs: {log_dir}",
    ]
    assert (log_dir / "A1.log").read_text(encoding="utf-8") == "$ echo one\nout of echo one\n"
