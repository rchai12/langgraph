# Phase 1: skeleton

## Goal

An installable `conductor` package with the parts every later phase stands on:

- settings that refuse any model host not on this machine;
- one place for the time and one for new ids, so tests can fix both;
- **the event log** (a critical module): the append-only record of every run, which later phases write to from every node, model call, tool call, and approval;
- `conductor doctor`, which says whether this machine is ready (Python, the data folder, Ollama, the model);
- `conductor runs list` and `conductor runs show`, to read the event log;
- `scripts/check.py` with test sections and a coverage gate on critical modules, and test guards (no network, isolated settings).

Nothing here talks to a model beyond asking Ollama which models it has. LangGraph arrives in Phase 5.

## Read first

- `AGENTS.md`, `docs/architecture.md` (sections "The event log", "State, threads, and storage", "Privacy and safety boundary"), `docs/testing.md`
- `docs/phase-conventions.md` (everything this spec does not repeat)

## Starting state

The repository holds only documents: `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `docs/`, and `.claude/`. There is no `.venv`, no `src/`, no `tests/`, no `scripts/`. `git status --short` prints nothing.

This phase has no N: before it, nothing runs. **Sections: core, cli.**

Python 3.12 is at `/opt/homebrew/bin/python3.12`. Ollama is installed on this machine; **do not** start, stop, or query it yourself, and do not pull models. Tests use a fake.

## Scope

| Path | What |
|---|---|
| `pyproject.toml` | given |
| `scripts/check.py`, `scripts/critical_modules.txt` | given |
| `tests/conftest.py`, `tests/support.py`, `tests/sections.toml` | given |
| `tests/unit/test_config.py`, `tests/unit/test_events.py`, `tests/e2e/test_cli_doctor.py`, `tests/e2e/test_cli_runs.py` | given |
| `src/conductor/__init__.py` | `__version__ = "0.1.0"` |
| `src/conductor/config.py` | `Settings`, `get_settings`, `SettingsError` (Part 1) |
| `src/conductor/clock.py`, `src/conductor/ids.py` | `now()`, `new_id()` (Part 1) |
| `src/conductor/events.py` | the event log (Part 2, critical) |
| `src/conductor/llm/__init__.py`, `src/conductor/llm/tags.py` | the model list from Ollama (Part 3) |
| `src/conductor/diagnostics.py` | the doctor's checks (Part 3) |
| `src/conductor/cli/__init__.py`, `src/conductor/cli/main.py` | the commands (Part 4) |
| `tests/unit/test_*.py`, `tests/integration/test_*.py` | the coder's own tests, if coverage needs them (Tests to write) |
| `README.md` | new: what the project is, how to install it (the two commands of Step 0), and `conductor doctor` |
| `docs/progress.md` | one new entry |

## Out of scope

- LangGraph, the `ollama` client library, MCP, FastAPI, or any dependency beyond those in the given `pyproject.toml`.
- Python's `logging` setup, log levels, or a log file other than the event log.
- Any command beyond `doctor`, `runs list`, `runs show`: no `ask`, no `--json` output, no filters, no `runs delete`.
- Pulling, starting, or calling a model; checking anything about a model beyond its name being listed.
- Rotating, compressing, or deleting event logs; locking a log against two writers.
- A `.env` file, `python -m conductor`, shell completion.

## Dependencies

Exactly those in the given `pyproject.toml`: `pydantic`, `pydantic-settings`, `typer`; for development `pytest`, `pytest-cov`, `ruff`.

### Step 0: the virtual environment

Run, from the repository root, after copying the given `pyproject.toml` and creating `src/conductor/__init__.py`:

```zsh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

These are the only install commands of this phase.

## Design

### Part 1: settings, time, ids

```python
# conductor/config.py
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
OLLAMA_HOST_MESSAGE = "must be an http address on this machine (127.0.0.1, localhost, or ::1)"
MODEL_MESSAGE = "must not be empty"

class SettingsError(Exception): ...

class Settings(BaseSettings):          # env_prefix "CONDUCTOR_"; no .env file
    data_dir: Path = Path("data")
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = "qwen3.8:27b"

    @property
    def runs_dir(self) -> Path: ...    # data_dir / "runs"

def get_settings() -> Settings: ...
```

```python
# conductor/clock.py
def now() -> datetime: ...             # datetime.now(UTC)

# conductor/ids.py
def new_id() -> str: ...               # uuid.uuid4().hex: 32 lowercase hexadecimal characters
```

### Part 2: the event log

```python
# conductor/events.py
RUN_ID_MESSAGE = "run id must be 32 lowercase hexadecimal characters"

class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    MODEL_REQUEST = "model_request"
    MODEL_REPLY = "model_reply"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    ESCALATED = "escalated"
    ERROR = "error"

class Event(BaseModel):                # frozen, extra="forbid"
    run_id: str
    seq: int                           # >= 1
    at: datetime                       # aware, UTC
    kind: EventKind
    node: str | None = None
    payload: dict[str, JsonValue] = {}

class EventLogCorrupt(Exception): ...
class RunNotFound(Exception): ...

@dataclass(frozen=True)
class RunSummary:
    run_id: str
    started_at: datetime               # the first event's `at`
    events: int

def check_run_id(run_id: str) -> str: ...

class EventLog:
    def __init__(self, folder: Path) -> None: ...
    def append(
        self,
        run_id: str,
        kind: EventKind,
        *,
        node: str | None = None,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> Event: ...
    def read(self, run_id: str) -> list[Event]: ...
    def runs(self) -> list[RunSummary]: ...
```

One file per run: `<folder>/<run_id>.jsonl`. One event per line. A line is

```python
json.dumps(<the event as JSON data>, ensure_ascii=False, sort_keys=True,
           separators=(",", ":"), allow_nan=False)
```

followed by `\n`, where `at` is written as `%Y-%m-%dT%H:%M:%S.%fZ` (always six digits of microseconds). The given test pins two whole lines.

### Part 3: the doctor's checks

```python
# conductor/llm/tags.py
class OllamaUnreachable(Exception): ...
class OllamaBadAnswer(Exception): ...

def fetch_model_names(host: str, *, timeout: float = 3.0) -> list[str]: ...
```

```python
# conductor/diagnostics.py
MIN_PYTHON = (3, 12)

@dataclass(frozen=True)
class Check:
    status: Literal["ok", "FAIL", "SKIP"]
    name: str
    detail: str = ""

    @property
    def line(self) -> str: ...

def python_version() -> tuple[int, int, int]: ...      # sys.version_info[:3]
def check_python() -> Check: ...
def check_data_folder(folder: Path) -> Check: ...
def check_ollama(host: str, model: str) -> list[Check]: ...   # the ollama check, then the model check
def run_checks(settings: Settings) -> list[Check]: ...        # python, data folder, ollama, model
def summary_line(checks: list[Check]) -> str: ...
```

### Part 4: commands

`conductor/cli/main.py` defines `app = typer.Typer(no_args_is_help=True, add_completion=False)` with the command `doctor`, and a second Typer app registered as `runs` with the commands `list` and `show RUN_ID [--payload]`. Output is plain text through `typer.echo`; no Rich tables.

## Requirements

### Part 1: settings, time, ids

- **R1.** `get_settings()` builds a new `Settings` on each call from the environment (prefix `CONDUCTOR_`; no `.env` file, no caching). Defaults: data folder `data`, Ollama host `http://127.0.0.1:11434`, model `qwen3.8:27b`.
- **R2.** `data_dir` is made absolute against the current folder with `Path.absolute()`; it is not resolved, so `..` and symbolic links stay as given. `runs_dir` is `data_dir / "runs"`.
- **R3.** `ollama_host` is accepted only when `urllib.parse.urlsplit` gives the scheme `http` and a host name in `LOOPBACK_HOSTS`; any trailing `/` is removed. Anything else is refused with `OLLAMA_HOST_MESSAGE`. Examples: `http://[::1]:11434/` is kept as `http://[::1]:11434`; `https://127.0.0.1:11434`, `http://127.0.0.1@example.com:11434`, and `127.0.0.1:11434` are refused.
- **R4.** `model` is refused with `MODEL_MESSAGE` when it is empty or only spaces.
- **R5.** When the settings are refused, `get_settings()` raises `SettingsError` (not Pydantic's error) whose text names every problem in field order, each as `CONDUCTOR_<FIELD>: <message>`, joined by `; `. Example: `CONDUCTOR_OLLAMA_HOST: must be an http address on this machine (127.0.0.1, localhost, or ::1); CONDUCTOR_MODEL: must not be empty`.
- **R6.** `clock.now()` returns `datetime.now(UTC)`; `ids.new_id()` returns `uuid.uuid4().hex`. Every module that needs the time or a new id calls them through the module (`clock.now()`), so a test that replaces `conductor.clock.now` changes what they see.

### Part 2: the event log (critical)

- **R7.** `check_run_id` returns the id when it is exactly 32 characters from `0-9a-f` (`re.fullmatch`), and otherwise raises `ValueError(RUN_ID_MESSAGE)`. `append` and `read` check the id first, before touching the disk, so a path such as `../x` can never be opened.
- **R8.** `append` writes one line (the format under Design) with `seq` one more than the last event of that run (1 for a new run) and `at` from `clock.now()`. It opens the file with `os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)`, writes the line, calls `os.fsync` on it, and closes it before returning the `Event`. It creates a missing folder (with parents) with mode `0o700`.
- **R9.** `append` writes nothing, and the next successful `append` still gets the next `seq`, when the event is invalid: a payload that is not JSON (a set, bytes, NaN, infinity), or a time from `clock.now()` that is naive or not at offset zero. It raises `ValueError` (Pydantic's `ValidationError` is one).
- **R10.** `seq` continues across `EventLog` objects: the first `append` to a run in an object reads the file (with the checks of R11) to find the count; later appends in the same object may keep the count in memory. One `EventLog` writes a given run at a time; nothing guards against two writers.
- **R11.** `read` returns every event in order. It raises `RunNotFound(f"no run {run_id}")` when the file does not exist, and `EventLogCorrupt` at the first bad line `n` (counting from 1):
  - `f"{run_id}.jsonl line {n} is not a valid event"` when the line is not UTF-8, not JSON, has a missing or extra field, an unknown kind, or a time not in UTC, or does not pass **strict** validation (`Event.model_validate_json(line, strict=True)`): a `seq` written as text or a time written as a number is refused, not converted;
  - `f"{run_id}.jsonl line {n} belongs to another run"` when its `run_id` differs;
  - `f"{run_id}.jsonl line {n} has seq {seq}, expected {n}"` when its `seq` is not `n`.

  The file is split on `\n`; a final empty piece (after the last newline) is not a line, so a last line cut off without its newline is still checked and refused. The message never includes the line's text. `append` to a damaged log raises the same `EventLogCorrupt` and writes nothing.
- **R12.** `runs()` returns a `RunSummary` for each file in the folder named `<valid run id>.jsonl`, newest `started_at` first and, for equal times, by run id ascending. Other files are ignored. A missing folder gives `[]` and is not created. A damaged log raises `EventLogCorrupt`.

### Part 3: the doctor's checks

- **R13.** `fetch_model_names` sends `GET <host>/api/tags` through `urllib.request.build_opener(urllib.request.ProxyHandler({}))`, so proxy variables in the environment are never used, and returns the `name` of every entry of `models`, sorted. It raises `OllamaBadAnswer("unexpected answer")` for an HTTP error status, a body that is not JSON, `models` not a list, or an entry without a text `name`; and `OllamaUnreachable("not reachable")` when no connection is made or it times out. It is the only code in this phase that opens a connection.
- **R14.** `diagnostics` calls `python_version()` and `tags.fetch_model_names` through their modules (`from conductor.llm import tags`), so tests can replace them.
- **R15.** The checks, in this order, each one line `Check.line`: the status padded to five characters, a space, the name, and `: <detail>` when there is a detail (`ok    python 3.12.13`, `FAIL  ollama http://127.0.0.1:9: not reachable`):

  | Check | Name | ok when | Otherwise |
  |---|---|---|---|
  | python | `python <a>.<b>.<c>` | version at least `MIN_PYTHON` | `FAIL`, detail `conductor needs Python 3.12 or newer` |
  | data folder | `data folder <data_dir>` | the folder exists or is created (mode `0o700`, with parents), and a file `.doctor-write-test` can be written in it and removed | `FAIL`, detail `not writable` (any `OSError`) |
  | ollama | `ollama <host>` | `fetch_model_names` answers | `FAIL`, detail `not reachable` or `unexpected answer` |
  | model | `model <model>` | the model is listed; a model with no `:` is looked up as `<model>:latest` | `FAIL`, detail `not pulled (run: ollama pull <model>)`; `SKIP`, detail `needs ollama` when the ollama check failed |

  Ollama is asked once.
- **R16.** `summary_line`: `All checks passed.` when no check is `FAIL` (a `SKIP` is not a failure), else `1 check failed.` or `<n> checks failed.`.

### Part 4: commands

- **R17.** `conductor doctor` prints every check line, then the summary line, on standard output; it exits 0 when no check failed, else 1.
- **R18.** `conductor runs list` prints, for each run from `EventLog(settings.runs_dir).runs()`, `<run_id>  <started_at as %Y-%m-%dT%H:%M:%SZ>  <n> event` (`events` when n is not 1); with no runs, `No runs yet.`. Exit 0.
- **R19.** `conductor runs show RUN_ID` prints one line per event: `seq` right-aligned in four characters, two spaces, `at` in the stored format (`%Y-%m-%dT%H:%M:%S.%fZ`), two spaces, the kind, and two spaces and the node when there is one. With `--payload`, each event whose payload is not empty is followed by `json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)`, every line indented by six spaces. Exit 0.
- **R20.** Every command loads the settings first. A `SettingsError`, `ValueError` from a run id, `RunNotFound`, or `EventLogCorrupt` prints `Error: <message>` on standard error, nothing on standard output, and exits 1 through `typer.Exit(1)`. `doctor` with refused settings runs no check (the data folder is not created).

## Given tests

65 tests in four files (counting each parameter set). Do not change them; if one fails, the code is wrong. The given configuration and helper files are also copied exactly.

`pyproject.toml`

```toml
[project]
name = "conductor"
version = "0.1.0"
description = "A supervisor agent on LangGraph and local models, for one household."
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.14,<3",
    "pydantic-settings>=2.16,<3",
    "typer>=0.27,<1",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.1,<10",
    "pytest-cov>=7.1,<8",
    "ruff>=0.17,<0.18",
]

[project.scripts]
conductor = "conductor.cli.main:app"

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["docs"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--import-mode=importlib --cov=conductor --cov-branch --cov-report=term-missing"

[tool.coverage.report]
fail_under = 90
show_missing = true
```

`scripts/check.py`

```python
"""Run everything a phase must pass: lint, format, tests, and the critical coverage gate.

Run it as: .venv/bin/python scripts/check.py [--first A,B | --section NAME]
"""

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITICAL_FILE = Path(__file__).resolve().parent / "critical_modules.txt"
SECTIONS_FILE = ROOT / "tests" / "sections.toml"
COVERAGE_STEP = "critical coverage"
LAYERS = ("unit", "integration", "e2e")


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str] | None


@dataclass(frozen=True)
class Tally:
    passed: int
    failed: int
    skipped: int


def read_critical(text: str) -> list[str]:
    """Return the module paths in the text, without comments and blank lines."""
    modules = []
    for line in text.splitlines():
        module = line.split("#", 1)[0].strip()
        if module:
            modules.append(module)
    return modules


def coverage_gaps(report: dict, modules: list[str]) -> list[str]:
    """Return one line for each module that is not fully covered, in the order of modules."""
    files = report["files"]
    gaps = []
    for module in modules:
        found = files.get(f"src/conductor/{module}")
        if found is None:
            gaps.append(f"{module}: not measured")
            continue
        lines = found["summary"]["missing_lines"]
        branches = found["summary"]["missing_branches"]
        if lines or branches:
            gaps.append(f"{module}: {lines} lines and {branches} branches not covered")
    return gaps


def read_sections(text: str) -> list[tuple[str, list[str]]]:
    return [(table["name"], list(table["patterns"])) for table in tomllib.loads(text)["section"]]


def section_of(path: str, sections: list[tuple[str, list[str]]]) -> str:
    for name, patterns in sections:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            return name
    raise ValueError(f"no section for {path}")


def _case_path(classname: str, name: str) -> str:
    parts = (classname or name).split(".")
    return f"{parts[1]}/{parts[2]}.py"


def tally(report: str, sections: list[tuple[str, list[str]]]) -> dict[str, Tally]:
    counts = {name: [0, 0, 0] for name, _ in sections}
    for case in ET.fromstring(report).iter("testcase"):
        section = section_of(_case_path(case.get("classname", ""), case.get("name", "")), sections)
        tags = {child.tag for child in case}
        if "failure" in tags or "error" in tags:
            counts[section][1] += 1
        elif "skipped" in tags:
            counts[section][2] += 1
        else:
            counts[section][0] += 1
    return {
        name: Tally(passed=passed, failed=failed, skipped=skipped)
        for name, (passed, failed, skipped) in counts.items()
    }


def section_lines(tallies: dict[str, Tally]) -> list[str]:
    lines = ["Sections:"]
    for name, found in tallies.items():
        line = (
            f"  {name:<11}{found.passed:>6} passed{found.failed:>5} failed"
            f"{found.skipped:>5} skipped"
        )
        if found.failed:
            line += f"  rerun: .venv/bin/python scripts/check.py --section {name}"
        lines.append(line)
    return lines


def section_files(names: list[str]) -> list[str]:
    sections = read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))
    wanted = set(names)
    found = []
    for layer in LAYERS:
        for path in (ROOT / "tests" / layer).glob("test_*.py"):
            relative = path.relative_to(ROOT / "tests").as_posix()
            if section_of(relative, sections) in wanted:
                found.append(f"tests/{relative}")
    return sorted(found)


def steps(python: str, coverage_json: Path, *, first: list[str] | None = None) -> list[Step]:
    found = [
        Step("lint", [python, "-m", "ruff", "check", "."]),
        Step("format", [python, "-m", "ruff", "format", "--check", "."]),
    ]
    if first:
        found.append(
            Step(
                f"tests ({','.join(first)})",
                [
                    python,
                    "-m",
                    "pytest",
                    "--no-cov",
                    f"--junitxml={coverage_json.with_name('first.xml')}",
                    "--continue-on-collection-errors",
                    *section_files(first),
                ],
            )
        )
    found.extend(
        [
            Step(
                "tests",
                [
                    python,
                    "-m",
                    "pytest",
                    f"--cov-report=json:{coverage_json}",
                    f"--junitxml={coverage_json.with_name('junit.xml')}",
                    "--continue-on-collection-errors",
                ],
            ),
            Step(COVERAGE_STEP, None),
        ]
    )
    return found


def run_command(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _critical_coverage(coverage_json: Path) -> bool:
    report = json.loads(coverage_json.read_text(encoding="utf-8"))
    modules = read_critical(CRITICAL_FILE.read_text(encoding="utf-8"))
    gaps = coverage_gaps(report, modules)
    for gap in gaps:
        print(f"  {gap}")
    return not gaps


def _print_table(report_path: Path, names: list[str] | None) -> None:
    if not report_path.is_file():
        return
    sections = read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))
    if names is not None:
        wanted = set(names)
        sections = [(name, patterns) for name, patterns in sections if name in wanted]
    print("\n".join(section_lines(tally(report_path.read_text(encoding="utf-8"), sections))))


def _section_names() -> list[str]:
    return [name for name, _ in read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))]


def _run_one_section(name: str, run: Callable[[list[str], Path], int]) -> int:
    files = section_files([name])
    with tempfile.TemporaryDirectory() as folder:
        report_path = Path(folder) / "junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--no-cov",
            f"--junitxml={report_path}",
            "--continue-on-collection-errors",
            *files,
        ]
        code = run(command, ROOT)
        _print_table(report_path, [name])
    print(f"Section {name}: {'passed.' if code == 0 else 'FAILED.'}")
    return 0 if code == 0 else 1


def main(argv: list[str] | None = None, run: Callable[[list[str], Path], int] = run_command) -> int:
    names = _section_names()
    parser = argparse.ArgumentParser(description="Run every check a phase must pass.")
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--section",
        choices=names,
        help="Run one section's tests alone, with no lint, format, or coverage.",
    )
    exclusive.add_argument(
        "--first",
        metavar="A[,B…]",
        help="Run these sections first; the full check only once they pass.",
    )
    options = parser.parse_args(argv)
    if options.section is not None:
        return _run_one_section(options.section, run)
    first: list[str] | None = None
    if options.first is not None:
        first = options.first.split(",")
        known = set(names)
        for name in first:
            if name not in known:
                parser.error(f"unknown section: {name}")
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as folder:
        coverage_json = Path(folder) / "coverage.json"
        planned = steps(sys.executable, coverage_json, first=first)
        failed = None
        for step in planned:
            print(f"== {step.name}", flush=True)
            if step.command is None:
                passed = _critical_coverage(coverage_json)
            else:
                passed = run(step.command, ROOT) == 0
                for part in step.command:
                    if part.startswith("--junitxml="):
                        wanted = first if step.name.startswith("tests (") else None
                        _print_table(Path(part.removeprefix("--junitxml=")), wanted)
                        break
            results[step.name] = "passed" if passed else "FAILED"
            if not passed:
                failed = step.name
                break
    print()
    print("Summary:")
    for step in planned:
        print(f"  {step.name}: {results.get(step.name, 'not run')}")
    print("All checks passed." if failed is None else f"Check failed at: {failed}")
    return 0 if failed is None else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

`scripts/critical_modules.txt`

```text
# Modules where a bug lets the agent act without approval, lose its record, or accept output it
# should refuse. Every line and every branch of each must be covered by tests. One path per line,
# relative to src/conductor/. Read by scripts/check.py.
events.py
```

`tests/sections.toml`

```toml
# Which section each test file belongs to, for `scripts/check.py --section NAME` and the table a
# full run prints. Paths are relative to tests/ and matched with fnmatch. Sections are tried in this
# order and the first that matches wins; the last, core, takes every file the others leave.

[[section]]
name = "scripts"
patterns = ["unit/test_check_script*.py"]

[[section]]
name = "cli"
patterns = ["e2e/test_cli*.py"]

[[section]]
name = "core"
patterns = ["*"]
```

`tests/conftest.py`

```python
import os
import socket
from pathlib import Path

import pytest

# Where a test's Ollama host points unless it starts its own server: a closed local port, so a
# test that forgets to replace the model fails at once instead of reaching a real Ollama.
CLOSED_OLLAMA = "http://127.0.0.1:9"

_LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost")
_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_TERMINAL_KEYS = ("FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE", "TTY_INTERACTIVE")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every connection and name lookup that leaves the machine."""
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: object) -> object:
        if self.family == socket.AF_UNIX:
            return real_connect(self, address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOCAL_HOSTS:
            raise AssertionError("a test tried to use the network")
        return real_connect(self, address)

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        if host not in _LOCAL_HOSTS:
            raise AssertionError("a test tried to use the network")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No CONDUCTOR_ variable from the shell; data under tmp_path; Ollama on a closed port."""
    for key in list(os.environ):
        if key.startswith("CONDUCTOR_"):
            monkeypatch.delenv(key)
    for key in _PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    for key in _TERMINAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", CLOSED_OLLAMA)
```

`tests/support.py`

```python
"""Helpers shared by tests: running a command, fixed times, and a fake Ollama on 127.0.0.1.

New tests import these instead of copying them.
"""

import json
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from typer.testing import CliRunner

from conductor import clock
from conductor.cli.main import app

runner = CliRunner(env={"COLUMNS": "200"})


def run(*args: object):
    """Run `conductor` with these arguments, each turned into text."""
    return runner.invoke(app, [str(arg) for arg in args])


def fixed_times(monkeypatch: pytest.MonkeyPatch, *moments: str) -> None:
    """Make `clock.now()` return these ISO moments, one per call, in order."""
    times = iter([datetime.fromisoformat(moment) for moment in moments])
    monkeypatch.setattr(clock, "now", lambda: next(times))


class FakeOllama:
    """What the fake answers to every GET: `status` and `body`. `paths` lists what was asked."""

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"models": []}'
        self.paths: list[str] = []

    def models(self, *names: str) -> None:
        listed = [{"name": name, "model": name, "size": 1} for name in names]
        self.body = json.dumps({"models": listed}).encode()


class _LocalServer(HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer looks up the machine's name here, which costs seconds on macOS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


@contextmanager
def fake_ollama() -> Iterator[tuple[FakeOllama, str]]:
    """Start a fake Ollama on 127.0.0.1; yield it and its host, such as http://127.0.0.1:50123."""
    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.paths.append(self.path)
            self.send_response(fake.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(fake.body)))
            self.end_headers()
            self.wfile.write(fake.body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _LocalServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
```

`tests/unit/test_config.py` (11 tests)

```python
from pathlib import Path

import pytest

from conductor.config import SettingsError, get_settings

HOST_REFUSED = (
    "CONDUCTOR_OLLAMA_HOST: must be an http address on this machine (127.0.0.1, localhost, or ::1)"
)


def test_the_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CONDUCTOR_DATA_DIR")
    monkeypatch.delenv("CONDUCTOR_OLLAMA_HOST")
    settings = get_settings()
    assert settings.data_dir == tmp_path / "data"
    assert settings.runs_dir == tmp_path / "data" / "runs"
    assert settings.ollama_host == "http://127.0.0.1:11434"
    assert settings.model == "qwen3.8:27b"


def test_a_relative_data_folder_is_made_absolute_without_resolving_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", "agent/../data")
    monkeypatch.setenv("CONDUCTOR_MODEL", "qwen3-coder:30b")
    settings = get_settings()
    assert settings.data_dir == tmp_path / "agent" / ".." / "data"
    assert settings.model == "qwen3-coder:30b"


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://[::1]:11434/", "http://[::1]:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
    ],
)
def test_a_host_on_this_machine_is_kept_without_a_trailing_slash(
    monkeypatch: pytest.MonkeyPatch, given: str, kept: str
) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", given)
    assert get_settings().ollama_host == kept


@pytest.mark.parametrize(
    "host",
    [
        "http://10.0.0.5:11434",
        "https://127.0.0.1:11434",
        "http://localhost.example.com:11434",
        "http://127.0.0.1@example.com:11434",
        "127.0.0.1:11434",
    ],
)
def test_a_host_elsewhere_is_refused(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == HOST_REFUSED


def test_every_problem_is_named_in_field_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_MODEL", "   ")
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://192.168.1.20:11434")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == f"{HOST_REFUSED}; CONDUCTOR_MODEL: must not be empty"
```

`tests/unit/test_events.py` (33 tests)

```python
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import clock
from conductor.events import (
    RUN_ID_MESSAGE,
    Event,
    EventKind,
    EventLog,
    EventLogCorrupt,
    RunNotFound,
    RunSummary,
    check_run_id,
)
from tests.support import fixed_times

RUN_A = "0123456789abcdef0123456789abcdef"
RUN_B = "fedcba9876543210fedcba9876543210"
RUN_C = "00000000000000000000000000000001"

LINE_1 = (
    '{"at":"2026-10-25T21:30:00.000000Z","kind":"run_started","node":null,'
    '"payload":{"b":[1,2.5,null,true],"request":"plan my week"},'
    '"run_id":"0123456789abcdef0123456789abcdef","seq":1}'
)
LINE_2 = (
    '{"at":"2026-10-25T21:30:01.250000Z","kind":"node_started","node":"route","payload":{},'
    '"run_id":"0123456789abcdef0123456789abcdef","seq":2}'
)


def write_two(folder: Path, monkeypatch: pytest.MonkeyPatch) -> list[Event]:
    fixed_times(monkeypatch, "2026-10-25T21:30:00+00:00", "2026-10-25T21:30:01.250+00:00")
    log = EventLog(folder)
    return [
        log.append(
            RUN_A,
            EventKind.RUN_STARTED,
            payload={"request": "plan my week", "b": [1, 2.5, None, True]},
        ),
        log.append(RUN_A, EventKind.NODE_STARTED, node="route"),
    ]


def test_the_kinds() -> None:
    assert [kind.value for kind in EventKind] == [
        "run_started",
        "run_finished",
        "node_started",
        "node_finished",
        "model_request",
        "model_reply",
        "tool_call",
        "tool_result",
        "approval_requested",
        "approval_decided",
        "escalated",
        "error",
    ]


def test_each_event_is_one_line_with_sorted_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = write_two(tmp_path / "runs", monkeypatch)
    text = (tmp_path / "runs" / f"{RUN_A}.jsonl").read_text(encoding="utf-8")
    assert text == f"{LINE_1}\n{LINE_2}\n"
    assert [(event.seq, event.kind, event.node) for event in events] == [
        (1, EventKind.RUN_STARTED, None),
        (2, EventKind.NODE_STARTED, "route"),
    ]
    assert events[1].at == datetime(2026, 10, 25, 21, 30, 1, 250000, tzinfo=UTC)
    assert events[1].payload == {}


def test_reading_returns_what_was_written(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events = write_two(tmp_path / "runs", monkeypatch)
    assert EventLog(tmp_path / "runs").read(RUN_A) == events


def test_text_is_written_as_utf8_not_escaped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(monkeypatch, "2026-10-25T21:30:00+00:00")
    EventLog(tmp_path).append(RUN_A, EventKind.MODEL_REPLY, payload={"text": "café ☕"})
    assert '"payload":{"text":"café ☕"}' in (tmp_path / f"{RUN_A}.jsonl").read_text("utf-8")


def test_a_new_log_on_the_same_folder_continues_the_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_two(tmp_path, monkeypatch)
    fixed_times(monkeypatch, "2026-10-25T21:31:00+00:00", "2026-10-25T21:31:01+00:00")
    log = EventLog(tmp_path)
    assert log.append(RUN_A, EventKind.RUN_FINISHED).seq == 3
    assert log.append(RUN_B, EventKind.RUN_STARTED).seq == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == [f"{RUN_A}.jsonl", f"{RUN_B}.jsonl"]


def test_only_the_owner_can_read_the_folder_and_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_two(tmp_path / "data" / "runs", monkeypatch)
    assert (tmp_path / "data" / "runs").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "data" / "runs" / f"{RUN_A}.jsonl").stat().st_mode & 0o777 == 0o600


def test_each_append_is_synced_to_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    synced: list[int] = []
    monkeypatch.setattr(os, "fsync", lambda descriptor: synced.append(descriptor))
    write_two(tmp_path, monkeypatch)
    assert len(synced) == 2


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "0123456789ABCDEF0123456789ABCDEF",
        "0123456789abcdef0123456789abcde",
        "../../../../../../tmp/elsewhere0",
        "0123456789abcdef0123456789abcdef\n",
    ],
)
def test_a_run_id_that_is_not_32_lowercase_hex_is_refused(tmp_path: Path, run_id: str) -> None:
    log = EventLog(tmp_path / "runs")
    with pytest.raises(ValueError) as raised:
        log.append(run_id, EventKind.RUN_STARTED)
    assert str(raised.value) == RUN_ID_MESSAGE
    with pytest.raises(ValueError) as raised:
        log.read(run_id)
    assert str(raised.value) == RUN_ID_MESSAGE
    assert not (tmp_path / "runs").exists()


def test_a_good_run_id_is_returned_as_it_is() -> None:
    assert RUN_ID_MESSAGE == "run id must be 32 lowercase hexadecimal characters"
    assert check_run_id(RUN_A) == RUN_A


@pytest.mark.parametrize("value", [{1, 2}, float("nan"), float("inf"), b"raw"])
def test_a_payload_that_is_not_json_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object
) -> None:
    fixed_times(monkeypatch, *[f"2026-10-25T21:30:0{second}+00:00" for second in range(3)])
    log = EventLog(tmp_path)
    log.append(RUN_A, EventKind.RUN_STARTED)
    before = (tmp_path / f"{RUN_A}.jsonl").read_bytes()
    with pytest.raises(ValueError):
        log.append(RUN_A, EventKind.TOOL_RESULT, payload={"value": value})
    assert (tmp_path / f"{RUN_A}.jsonl").read_bytes() == before
    assert log.append(RUN_A, EventKind.RUN_FINISHED).seq == 2


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 10, 25, 21, 30),
        datetime(2026, 10, 25, 23, 30, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_a_time_that_is_not_utc_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, moment: datetime
) -> None:
    monkeypatch.setattr(clock, "now", lambda: moment)
    with pytest.raises(ValueError):
        EventLog(tmp_path).append(RUN_A, EventKind.RUN_STARTED)
    assert not (tmp_path / f"{RUN_A}.jsonl").exists()


@pytest.mark.parametrize(
    ("after_line_1", "message"),
    [
        (b"{not json\n", "line 2 is not a valid event"),
        (b'{"at":"2026-10-25T21:3', "line 2 is not a valid event"),
        (b"\n" + LINE_2.encode() + b"\n", "line 2 is not a valid event"),
        (b"\xff\xfe\n", "line 2 is not a valid event"),
        (LINE_2.replace('"seq":2', '"seq":2,"extra":1').encode(), "line 2 is not a valid event"),
        (LINE_2.replace("node_started", "launched").encode(), "line 2 is not a valid event"),
        (
            LINE_2.replace("21:30:01.250000Z", "21:30:01+02:00").encode(),
            "line 2 is not a valid event",
        ),
        (LINE_2.replace('"seq":2', '"seq":"2"').encode(), "line 2 is not a valid event"),
        (
            LINE_2.replace('"2026-10-25T21:30:01.250000Z"', "1792963801.25").encode(),
            "line 2 is not a valid event",
        ),
        (LINE_2.replace(RUN_A, RUN_B).encode(), "line 2 belongs to another run"),
        (LINE_2.replace('"seq":2', '"seq":3').encode(), "line 2 has seq 3, expected 2"),
    ],
)
def test_a_damaged_log_is_refused_with_its_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, after_line_1: bytes, message: str
) -> None:
    damaged = LINE_1.encode() + b"\n" + after_line_1
    (tmp_path / f"{RUN_A}.jsonl").write_bytes(damaged)
    log = EventLog(tmp_path)
    with pytest.raises(EventLogCorrupt) as raised:
        log.read(RUN_A)
    assert str(raised.value) == f"{RUN_A}.jsonl {message}"
    fixed_times(monkeypatch, "2026-10-25T21:40:00+00:00")
    with pytest.raises(EventLogCorrupt):
        log.append(RUN_A, EventKind.RUN_FINISHED)
    assert (tmp_path / f"{RUN_A}.jsonl").read_bytes() == damaged


def test_reading_a_run_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(RunNotFound) as raised:
        EventLog(tmp_path).read(RUN_A)
    assert str(raised.value) == f"no run {RUN_A}"


def test_runs_newest_first_then_by_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixed_times(
        monkeypatch,
        "2026-10-25T21:30:00+00:00",
        "2026-10-25T21:31:00.500+00:00",
        "2026-10-25T21:32:00+00:00",
        "2026-10-25T21:30:00+00:00",
    )
    log = EventLog(tmp_path)
    log.append(RUN_A, EventKind.RUN_STARTED)
    log.append(RUN_B, EventKind.RUN_STARTED)
    log.append(RUN_A, EventKind.RUN_FINISHED)
    log.append(RUN_C, EventKind.RUN_STARTED)
    (tmp_path / "notes.txt").write_text("not a run", encoding="utf-8")
    (tmp_path / "README.jsonl").write_text("not a run either", encoding="utf-8")
    assert log.runs() == [
        RunSummary(RUN_B, datetime(2026, 10, 25, 21, 31, 0, 500000, tzinfo=UTC), 1),
        RunSummary(RUN_C, datetime(2026, 10, 25, 21, 30, tzinfo=UTC), 1),
        RunSummary(RUN_A, datetime(2026, 10, 25, 21, 30, tzinfo=UTC), 2),
    ]


def test_runs_of_a_folder_not_made_yet(tmp_path: Path) -> None:
    assert EventLog(tmp_path / "runs").runs() == []
    assert not (tmp_path / "runs").exists()
```

`tests/e2e/test_cli_doctor.py` (12 tests)

```python
from pathlib import Path

import pytest

from conductor import diagnostics
from tests.support import fake_ollama, run

HOST_REFUSED = (
    "Error: CONDUCTOR_OLLAMA_HOST: must be an http address on this machine "
    "(127.0.0.1, localhost, or ::1)\n"
)


@pytest.fixture(autouse=True)
def python_3_12_13(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def test_everything_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with fake_ollama() as (fake, host):
        fake.models("nomic-embed-text:latest", "qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout == (
        "ok    python 3.12.13\n"
        f"ok    data folder {tmp_path / 'data'}\n"
        f"ok    ollama {host}\n"
        "ok    model qwen3.8:27b\n"
        "All checks passed.\n"
    )
    assert result.stderr == ""
    assert result.exit_code == 0
    assert fake.paths == ["/api/tags"]
    assert (tmp_path / "data").stat().st_mode & 0o777 == 0o700
    assert list((tmp_path / "data").iterdir()) == []


def test_ollama_not_running(tmp_path: Path) -> None:
    result = run("doctor")
    assert result.stdout == (
        "ok    python 3.12.13\n"
        f"ok    data folder {tmp_path / 'data'}\n"
        "FAIL  ollama http://127.0.0.1:9: not reachable\n"
        "SKIP  model qwen3.8:27b: needs ollama\n"
        "1 check failed.\n"
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b"<html>not ollama</html>"),
        (500, b'{"models": []}'),
        (200, b'{"models": "qwen3.8:27b"}'),
        (200, b'{"models": [{"model": "qwen3.8:27b"}]}'),
    ],
)
def test_something_else_answering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: int, body: bytes
) -> None:
    with fake_ollama() as (fake, host):
        fake.status = status
        fake.body = body
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"FAIL  ollama {host}: unexpected answer",
        "SKIP  model qwen3.8:27b: needs ollama",
        "1 check failed.",
    ]
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("model", "pulled", "line"),
    [
        (
            "qwen3.8:27b",
            ["qwen3-coder:30b"],
            "FAIL  model qwen3.8:27b: not pulled (run: ollama pull qwen3.8:27b)",
        ),
        ("qwen3-coder", ["qwen3-coder:latest"], "ok    model qwen3-coder"),
        (
            "qwen3-coder",
            ["qwen3-coder:30b"],
            "FAIL  model qwen3-coder: not pulled (run: ollama pull qwen3-coder)",
        ),
    ],
)
def test_the_model_must_be_pulled(
    monkeypatch: pytest.MonkeyPatch, model: str, pulled: list[str], line: str
) -> None:
    with fake_ollama() as (fake, host):
        fake.models(*pulled)
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("CONDUCTOR_MODEL", model)
        result = run("doctor")
    assert result.stdout.splitlines()[3] == line
    assert result.exit_code == (0 if line.startswith("ok") else 1)


def test_a_proxy_in_the_environment_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_ollama() as (fake, host):
        fake.models("qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
        result = run("doctor")
    assert result.stdout.splitlines()[2:] == [
        f"ok    ollama {host}",
        "ok    model qwen3.8:27b",
        "All checks passed.",
    ]


def test_old_python_and_a_data_folder_that_cannot_be_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 11, 9))
    (tmp_path / "taken").write_text("a file, not a folder", encoding="utf-8")
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "taken" / "data"))
    result = run("doctor")
    assert result.stdout == (
        "FAIL  python 3.11.9: conductor needs Python 3.12 or newer\n"
        f"FAIL  data folder {tmp_path / 'taken' / 'data'}: not writable\n"
        "FAIL  ollama http://127.0.0.1:9: not reachable\n"
        "SKIP  model qwen3.8:27b: needs ollama\n"
        "3 checks failed.\n"
    )
    assert result.exit_code == 1


def test_settings_that_point_elsewhere_stop_before_any_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://10.0.0.5:11434")
    result = run("doctor")
    assert result.stdout == ""
    assert result.stderr == HOST_REFUSED
    assert result.exit_code == 1
    assert not (tmp_path / "data").exists()
```

`tests/e2e/test_cli_runs.py` (9 tests)

```python
from pathlib import Path

import pytest

from conductor.events import EventKind, EventLog
from tests.support import fixed_times, run

RUN_A = "0123456789abcdef0123456789abcdef"
RUN_B = "fedcba9876543210fedcba9876543210"


def two_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixed_times(
        monkeypatch,
        "2026-10-25T21:30:00+00:00",
        "2026-10-25T21:30:01.250+00:00",
        "2026-10-25T21:31:00.500+00:00",
    )
    log = EventLog(tmp_path / "data" / "runs")
    log.append(
        RUN_A,
        EventKind.RUN_STARTED,
        payload={"request": "plan my week at the café", "steps": [1, 2]},
    )
    log.append(RUN_A, EventKind.NODE_STARTED, node="route")
    log.append(RUN_B, EventKind.RUN_STARTED, payload={"request": "check the build"})


def test_no_runs_yet() -> None:
    result = run("runs", "list")
    assert result.stdout == "No runs yet.\n"
    assert result.exit_code == 0


def test_runs_newest_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    two_runs(monkeypatch, tmp_path)
    result = run("runs", "list")
    assert result.stdout == (
        "fedcba9876543210fedcba9876543210  2026-10-25T21:31:00Z  1 event\n"
        "0123456789abcdef0123456789abcdef  2026-10-25T21:30:00Z  2 events\n"
    )
    assert result.exit_code == 0


def test_show_a_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    two_runs(monkeypatch, tmp_path)
    result = run("runs", "show", RUN_A)
    assert result.stdout == (
        "   1  2026-10-25T21:30:00.000000Z  run_started\n"
        "   2  2026-10-25T21:30:01.250000Z  node_started  route\n"
    )
    assert result.exit_code == 0


def test_show_a_run_with_its_payloads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    two_runs(monkeypatch, tmp_path)
    result = run("runs", "show", RUN_A, "--payload")
    assert result.stdout == (
        "   1  2026-10-25T21:30:00.000000Z  run_started\n"
        "      {\n"
        '        "request": "plan my week at the café",\n'
        '        "steps": [\n'
        "          1,\n"
        "          2\n"
        "        ]\n"
        "      }\n"
        "   2  2026-10-25T21:30:01.250000Z  node_started  route\n"
    )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["show", RUN_B], f"Error: no run {RUN_B}\n"),
        (["show", "latest"], "Error: run id must be 32 lowercase hexadecimal characters\n"),
    ],
)
def test_show_refuses(args: list[str], message: str) -> None:
    result = run("runs", *args)
    assert result.stdout == ""
    assert result.stderr == message
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize("command", [["show", RUN_A], ["list"]])
def test_a_damaged_log_stops_both_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: list[str]
) -> None:
    two_runs(monkeypatch, tmp_path)
    with (tmp_path / "data" / "runs" / f"{RUN_A}.jsonl").open("a", encoding="utf-8") as file:
        file.write("{half a line")
    result = run("runs", *command)
    assert result.stdout == ""
    assert result.stderr == f"Error: {RUN_A}.jsonl line 3 is not a valid event\n"
    assert result.exit_code == 1


def test_settings_that_point_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", "http://ollama.example.com:11434")
    result = run("runs", "list")
    assert result.stderr == (
        "Error: CONDUCTOR_OLLAMA_HOST: must be an http address on this machine "
        "(127.0.0.1, localhost, or ::1)\n"
    )
    assert result.exit_code == 1
```

## Tests to write

The given tests cover every requirement's main path. Write more only where `check.py` reports a gap in coverage, from the requirement the line serves:

- `events.py` must reach 100% of lines and branches (critical). Likely gaps: a folder that already exists when the first event is written; reading a log whose last line ends without a newline but is valid.
- `llm/tags.py`: a timeout (`OllamaUnreachable`). Use a server on 127.0.0.1 that accepts and never answers, with a short timeout, not a real Ollama.
- `ids.new_id()`: 32 lowercase hexadecimal characters, two calls differ.

Put each new file in `tests/unit/` or `tests/integration/`; `core` takes them.

## Rules for this phase

- **The event log is critical**: 100% of lines and branches, measured by the coverage command below. No `# pragma: no cover`.
- **No network beyond 127.0.0.1**, and none at all outside `llm/tags.py`. Never contact the real Ollama from a test; `tests/conftest.py` points the host at port 9.
- **Messages are constant text plus identifiers.** No message includes a line from a log, a payload, or a reply body.
- **Time and ids through their modules** (R6). No `datetime.now`, `datetime.utcnow`, `time.time`, or `uuid` anywhere in `src/` except `clock.py` and `ids.py`.
- **Install only with the two commands of Step 0.**
- **`ruff format --check .` reads Markdown outside `docs/`** and formats its Python code blocks. Write the README's commands in `zsh` blocks.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core,cli`; at least 65 passed (no N);
- the given test files above, `65 passed`:
  `.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_events.py tests/e2e/test_cli_doctor.py tests/e2e/test_cli_runs.py --no-cov`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/events.py,*/conductor/config.py,*/conductor/llm/tags.py,*/conductor/diagnostics.py" --fail-under=100`;
- the searches, each with no output:
  - `git grep --untracked -n -E "datetime\.now|utcnow|time\.time\(|uuid" -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'`
  - `git grep --untracked -n -E "urlopen|build_opener|socket|http\.client" -- src ':!src/conductor/llm/tags.py'`
  - `git grep --untracked -n "pragma: no cover" -- src`
- `git status --short` lists only the Scope paths and `.venv/` is not among them (it is gitignored).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 1: skeleton (YYYY-MM-DD)`, with `Tests: 0 -> <passed> (given 65)`.
