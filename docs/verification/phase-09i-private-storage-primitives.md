# Verify Phase 9i: Private storage primitives

Spec: `docs/phases/phase-09i-private-storage-primitives.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09i-private-storage-primitives.md`.

## First: establish that the coder ran

- No `## Phase 9i: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09i-private-storage-primitives.md docs/verification/phase-09i-private-storage-primitives.md tests/unit/test_private.py tests/integration/test_private_writers.py tests/e2e/test_cli_doctor_private.py docs/verification/probe-09i.py` must succeed: the gates judge against a committed baseline.

The coder:
- wrote `src/conductor/private.py` (`DIR_MODE`, `FILE_MODE`, `ensure_dir`, `open_file`, `ensure_file`, `open_to_others`) and listed it in `scripts/critical_modules.txt`;
- replaced the folder and file creation in `events.py`, `store.py`, `runtime.py`, `evals/report.py` and `mcp_client/client.py` with calls to it;
- made `check_data_folder` create through `ensure_dir` and fail on a data folder open to others.

## 1. Gates

N is `1271`. Given count: 30. `.venv/bin/python scripts/accept.py --phase 9i --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1301 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/private.py,*/conductor/diagnostics.py,*/conductor/evals/report.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_private.py tests/integration/test_private_writers.py tests/e2e/test_cli_doctor_private.py --no-cov -q` | `30 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09i.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_private.py tests/integration/test_private_writers.py tests/e2e/test_cli_doctor_private.py docs/verification/probe-09i.py src/conductor/config.py src/conductor/cli src/conductor/web src/conductor/contracts src/conductor/acceptance.py` | no output |
| G6 | `git diff 181e104 --stat -- tests ':!tests/unit/test_private.py' ':!tests/integration/test_private_writers.py' ':!tests/e2e/test_cli_doctor_private.py' ':!tests/unit/test_private_more.py' ':!tests/e2e/test_cli_doctor_private_more.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9i: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9i` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_modes` | passes |
| R2 | `test_every_missing_folder_is_private` (2 cases), `test_an_existing_folder_keeps_its_mode` (3 cases); probe check 1 | pass; `ok` |
| R3 | `test_a_folder_made_meanwhile_is_accepted`, `test_a_file_in_the_way_is_refused` (2 cases); probe check 3 | pass; `ok` |
| R4 | `test_open_file_creates_a_private_file` (2 cases), `test_open_file_appends_to_an_existing_file`, `test_an_exclusive_open_refuses_an_existing_file`; the coder's `fchmod` and `O_EXCL` tests; probe check 1 | pass; `ok` |
| R5 | `test_a_new_file_is_private_and_empty` (2 cases), `test_an_existing_file_is_kept`, `test_a_file_made_meanwhile_is_accepted`; probe checks 1 and 3 | pass; `ok` |
| R6 | the coder's four `open_to_others` cases; read the function | pass; the mask is `0o077` |
| R7 | `tests/integration/test_private_writers.py` (7 tests); the earlier mode tests named in the spec's "Read first" (in G1); search 8; read each of the five call sites | pass; silent; each writer calls `private` and keeps its flags (`O_APPEND` in the log, `O_EXCL` in the report) |
| R8 | `tests/e2e/test_cli_doctor_private.py` (6 tests); the coder's `0o555` and file-parent tests; `tests/e2e/test_cli_doctor.py` (in G1); probe check 2; read `check_data_folder` | pass; `ok`; the write probe runs before `open_to_others`, and no mode is changed |
| R9 | search 9; read `scripts/critical_modules.txt`; G5, G6, G7 | silent; `private.py` listed; as given |
| R10 | G1 (the critical gate), G2 | as given |

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09i.py` (G4). It checks:
- 200 random paths, 1 to 4 levels deep, with a random number of existing levels at random modes (`0700`, `0755`, `0750`, `0711`), a random umask (`022`, `077`, `277`, `002`), and `ensure_dir`, `ensure_file` or `open_file` on a new or an existing file: every new level is `0700`, every existing level keeps its mode, a new file is empty `0600`, an existing file keeps its mode and content;
- 100 random data-folder modes (owner `rwx` plus random group and other bits) through `diagnostics.check_data_folder`: `FAIL` with the exact hint exactly when a group or other bit is set, the mode and the (empty) contents unchanged; a missing nested folder gives `ok` and two `0700` levels;
- 20 rounds of 8 threads released together by a barrier, half calling `ensure_dir` and half `ensure_file` on one new 4-level path: no thread raises, and every level is `0700` and the file `0600`.

A stop at its own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

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

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09i`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09i`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | drop the `chmod` after a new level's `mkdir` (`ensure_dir`) | `tests/unit/test_private.py::test_every_missing_folder_is_private[umask-277]` | `[448, 448, 448]` | `PermissionError` |
| S2 | create only `folder` with `mkdir(parents=True)` and `chmod` it (`ensure_dir`) | `tests/unit/test_private.py::test_every_missing_folder_is_private[umask-022]` | `[448, 448, 448]` | `[493, 493, 448]` |
| S3 | `chmod` the folder whether or not it was missing (`ensure_dir`) | `tests/unit/test_private.py::test_an_existing_folder_keeps_its_mode[755]` | `(493, 448)` | `(448, 448)` |
| S4 | let `FileExistsError` from `mkdir` propagate (`ensure_dir`) | `tests/unit/test_private.py::test_a_folder_made_meanwhile_is_accepted` | no error, `0o755` kept | `FileExistsError` |
| S5 | drop the final not-a-folder check (`ensure_dir`) | `tests/unit/test_private.py::test_a_file_in_the_way_is_refused[itself]` | `NotADirectoryError` | `DID NOT RAISE` |
| S6 | drop the `fchmod` of a new file (`open_file`) | `tests/unit/test_private.py::test_open_file_creates_a_private_file[umask-277]` | `(448, 384, b'one\n')` | mode `256` |
| S7 | on `FileExistsError` re-raise whatever the flags (`open_file`) | `tests/unit/test_private.py::test_open_file_appends_to_an_existing_file` | `(420, b'one\ntwo\n')` | `FileExistsError` |
| S8 | open with `flags \| O_CREAT` and `fchmod` every time, with no `O_EXCL` attempt (`open_file`) | `tests/unit/test_private.py::test_a_file_made_meanwhile_is_accepted` | `(['raced'], 420, b'other')` | mode `384` |
| S9 | drop `os.O_EXCL` from the report's flags (`save_report`) | `tests/unit/test_eval_report.py::test_a_report_name_is_never_reused` | `FileExistsError` | `DID NOT RAISE` |
| S10 | test the mask `0o007` instead of `0o077` (`open_to_others`) | `tests/e2e/test_cli_doctor_private.py::test_an_existing_folder_open_to_others_fails[750]` | the `FAIL … open to other users` line | the `ok    data folder` line |
| S11 | call `os.open(path, flags \| os.O_CREAT, 0o600)` in place of `private.open_file` (`EventLog._write_line`) | `tests/integration/test_private_writers.py::test_the_event_log_makes_every_folder_private[umask-022]` | `[448, 448, 448]` | `FileNotFoundError` |

Notes for tracing. Modes are printed in decimal by pytest: `448` is `0o700`, `493` `0o755`, `384` `0o600`, `420` `0o644`, `256` `0o400`. S1: under umask `0o277` the level `a` is made `0o500`, so making `b` inside it is refused. S2: `Path.mkdir(parents=True)` makes the parents with the default mode `0o777` less the umask `0o022`. S5: `os.mkdir` is never reached for an existing path, so without the check nothing raises. S7: the file exists before the call, so the exclusive attempt raises and the fallback is the only open. S8: the race wrapper makes the file `0o644` on the first `O_CREAT` call; a plain `O_CREAT` open then succeeds and the unconditional `fchmod` changes it. S9: without `O_EXCL` in the caller's flags, `open_file` falls back to opening the existing report, so the second save does not raise. S11: the folder is missing and nothing creates it. Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside the Scope modules, and extra behaviour tests in the coder's two `*_more.py` files.
- `store._prepare` kept as a one-line wrapper or removed in favour of the call.
- Collecting the missing levels with `exists()` or `os.path.lexists`, and the loop written either way, as long as the top-most missing level is made first.
- `open_to_others` reading the mode with `os.stat` or `Path.stat`.
- `import errno` used or the `NotADirectoryError` built another way, as long as it is that class and its text holds no more than the path.

## 7. Out of scope

Each must be absent:
- A `chmod` of an existing path anywhere in `src/`, or a warning about one other than doctor's data-folder line.
- Doctor checking files or subfolders inside the data folder, or changing any mode.
- Any change to `acceptance.py`, `config.py`, `cli/`, `web/` or `contracts/`.
- Any change to the event log's line format, sequence counting or reading; to the store's schema or version check; to SQLite's connection settings.
- Sharing the id pattern, request bounds or time format (9j), or other refactors.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09i-private-storage-primitives.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9i`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9i` must print `Reports OK.`
