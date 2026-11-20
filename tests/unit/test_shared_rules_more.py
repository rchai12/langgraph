from pathlib import Path

import pytest
from langgraph.types import Interrupt

from conductor.evals.cases import load_cases
from conductor.events import EventKind, EventLog
from tests.support import fixed_times
from tests.unit.test_checkpoint_status_cases import APPROVAL, record, refused
from tests.unit.test_eval_cases import CASE, REGISTRY, problem, write

OTHER = "0123456789abcdef0123456789abcdef"


def test_runs_lists_only_a_valid_event_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(monkeypatch, "2026-11-20T09:00:00+00:00")
    log = EventLog(tmp_path)
    log.append(OTHER, EventKind.RUN_STARTED)
    (tmp_path / f"{OTHER}.jsonl.jsonl").write_bytes(b"not an event")
    (tmp_path / f"{OTHER}x.jsonl").write_bytes(b"not an event")
    assert [item.run_id for item in log.runs()] == [OTHER]


def test_a_jsonl_suffix_in_another_case_is_skipped(tmp_path: Path) -> None:
    (tmp_path / f"{OTHER}.JSONL").write_bytes(b"not an event")
    assert EventLog(tmp_path).runs() == []


def test_an_interrupt_id_must_be_exactly_str() -> None:
    class IdText(str):
        pass

    saved = record(
        {"branch:to:wait_approval": None},
        [("task", "__interrupt__", [Interrupt({"approval_id": IdText(APPROVAL)})])],
    )
    refused(saved)


def test_a_case_request_uses_the_shared_bound(tmp_path: Path) -> None:
    message = "case 1: request must have 1 to 2000 characters"
    long = "x" * 2001
    assert problem(tmp_path, CASE.replace('request = "Echo hi"', f'request = "{long}"')) == message
    assert problem(tmp_path, CASE.replace('request = "Echo hi"', 'request = " \\t "')) == message
    exact = "y" * 2000
    path = write(tmp_path, CASE.replace('request = "Echo hi"', f'request = "{exact}"'))
    assert load_cases(path, REGISTRY)[0].request == exact
