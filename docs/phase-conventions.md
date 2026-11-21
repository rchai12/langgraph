# Phase conventions

Every phase spec and verification guide follows this document. A spec states only what is particular to its phase and points here for the rest. Where a spec says something different, the spec wins.

The role entry points and baseline, isolation, evidence and correction procedures
are in [ai-workflow.md](ai-workflow.md). Implementation and independent review
are separate assignments.

## For the coder

### Before you start

- The spec, its guide and its given files are committed and the tree is clean: `git status --short` prints nothing.
- Read the spec and its Corrections section and the given files in full. A standard coder does not read verification guides or reviews; the owner hands back findings. Resolve unrelated changes through the shared isolation procedure before implementation.
- From Phase 2 on: run `.venv/bin/python scripts/check.py --quiet`. It must end with `All checks passed.`. The passed counts of its `tests` Sections table add up to the number the spec calls **N** (the previous phase's progress entry records it).

### Sections

The tests are grouped into the sections of `tests/sections.toml`. Each spec names its own under "Sections" in its Starting state, for example `cli, core`.

- While you work, run a section alone: `.venv/bin/python scripts/check.py --section core` (no coverage, seconds).
- Your check is `.venv/bin/python scripts/check.py --first <the spec's sections>`: its sections' tests run first, and the full run, coverage, and gates follow only once they all pass. Fix a failing section before anything else.
- **When coverage falls short**, a behaviour has no test. Write a test that checks what the uncovered line or branch does, from the spec, not one that only runs it. If the line can never run, or the spec does not need it, remove it and say so in your progress entry. Never add `# pragma: no cover` (unless the spec allows one) and never change a given test to reach the number.
- A new test file belongs in the section of the code it tests. If `core` would take it otherwise, add a pattern to `tests/sections.toml`, and list that file in your Scope.
- Your tests go in the module's existing `test_<module>.py`, or in a new file named for the behaviour they cover (`test_<module>_<behaviour>.py`), the file the spec's "Tests to write" names. Never a name that says when it was added (`_more`, `_extra`, a phase id): `tests/unit/test_suite_layout.py` fails on one.

### Scope

- Change only the paths in the spec's Scope table. You may add private helpers inside them. Any other production file, existing test, or given file stays as it is unless the spec lists it.
- **Given files** (tests, fakes, configuration, the probe) are never changed. From Phase 9f they are committed with the spec and listed in its "Given files" table; `git diff HEAD --stat -- <given files>` prints nothing. In Phase 9e and earlier specs they are embedded blocks, copied exactly. If a given test fails, the code is wrong. If you believe a given file itself is wrong, stop and report; do not edit it.
- The probe `docs/verification/probe-NNx.py` is a given file the coder only runs, by the path Acceptance gives. A standard coder reads nothing else under `docs/verification/`.
- Build nothing from "Out of scope", even when it would be easy.

### Rules that hold in every phase

- **Commands** start with `.venv/bin/python` (or `.venv/bin/conductor`). Never type `python`, `python3`, `ruff`, or `pytest` on their own. Do not activate the virtual environment, and do not create one. Install packages only when the spec has a step for it.
- **Git.** Do not commit. Never run `git restore`, `git checkout`, `git reset`, `git stash`, or `git clean`.
- **Real systems.** Do not run the agent against a real Ollama model, a real MCP server, a mailbox, or the `finances` data. Tests replace them. The owner runs the real thing after verification.
- **Tests** use synthetic data only, touch no network, and read time and ids only through replaced `conductor.clock.now` and `conductor.ids.new_id`.
- Everything in `AGENTS.md` applies.

### Acceptance

`.venv/bin/python scripts/accept.py --phase <id>` runs the spec's Acceptance table and its searches in order, prints one line per row, and keeps each row's full output in the log folder it names. It does not judge a row; compare each line with "Must show". Unless the spec adds more, the table holds:

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first <the spec's sections>` | last line `All checks passed.`; the summary lists `tests (<sections>): passed`; in the `tests` step 0 failed, 0 skipped, 0 xfailed, no warnings summary, and at least N plus the spec's given test count passed; every line of the `Sections:` table shows 0 failed |
| `.venv/bin/python -m pytest <the given test files> --no-cov` | exactly the spec's given test count passed |
| the spec's coverage command | `.venv/bin/python -m coverage report --include=… --fail-under=100`, run right after `check.py` on the data that run left: exit 0 and its `TOTAL` line at `100%` |
| `.venv/bin/python docs/verification/probe-NNx.py` (from Phase 9f) | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- <the given files>` (from Phase 9f) | no output |
| each of the spec's searches | no output, or exactly the lines the spec names |
| `git status --short` | only the paths in the Scope table |
| `.venv/bin/python scripts/check_reports.py --phase <the spec's phase id>`, after writing the progress entry | `Reports OK.` |

### Report

Write the entry with `scripts/progress.py` (`--phase`, `--title`, `--date`, `--tests-before`, `--tests-after`, `--given`, `--names`, `--changed`, and one `--deviation` or `--follow-up` per item). It appends the entry at the end of `docs/progress.md`, or replaces this phase's own entry on a rerun, in exactly this form, and refuses an entry out of form. Every field is one line, or `None`; the architect reads these fields instead of your final message, so keep them short and literal. `scripts/check_reports.py` checks this form: the fields in this order, each list with at least one `  - ` line, and nothing else in the entry.

```markdown
## Phase NN: <the spec's title> (YYYY-MM-DD)
- Tests: <N> -> <passed after> (given <the spec's given count>)
- New public names: `<module>`: `<name>`, `<name>`; `<module>`: `<name>` (or None)
- Changed files: <how many paths git status --short lists>
- Deviations:
  - <one line each: a choice the spec left open, or anything the spec did not ask for> (or None)
- Follow-ups:
  - <one line each: something the next phase or the architect should know> (or None)
```

In your final message give `accept.py`'s output as it printed it, and for each requirement the name of a test (or the probe line) that covers it.

### When you stop

Still write the phase entry using the exact schema above. Put
`Stopped: <requirement/command> | <observation> | <what allows completion>` as the
first Follow-ups item. Use actual measured counts and identify unrun gates;
never report blocked work as accepted. Preserve earlier entries. Workflow
maintenance has no application phase id and is recorded separately.

## For the verifier

- Do not modify any file in the repository, except to write your report (below). Report findings only. The work under review is uncommitted: "the diff" is `git status --short` plus `git diff HEAD` plus the untracked files, read before you write the report.
- Run the guide's gates exactly as written, from the repository root: `.venv/bin/python scripts/accept.py --phase <id> --guide` runs its Gates and Searches in order and prints one line per row. The first gate is `scripts/check.py --quiet --first <the spec's sections>`; if a section fails, report it with the table's rerun command.
- **Scope audit**: `git status --short` shows only the spec's Scope paths; given files are unchanged (`git diff HEAD --stat` on them prints nothing; for Phase 9e and earlier, identical to the blocks in the spec); no existing test or unlisted module changed.
- The probe: from Phase 9f, run the committed `docs/verification/probe-NNx.py` from the repository root. For Phase 9e and earlier, save the guide's embedded probe **outside the repository**, run it from the root with `.venv/bin/python <path>`, and delete it afterwards. Every check line must start with `ok`, matching `probe_skeleton.py`; the last line must be `FAILURES 0`.
- Judge code by what it does, never by resemblance to another way of writing it.
- **Coverage reached the wrong way is a finding**: a test that runs a line but asserts nothing about what it does, a `# pragma: no cover` the spec did not allow, or code the spec requires removed to close a gap.
- **Spot checks**: use an isolated scratch copy of the reviewed bytes and its own imports, through `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<node id>' --row S<n> --root <scratch copy>`. It confirms the original deciding test passes, makes the one exact change, runs the test, restores the saved bytes, and prints one line; confirm it failed for the intended reason. Collection or setup failures do not prove the mutation was caught. Confirm the reviewed tree is unchanged. Never use `git checkout` or `git restore`.

### Report and verdict

Write your report to `docs/reviews/<the spec's file name>`. It is the only file you write; the owner commits it with the phase. It starts with this block, each field on one line:

```markdown
# Review: Phase NN

- Verdict: PASS (or FAIL)
- Passed: <the count from the tests step>
- Findings: <how many>
- Approved deviations: <one line, or None>
- For the architect: <one line the architect should act on, or None>
```

Then, under `## Findings`, one line per finding in this form, or `None`:

`<requirement id or section> | <file>:<line> | expected <...> | found <...>`

Then, after the findings and an empty line, `Parts that needed a repair: <none, or the parts>`, an empty line, and `Built beyond the spec: <none, or what>`, and after that any detail you think useful (gate output, probe output, spot-check results). The head keeps its exact lines: the heading on line 1, the five fields on lines 3 to 7, `## Findings` on line 9. When the report is written, run `.venv/bin/python scripts/check_reports.py --phase <the phase id>`; it must print `Reports OK.`. If it names your report, correct the report's form (only its form) and run it again.

If the verdict is FAIL, send the coder each finding as: the requirement, what was observed, and what is required. Do not prescribe the code.
