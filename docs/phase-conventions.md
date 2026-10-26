# Phase conventions

Every phase spec and verification guide follows this document. A spec states only what is particular to its phase and points here for the rest. Where a spec says something different, the spec wins.

## For the coder

### Before you start

- The spec is committed and the tree is clean: `git status --short` prints nothing.
- From Phase 2 on: run `.venv/bin/python scripts/check.py`. It must end with `All checks passed.`. Note the number passed in its `tests` step: the spec calls it **N**.

### Sections

The tests are grouped into the sections of `tests/sections.toml`. Each spec names its own under "Sections" in its Starting state, for example `cli, core`.

- While you work, run a section alone: `.venv/bin/python scripts/check.py --section core` (no coverage, seconds).
- Your check is `.venv/bin/python scripts/check.py --first <the spec's sections>`: its sections' tests run first, and the full run, coverage, and gates follow only once they all pass. Fix a failing section before anything else.
- **When coverage falls short**, a behaviour has no test. Write a test that checks what the uncovered line or branch does, from the spec, not one that only runs it. If the line can never run, or the spec does not need it, remove it and say so in your progress entry. Never add `# pragma: no cover` (unless the spec allows one) and never change a given test to reach the number.
- A new test file belongs in the section of the code it tests. If `core` would take it otherwise, add a pattern to `tests/sections.toml`, and list that file in your Scope.

### Scope

- Change only the paths in the spec's Scope table. You may add private helpers inside them. Any other production file, existing test, or given file stays as it is unless the spec lists it.
- Given files (tests, scripts, configuration) are copied exactly as shown, and never changed. If a given test fails, the code is wrong. If you believe a given file itself is wrong, stop and report; do not edit it.
- Build nothing from "Out of scope", even when it would be easy.

### Rules that hold in every phase

- **Commands** start with `.venv/bin/python` (or `.venv/bin/conductor`). Never type `python`, `python3`, `ruff`, or `pytest` on their own. Do not activate the virtual environment, and do not create one. Install packages only when the spec has a step for it.
- **Git.** Do not commit. Never run `git restore`, `git checkout`, `git reset`, `git stash`, or `git clean`.
- **Real systems.** Do not run the agent against a real Ollama model, a real MCP server, a mailbox, or the `finances` data. Tests replace them. The owner runs the real thing after verification.
- **Tests** use synthetic data only, touch no network, and read time and ids only through replaced `conductor.clock.now` and `conductor.ids.new_id`.
- Everything in `AGENTS.md` applies.

### Acceptance

Unless the spec adds more, run before you report:

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first <the spec's sections>` | last line `All checks passed.`; the summary lists `tests (<sections>): passed`; in the `tests` step 0 failed, 0 skipped, 0 xfailed, no warnings summary, and at least N plus the spec's given test count passed; every line of the `Sections:` table shows 0 failed |
| `.venv/bin/python -m pytest <the given test files> --no-cov` | exactly the spec's given test count passed |
| the spec's coverage command | `.venv/bin/python -m coverage report --include=… --fail-under=100`, run right after `check.py` on the data that run left: exit 0 and its `TOTAL` line at `100%` |
| each of the spec's searches | no output, or exactly the lines the spec names |
| `git status --short` | only the paths in the Scope table |

### Report

Add an entry at the end of `docs/progress.md` in exactly this form. Every field is one line, or `None`; the architect reads these fields instead of your final message, so keep them short and literal.

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

In your final message give the `Sections:` table and the last ten lines of `scripts/check.py`'s output, the output line of each other acceptance command, and for each requirement the name of a test (or the probe line) that covers it.

## For the verifier

- Do not modify any file in the repository, except to write your report (below). Report findings only. The work under review is uncommitted: "the diff" is `git status --short` plus `git diff HEAD` plus the untracked files, read before you write the report.
- Run the guide's gates exactly as written, from the repository root. The first gate is `scripts/check.py --first <the spec's sections>`; if a section fails, report it with the table's rerun command.
- **Scope audit**: `git status --short` shows only the spec's Scope paths; given files are identical to the blocks in the spec; no existing test or unlisted module changed.
- Save the guide's probe script **outside the repository**, run it from the repository root with `.venv/bin/python <path>`, and delete it afterwards. Every line must end in `ok`; the last line must be `FAILURES 0`.
- Judge code by what it does, never by resemblance to another way of writing it.
- **Coverage reached the wrong way is a finding**: a test that runs a line but asserts nothing about what it does, a `# pragma: no cover` the spec did not allow, or code the spec requires removed to close a gap.
- **Spot checks**: for each row of the guide's spot-check table, make the named one-line change in a copy of the module outside the repository or restore it from a copy you made first (never with `git checkout` or `git restore`), run the deciding test, and confirm it fails; then restore the file and confirm `git diff` is as before.

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

Then `Parts that needed a repair: <none, or the parts>` and `Built beyond the spec: <none, or what>`, and after that any detail you think useful (gate output, probe output, spot-check results).

If the verdict is FAIL, send the coder each finding as: the requirement, what was observed, and what is required. Do not prescribe the code.
