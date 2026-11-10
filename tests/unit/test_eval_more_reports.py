import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.report import (
    CaseNumbers,
    Report,
    ReportError,
    build_report,
    compare_lines,
    latest_report,
)
from conductor.evals.run import CaseResult, run_case
from conductor.events import EventLog
from conductor.llm.model import ModelInfo, ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from tests.support import run

REGISTRY = Registry((demo.DOMAIN,))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
PLAN = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})


def _result(case_id: str, *counts: int | None, runs: int = 5) -> CaseResult:
    consistent, route, plan, args, valid, escalated = counts
    return CaseResult(
        case_id,
        runs,
        consistent,  # type: ignore[arg-type]
        route,  # type: ignore[arg-type]
        plan,  # type: ignore[arg-type]
        args,
        valid,  # type: ignore[arg-type]
        escalated,  # type: ignore[arg-type]
        0,
        (1.0,) * runs,
    )


def _report(cases: list[CaseNumbers]) -> Report:
    return Report(
        version=1,
        created=NOW,
        model="test-model:1b",
        digests=["1" * 64],
        templates={"plan": ["2" * 64]},
        case_files={"demo.toml": "4" * 64},
        runs=5,
        cases=cases,
    )


def _numbers(case_id: str, *counts: int | None, runs: int = 5) -> CaseNumbers:
    consistent, route, plan, args, valid, escalated = counts
    return CaseNumbers(
        id=case_id,
        runs=runs,
        consistent=consistent,  # type: ignore[arg-type]
        route_ok=route,  # type: ignore[arg-type]
        plan_ok=plan,  # type: ignore[arg-type]
        args_ok=args,
        valid=valid,  # type: ignore[arg-type]
        escalated=escalated,  # type: ignore[arg-type]
        unavailable=0,
        seconds=[1.0] * runs,
        run_ids=["a" * 32] * runs,
    )


def test_one_run_keeps_its_id(tmp_path: Path) -> None:
    case = EvalCase("say-hi", "demo: say hi", "demo", ("echo",))
    model = ScriptedModel([ScriptedReply("plan", ModelReply(content=PLAN, total_ns=10**9))])
    result = run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=1,
    )
    assert len(result.run_ids) == 1
    assert (tmp_path / "runs" / f"{result.run_ids[0]}.jsonl").is_file()


def test_two_files_and_two_results_keep_their_order(tmp_path: Path) -> None:
    first = tmp_path / "a.toml"
    second = tmp_path / "b.toml"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    alpha = _result("alpha", 1, 1, 1, 1, 1, 0, runs=1)
    beta = _result("beta", 1, 1, 1, None, 1, 0, runs=1)
    built = build_report(
        [alpha, beta],
        files=[first, second],
        model_name="test-model:1b",
        runs=1,
        log=EventLog(tmp_path / "runs"),
    )
    assert [case.id for case in built.cases] == ["alpha", "beta"]
    assert built.case_files == {
        "a.toml": hashlib.sha256(b"one").hexdigest(),
        "b.toml": hashlib.sha256(b"two").hexdigest(),
    }


def test_two_digests_are_kept_sorted(tmp_path: Path) -> None:
    case = EvalCase("say-hi", "demo: say hi", "demo", ("echo",))
    log = EventLog(tmp_path / "runs")
    results = []
    for digest in ("b" * 64, "a" * 64):
        model = ScriptedModel(
            [ScriptedReply("plan", ModelReply(content=PLAN, total_ns=10**9))],
            info=ModelInfo(name="m", digest=digest, capabilities=("completion",)),
        )
        results.append(run_case(case, REGISTRY, model=model, model_name="m", log=log, runs=1))
    built = build_report(results, files=[], model_name="m", runs=1, log=log)
    assert built.digests == ["a" * 64, "b" * 64]


def test_a_run_with_no_log_adds_nothing(tmp_path: Path) -> None:
    missing = CaseResult("gone", 1, 1, 1, 1, None, 1, 0, 0, (1.0,), ("f" * 32,))
    built = build_report(
        [missing],
        files=[],
        model_name="m",
        runs=1,
        log=EventLog(tmp_path / "runs"),
    )
    assert (built.digests, built.templates) == ([], {})


def test_a_report_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    name = "20261110T090000000000Z.json"
    (folder / name).write_bytes(b"\xff")
    with pytest.raises(ReportError) as raised:
        latest_report(folder)
    assert str(raised.value) == f"{name} is not a report"
    assert "\xff" not in str(raised.value)


def test_a_removed_case_and_an_escalation_are_named_alone() -> None:
    both = _report(
        [
            _numbers("say-hi", 5, 5, 5, 5, 5, 0),
            _numbers("weather", 5, 5, 5, None, 5, 5),
        ]
    )
    kept = both.model_copy(update={"cases": [both.cases[0]]})
    assert compare_lines(both, kept) == ["removed: case weather"]
    moved = both.cases[0].model_copy(update={"escalated": 1})
    assert compare_lines(both, both.model_copy(update={"cases": [moved, both.cases[1]]})) == [
        "say-hi  escalated 0/5 -> 1/5"
    ]


def test_notes_are_not_a_previous_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    replies: list[ScriptedReply] = [ScriptedReply("plan", ModelReply(content=PLAN, total_ns=10**9))]
    monkeypatch.setattr("conductor.evals.run.model_for", lambda settings: ScriptedModel(replies))
    cases = tmp_path / "only.toml"
    cases.write_text(
        '[[case]]\nid = "say-hi"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n',
        encoding="utf-8",
    )
    folder = tmp_path / "data" / "evals" / "reports"
    folder.mkdir(parents=True)
    (folder / "notes.json").write_text("{}", encoding="utf-8")
    result = run("eval", "run", "--cases", cases, "--runs", "1")
    assert result.exit_code == 0
    assert any(line.startswith("report ") for line in result.stdout.splitlines())
    assert not any(line.startswith("previous ") for line in result.stdout.splitlines())


def test_a_bad_run_count_wins_over_an_unreadable_report(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "evals" / "reports"
    folder.mkdir(parents=True)
    (folder / "20261109T000000000000Z.json").write_text("SYNTHETIC-SECRET", encoding="utf-8")
    result = run("eval", "run", "--runs", "0")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        "Error: --runs must be 1 to 100\n",
    )
