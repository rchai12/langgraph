# Verify Phase 1: skeleton

Spec: `docs/phases/phase-01-skeleton.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict.

The coder created the package, the virtual environment, the settings, the event log (critical), the doctor's checks, three commands, and copied the given configuration, scripts, helpers, and four test files (65 tests).

## 1. Gates

There is no N: nothing ran before this phase. Sections: core, cli.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core,cli` | last line `All checks passed.`; the summary lists `tests (core,cli): passed`; at least 65 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/events.py,*/conductor/config.py,*/conductor/llm/tags.py,*/conductor/diagnostics.py" --fail-under=100` (right after the check, on the data it left) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_events.py tests/e2e/test_cli_doctor.py tests/e2e/test_cli_runs.py --no-cov` | exactly `65 passed` |
| `.venv/bin/python -m pip list` | packages beyond the standard library come only from the given `pyproject.toml` and their dependencies: no `langgraph`, `langchain*`, `langsmith`, `ollama`, `mcp`, `fastapi`, `httpx`, `requests`, `opentelemetry*` |

Searches (gates 4 to 6), each with no output:

4. `git grep --untracked -n -E "datetime\.now|utcnow|time\.time\(|uuid" -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'`
5. `git grep --untracked -n -E "urlopen|build_opener|socket|http\.client" -- src ':!src/conductor/llm/tags.py'`
6. `git grep --untracked -n "pragma: no cover" -- src`

## 2. Scope paths

`git status --short` lists only: `pyproject.toml`, `README.md`, `scripts/`, `src/`, `tests/`, `docs/progress.md` (untracked folders may show as one line each). `.venv/` must not appear (it is gitignored). Compare each given file with its block in the spec (`pyproject.toml`, `scripts/check.py`, `scripts/critical_modules.txt`, `tests/sections.toml`, `tests/conftest.py`, `tests/support.py`, and the four test files); any difference is a finding. Under `src/conductor/` only the Scope's modules exist (private helpers inside them are allowed; another module is a finding).

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_defaults`; read `get_settings` | a new `Settings` per call, no cache, no `env_file` |
| R2 | `test_a_relative_data_folder_is_made_absolute_without_resolving_links` | pass |
| R3 | `test_a_host_on_this_machine_is_kept_without_a_trailing_slash`, `test_a_host_elsewhere_is_refused`; probe "hosts on this machine only" | pass; probe ok |
| R4, R5 | `test_every_problem_is_named_in_field_order` | pass; `SettingsError` is not a Pydantic error |
| R6 | search 4; read `clock.py`, `ids.py`; probe "new ids ...", "the real clock ..." | no output; ok |
| R7 | `test_a_run_id_that_is_not_32_lowercase_hex_is_refused`, `test_a_good_run_id_is_returned_as_it_is`; read `append`, `read` | the id is checked before any path is built |
| R8 | `test_each_event_is_one_line_with_sorted_keys`, `test_only_the_owner_can_read_the_folder_and_files`, `test_each_append_is_synced_to_disk`; probe "an existing folder ..." | pass; ok |
| R9 | `test_a_payload_that_is_not_json_writes_nothing`, `test_a_time_that_is_not_utc_is_refused` | pass |
| R10 | `test_a_new_log_on_the_same_folder_continues_the_count`; probe "another process continues the count" | pass; ok |
| R11 | `test_a_damaged_log_is_refused_with_its_line`, `test_reading_a_run_that_does_not_exist`; probes "line separators ...", "strict lines are refused", "a large payload ..." | pass; ok |
| R12 | `test_runs_newest_first_then_by_id`, `test_runs_of_a_folder_not_made_yet` | pass |
| R13 | `test_something_else_answering`, `test_a_proxy_in_the_environment_is_not_used`; probe "a silent server times out"; search 5 | pass; ok; no output |
| R14 | read `diagnostics.py`: `tags.fetch_model_names(...)` and `python_version()` called through their modules | yes |
| R15, R16 | every test in `test_cli_doctor.py` | pass |
| R17 | `test_everything_ready`, `test_ollama_not_running`; probe "the installed command runs doctor" | pass; ok |
| R18, R19 | `test_cli_runs.py`; probe "the installed command shows a run" | pass; ok |
| R20 | `test_show_refuses`, `test_a_damaged_log_stops_both_commands`, `test_settings_that_point_elsewhere`, `test_settings_that_point_elsewhere_stop_before_any_check` | pass |

## 4. Probe

Save this script outside the repository (for example `/tmp/probe_01.py`), run it from the repository root with `.venv/bin/python /tmp/probe_01.py`, then delete it. It starts its own servers on 127.0.0.1, runs the installed `.venv/bin/conductor`, and never contacts the real Ollama.

```python
"""Probe for Phase 1. Save outside the repository; run from the repository root with
.venv/bin/python <path>. Every line ends in ok; the last line is FAILURES 0."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FAILURES = 0
RUN = "abcdefabcdefabcdefabcdefabcdef01"
ROOT = Path.cwd()
CONDUCTOR = ROOT / ".venv" / "bin" / "conductor"
PYTHON = ROOT / ".venv" / "bin" / "python"


def check(name: str, test: Callable[[], None]) -> None:
    global FAILURES
    try:
        test()
        print(f"ok   {name}")
    except Exception as error:  # noqa: BLE001 - a probe reports every failure and goes on
        FAILURES += 1
        print(f"FAIL {name}: {type(error).__name__}: {error}")


def expect(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def clean_env(**extra: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CONDUCTOR_") and "proxy" not in key.lower()
    }
    env.update(extra)
    return env


class Fake(HTTPServer):
    def server_bind(self) -> None:
        import socketserver

        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def serve(body: bytes) -> tuple[Fake, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = Fake(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def line_separators_stay_inside_one_line() -> None:
    from conductor.events import EventKind, EventLog

    with tempfile.TemporaryDirectory() as folder:
        log = EventLog(Path(folder))
        text = "a\nb c d\x85e\rf"
        log.append(RUN, EventKind.MODEL_REPLY, payload={"text": text})
        log.append(RUN, EventKind.RUN_FINISHED)
        raw = (Path(folder) / f"{RUN}.jsonl").read_bytes()
        expect(raw.count(b"\n") == 2, f"{raw.count(b'\n')} newlines for 2 events")
        events = log.read(RUN)
        expect([event.seq for event in events] == [1, 2], "seqs")
        expect(events[0].payload == {"text": text}, "payload changed")


def a_large_payload_round_trips() -> None:
    from conductor.events import EventKind, EventLog

    with tempfile.TemporaryDirectory() as folder:
        log = EventLog(Path(folder))
        big = {"reply": "x" * 1_000_000, "nested": {"list": list(range(1000))}}
        log.append(RUN, EventKind.MODEL_REPLY, payload=big)
        expect(log.read(RUN)[0].payload == big, "payload changed")


def another_process_continues_the_count() -> None:
    from conductor.events import EventKind, EventLog

    with tempfile.TemporaryDirectory() as folder:
        code = (
            "import sys; from pathlib import Path; from conductor.events import EventKind, EventLog; "
            "log = EventLog(Path(sys.argv[1])); "
            f"log.append('{RUN}', EventKind.RUN_STARTED); log.append('{RUN}', EventKind.NODE_STARTED, node='route')"
        )
        subprocess.run([str(PYTHON), "-c", code, folder], check=True, env=clean_env())
        event = EventLog(Path(folder)).append(RUN, EventKind.RUN_FINISHED)
        expect(event.seq == 3, f"seq {event.seq}")
        expect(len(EventLog(Path(folder)).read(RUN)) == 3, "count")


def an_existing_folder_keeps_its_mode_and_files_are_owner_only() -> None:
    from conductor.events import EventKind, EventLog

    with tempfile.TemporaryDirectory() as parent:
        folder = Path(parent) / "runs"
        folder.mkdir(mode=0o755)
        os.chmod(folder, 0o755)
        EventLog(folder).append(RUN, EventKind.RUN_STARTED)
        expect(folder.stat().st_mode & 0o777 == 0o755, oct(folder.stat().st_mode & 0o777))
        mode = (folder / f"{RUN}.jsonl").stat().st_mode & 0o777
        expect(mode == 0o600, oct(mode))


def new_ids_are_run_ids_and_differ() -> None:
    from conductor import ids
    from conductor.events import check_run_id

    made = {ids.new_id() for _ in range(1000)}
    expect(len(made) == 1000, "duplicates")
    for run_id in made:
        check_run_id(run_id)


def the_real_clock_round_trips() -> None:
    from conductor import clock
    from conductor.events import EventKind, EventLog

    before = datetime.now(UTC)
    moment = clock.now()
    expect(moment.utcoffset() is not None and moment.utcoffset().total_seconds() == 0, "not UTC")
    expect(abs((moment - before).total_seconds()) < 5, "not now")
    with tempfile.TemporaryDirectory() as folder:
        log = EventLog(Path(folder))
        event = log.append(RUN, EventKind.RUN_STARTED)
        expect(log.read(RUN) == [event], "read differs")


def strict_lines_are_refused() -> None:
    from conductor.events import EventKind, EventLog, EventLogCorrupt

    with tempfile.TemporaryDirectory() as folder:
        log = EventLog(Path(folder))
        log.append(RUN, EventKind.RUN_STARTED, node="route", payload={"a": 1})
        good = (Path(folder) / f"{RUN}.jsonl").read_text("utf-8").strip()
        for bad in (
            good.replace('"node":"route"', '"node":5'),
            good.replace('"payload":{"a":1}', '"payload":[1]'),
            good.replace('"seq":1', '"seq":true'),
        ):
            (Path(folder) / f"{RUN}.jsonl").write_text(bad + "\n", "utf-8")
            try:
                log.read(RUN)
            except EventLogCorrupt as error:
                expect(str(error) == f"{RUN}.jsonl line 1 is not a valid event", str(error))
            else:
                raise AssertionError(f"accepted {bad[:60]}")


def hosts_on_this_machine_only() -> None:
    from conductor.config import SettingsError, get_settings

    saved = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith("CONDUCTOR_")}
    try:
        for host in ("http://LOCALHOST:11434", "http://[::1]", "http://127.0.0.1"):
            os.environ["CONDUCTOR_OLLAMA_HOST"] = host
            expect(get_settings().ollama_host == host, f"{host} changed")
        for host in (
            "http://127.0.0.2:11434",
            "http://0.0.0.0:11434",
            "http://[::ffff:127.0.0.1]:11434",
            "ftp://127.0.0.1:11434",
            "http://",
        ):
            os.environ["CONDUCTOR_OLLAMA_HOST"] = host
            try:
                get_settings()
            except SettingsError as error:
                expect(str(error).startswith("CONDUCTOR_OLLAMA_HOST: must be"), str(error))
            else:
                raise AssertionError(f"accepted {host}")
    finally:
        os.environ.pop("CONDUCTOR_OLLAMA_HOST", None)
        os.environ.update(saved)


def a_silent_server_times_out() -> None:
    from conductor.llm import tags

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        started = time.monotonic()
        try:
            tags.fetch_model_names(f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=0.5)
        except tags.OllamaUnreachable as error:
            expect(str(error) == "not reachable", str(error))
        else:
            raise AssertionError("answered")
        expect(time.monotonic() - started < 3, "took too long")
    finally:
        listener.close()


def the_installed_command_runs_doctor() -> None:
    server, host = serve(json.dumps({"models": [{"name": "qwen3.8:27b"}]}).encode())
    try:
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "nested" / "data"
            env = clean_env(CONDUCTOR_DATA_DIR=str(data), CONDUCTOR_OLLAMA_HOST=host)
            done = subprocess.run(
                [str(CONDUCTOR), "doctor"], capture_output=True, text=True, env=env, cwd=folder
            )
            expect(done.returncode == 0, f"exit {done.returncode}: {done.stdout}{done.stderr}")
            lines = done.stdout.splitlines()
            expect(lines[0].startswith(f"ok    python {sys.version_info[0]}."), lines[0])
            expect(
                lines[1:]
                == [
                    f"ok    data folder {data}",
                    f"ok    ollama {host}",
                    "ok    model qwen3.8:27b",
                    "All checks passed.",
                ],
                repr(lines),
            )
            env["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"
            done = subprocess.run(
                [str(CONDUCTOR), "doctor"], capture_output=True, text=True, env=env, cwd=folder
            )
            expect(done.returncode == 1, f"exit {done.returncode}")
            expect("FAIL  ollama http://127.0.0.1:9: not reachable" in done.stdout, done.stdout)
    finally:
        server.shutdown()
        server.server_close()


def the_installed_command_shows_a_run() -> None:
    from conductor.events import EventKind, EventLog

    with tempfile.TemporaryDirectory() as folder:
        data = Path(folder) / "data"
        EventLog(data / "runs").append(
            RUN, EventKind.TOOL_RESULT, node="finance", payload={"text": "a\nb", "n": 1.5}
        )
        env = clean_env(CONDUCTOR_DATA_DIR=str(data))
        done = subprocess.run(
            [str(CONDUCTOR), "runs", "show", RUN, "--payload"],
            capture_output=True,
            text=True,
            env=env,
            cwd=folder,
        )
        expect(done.returncode == 0, f"exit {done.returncode}: {done.stderr}")
        lines = done.stdout.splitlines()
        expect(
            lines[0].startswith("   1  ") and lines[0].endswith("  tool_result  finance"), lines[0]
        )
        expect(
            lines[1:] == ["      {", '        "n": 1.5,', '        "text": "a\\nb"', "      }"],
            repr(lines),
        )
        done = subprocess.run(
            [str(CONDUCTOR), "runs", "list"], capture_output=True, text=True, env=env, cwd=folder
        )
        expect(
            done.stdout.startswith(f"{RUN}  ") and done.stdout.endswith("  1 event\n"), done.stdout
        )


for name, test in [
    ("line separators stay inside one line", line_separators_stay_inside_one_line),
    ("a large payload round-trips", a_large_payload_round_trips),
    ("another process continues the count", another_process_continues_the_count),
    (
        "an existing folder keeps its mode; files are 0600",
        an_existing_folder_keeps_its_mode_and_files_are_owner_only,
    ),
    ("new ids are run ids and differ", new_ids_are_run_ids_and_differ),
    ("the real clock round-trips", the_real_clock_round_trips),
    ("strict lines are refused", strict_lines_are_refused),
    ("hosts on this machine only", hosts_on_this_machine_only),
    ("a silent server times out", a_silent_server_times_out),
    ("the installed command runs doctor", the_installed_command_runs_doctor),
    ("the installed command shows a run", the_installed_command_shows_a_run),
]:
    check(name, test)

print(f"FAILURES {FAILURES}")
```

## 5. The coder's tests and spot checks

The coder writes tests only where coverage needed them. Each such test must assert the behaviour it covers (an exception's type and message, a returned value), not only run the line. Tests use 127.0.0.1 servers they start themselves, never the real Ollama, and replace `conductor.clock.now` rather than depend on the date.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore (see `docs/phase-conventions.md`).

| # | Change (function) | Deciding test or probe, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `allow_nan=False` removed from the line's `json.dumps` (`events.EventLog.append` or its helper) | `test_a_payload_that_is_not_json_writes_nothing`, the NaN case | `ValueError`, nothing written | `NaN` written, no error |
| 2 | strict validation off in `events.EventLog.read` | `test_a_damaged_log_is_refused_with_its_line`, the `"seq":"2"` case | `line 2 is not a valid event` | read succeeds |
| 3 | the file split with `str.splitlines()` instead of on `\n` (`events.EventLog.read`) | probe "line separators stay inside one line" (U+2028 in a payload) | 2 events read | `EventLogCorrupt` |
| 4 | the host check reduced to `host.startswith(("http://127.0.0.1", "http://localhost"))` (`config`) | `test_a_host_elsewhere_is_refused`, the case `http://127.0.0.1@example.com:11434` | refused | accepted |
| 5 | `urllib.request.urlopen` used directly instead of the proxy-free opener (`tags.fetch_model_names`) | `test_a_proxy_in_the_environment_is_not_used` | `ok    ollama ...` | `FAIL  ollama ...: not reachable` |
| 6 | `os.fsync` call removed (`events.EventLog.append`) | `test_each_append_is_synced_to_disk` | 2 syncs | 0 |
| 7 | the `:latest` rule removed (`diagnostics.check_ollama`) | `test_the_model_must_be_pulled`, the case `qwen3-coder` with `qwen3-coder:latest` pulled | `ok    model qwen3-coder` | `FAIL  model qwen3-coder: ...` |
| 8 | ties ordered by run id descending (`events.EventLog.runs`) | `test_runs_newest_first_then_by_id` | RUN_C before RUN_A | RUN_A before RUN_C |
| 9 | a new `EventLog` starts every run at seq 1 without reading the file (`events.EventLog.append`) | `test_a_new_log_on_the_same_folder_continues_the_count` | seq 3 | seq 1 |
| 10 | file mode `0o644` in `os.open` (`events.EventLog.append`) | `test_only_the_owner_can_read_the_folder_and_files` | `0o600` | `0o644` |

Reasonable variations that are correct: a private helper that builds the line or parses it; keeping the next `seq` in a dict per run; catching `OSError` broadly in `tags.fetch_model_names` after `HTTPError`; building the doctor's lines in `cli` from `Check.line`.

## 6. Project rules

- Searches 4 to 6 (time and ids, network, pragmas).
- No message in `src/` formats a payload, a log line, or a reply body: read every `raise` and `typer.echo(..., err=True)` in `events.py`, `tags.py`, and `cli/main.py`.
- `README.md`: its commands are in `zsh` blocks; it mentions no hosted model or API key.

## 7. Out of scope

Each must be absent: any dependency not in the given `pyproject.toml`; a `logging` configuration; any command other than `doctor`, `runs list`, `runs show`; options other than `--payload`; a `.env` file or `env_file` setting; `python -m conductor` (`src/conductor/__main__.py`); log rotation or deletion; a lock for writers.

## 8. Progress log

The entry exists in the form of `docs/phase-conventions.md`, headed `## Phase 1: skeleton (...)`, with `Tests: 0 -> <passed> (given 65)`, and each deviation it lists is real and justified.
