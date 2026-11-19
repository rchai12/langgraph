# Verify Phase NNx: <name>

Spec: `docs/phases/phase-NNx-<slug>.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-NNx-<slug>.md`.

## First: establish that the coder ran

- No `## Phase NNx: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-NNx-<slug>.md docs/verification/phase-NNx-<slug>.md <given files>` must succeed: the gates judge against a committed baseline.

The coder:
- <what the coder did, one line per part>

## 1. Gates

N is `{{var:N}}`. Given count: {{var:GIVEN}}. `.venv/bin/python scripts/accept.py --phase NNx --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first <sections>` | last line `All checks passed.`; at least {{var:MIN}} passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='<modules>' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest <given test paths> --no-cov -q` | `{{var:GIVEN}} passed` |
| G4 | `.venv/bin/python docs/verification/probe-NNx.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- <given files> docs/verification/probe-NNx.py <protected paths>` | no output |
| G6 | `git status --short --untracked-files=all` | only the Scope paths |
| G7 | `grep -c '^## Phase NNx: ' docs/progress.md` | `1` |
| G8 | `.venv/bin/python scripts/check_reports.py --phase NNx` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | <named tests; a probe check; a place to read> | <observation> |

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-NNx.py` (G4). It checks:
- <one line per check the given tests do not reach>

A stop at its own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

```sh
git grep --untracked -n -E '<pattern, no \b>' -- <paths>
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spotNNx`, then copy in the uncommitted Scope files and link `.venv`). For each row run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spotNNx`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | <one-line change> | `<test id>` | <traced output> | <traced output> |

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.
- <list>

## 7. Out of scope

Each must be absent:
- <the spec's Out of scope, one line each>

## 8. Verdict

Write `docs/reviews/phase-NNx-<slug>.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase NNx`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase NNx` must print `Reports OK.`
