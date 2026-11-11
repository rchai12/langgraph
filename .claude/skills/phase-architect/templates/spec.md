# Phase NNx: <name>

## Goal

<One paragraph: what exists after this phase that did not before.>

Decided with the owner (YYYY-MM-DD):
- **<decision>.** <one line of why>

Decided by the architect, within those answers:
- <choice, and the reason>

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (<rules that bite>), `docs/architecture.md` ("<sections>")
- <real modules and tests the phase builds on, with the names to look at>

## Starting state

Phase <NN-1> is built and verified, and everything is committed: N is `{{var:N}}`. **Sections: <sections>.** <What does not exist yet.> No new dependency.

## Scope

| Path | What |
|---|---|
| `<path>` | <given / new / one change> (Part n) |
| `<test paths>` | given |
| `<coder test paths>` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- <what a capable coder would over-deliver: extra options, refactors, later phases>
- Any change to <protected modules>.

## Dependencies

None new.

## Design

### Part 1: <area>

<Exact names, signatures, messages, and behaviour. Given code as {{file:...}} blocks.>

## Facts

From a spike on YYYY-MM-DD. <Only facts read from the real library, model, or server, with synthetic inputs.>

## Requirements

### Part 1: <area>

- **R1.** <testable behaviour>

### Part n: the rules

- **Rn.** Only the Scope's paths change. No earlier test changes <except the given edits>.
- **Rn.** <the coverage requirement>

## Given tests

{{var:GIVEN}} new tests in <k> files (counting each parameter set). Do not change them; if one fails, the code is wrong. Before your change, <which fail, and why>.

`<path>` (<count> tests)

{{file:<path>}}

## Tests to write

Each with its deciding input:

- In `<path>`:
  - R<n>: <behaviour>, with <deciding input>.

## Rules for this phase

- <the rules of AGENTS.md that bite, restated>
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first <sections>`; at least N + {{var:GIVEN}} = {{var:MIN}} passed;
- the given files: `.venv/bin/python -m pytest <given paths> --no-cov`, exactly `{{var:GIVEN_RUN}} passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="<modules>" --fail-under=100`;
- `grep -c "^## Phase NNx: " docs/progress.md` prints `1`, and then `.venv/bin/python scripts/check_reports.py --phase NNx` prints `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "<pattern, no \b>" -- <paths>`
- `git diff --stat HEAD -- <protected paths>` prints nothing.

## Report

As in `docs/phase-conventions.md`, headed `## Phase NNx: <name> (YYYY-MM-DD)`, with `Tests: {{var:N}} -> <passed> (given {{var:GIVEN}})`.
