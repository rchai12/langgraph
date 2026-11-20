import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.evals.report import save_report
from conductor.events import EventKind, EventLog
from conductor.llm.scripted import ScriptedModel
from conductor.mcp_client.client import client_for
from conductor.runtime import open_runtime
from conductor.store import Store
from tests.integration.test_mcp_client import COMMAND, FAKE_SERVER
from tests.support import fixed_times
from tests.unit.test_eval_report import PLAN, build, run, scripted

RUN_A = "0123456789abcdef0123456789abcdef"


@contextmanager
def umask(value: int) -> Iterator[None]:
    previous = os.umask(value)
    try:
        yield
    finally:
        os.umask(previous)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def levels(top: Path, *names: str) -> list[int]:
    found = []
    for name in names:
        top = top / name
        found.append(mode(top))
    return found


@pytest.mark.parametrize("mask", [0o022, 0o277], ids=["umask-022", "umask-277"])
def test_the_event_log_makes_every_folder_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mask: int
) -> None:
    fixed_times(monkeypatch, "2026-11-20T09:00:00+00:00")
    with umask(mask):
        EventLog(tmp_path / "x" / "data" / "runs").append(RUN_A, EventKind.RUN_STARTED)
    assert levels(tmp_path, "x", "data", "runs") == [0o700, 0o700, 0o700]
    assert mode(tmp_path / "x" / "data" / "runs" / f"{RUN_A}.jsonl") == 0o600


@pytest.mark.parametrize("mask", [0o022, 0o277], ids=["umask-022", "umask-277"])
def test_a_report_makes_every_folder_private(tmp_path: Path, mask: int) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    with umask(mask):
        path = save_report(built, tmp_path / "x" / "reports")
    assert levels(tmp_path, "x", "reports") == [0o700, 0o700]
    assert mode(path) == 0o600


def test_the_store_makes_every_folder_private(tmp_path: Path) -> None:
    with umask(0o022):
        Store(tmp_path / "x" / "data" / "conductor.db")
    assert levels(tmp_path, "x", "data") == [0o700, 0o700]
    assert mode(tmp_path / "x" / "data" / "conductor.db") == 0o600


def test_the_runtime_makes_every_folder_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "x" / "data"))
    with umask(0o022), open_runtime(get_settings(), model=ScriptedModel([])):
        assert levels(tmp_path, "x", "data") == [0o700, 0o700]
        data = tmp_path / "x" / "data"
        assert (mode(data / "checkpoints.db"), mode(data / "conductor.db")) == (0o600, 0o600)


def test_the_tool_log_makes_every_folder_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "x" / "data"))
    monkeypatch.setenv("CONDUCTOR_MCP__FAKE", COMMAND)
    with umask(0o022):
        client_for(FAKE_SERVER, get_settings()).list_tools()
    assert levels(tmp_path, "x", "data", "mcp") == [0o700, 0o700, 0o700]
    assert mode(tmp_path / "x" / "data" / "mcp" / "fake.log") == 0o600
