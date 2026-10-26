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
