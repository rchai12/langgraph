# Phase NNx: <name>

## Goal

<One paragraph: what exists after this phase that did not before.>

Decided with the owner (YYYY-MM-DD):
- **<decision>.** <one line of why>

Decided by the architect, within those answers:
- <choice, and the reason>

## Read first

- The given files below, in full: they are the contract.
- <real modules and tests the phase builds on, with the names to look at>
- `docs/architecture.md` ("<section>") only where this phase changes it.

## Starting state

Phase <NN-1> is built and verified, and everything is committed: N is `{{var:N}}`. **Sections: <sections>.** <What does not exist yet.> No new dependency.

## Scope

| Path | What |
|---|---|
| `<path>` | <new / one change> (Part n) |
| `<coder test paths>` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- <what a capable coder would over-deliver: extra options, refactors, later phases>
- Any change to a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: <area>

<Exact names, signatures, messages, and behaviour.>

## Facts

Checked on YYYY-MM-DD. <Facts from installed library source or small offline synthetic spikes; use ScriptedModel and fake servers. Live-system facts become owner checks before building.>

## Requirements

### Part 1: <area>

- **R1.** <testable behaviour>

### Part n: the rules

- **Rn.** Only the Scope's paths change; given files stay byte-identical.
- **Rn.** <the coverage requirement>

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, <which fail, and why>.

| File | What it is |
|---|---|
| `<tests/unit/test_x.py>` | <what it pins> ({{var:K1}} tests from <f> functions) |
| `docs/verification/probe-NNx.py` | the probe, run by its path in Acceptance |

Given test count: **{{var:GIVEN}}**.

## Tests to write

Each with its deciding input:

- In `<path>` (the module's `test_<module>.py`, or a new `test_<module>_<behaviour>.py`; never `_more` or a phase id):
  - R<n>: <behaviour>, with <deciding input>.

## Rules for this phase

- <the rules of AGENTS.md that bite, restated>
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase NNx` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first <sections>` | last line `All checks passed.`; at least {{var:MIN}} passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='<modules>' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest <given test paths> --no-cov -q` | `{{var:GIVEN}} passed` |
| `.venv/bin/python docs/verification/probe-NNx.py` | last line `FAILURES 0` |
| `git diff HEAD --stat -- <given files> docs/verification/probe-NNx.py <protected paths>` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase NNx: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase NNx` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E '<pattern, no \b>' -- <paths>
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `<name>`, with `--tests-before {{var:N}} --given {{var:GIVEN}}`.
