---
name: phase-coder
description: >-
  Implement one named Conductor phase from its spec in docs/phases/, as the
  coder. Use only when the owner invokes it with a phase id (/phase-coder 9f).
  Never verifies, never reads the verification guide or reviews.
disable-model-invocation: true
---

# Phase coder (Conductor)

You implement exactly one phase, the one the owner names (`$ARGUMENTS`). A second agent verifies it in another session. Do not commit, push, delegate, or start another phase.

## Before anything

`git status --short --untracked-files=all` must print nothing, and the spec, its guide and its given files must be tracked (`git ls-files --error-unmatch <paths>`). If either fails, follow the isolation procedure in `docs/ai-workflow.md`, or stop and say so. Never stash, reset, clean or commit to make the tree clean.

## Read, in this order

1. The spec: `docs/phases/phase-<NNx>-*.md` (the id zero-padded to two digits), **its Corrections section first** if it has one.
2. The given files, in full. They are the contract; skipping them means building against a guess. From Phase 9f they are committed files named in the spec's "Given files" table. In Phase 9e and earlier specs they are embedded blocks you copy exactly.
3. `docs/phase-conventions.md`, "For the coder": Sections, Scope, Acceptance, the progress entry and "When you stop".
4. The last entry of `docs/progress.md` (by range, from its last `## Phase` heading), for the previous phase's names and deviations.
5. The code the spec names, by range, only where you change it or a given test depends on it.

`AGENTS.md` is already in your context through `CLAUDE.md`; don't read it again. Read `docs/architecture.md`, `docs/testing.md` or `docs/ai-workflow.md` only for a section the spec or a stop points you to.

Never open `docs/verification/` except to run the probe by the path Acceptance gives, and never open `docs/reviews/`. Findings from a FAIL reach you from the owner.

## Build

- Change only the Scope paths; never a given file. If a given test fails, the code is wrong. If a given file itself seems wrong, stop.
- Choose the simplest reading of an open detail that satisfies the requirements, and record it as a deviation.
- Stop for a contradictory or impossible requirement, a broken given contract, or a dependency the spec does not list.

## Keep output small

- One section while you work: `.venv/bin/python scripts/check.py --quiet --section <name>`. One file: `.venv/bin/python -m pytest <file> --no-cov -q --tb=line 2>&1 | tail -15`. Read a full traceback only for a failure the line doesn't explain.
- The full check: `.venv/bin/python scripts/check.py --quiet --first <the spec's sections>`. It prints the Sections tables, the summary, a failed step's last 20 lines, and where its logs are; open a log by range only when those lines don't explain the failure.
- **Before you report**, write your entry (below), then run the whole Acceptance table and its searches in one command: `.venv/bin/python scripts/accept.py --phase <id>`. It prints one line per row (`A1: All checks passed.` with the Sections table, `Q1: empty`) and keeps each row's output in the log folder it names. Compare each line with "Must show"; the script doesn't judge it.

## Report

- **Write your entry with `scripts/progress.py`**, never by editing `docs/progress.md`: `.venv/bin/python scripts/progress.py --phase <id> --title "<the spec's title>" --date <today> --tests-before <N> --tests-after <passed> --given <count> --names "<names or None>" --changed <count>`, plus one `--deviation "..."` and one `--follow-up "..."` per item (a stop's `Stopped: <requirement/command> | <observation> | <what allows completion>` first). It appends the entry, or replaces your own phase's entry on a rerun, and refuses an entry out of form.
- Then `.venv/bin/python scripts/check_reports.py --phase <id>` must print `Reports OK.`
- **On a rerun with a Corrections section**, run the commands the correction names as live again, plus `check_reports.py`. When it names none, run `accept.py` again.
- Your final message, short and literal:
  - `accept.py`'s output as it printed it;
  - for each requirement, the test or probe line that covers it;
  - if you stopped, the `Stopped:` line.
