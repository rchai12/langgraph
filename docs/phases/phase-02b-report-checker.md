# Phase 2b: report checker

## Goal

The coder's progress entry and the verifier's review are the documents the architect, and later the agent itself (Phase 10), read to learn what a phase did. Today their form is only described in `docs/phase-conventions.md`; nothing checks it. After this phase:

- `conductor.reports` (a critical module) parses `docs/progress.md` and every file in `docs/reviews/` into typed data, and reports the first problem in each entry or review with its file and line;
- `scripts/check_reports.py` prints those problems, or `Reports OK.`;
- both agents run it as their last step, so a report in the wrong form fails like a failing test.

Phase 10's coding pipeline will read a verdict with `parse_review`, so the parser is strict: fixed headings, fixed lines, fixed order.

## Read first

- `docs/phase-conventions.md` ("Report", "Report and verdict": the forms this phase enforces)
- `docs/progress.md`, `docs/reviews/phase-01-skeleton.md`, `docs/reviews/phase-02a-contracts.md` (real documents in the form; they must pass)
- `scripts/check.py` for how a script in `scripts/` is written

## Starting state

Phase 2a is built and committed: N is `114`. **Sections: core.** `src/conductor/reports.py` and `scripts/check_reports.py` do not exist. `scripts/critical_modules.txt` lists only `events.py`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/reports.py` | new: the parsers and `check_reports` (critical) |
| `scripts/check_reports.py` | new: the command (R11) |
| `scripts/critical_modules.txt` | add the line `reports.py` after `events.py` |
| `docs/testing.md` | under "Critical modules", add `- \`reports.py\` (progress entries and reviews; Phase 2b)` after the `events.py` line, and remove "the verdict parser (Phase 10)" from the "Planned" line |
| `docs/phase-conventions.md` | the given edits below |
| `tests/unit/test_reports.py`, `tests/e2e/test_check_reports_script.py` | given |
| `tests/unit/test_reports_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Any check of a review's body after `Built beyond the spec:` (gate output, tables, probe output are free-form).
- Comparing numbers between documents (a review's `Passed` against the entry's tests), checking that a spec has a review, or reading the specs' contents.
- Running the checker inside `scripts/check.py`, a git hook, or a `conductor` command.
- Fixing a report automatically; JSON output.
- Any change to existing entries or reviews.

## Dependencies

None new.

## Design

```python
# conductor/reports.py
@dataclass(frozen=True)
class Problem:
    path: str                    # relative to the root, with "/"
    line: int                    # from 1
    message: str

    @property
    def text(self) -> str: ...   # f"{path}:{line}: {message}"

@dataclass(frozen=True)
class ProgressEntry:
    phase: str                   # "1", "2a"
    title: str
    date: date
    tests_before: int
    tests_after: int
    given: int
    new_names: str
    changed_files: int
    deviations: tuple[str, ...]
    follow_ups: tuple[str, ...]
    line: int                    # the heading's line in the file

@dataclass(frozen=True)
class Finding:
    requirement: str
    file: str
    line: int
    expected: str
    found: str

@dataclass(frozen=True)
class Review:
    phase: str
    verdict: Literal["PASS", "FAIL"]
    passed: int
    findings: tuple[Finding, ...]
    approved_deviations: str
    for_architect: str
    repaired: str                # after "Parts that needed a repair: "
    built_beyond: str            # after "Built beyond the spec: "

def phase_of(spec_name: str) -> str | None: ...
def parse_progress(text: str, path: str = "docs/progress.md") -> tuple[list[ProgressEntry], list[Problem]]: ...
def parse_review(text: str, path: str) -> tuple[Review | None, list[Problem]]: ...
def check_reports(root: Path) -> list[Problem]: ...
```

Lines are numbered from 1 over `text.split("\n")`. "The line where X is expected" is the number of the line that should have held it; past the end of the text it is one more than the last line.

### The progress entry

```text
## Phase <id>: <title> (YYYY-MM-DD)
- Tests: <before> -> <after> (given <n>)
- New public names: <text>
- Changed files: <n>
- Deviations:
  - <text>                        (one or more lines)
- Follow-ups:
  - <text>                        (one or more lines)
```

`<id>` is `[1-9][0-9]*[a-z]?`; numbers are `[0-9]+`; `<title>` and `<text>` are at least one character. An entry's lines are consecutive. After its last follow-up only empty lines may come before the next line that starts with `## ` or the end.

### The review's head

```text
# Review: Phase <id>                                 line 1
                                                     line 2, empty
- Verdict: PASS                                      line 3, PASS or FAIL
- Passed: <n>                                        line 4
- Findings: <n>                                      line 5
- Approved deviations: <text>                        line 6
- For the architect: <text>                          line 7
                                                     line 8, empty
## Findings                                          line 9
                                                     line 10, empty
None                                                 line 11, or the first finding
```

Findings run from line 11 to the first empty line or the end, each `<requirement> | <file>:<line> | expected <text> | found <text>`, where `<requirement>` and `<file>` contain no `|` (and `<file>` no `:`), `<line>` is `[0-9]+`, and the expected text contains no `|`. After the findings (or `None`), skipping empty lines, the next line is `Parts that needed a repair: <text>`; skipping empty lines again, the next is `Built beyond the spec: <text>`. Anything may follow.

### Messages

| When | Message |
|---|---|
| entry heading | ``heading must be `## Phase <id>: <title> (YYYY-MM-DD)` `` |
| a date that does not exist | `the date is not a real date` |
| an entry line | ``expected `- Tests: <before> -> <after> (given <n>)` ``, ``expected `- New public names: <names or None>` ``, ``expected `- Changed files: <n>` ``, ``expected `- Deviations:` ``, ``expected `- Follow-ups:` `` |
| no item under a list | ``expected at least one `  - ` line under Deviations`` (or `Follow-ups`) |
| a non-empty line after an entry | `unexpected line in the entry` |
| a review with no matching spec | `no spec docs/phases/<file name>` |
| review heading | ``expected `# Review: Phase <id>` `` with the id from the file name |
| lines 2, 8, 10 | `expected an empty line` |
| head lines | ``expected `- Verdict: PASS or FAIL` ``, ``expected `- Passed: <n>` ``, ``expected `- Findings: <n>` ``, ``expected `- Approved deviations: <text or None>` ``, ``expected `- For the architect: <text or None>` ``, ``expected `## Findings` `` |
| a finding line | ``expected `<requirement> \| <file>:<line> \| expected <...> \| found <...>` or `None` `` |
| count differs (line 5) | `Findings says <n> but <m> are listed` |
| verdict and findings disagree (line 3) | `a PASS review has no findings`, `a FAIL review lists at least one finding` |
| the two closing lines | ``expected `Parts that needed a repair: <parts or none>` ``, ``expected `Built beyond the spec: <what or none>` `` |
| the review's phase has no entry (line 1) | `no progress entry for Phase <id>` |
| no `docs/progress.md` (line 1) | `missing` |

(In the table, `\|` stands for `|`; the given tests hold the exact text.)

## Requirements

### Part 1: parsing

- **R1.** `phase_of` turns a spec file name `phase-<two or more digits><optional letter>-<slug>.md` into the id with leading zeros removed (`phase-01-skeleton.md` → `"1"`, `phase-02a-contracts.md` → `"2a"`), and returns `None` for any other name (`phase-2a-x.md` has one digit).
- **R2.** `parse_progress` ignores every line before the first line that starts with `## `. Each line that starts with `## ` begins an entry. A good entry becomes a `ProgressEntry`; an entry with a problem gives exactly one `Problem` (the first, checking in line order) and no `ProgressEntry`, and parsing continues at the next `## ` line. A text with no entry gives `([], [])`.
- **R3.** An entry is checked against the form under Design, field by field in order, with the messages of the table and the line where each was expected. `date` must be a real calendar date (`date.fromisoformat`).
- **R4.** `parse_review` checks the head line by line (lines 1 to 10), then the findings, then the count (`Findings: <n>` against the findings listed, reported at line 5), then the verdict (`PASS` needs 0 findings, `FAIL` at least 1, reported at line 3), then the two closing lines. It returns the `Review` and `[]`, or `None` and the first problem only.
- **R5.** A `Finding` is split as the given test shows: `requirement`, `file`, `line` (an `int`), `expected` (after `expected `), `found` (after `found `, to the end of the line, `|` allowed there).

### Part 2: the repository

- **R6.** `check_reports(root)` returns the problems of `root/docs/progress.md` (a missing file gives one problem, `missing` at line 1), then those of each `*.md` file in `root/docs/reviews/` in name order (a missing folder gives none). Other files in that folder are ignored.
- **R7.** For each review: the file name must be a spec in `root/docs/phases/` (`no spec docs/phases/<name>`, line 1, checked first, before the text); the heading's id must be `phase_of(<name>)` (the message shows the literal text `<id>` when the name has none); after the review parses, `docs/progress.md` must hold an entry for its phase (`no progress entry for Phase <id>`, line 1). An entry with a problem does not count.
- **R8.** Paths in problems are relative to `root` and use `/` (`docs/reviews/phase-02a-contracts.md`).
- **R9.** No message includes text from the documents beyond the phase id and the file name; the messages are those of the table.

### Part 3: the command and the conventions

- **R10.** `reports.py` imports only the standard library (no Pydantic, no `conductor` module); parsing reads only what `check_reports` is given.
- **R11.** `scripts/check_reports.py` takes `--root PATH` (default: the repository, the folder above `scripts/`), prints each problem's `text` on standard output in order, then `Reports OK.`, `1 problem.`, or `<n> problems.`, and exits 0 when there is none, else 1. It has `main(argv: list[str] | None = None) -> int` and ends with `if __name__ == "__main__":  # pragma: no cover` and `sys.exit(main())`, as `check.py` does.
- **R12.** Run on this repository after the progress entry is written, it prints `Reports OK.` (the two existing reviews and three entries pass unchanged).

### The edits to `docs/phase-conventions.md`

1. In "For the coder", the Acceptance table, add this row after the `git status --short` row:

   ```text
   | `.venv/bin/python scripts/check_reports.py`, after writing the progress entry | `Reports OK.` |
   ```

2. In "For the coder", "Report", replace the sentence `Every field is one line, or \`None\`; the architect reads these fields instead of your final message, so keep them short and literal.` with:

   ```text
   Every field is one line, or `None`; the architect reads these fields instead of your final message, so keep them short and literal. `scripts/check_reports.py` checks this form: the fields in this order, each list with at least one `  - ` line, and nothing else in the entry.
   ```

3. In "For the verifier", "Report and verdict", replace the sentence that begins `Then \`Parts that needed a repair:` with:

   ```text
   Then, after the findings and an empty line, `Parts that needed a repair: <none, or the parts>`, an empty line, and `Built beyond the spec: <none, or what>`, and after that any detail you think useful (gate output, probe output, spot-check results). The head keeps its exact lines: the heading on line 1, the five fields on lines 3 to 7, `## Findings` on line 9. When the report is written, run `.venv/bin/python scripts/check_reports.py`; it must print `Reports OK.`. If it names your report, correct the report's form (only its form) and run it again.
   ```

## Given tests

34 tests in two files (counting each parameter set). Do not change them; if one fails, the code is wrong.

`tests/unit/test_reports.py` (30 tests)

```python
from datetime import date
from pathlib import Path

import pytest

from conductor.reports import (
    Finding,
    Problem,
    ProgressEntry,
    Review,
    check_reports,
    parse_progress,
    parse_review,
    phase_of,
)

ENTRY_1 = """## Phase 1: skeleton (2026-10-25)
- Tests: 0 -> 70 (given 65)
- New public names: `events`: `EventLog`
- Changed files: 6
- Deviations:
  - An invalid event raises ValueError("event is not valid").
- Follow-ups:
  - None
"""

ENTRY_2A = """## Phase 2a: contracts (2026-10-26)
- Tests: 70 -> 114 (given 38)
- New public names: None
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - The tree had edits this phase did not make.
  - A second follow-up.
"""

PROGRESS = f"# Progress\n\nThe coding agent appends one entry per phase.\n\n{ENTRY_1}\n{ENTRY_2A}"

PASS_REVIEW = """# Review: Phase 2a

- Verdict: PASS
- Passed: 114
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gate output

Anything at all may follow, | even | pipes.
"""

FAIL_REVIEW = """# Review: Phase 2a

- Verdict: FAIL
- Passed: 112
- Findings: 2
- Approved deviations: None
- For the architect: R3's example contradicts its rule

## Findings

R3 | src/conductor/contracts/base.py:12 | expected `^` anchoring | found an unanchored pattern
Scope audit | tests/unit/test_contracts_plans.py:1 | expected the given file | found it re-sorted

Parts that needed a repair: Part 1

Built beyond the spec: a `to_dict` helper
"""


def lines_with(text: str, number: int, replacement: str | None) -> str:
    """The text with line `number` (from 1) replaced, or removed when replacement is None."""
    lines = text.split("\n")
    if replacement is None:
        del lines[number - 1]
    else:
        lines[number - 1] = replacement
    return "\n".join(lines)


def test_phase_ids_from_spec_names() -> None:
    assert phase_of("phase-01-skeleton.md") == "1"
    assert phase_of("phase-02a-contracts.md") == "2a"
    assert phase_of("phase-12-finance-domain.md") == "12"
    assert phase_of("phase-2a-contracts.md") is None
    assert phase_of("notes.md") is None


def test_a_good_progress_file() -> None:
    entries, problems = parse_progress(PROGRESS)
    assert problems == []
    assert entries == [
        ProgressEntry(
            phase="1",
            title="skeleton",
            date=date(2026, 10, 25),
            tests_before=0,
            tests_after=70,
            given=65,
            new_names="`events`: `EventLog`",
            changed_files=6,
            deviations=('An invalid event raises ValueError("event is not valid").',),
            follow_ups=("None",),
            line=5,
        ),
        ProgressEntry(
            phase="2a",
            title="contracts",
            date=date(2026, 10, 26),
            tests_before=70,
            tests_after=114,
            given=38,
            new_names="None",
            changed_files=8,
            deviations=("None",),
            follow_ups=("The tree had edits this phase did not make.", "A second follow-up."),
            line=14,
        ),
    ]


def test_a_progress_file_with_no_entries_yet() -> None:
    assert parse_progress("# Progress\n\nThe coding agent appends one entry per phase.\n") == (
        [],
        [],
    )


@pytest.mark.parametrize(
    ("number", "replacement", "line", "message"),
    [
        (
            1,
            "## Phase 2a contracts (2026-10-26)",
            1,
            "heading must be `## Phase <id>: <title> (YYYY-MM-DD)`",
        ),
        (1, "## Phase 2a: contracts (2026-02-30)", 1, "the date is not a real date"),
        (2, "- Tests: 70 -> 114", 2, "expected `- Tests: <before> -> <after> (given <n>)`"),
        (3, None, 3, "expected `- New public names: <names or None>`"),
        (4, "- Changed files: eight", 4, "expected `- Changed files: <n>`"),
        (6, "  -", 6, "expected at least one `  - ` line under Deviations"),
        (7, "- Follow ups:", 7, "expected `- Follow-ups:`"),
        (8, "- None", 8, "expected at least one `  - ` line under Follow-ups"),
        (10, "Done.", 10, "unexpected line in the entry"),
    ],
)
def test_the_first_problem_in_an_entry(
    number: int, replacement: str | None, line: int, message: str
) -> None:
    entries, problems = parse_progress(lines_with(ENTRY_2A, number, replacement))
    assert problems == [Problem("docs/progress.md", line, message)]
    assert entries == []


def test_an_entry_cut_short_is_reported_where_the_line_is_missing() -> None:
    _, problems = parse_progress(
        "## Phase 3: model client (2026-10-27)\n- Tests: 1 -> 2 (given 1)\n"
    )
    assert problems == [
        Problem("docs/progress.md", 3, "expected `- New public names: <names or None>`")
    ]


def test_a_bad_entry_does_not_hide_the_good_ones() -> None:
    broken = lines_with(ENTRY_1, 4, "- Changed files: six")
    entries, problems = parse_progress(f"# Progress\n\n{broken}\n{ENTRY_2A}")
    assert [entry.phase for entry in entries] == ["2a"]
    assert problems == [Problem("docs/progress.md", 6, "expected `- Changed files: <n>`")]
    assert problems[0].text == "docs/progress.md:6: expected `- Changed files: <n>`"


def test_a_pass_review() -> None:
    review, problems = parse_review(PASS_REVIEW, "docs/reviews/phase-02a-contracts.md")
    assert problems == []
    assert review == Review(
        phase="2a",
        verdict="PASS",
        passed=114,
        findings=(),
        approved_deviations="None",
        for_architect="None",
        repaired="none",
        built_beyond="none",
    )


def test_a_fail_review_with_its_findings() -> None:
    review, problems = parse_review(FAIL_REVIEW, "docs/reviews/phase-02a-contracts.md")
    assert problems == []
    assert review is not None
    assert (review.verdict, review.passed, review.for_architect) == (
        "FAIL",
        112,
        "R3's example contradicts its rule",
    )
    assert review.findings == (
        Finding(
            requirement="R3",
            file="src/conductor/contracts/base.py",
            line=12,
            expected="`^` anchoring",
            found="an unanchored pattern",
        ),
        Finding(
            requirement="Scope audit",
            file="tests/unit/test_contracts_plans.py",
            line=1,
            expected="the given file",
            found="it re-sorted",
        ),
    )
    assert (review.repaired, review.built_beyond) == ("Part 1", "a `to_dict` helper")


@pytest.mark.parametrize(
    ("text", "number", "replacement", "line", "message"),
    [
        (PASS_REVIEW, 1, "# Review: Phase 2", 1, "expected `# Review: Phase 2a`"),
        (PASS_REVIEW, 2, "Verdict below.", 2, "expected an empty line"),
        (PASS_REVIEW, 3, "- Verdict: PASSED", 3, "expected `- Verdict: PASS or FAIL`"),
        (PASS_REVIEW, 4, "- Passed: many", 4, "expected `- Passed: <n>`"),
        (PASS_REVIEW, 6, None, 6, "expected `- Approved deviations: <text or None>`"),
        (PASS_REVIEW, 9, "## Findings:", 9, "expected `## Findings`"),
        (PASS_REVIEW, 5, "- Findings: 1", 5, "Findings says 1 but 0 are listed"),
        (
            FAIL_REVIEW,
            12,
            "R3 | base.py | expected x | found y",
            12,
            "expected `<requirement> | <file>:<line> | expected <...> | found <...>` or `None`",
        ),
        (FAIL_REVIEW, 3, "- Verdict: PASS", 3, "a PASS review has no findings"),
        (PASS_REVIEW, 3, "- Verdict: FAIL", 3, "a FAIL review lists at least one finding"),
        (
            PASS_REVIEW,
            13,
            "Parts repaired: none",
            13,
            "expected `Parts that needed a repair: <parts or none>`",
        ),
        (
            PASS_REVIEW,
            15,
            "Built beyond: none",
            15,
            "expected `Built beyond the spec: <what or none>`",
        ),
    ],
)
def test_the_first_problem_in_a_review(
    text: str, number: int, replacement: str | None, line: int, message: str
) -> None:
    path = "docs/reviews/phase-02a-contracts.md"
    review, problems = parse_review(lines_with(text, number, replacement), path)
    assert (review, problems) == (None, [Problem(path, line, message)])


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_checking_a_repository(tmp_path: Path) -> None:
    write(tmp_path, "docs/progress.md", PROGRESS)
    write(tmp_path, "docs/phases/phase-01-skeleton.md", "# Phase 1: skeleton\n")
    write(tmp_path, "docs/phases/phase-02a-contracts.md", "# Phase 2a: contracts\n")
    write(tmp_path, "docs/phases/phase-02b-report-checker.md", "# Phase 2b: report checker\n")
    write(tmp_path, "docs/reviews/phase-02a-contracts.md", PASS_REVIEW)
    assert check_reports(tmp_path) == []
    write(tmp_path, "docs/reviews/phase-02b-report-checker.md", PASS_REVIEW.replace("2a", "2b"))
    write(tmp_path, "docs/reviews/phase-09-later.md", PASS_REVIEW.replace("2a", "9"))
    write(tmp_path, "docs/reviews/README.txt", "not a review")
    assert check_reports(tmp_path) == [
        Problem("docs/reviews/phase-02b-report-checker.md", 1, "no progress entry for Phase 2b"),
        Problem("docs/reviews/phase-09-later.md", 1, "no spec docs/phases/phase-09-later.md"),
    ]


def test_a_repository_without_a_progress_file(tmp_path: Path) -> None:
    assert check_reports(tmp_path) == [Problem("docs/progress.md", 1, "missing")]
```

`tests/e2e/test_check_reports_script.py` (4 tests)

```python
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
```

## Tests to write

In `tests/unit/test_reports_more.py` (critical module: every line and branch), each with its deciding input:

- A review that ends right after `None` (no closing lines): the problem is at the line after the last.
- A review whose findings block reaches the end of the file without the closing lines.
- `Findings: 2` with one finding listed: `Findings says 2 but 1 are listed`, line 5.
- Lines 8 and 10 not empty: `expected an empty line` at each.
- `- Findings: x` and `- For the architect:` with nothing after the colon and space.
- A review file `notes.md` in `docs/reviews/`, with `docs/phases/notes.md` existing: the heading check fails because `phase_of("notes.md")` is `None` (expect ``expected `# Review: Phase <id>` `` with the literal text `<id>`).
- An entry heading with a phase id `0` or `2ab`; `## Notes` between two entries (a heading that is not an entry: its problem, then the next entry still parsed).
- A review for a phase whose only entry has a problem: `no progress entry for Phase <id>`.

## Rules for this phase

- **Critical module**: `reports.py` at 100% of lines and branches; it joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **Standard library only** in `reports.py` (R10): it must stay importable by a script without the package's settings.
- **The existing documents are not edited.** If R12 fails on them, the parser is wrong; if you believe the documents are, stop and report.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md` (as edited here, so including its new last row), with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 34 = 148 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_reports.py tests/e2e/test_check_reports_script.py --no-cov`, exactly `34 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/reports.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.`, exit 0;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) (pydantic|conductor)" -- src/conductor/reports.py`
  - `git diff HEAD -- docs/reviews docs/progress.md | grep "^-" | grep -v "^---"` (no line removed from existing reports)
- `git diff --stat HEAD -- tests src/conductor/contracts src/conductor/events.py` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 2b: report checker (YYYY-MM-DD)`, with `Tests: 114 -> <passed> (given 34)`.
