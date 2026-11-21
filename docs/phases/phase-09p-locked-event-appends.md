# Phase 9p: Locked event appends

## Goal

`EventLog.append` learns a run's next `seq` once per `EventLog`, by reading the whole file. After that it counts in memory. Two `EventLog`s on one run file, in two threads or two processes, therefore mint the same `seq`. The second one's line then makes the file unreadable (`line N has seq M, expected N`). Today only the run lease keeps that from happening. A reader can also see a half-written last line while an append is in progress.

This phase does four things:
- locks each append;
- finds the next `seq` from the file under that lock, parsing only the lines this `EventLog` has not seen;
- refuses a file that shrank or ends in an unfinished line;
- has `read` wait for an append in progress.

The line format, the messages for damaged lines, `read`'s result and `runs()` stay as today.

Decided with the owner (2026-11-21):
- **Scope.** Appends only. The run listing gets its own later slice (9s, after 9r).
- **Ownership.** An exclusive `fcntl.flock` on the run's file is held around finding the next `seq`, writing the line and `fsync`. Any number of `EventLog`s, threads and processes may append to one run.
- **Next seq.** Each `EventLog` remembers, per run, the file size and the last `seq` it has seen. Under the lock it parses only the bytes added since then. A file smaller than remembered is corrupt. `read` still parses every line.
- **Readers.** `read` holds a shared `flock` while it reads. It waits for an append in progress, never for another reader.

Decided by the architect, within those answers:
- The lock is taken on the run file itself, opened through `private.open_file` as today, so the file is still created owner-only. There is no separate lock file.
- Two new refusals, both `EventLogCorrupt` with constant text plus the file name and a line number:
  - `<run>.jsonl is shorter than when it was last read`;
  - `<run>.jsonl line N is not finished`, for bytes after the last newline.

  Complete lines are checked first, in order, with today's three messages, so an earlier bad line is reported before an unfinished one.
- A refused append writes nothing and releases the lock, whatever it raised.
- `_parse_line` stays the only function that parses a line, for appends and reads (the probe counts its calls).
- What each `EventLog` remembers is one size and one `seq` per run it has appended to. This grows with the runs that one instance writes, as `_counts` does today.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/events.py` (all of it) and `src/conductor/private.py` (`open_file`).
- `tests/unit/test_events.py` and `tests/unit/test_event_files.py`: they pin today's line format, messages and modes, and must keep passing unchanged.

## Starting state

Phase 9o is built and verified, and everything is committed at 66f5612: N is `1518`. **Sections: core.** `events.py` is critical and 100% covered. `EventLog` is created in `runtime.open_runtime`, the eval command and the `runs` commands. No new dependency (`fcntl` is standard library).

## Scope

| Path | What |
|---|---|
| `src/conductor/events.py` | locked appends, sequence discovery from the file, the two new refusals, the shared lock in `read` |
| `tests/unit/test_event_locks.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- `runs()` and the listing (9s), and any index, cache file or sidecar next to the run files.
- A lock held between appends, a `close` method, a timeout or a non-blocking lock.
- `fcntl.lockf` or `fcntl.fcntl` locks. On macOS they interact with `flock`, so mixing the two can deadlock.
- Changes to the line format, the `Event` model, `RunSummary`, the existing messages or `read`'s acceptance of a valid last line without a newline.
- Changes outside `events.py`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: an append

```python
def append(self, run_id, kind, *, node=None, payload=None) -> Event:
```

1. Check the run id as today.
2. Open the run file with `private.open_file(path, os.O_RDWR | os.O_APPEND)` and take `fcntl.flock(descriptor, fcntl.LOCK_EX)`.
3. Find the next `seq` (Part 2).
4. Build the event and its line as today (`_event`, `_event_line`), write it, `fsync`, and remember the new size and `seq`.
5. Close the descriptor in a `finally`, which releases the lock, on success and on every error.

A payload that is refused (`ValueError`) is refused while the lock is held, writes nothing, and leaves the remembered size and `seq` unchanged.

### Part 2: the next seq

The `EventLog` keeps, per run, the size `S` and `seq` `Q` it last saw. An unseen run has `S = 0` and `Q = 0`. Under the lock:
- the file's size (`os.fstat`) is less than `S`: raise `EventLogCorrupt(f"{run_id}.jsonl is shorter than when it was last read")`;
- it equals `S`: the next `seq` is `Q + 1`;
- it is larger: read the bytes from offset `S` to the end (`os.pread`). Each complete line is parsed by `_parse_line` with line numbers `Q + 1`, `Q + 2`, and so on, with today's three checks and messages. Bytes after the last newline raise `EventLogCorrupt(f"{run_id}.jsonl line {n} is not finished")`. Then `S` and `Q` become the file's size and the last parsed `seq`.

### Part 3: a read

`read` opens the file read-only (missing: `RunNotFound` as today) and takes `fcntl.flock(descriptor, fcntl.LOCK_SH)`. It reads the whole file through that descriptor and closes it. Then it parses as today, including today's acceptance of a valid last line without a newline.

## Facts

Checked on 2026-11-21 on macOS with Python 3.12, outside the repository:
- `flock` is per open file. A second descriptor on the same file in the same process waits for an exclusive lock, and so does another process. A shared lock waits while an exclusive one is held. Closing the holding descriptor releases its lock.
- `fcntl.lockf` on another descriptor of a file whose `flock` is held waited indefinitely: on macOS the two kinds of lock interact. Hence flock only.
- Today two `EventLog`s on one run, alternating, write `seq` 1 twice. The file is then refused with `line 2 has seq 1, expected 2`.
- The given tests hold a lock themselves on a read-only descriptor, then start the work in a thread and check that it is still waiting after 0.3 seconds. The cross-process tests start `sys.executable -c` children with `PYTHONPATH` set to the package's `src` folder, so they need no network.
- On today's code the probe printed `FAIL` for all three checks and reached its end.

## Requirements

### Part 1: one writer at a time

- **R1.** Appends to one run from several `EventLog`s, in turn or in threads, get `seq` 1 to n with no repeat, and the file reads back whole.
- **R2.** The same holds across processes: an append after another process wrote continues from that process's last line.
- **R3.** An append waits while another descriptor holds an exclusive or shared `flock` on the run file. A refused append, for a bad payload or a corrupt file, releases the file and writes nothing.

### Part 2: the next seq from the file

- **R4.** An append parses only the lines its own `EventLog` has not seen: a line rewritten in place among the seen ones is not noticed by that log, but a new `EventLog` refuses it with today's message.
- **R5.** Lines another writer added are checked with today's three messages. Bytes after the last newline are `line N is not finished`, after any earlier bad line.
- **R6.** A file smaller than the one this log last saw is `<run>.jsonl is shorter than when it was last read`. A new log continues it. An existing empty file starts at `seq` 1.

### Part 3: readers

- **R7.** `read` waits for an append in progress (an exclusive lock), not for another reader (a shared lock).

### Part 4: the same log

- **R8.** The line format, the file mode, every existing message and `read`'s result are unchanged. The existing event, runtime and CLI tests pass unchanged.
- **R9.** Only the Scope's paths change. Given files and existing tests stay byte-identical. There is no `noqa` or `pragma: no cover` in `events.py`, and it stays 100% covered (lines and branches).

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, 15 of the given tests fail and 4 pass. The 4 are guards that hold today because nothing locks:
- readers do not wait for each other;
- a refused payload releases the file;
- a corrupt file releases the file;
- an existing empty file starts at 1.

| File | What it is |
|---|---|
| `tests/unit/test_event_appends.py` | R1, R3 to R7: logs taking turns, threads, waiting for a writer and a reader, a read waiting, readers not waiting, the file released after a refusal, only new lines read, lines another writer added (5 cases), a shrunk file, an unfinished line, an empty file (17 tests from 12 functions) |
| `tests/integration/test_event_log_writers.py` | R2: an append after another process wrote, and three processes appending together with this one (2 tests from 2 functions) |
| `docs/verification/probe-09p.py` | the probe, run by its path in Acceptance |

Given test count: **19**.

## Tests to write

In `tests/unit/test_event_locks.py` (section `core`):
- R3: an append that fails at `os.write` (patched to raise `OSError`) releases the file, and the next append by the same log gets the same `seq` the failed one would have had.
- R4: with `events._parse_line` wrapped to count its calls, a log's first append to a 500-line file parses 500 lines and its second append parses none.
- R6: a log that appended to two runs keeps them apart: lines another writer adds to one run do not affect the other run's next `seq`.
- R9: any branch of `events.py` that the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- The event log stays append-only: no rewrite, truncation or repair of a run file, ever. A damaged file is refused.
- Error messages stay constant text plus identifiers (file name, line number, seq). Nothing echoes a line's content.
- Time and ids still come from `clock.now()` and `ids.new_id()`.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9p` runs every row and search below in order and prints one line each; compare each with "Must show". `SPEC` below is the commit that added this spec: `$(git log -1 --format=%h -- docs/phases/phase-09p-locked-event-appends.md)`. Rows that use it stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1537 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/events.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_event_appends.py tests/integration/test_event_log_writers.py --no-cov -q` | `19 passed` |
| `.venv/bin/python docs/verification/probe-09p.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09p-locked-event-appends.md) --stat -- tests/unit/test_event_appends.py tests/integration/test_event_log_writers.py docs/verification/probe-09p.py` | no output |
| `git diff 66f5612 --stat -- src scripts tests pyproject.toml ':!src/conductor/events.py' ':!tests/unit/test_event_appends.py' ':!tests/integration/test_event_log_writers.py' ':!tests/unit/test_event_locks.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9p: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9p` (after writing progress) | `Reports OK.` |

The second diff row compares against 66f5612 (the commit before this spec), excluding the Scope and given files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match). Before the build, the eighth matches today's `read` (`path.read_bytes()`), which Part 3 replaces with a read through the locked descriptor.

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Locked event appends`, with `--tests-before 1518 --given 19`.
