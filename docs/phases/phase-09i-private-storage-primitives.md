# Phase 9i: Private storage primitives

## Goal

One small module, `conductor.private`, creates every folder and file the agent keeps under the data folder: folders `0700` and files `0600`, whatever the umask, and every missing parent along the way, not only the last one. The event log, the store, the runtime's checkpoints, the MCP server logs and the evaluation reports all use it instead of their own copies. Creation is safe when two processes (the web server and a CLI command) create the same path at once. `conductor doctor` creates the data folder through the same module and fails when an existing data folder is open to other users.

Decided with the owner (2026-11-20):
- **Doctor reports a loose data folder and changes nothing.** An existing data folder with any group or other permission bit gives `FAIL` with a `chmod 700` hint, so doctor exits 1. Doctor stays a check that never alters the owner's files.
- **Writers never tighten what exists.** Only folders and files the code creates get `0700` and `0600`. An existing folder or file keeps its mode (earlier tests pin this for the runs and MCP log folders). Doctor is the one place that notices a loose data folder.
- **Every folder the code creates is private.** When several levels are missing (`data/` and `data/runs/`), each one is created `0700`. Today only the last one is, and `data/` gets the umask default, usually `0755`.
- **"Already exists" is success.** A folder or file that another process creates between the check and the create is accepted and keeps the mode its creator gave it. An evaluation report keeps its exclusive create: a report name is never reused.

Decided by the architect, within those answers:
- The module is `src/conductor/private.py`, imports only the standard library, and is a critical module (every line and branch covered): it decides who can read the household's logs and finance data.
- Each created file is `fchmod`ed to `0600` and each created folder `chmod`ed to `0700`, because the umask can remove owner bits from the mode given to `os.open` and `os.mkdir` (spike below).
- Creating a file tries `O_CREAT | O_EXCL` first: only that tells the code whether it made the file, and so whether it may set the mode. On `FileExistsError` it opens the existing file with the caller's flags, unless the caller asked for `O_EXCL`.
- `ensure_dir` refuses a path that exists and is not a folder with `NotADirectoryError`, so a mistake shows at the folder, not at the next `open`.
- The doctor's "not writable" check comes first; the permission check runs only on a folder doctor could write in.

## Read first

- The given files below, in full: they are the contract.
- The six copies this phase replaces: `EventLog._write_line` in `src/conductor/events.py`, `_prepare` in `src/conductor/store.py`, the start of `open_runtime` in `src/conductor/runtime.py`, `save_report` in `src/conductor/evals/report.py`, `_log_path` in `src/conductor/mcp_client/client.py`, and `check_data_folder` in `src/conductor/diagnostics.py`.
- The tests that pin today's modes, which must keep passing unchanged: `tests/unit/test_event_files.py::test_an_existing_folder_keeps_its_mode`, `tests/integration/test_mcp_client_more.py::test_an_existing_log_folder_keeps_its_mode`, `tests/integration/test_runtime.py` (the `checkpoints.db`, `-shm` and `-wal` modes), `tests/integration/test_runtime_more.py::test_private_files_are_kept_and_the_connection_closes`, `tests/unit/test_store_more.py::test_a_missing_folder_is_private_and_an_empty_file_gets_the_schema`, `tests/unit/test_eval_report.py::test_a_saved_report_reads_back` and `test_a_report_name_is_never_reused`, `tests/e2e/test_cli_doctor.py::test_everything_ready` and `test_old_python_and_a_data_folder_that_cannot_be_made`.
- `docs/architecture.md` ("Storage") only where this phase changes it.

## Starting state

Phase 9h is built and verified, and everything is committed: N is `1271`. **Sections: cli, core.** `conductor.private` does not exist. Five modules each create their folder with `mkdir(parents=True, mode=0o700)` and `chmod` only the last level, and their file with `os.open(..., 0o600)` and no `fchmod`. `check_data_folder` uses `mkdir(parents=True, mode=0o700, exist_ok=True)` with no `chmod`, and reports `ok` for an existing folder whatever its mode. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/private.py` | new: the primitives (Part 1) |
| `src/conductor/events.py` | `_write_line` opens through `private.open_file` (Part 2) |
| `src/conductor/store.py` | `_prepare` becomes `private.ensure_file` (Part 2) |
| `src/conductor/runtime.py` | `open_runtime` makes `checkpoints.db` with `private.ensure_file` (Part 2) |
| `src/conductor/evals/report.py` | `save_report` opens through `private.open_file` (Part 2) |
| `src/conductor/mcp_client/client.py` | `_log_path` uses `private.ensure_file` (Part 2) |
| `src/conductor/diagnostics.py` | `check_data_folder` (Part 3) |
| `scripts/critical_modules.txt` | one new line, `private.py` |
| `tests/unit/test_private_more.py` | new: the coder's tests of the module |
| `tests/e2e/test_cli_doctor_private_more.py` | new: the coder's doctor tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Tightening, or warning about, any existing folder or file other than doctor's data-folder check: no `chmod` of an existing path anywhere.
- Doctor checking the modes of files or subfolders inside the data folder, or offering to fix anything.
- `src/conductor/acceptance.py` and its log folder (phase tooling under the temporary folder, not the data folder).
- Any change to the event log's line format, its sequence counting or its reading; to the store's schema or its version check; to SQLite's connection settings.
- Sharing the 32-hex id, the request bounds or the time format (9j), or any other refactor of the touched modules.
- A setting, or any change to `config.py`, `cli/`, `web/` or `contracts/`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: `conductor.private`

`src/conductor/private.py` imports only the standard library (`errno`, `os`, `stat`, `pathlib`).

```python
DIR_MODE = 0o700
FILE_MODE = 0o600

def ensure_dir(folder: Path) -> None: ...
def open_file(path: Path, flags: int) -> int: ...
def ensure_file(path: Path) -> None: ...
def open_to_others(path: Path) -> bool: ...
```

`ensure_dir(folder)`:
1. Collect the missing levels: `folder`, then its parents upward, while the level does not exist.
2. Create them from the top-most missing level down. For each: `os.mkdir(level, DIR_MODE)`, then `os.chmod(level, DIR_MODE)`. If `os.mkdir` raises `FileExistsError`, another process made that level first: accept it, leave its mode, and go on to the next level. Any other `OSError` propagates.
3. If `folder` is not a directory now, raise `NotADirectoryError(errno.ENOTDIR, "not a folder", str(folder))`.

A level that existed before the call keeps its mode.

`open_file(path, flags)` returns an open descriptor the caller closes:
1. `ensure_dir(path.parent)`.
2. Try `os.open(path, flags | os.O_CREAT | os.O_EXCL, FILE_MODE)`. On success, `os.fchmod(descriptor, FILE_MODE)` and return the descriptor. If `fchmod` raises, close the descriptor and let the error propagate.
3. On `FileExistsError`: if `flags` contains `os.O_EXCL`, re-raise it. Otherwise return `os.open(path, flags)`. The existing file keeps its mode and its content (the caller's flags decide whether it is appended to).

`ensure_file(path)` is `os.close(open_file(path, os.O_RDONLY))`: a new file is empty and `0600`, an existing one is untouched.

`open_to_others(path)` is `stat.S_IMODE(path.stat().st_mode) & 0o077 != 0`.

### Part 2: the five writers

Each imports the module (`from conductor import private`) and calls it in place of its own copy. Their behaviour is otherwise unchanged.

| Where | Today | After |
|---|---|---|
| `EventLog._write_line` | folder block, then `os.open(path, O_WRONLY \| O_APPEND \| O_CREAT, 0o600)` | `descriptor = private.open_file(path, os.O_WRONLY \| os.O_APPEND)`, then the same write, `fsync` and close |
| `store._prepare(path)` | folder block, then an exclusive create if missing | `private.ensure_file(path)` (the function may stay as a one-line wrapper or be replaced by the call) |
| `open_runtime` | data-folder block, then an exclusive create of `checkpoints.db` if missing | `private.ensure_file(settings.checkpoints_path)`, before `sqlite3.connect` |
| `save_report` | folder block, then `os.open(path, O_WRONLY \| O_CREAT \| O_EXCL, 0o600)` | `descriptor = private.open_file(path, os.O_WRONLY \| os.O_EXCL)`, then the same write, `fsync` and close |
| `client._log_path` | folder block, then an exclusive create if missing | `private.ensure_file(path)`, then `return path` |

After this, no module under `src/` other than `private.py` and `acceptance.py` calls `mkdir`, `makedirs`, `os.open`, `chmod` or `fchmod`, or writes a `0o` mode literal (a search in Acceptance).

SQLite's `-wal` and `-shm` side files take the main file's mode, so `checkpoints.db` being `0600` before the first connect keeps them `0600` (`tests/integration/test_runtime.py` pins this).

### Part 3: doctor's data-folder check

```python
def check_data_folder(folder: Path) -> Check:
    name = f"data folder {folder}"
    probe = folder / ".doctor-write-test"
    try:
        private.ensure_dir(folder)
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return Check("FAIL", name, "not writable")
    if private.open_to_others(folder):
        return Check("FAIL", name, f"open to other users (run: chmod 700 {folder})")
    return Check("ok", name)
```

The printed line is `FAIL  data folder <folder>: open to other users (run: chmod 700 <folder>)`. Doctor changes no mode. `NotADirectoryError` is an `OSError`, so a data folder path that is a file stays `not writable`.

## Facts

Checked on 2026-11-20 with the project's Python 3.12.16 on macOS, in a scratch folder with no project code:
- Under umask `0o277`, `os.open(path, O_RDONLY | O_CREAT | O_EXCL, 0o600)` makes a `0o400` file and `os.mkdir(path, 0o700)` a `0o500` folder; `os.fchmod` on the read-only descriptor and `os.chmod` then give `0o600` and `0o700`. So the mode argument alone is not enough, and a parent left at `0o500` refuses the next level (today's `PermissionError` in the given umask-277 cases).
- `pathlib.Path.mkdir` calls `os.mkdir(self, mode)`, so a test that replaces `os.mkdir` sees either spelling.
- An SQLite database created empty at `0600` (umask `0o022`) and then opened in WAL mode gets `-wal` and `-shm` at `0600`.

## Requirements

### Part 1: `conductor.private`

- **R1.** `DIR_MODE` is `0o700` and `FILE_MODE` is `0o600`.
- **R2.** `ensure_dir` creates every missing level of the path, each `0700` under any umask, and leaves every existing level, and the levels above, with their mode.
- **R3.** `ensure_dir` accepts a level another process creates first and leaves its mode; it raises `NotADirectoryError` when the path, or a level above it, is a file, and leaves that file unchanged.
- **R4.** `open_file` creates a missing file (and its folders) at `0600` under any umask with the caller's flags; it opens an existing file with the caller's flags and leaves its mode and content; with `O_EXCL` it refuses an existing file with `FileExistsError`; if `fchmod` fails it closes the descriptor and the error propagates.
- **R5.** `ensure_file` leaves a new empty `0600` file, leaves an existing one unchanged, and accepts a file another process creates first.
- **R6.** `open_to_others` is true exactly when the path's mode has a bit in `0o077`.

### Part 2: the writers

- **R7.** The event log, the store, `open_runtime`, `save_report` and the MCP log create their folders and files only through `conductor.private`: every new level `0700`, every new file `0600`. Appending, the exclusive report name, existing modes and the SQLite side files' `0600` are unchanged.

### Part 3: doctor

- **R8.** `check_data_folder` creates a missing data folder (and its parents) through `ensure_dir`; an existing folder open to others gives the exact `FAIL` line above and keeps its mode and contents; `not writable` comes first.

### Part 4: the rules

- **R9.** `private.py` imports only the standard library and is listed in `scripts/critical_modules.txt`. Only the Scope's paths change; given files and existing tests stay byte-identical.
- **R10.** `private.py`, `diagnostics.py` and `evals/report.py` are covered 100% (lines and branches), and the critical-module gate passes.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, every given test fails except `test_a_private_existing_folder_passes`, a guard: a private data folder already passes and must keep passing. With names-only stubs nothing else passes. The umask-277 cases of the writers fail with `PermissionError`: today a parent is left at `0o500`.

| File | What it is |
|---|---|
| `tests/unit/test_private.py` | R1 to R5: the module (17 tests from 11 functions) |
| `tests/integration/test_private_writers.py` | R7: each writer under umask `0o022` and, where no SQLite is involved, `0o277` (7 tests from 5 functions) |
| `tests/e2e/test_cli_doctor_private.py` | R8: doctor on a loose, a private and a new nested data folder (6 tests from 3 functions) |
| `docs/verification/probe-09i.py` | the probe, run by its path in Acceptance |

Given test count: **30**.

## Tests to write

In `tests/unit/test_private_more.py` (section `core`):
- R4: `os.fchmod` replaced to raise `PermissionError` on a new file: `open_file` raises `PermissionError` and the descriptor it opened is closed (record the descriptor from a wrapped `os.open` and check `os.fstat` on it raises `OSError`).
- R4: a new file opened with `os.O_WRONLY | os.O_EXCL` writes and is `0600`.
- R6: `open_to_others` for `0o700` (false), `0o600` (false), `0o710` (true), `0o704` (true).
- R10: any branch of `private.py` the given tests leave uncovered, tested for what it does.

In `tests/e2e/test_cli_doctor_private_more.py` (section `cli`):
- R8: an existing data folder at `0o555` (open to others and not writable) prints `not writable`, not the `chmod` hint; restore `0o755` in a `finally` so `tmp_path` can be removed.
- R8: a data folder path whose parent is a file still prints `not writable` (the `NotADirectoryError` path).

## Rules for this phase

- Privacy: everything under the data folder is owner-only from the moment the code creates it. Never `chmod` a path the code did not create, except to restore a mode inside a test.
- Error messages are constant text plus identifiers (here a folder path). Never `str()` an `OSError` into a message.
- `contracts` imports nothing from the project, and `private.py` imports nothing from it either.
- Tests use `tmp_path` only, restore the umask in a `finally` (or the given `umask` context manager), and touch no network.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9i` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1301 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/private.py,*/conductor/diagnostics.py,*/conductor/evals/report.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_private.py tests/integration/test_private_writers.py tests/e2e/test_cli_doctor_private.py --no-cov -q` | `30 passed` |
| `.venv/bin/python docs/verification/probe-09i.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_private.py tests/integration/test_private_writers.py tests/e2e/test_cli_doctor_private.py docs/verification/probe-09i.py src/conductor/config.py src/conductor/cli src/conductor/web src/conductor/contracts src/conductor/acceptance.py` | no output |
| `git diff 181e104 --stat -- tests ':!tests/unit/test_private.py' ':!tests/integration/test_private_writers.py' ':!tests/e2e/test_cli_doctor_private.py' ':!tests/unit/test_private_more.py' ':!tests/e2e/test_cli_doctor_private_more.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9i: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9i` (after writing progress) | `Reports OK.` |

The second diff row compares against 181e104 (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/private.py src/conductor/diagnostics.py
git grep --untracked -n -E 'mkdir\(|makedirs|os\.open\(|chmod\(|0o[0-7]{3}' -- src ':!src/conductor/private.py' ':!src/conductor/acceptance.py'
git grep --untracked -n -E '^(from|import) (conductor|\.)' -- src/conductor/private.py
git grep --untracked -n -E 'str\((error|exc|exception)\)|strerror' -- src/conductor/private.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Private storage primitives`, with `--tests-before 1271 --given 30`.
