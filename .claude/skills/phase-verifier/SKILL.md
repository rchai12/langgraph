---
name: phase-verifier
description: >-
  Verify one named Conductor phase against its verification guide, as the
  verifier, and write the review. Use only when the owner invokes it with a
  phase id (/phase-verifier 9f). Never changes the implementation.
disable-model-invocation: true
---

# Phase verifier (Conductor)

You verify exactly one phase, the one the owner names (`$ARGUMENTS`), against the uncommitted work of a coder in another session. The only file you write is `docs/reviews/<the spec's file name>`. Never repair code, rewrite the spec, commit or push.

## Read, in this order

1. The spec: `docs/phases/phase-<NNx>-*.md`, **its Corrections section first** if it has one.
2. The guide: `docs/verification/phase-<NNx>-*.md`. Its first section can end the review early; do it before anything else.
3. `docs/phase-conventions.md`, "For the verifier", when it changed since your last review (`git log -1 --format=%cd -- docs/phase-conventions.md`) or you haven't read it in this project before.
4. The coder's progress entry for this phase (by range, from its `## Phase` heading).
5. The diff: `git status --short --untracked-files=all`, `git diff HEAD`, and each untracked file. Read code by range, mainly to place each spot check's edit; the gates already run the tests.

`AGENTS.md` is already in your context through `CLAUDE.md`; don't read it again. `docs/ai-workflow.md` holds the isolation procedure for mixed scope and permitted evidence reuse; read it when the guide or the tree needs it.

## Stop early

- No progress entry and no Scope path changed: the coder didn't run. Tell the owner, and write no review: `check_reports.py` requires a progress entry for every review.
- An entry whose first `Follow-ups` item starts with `Stopped:`: write the FAIL review the conventions describe, run the given test files once for `Passed`, and stop.

## Keep output small

- **Gates and searches in one command**: `.venv/bin/python scripts/accept.py --phase <id> --guide`. It runs the guide's gates in order and then its searches, and prints one line per row (`G1: All checks passed.` with the Sections table, `Q1: empty`, or the matching lines). Each row's full output is in the log folder it names. Compare each line with the guide's "Must show"; the script doesn't judge it. For a guide of Phase 9e or earlier, save the embedded probe outside the repository and run it as that guide says; its probe gate's placeholder path does not run.
- **Spot checks** run in a scratch copy of the reviewed bytes, never in the repository: `git clone -q . <scratch>/spot<NNx>`, copy in each changed and untracked Scope file, and link `.venv`. Write each row's change as an exact old and new text (one match in the module the coder wrote), then `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot<NNx>`. It checks the test passes unchanged, applies the change, runs the test with that copy's `src` on `PYTHONPATH`, always restores the bytes, and prints one line (`S7 fails: ...`, `S8 passes`, `S9 no test ran`, `error: ...`). Rerun by hand with `-vv` only for a row whose line isn't the guide's "Broken" value. A collection error is not a caught mutation.
- After the spot checks, the repository's `git status --short` and `git diff --stat` are as they were before.

## Judgment stays yours

A spot check whose result differs from its "Broken" value is a note; one that passes means either the code is wrong or the test can't see the change. Trace it through schema constraints, fake clocks and later reads, decide which, and say it in `For the architect`. Decide whether each deviation in the progress entry is one the guide's "Reasonable variations" or the spec allows; one in an approval, policy or escalation path must fail closed. Separate environment and baseline failures from code defects; do not waive a literal gate yourself.

## Report

Write `docs/reviews/<the spec's file name>` in the form the conventions give: the five-line head, `## Findings`, the `Parts that needed a repair` and `Built beyond the spec` lines. After them, a digest instead of prose:

- one line per gate (`G1: All checks passed, 1120 passed`, `G4: FAILURES 0`);
- one line per spot check (`S7 fails: assert 503 == 404`, `S8 differs: <what> (note)`);
- `searches: silent`.

Then `.venv/bin/python scripts/check_reports.py --phase <id>` must print `Reports OK.` For a FAIL, give the owner each finding as requirement, observation and required result, without prescribing code.
