# Verify Phase 2b: report checker

Spec: `docs/phases/phase-02b-report-checker.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. This phase changes that document: read its edited version, including the new last step for your own report.

The coder created `conductor.reports` (critical) and `scripts/check_reports.py`, added `reports.py` to the critical modules, edited `docs/phase-conventions.md` and `docs/testing.md`, copied two given test files (34 tests), and wrote `tests/unit/test_reports_more.py`.

## 1. Gates

N is `114`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 148 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; the `critical coverage` step passed (it now includes `reports.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/reports.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_reports.py tests/e2e/test_check_reports_script.py --no-cov` | exactly `34 passed` |
| `.venv/bin/python scripts/check_reports.py` (before you write your report) | `Reports OK.`, exit 0 |
| `git diff --stat HEAD -- tests src/conductor/contracts src/conductor/events.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) (pydantic|conductor)" -- src/conductor/reports.py`
2. `git diff HEAD -- docs/reviews docs/progress.md | grep "^-" | grep -v "^---"`

## 2. Scope paths

`git status --short` lists only: `src/conductor/reports.py`, `scripts/check_reports.py`, `scripts/critical_modules.txt`, `docs/testing.md`, `docs/phase-conventions.md`, the two given test files, `tests/unit/test_reports_more.py`, `docs/progress.md`. The given test files equal the spec's blocks. `git diff HEAD -- docs/phase-conventions.md` shows exactly the three edits of the spec, word for word; `docs/testing.md` and `scripts/critical_modules.txt` exactly theirs.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_phase_ids_from_spec_names` | pass |
| R2 | `test_a_good_progress_file`, `test_a_progress_file_with_no_entries_yet`, `test_a_bad_entry_does_not_hide_the_good_ones`; probe "damaged documents never crash" | pass; ok |
| R3 | `test_the_first_problem_in_an_entry`, `test_an_entry_cut_short_is_reported_where_the_line_is_missing` | pass |
| R4 | `test_a_pass_review`, `test_the_first_problem_in_a_review`; probe "damaged documents never crash" | pass; ok |
| R5 | `test_a_fail_review_with_its_findings`; probe "a found text may hold pipes" | pass; ok |
| R6, R8 | `test_checking_a_repository`, `test_a_repository_without_a_progress_file` | pass |
| R7 | `test_checking_a_repository`; probe "a review for an entry with a problem"; the coder's `notes.md` test | pass; ok |
| R9 | probe "messages hold no document text"; read every message in `reports.py` against the spec's table | ok; the same texts |
| R10 | search 1 | no output |
| R11 | `test_check_reports_script.py`; probe "the script finds the repository from anywhere"; read the end of the script | pass; ok; `# pragma: no cover` only on the `__main__` line |
| R12 | gate 4; probe "the real documents parse" | `Reports OK.`; ok |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it.

```python
"""Probe for Phase 2b. Save outside the repository; run from the repository root with
.venv/bin/python <path>. Every line ends in ok; the last line is FAILURES 0."""

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

FAILURES = 0
ROOT = Path.cwd()


def check(name: str, test: Callable[[], None]) -> None:
    global FAILURES
    try:
        test()
        print(f"ok   {name}")
    except Exception as error:  # noqa: BLE001 - a probe reports every failure and goes on
        FAILURES += 1
        print(f"FAIL {name}: {type(error).__name__}: {error}")


def expect(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def the_real_documents_parse() -> None:
    from conductor.reports import parse_progress, parse_review

    entries, problems = parse_progress((ROOT / "docs/progress.md").read_text("utf-8"))
    expect(problems == [], repr(problems))
    expect([entry.phase for entry in entries][:3] == ["1", "2a", "2b"], repr(entries))
    for name, passed in (("phase-01-skeleton.md", 70), ("phase-02a-contracts.md", 114)):
        path = f"docs/reviews/{name}"
        review, problems = parse_review((ROOT / path).read_text("utf-8"), path)
        expect(problems == [] and review is not None, repr(problems))
        expect((review.verdict, review.passed, review.findings) == ("PASS", passed, ()), name)


GOOD_REVIEW = """# Review: Phase 3

- Verdict: FAIL
- Passed: 10
- Findings: 1
- Approved deviations: None
- For the architect: None

## Findings

R2 | src/conductor/llm/decide.py:40 | expected an escalation | found a retry | then a log

Parts that needed a repair: Part 2

Built beyond the spec: none
"""

GOOD_ENTRY = """## Phase 3: model client (2026-10-30)
- Tests: 148 -> 180 (given 30)
- New public names: `llm.decide`: `decide`
- Changed files: 7
- Deviations:
  - None
- Follow-ups:
  - None
"""


def damaged_documents_never_crash_and_give_at_most_one_problem() -> None:
    from conductor.reports import parse_progress, parse_review

    path = "docs/reviews/phase-03-model-client.md"
    for text, parse, single in (
        (GOOD_REVIEW, lambda t: parse_review(t, path), True),
        (GOOD_ENTRY, parse_progress, False),
    ):
        lines = text.split("\n")
        variants = []
        for index in range(len(lines)):
            variants.append("\n".join(lines[:index] + lines[index + 1 :]))
            variants.append("\n".join(lines[: index + 1] + lines[index:]))
            variants.append("\n".join(lines[:index] + [lines[index] + " x"] + lines[index + 1 :]))
            variants.append("\n".join(lines[:index]))
        for variant in variants:
            found, problems = parse(variant)
            expect(len(problems) <= 1, f"{len(problems)} problems")
            if problems and single:
                expect(found is None, "a review and a problem")


def a_found_text_may_hold_pipes() -> None:
    from conductor.reports import parse_review

    review, problems = parse_review(GOOD_REVIEW, "docs/reviews/phase-03-model-client.md")
    expect(problems == [], repr(problems))
    expect(review.findings[0].found == "a retry | then a log", review.findings[0].found)
    expect(review.findings[0].line == 40, "line")


def messages_hold_no_document_text() -> None:
    from conductor.reports import parse_progress, parse_review

    secret = "SECRET4417"
    path = "docs/reviews/phase-03-model-client.md"
    texts = [
        parse_review(GOOD_REVIEW.replace("- Passed: 10", f"- Passed: {secret}"), path)[1],
        parse_review(GOOD_REVIEW.replace("R2 | src", f"{secret} src"), path)[1],
        parse_progress(GOOD_ENTRY.replace("- Changed files: 7", f"- Changed: {secret}"))[1],
        parse_progress(GOOD_ENTRY + f"{secret}\n")[1],
    ]
    for problems in texts:
        expect(len(problems) == 1, repr(problems))
        expect(secret not in problems[0].text, problems[0].text)


def the_script_finds_the_repository_from_anywhere() -> None:
    with tempfile.TemporaryDirectory() as folder:
        done = subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/check_reports.py")],
            capture_output=True,
            text=True,
            cwd=folder,
        )
    expect((done.stdout, done.returncode) == ("Reports OK.\n", 0), done.stdout + done.stderr)


def a_review_for_an_entry_with_a_problem() -> None:
    from conductor.reports import Problem, check_reports

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "docs/phases").mkdir(parents=True)
        (root / "docs/reviews").mkdir()
        (root / "docs/phases/phase-03-model-client.md").write_text("# Phase 3\n", "utf-8")
        (root / "docs/reviews/phase-03-model-client.md").write_text(GOOD_REVIEW, "utf-8")
        broken = GOOD_ENTRY.replace("- Changed files: 7\n", "")
        (root / "docs/progress.md").write_text(f"# Progress\n\n{broken}", "utf-8")
        found = check_reports(root)
        expect(
            found
            == [
                Problem("docs/progress.md", 6, "expected `- Changed files: <n>`"),
                Problem(
                    "docs/reviews/phase-03-model-client.md", 1, "no progress entry for Phase 3"
                ),
            ],
            repr(found),
        )


for name, test in [
    ("the real documents parse", the_real_documents_parse),
    ("damaged documents never crash", damaged_documents_never_crash_and_give_at_most_one_problem),
    ("a found text may hold pipes", a_found_text_may_hold_pipes),
    ("messages hold no document text", messages_hold_no_document_text),
    (
        "the script finds the repository from anywhere",
        the_script_finds_the_repository_from_anywhere,
    ),
    ("a review for an entry with a problem", a_review_for_an_entry_with_a_problem),
]:
    check(name, test)

print(f"FAILURES {FAILURES}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_reports_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the count check removed (`parse_review`) | `test_the_first_problem_in_a_review`, `- Findings: 1` over `None` | `Findings says 1 but 0 are listed` | the review parses |
| 2 | the finding pattern makes `:<line>` optional (`parse_review` or its helper) | `test_the_first_problem_in_a_review`, line 12 `R3 \| base.py \| ...` | the finding problem | the review parses |
| 3 | parsing stops at the first bad entry (`parse_progress`) | `test_a_bad_entry_does_not_hide_the_good_ones` | entries `["2a"]` | `[]` |
| 4 | leading zeros kept (`phase_of`) | `test_phase_ids_from_spec_names`, `phase-01-skeleton.md` | `"1"` | `"01"` |
| 5 | the spec check skipped (`check_reports`) | `test_checking_a_repository`, `phase-09-later.md` | `no spec docs/phases/phase-09-later.md` | `no progress entry for Phase 9` |
| 6 | absolute paths in problems (`check_reports`) | `test_checking_a_repository` | `docs/reviews/...` | `/private/...` |
| 7 | exit code 0 always (`scripts/check_reports.py` `main`) | `test_one_problem` | 1 | 0 |
| 8 | a list may have no `  - ` item (`parse_progress`) | `test_the_first_problem_in_an_entry`, line 8 `- None` | the Follow-ups problem | the entry parses |
| 9 | non-empty lines allowed after an entry (`parse_progress`) | `test_the_first_problem_in_an_entry`, line 10 `Done.` | `unexpected line in the entry` | the entry parses |

(`\|` in the table stands for `|`.)

Reasonable variations that are correct: regular expressions or plain string checks; a small line cursor class; parsing the head with a list of (prefix, message) pairs; the script importing `conductor.reports` directly.

## 6. Project rules

- Searches 1 and 2.
- Every message in `reports.py` is one of the spec's table, with only a phase id, a count, or a file name filled in.

## 7. Out of scope

Each must be absent: checks of the review body after `Built beyond the spec:`; comparisons of numbers between documents; a step in `scripts/check.py`, a git hook, or a `conductor` command for the checker; automatic fixes; JSON output; edits to existing entries or reviews.

## 8. Progress log and your own report

The entry exists, headed `## Phase 2b: report checker (...)`, with `Tests: 114 -> <passed> (given 34)`, and each deviation it lists is real and justified. After writing your report, run `.venv/bin/python scripts/check_reports.py` as the edited conventions require; it must print `Reports OK.`.
