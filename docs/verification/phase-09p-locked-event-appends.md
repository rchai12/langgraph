# Verify Phase 9p: Locked event appends

Spec: `docs/phases/phase-09p-locked-event-appends.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09p-locked-event-appends.md`.

## First: establish that the coder ran

- No `## Phase 9p: ` entry in `docs/progress.md` and no Scope path changed since 66f5612: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09p-locked-event-appends.md docs/verification/phase-09p-locked-event-appends.md tests/unit/test_event_appends.py tests/integration/test_event_log_writers.py docs/verification/probe-09p.py` must succeed. The gates judge against a committed baseline.
- The build may be uncommitted or already committed. The diff under review is `git diff $(git log -1 --format=%h -- docs/phases/phase-09p-locked-event-appends.md)` plus untracked files. G5 and G6 use the spec's commit and 66f5612, so they hold either way.

The coder:
- locked each append with an exclusive `flock` on the run file;
- found the next `seq` from the bytes added since the log last looked, with two new refusals (a shrunk file, an unfinished line);
- made `read` hold a shared `flock`;
- wrote `tests/unit/test_event_locks.py`.

## 1. Gates

N is `1518`. Given count: 19. `.venv/bin/python scripts/accept.py --phase 9p --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1537 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/events.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_event_appends.py tests/integration/test_event_log_writers.py --no-cov -q` | `19 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09p.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff $(git log -1 --format=%h -- docs/phases/phase-09p-locked-event-appends.md) --stat -- tests/unit/test_event_appends.py tests/integration/test_event_log_writers.py docs/verification/probe-09p.py` | no output |
| G6 | `git diff 66f5612 --stat -- src scripts tests pyproject.toml ':!src/conductor/events.py' ':!tests/unit/test_event_appends.py' ':!tests/integration/test_event_log_writers.py' ':!tests/unit/test_event_locks.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| G8 | `grep -c '^## Phase 9p: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9p` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_two_logs_on_one_run_take_turns_without_repeating_a_seq`, `test_threads_with_their_own_logs_never_repeat_a_seq`; probe check 1 | pass; `ok` |
| R2 | `test_an_append_after_another_process_wrote_continues_its_sequence`, `test_processes_appending_together_never_repeat_a_seq` | pass |
| R3 | `test_an_append_waits_for_the_file` (2 cases), `test_a_refused_payload_releases_the_file`, `test_a_corrupt_file_releases_the_file`; the coder's `os.write` failure test; search 8 | pass; silent |
| R4 | `test_a_log_reads_only_the_lines_it_has_not_seen`; probe check 2; the coder's 500-line count test | pass; `ok`; pass |
| R5 | `test_lines_another_writer_added_are_checked` (5 cases); probe check 3 | pass; `ok` |
| R6 | `test_a_file_that_shrank_is_corrupt`, `test_an_unfinished_last_line_is_refused_by_a_new_log`, `test_an_existing_empty_file_starts_at_one`; probe check 3; the coder's two-runs test | pass; `ok`; pass |
| R7 | `test_a_read_waits_for_an_append_in_progress`, `test_readers_do_not_wait_for_each_other` | pass |
| R8 | `tests/unit/test_events.py`, `tests/unit/test_event_files.py` and the runtime and CLI tests (in G1) | pass |
| R9 | G2, G5 to G7; searches 7 to 9 | as given; silent |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

Read `append` against the spec's Part 1: the lock is taken before the size is read, the line is written and synced before the remembered size and `seq` change, and the descriptor is closed in a `finally`. Read Part 2's three size cases, and that every line goes through `_parse_line`.

## 3. Probe

The probe is the given file `docs/verification/probe-09p.py` (G4). Its oracle is a table: the file is a count of good lines, and each log knows how many it has seen. An append gets the next `seq` and parses exactly the lines its log has not seen. The probe counts `events._parse_line` calls during each append. It checks:
- 300 schedules of 2 to 4 logs on one run (1 to 40 appends, the log chosen at random): every append's `seq` is the oracle's, and the file reads back as 1 to n;
- in those schedules, every append parsed exactly the oracle's number of lines;
- 200 damaged files. After a short schedule, the probe adds one fault and a fresh log, then appends with the logs in random order. The faults are a bad line, an unfinished line, a line rewritten in place and a file cut short. For the last two, only one log appends. Each append must refuse with the oracle's message, or continue with its `seq`. A refusal must leave the file's bytes unchanged. The oracle's outcomes reach each fault and both outcomes at least 20 times.

Before handover the architect ran it on today's code. All three checks printed `FAIL` (repeated `seq`s stop today's reads), and the run reached `FAILURES 3`.

A stop at its own `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names. (Before the build, the eighth matched today's `read`, which Part 3 replaces.)

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/events.py
git grep --untracked -n -E 'lockf|fcntl\.fcntl|LOCK_NB|O_TRUNC|truncate\(|write_bytes|read_bytes' -- src/conductor/events.py
git grep --untracked -n -E 'flock|import fcntl' -- src ':!src/conductor/events.py'
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09p`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match). Then run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09p`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect. A pass is a finding, unless you trace it to a test that cannot see the change (say which in "For the architect").

Each change below is the shape of an edit; copy the exact old text from the coder's line.

| # | Change (module) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | in `append`, replace the `fcntl.flock(..., fcntl.LOCK_EX)` call with `pass` (`events.py`) | `tests/unit/test_event_appends.py::test_an_append_waits_for_the_file[writer]` | waiting `True` | waiting `False` |
| S2 | in `read`, replace `fcntl.LOCK_SH` with `fcntl.LOCK_EX` (`events.py`) | `tests/unit/test_event_appends.py::test_readers_do_not_wait_for_each_other` | waiting `False` | waiting `True` |
| S3 | in `read`, replace the `fcntl.flock(..., fcntl.LOCK_SH)` call with `pass` (`events.py`) | `tests/unit/test_event_appends.py::test_a_read_waits_for_an_append_in_progress` | waiting `True` | waiting `False` |
| S4 | in the next-seq code, replace the size-less-than comparison's condition with `False` (`events.py`) | `tests/unit/test_event_appends.py::test_a_file_that_shrank_is_corrupt` | refused, `is shorter than when it was last read` | no refusal |
| S5 | in the next-seq code, replace the remembered size used as the read offset with `0`, and the remembered `seq` used for numbering with `0` (`events.py`) | `tests/unit/test_event_appends.py::test_a_log_reads_only_the_lines_it_has_not_seen` | seq `4` | `line 1 is not a valid event` |
| S6 | in the next-seq code, replace the condition that detects bytes after the last newline with `False` (`events.py`) | `tests/unit/test_event_appends.py::test_lines_another_writer_added_are_checked[unfinished]` | refused, `line 2 is not finished` | no refusal |

Notes for tracing:
- S1: without the lock the thread finishes inside 0.3 seconds, so `waiting` is `False`.
- S2: the test holds a shared lock; an exclusive request waits for it.
- S4: the file is 2 lines and the log remembers 3. With the check gone, the coder's code may then read an empty or negative range, or reach "equal" by another path. Whatever happens, no `shorter` refusal is raised. If it raises another `EventLogCorrupt`, that is the different-failure note above.
- S5: from offset 0 the log re-parses line 1, which the test overwrote with `x`.
- S6: without the check, the trailing `LINE_2` (valid, `seq` 2) is parsed as a complete line or ignored. Either way the append writes instead of refusing.

Spot rows that make the same change in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Reading the new bytes with `os.pread` on the append descriptor, or with a second read-only descriptor opened after the lock is taken.
- What each log remembers kept as a dict of tuples, a small dataclass, or two dicts.
- `read` reading in one call or in a loop until end of file, through the locked descriptor.
- A private helper for the next-seq step, as long as every line goes through `_parse_line`.
- Extra behaviour tests in `tests/unit/test_event_locks.py`.

## 7. Out of scope

Each must be absent:
- Any change to `runs()`, an index, cache file or sidecar, or a lock file.
- A lock held between appends, a `close` method, a timeout, or a non-blocking lock.
- `lockf` or `fcntl.fcntl` locks.
- A changed line format, `Event` model, `RunSummary`, existing message, file mode, or `read`'s acceptance of a valid last line without a newline.
- Any change outside `events.py` and the Scope paths, to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09p-locked-event-appends.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9p`), with a digest: one line per gate, one per spot check, and `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9p` must print `Reports OK.`
