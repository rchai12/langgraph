# Verify Phase NNx: <name>

Spec: `docs/phases/phase-NNx-<slug>.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase NNx` on your own report.

**First, check that the coder ran.** If `git status --short` lists none of <the coder's new files or changed modules>, stop. Report under "For the architect" that there is no implementation to verify, and write no review file, because a FAIL review without a progress entry breaks `check_reports.py` on `main`.

The coder:
- <what the coder did, one line per part>

## 1. Gates

N is `{{var:N}}`. Sections: <sections>.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first <sections>` | last line `All checks passed.`; at least {{var:MIN}} passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="<modules>" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest <given paths> --no-cov` | exactly `{{var:GIVEN_RUN}} passed` |
| `grep -c "^## Phase NNx: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase NNx` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- <protected paths>` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "<pattern, no \b>" -- <paths>`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | <named tests; a probe check; a place to read> | <observation> |

## 4. Probe

Save the probe outside the repository, run it from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok`, and the last must be `FAILURES 0`.

It checks:
- <one line per check>

A stop at its `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

{{file:probe_NNx.py}}

## 5. The coder's tests and spot checks

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change, run the deciding test, see it fail, and restore. Run them with `PYTHONDONTWRITEBYTECODE=1` and `-vv`. Restore with the reverse edit, not by copying a saved file back. Afterwards, run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.

Write down what each broken run printed. A different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | <one-line change> | `<test id>` | <traced output> | <traced output> |

Reasonable variations that are correct: <list>.

## 6. Project rules

- <the searches, and the rules of AGENTS.md this phase touches>

## 7. Out of scope

Each must be absent:
- <the spec's Out of scope, one line each>

## 8. Progress log

The entry exists, headed `## Phase NNx: <name> (...)`, with `Tests: {{var:N}} -> <passed> (given <GIVEN>)`, and each deviation it lists is real and justified.
