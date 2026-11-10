import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import clock
from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.report import (
    CaseNumbers,
    Report,
    ReportError,
    build_report,
    compare_lines,
    latest_report,
    save_report,
)
from conductor.evals.run import CaseResult, run_case
from conductor.events import EventKind, EventLog
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.prompts import load_template
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
ECHO = EvalCase(
    id="say-hi",
    request="Say hi back to me",
    route="demo",
    plan=("echo",),
    args=({"text": "hi"},),
)
ROUTE = '{"domain": "demo"}'
PLAN = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
EMPTY = json.dumps({"steps": []})
NOW = datetime(2026, 11, 10, 9, 30, 15, 250000, tzinfo=UTC)
NAME = "20261110T093015250000Z.json"


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def scripted(*plans: str) -> ScriptedModel:
    replies = []
    for content in plans:
        replies.append(ScriptedReply("route", ModelReply(content=ROUTE, total_ns=10**9)))
        replies.append(ScriptedReply("plan", ModelReply(content=content, total_ns=2 * 10**9)))
    return ScriptedModel(replies)


def run(tmp_path: Path, model: ScriptedModel, runs: int) -> CaseResult:
    return run_case(
        ECHO,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=runs,
    )


def build(tmp_path: Path, result: CaseResult) -> Report:
    cases = tmp_path / "demo.toml"
    cases.write_bytes(b"# synthetic cases\n")
    return build_report(
        [result],
        files=[cases],
        model_name="test-model:1b",
        runs=result.runs,
        log=EventLog(tmp_path / "runs"),
    )


# run ids


def test_each_run_keeps_its_id_in_order(tmp_path: Path) -> None:
    result = run(tmp_path, scripted(PLAN, EMPTY), 2)
    log = EventLog(tmp_path / "runs")
    contents = [
        [
            event.payload["content"]
            for event in log.read(run_id)
            if event.kind is EventKind.MODEL_REPLY
        ]
        for run_id in result.run_ids
    ]
    assert contents == [[ROUTE, PLAN], [ROUTE, EMPTY]]
    assert result == CaseResult("say-hi", 2, 1, 2, 1, 1, 2, 1, 0, (3.0, 3.0))


# building


def test_a_report_holds_the_numbers_and_the_fingerprint(tmp_path: Path) -> None:
    result = run(tmp_path, scripted(PLAN, PLAN), 2)
    assert build(tmp_path, result) == Report(
        version=1,
        created=NOW,
        model="test-model:1b",
        digests=[SCRIPTED_INFO.digest],
        templates={
            "plan": [load_template("plan.v2").sha256],
            "route": [load_template("route.v1").sha256],
        },
        case_files={"demo.toml": hashlib.sha256(b"# synthetic cases\n").hexdigest()},
        runs=2,
        cases=[
            CaseNumbers(
                id="say-hi",
                runs=2,
                consistent=2,
                route_ok=2,
                plan_ok=2,
                args_ok=2,
                valid=2,
                escalated=0,
                unavailable=0,
                seconds=[3.0, 3.0],
                run_ids=list(result.run_ids),
            )
        ],
    )


def test_the_fingerprint_reads_only_these_runs(tmp_path: Path) -> None:
    EventLog(tmp_path / "runs").append(
        "f" * 32,
        EventKind.MODEL_REQUEST,
        payload={"point": "answer", "template_sha256": "e" * 64, "digest": "d" * 64},
    )
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    assert (built.digests, sorted(built.templates)) == ([SCRIPTED_INFO.digest], ["plan", "route"])


def test_a_model_that_is_down_leaves_no_fingerprint(tmp_path: Path) -> None:
    model = ScriptedModel([], info=ModelUnavailable("timeout"))
    built = build(tmp_path, run(tmp_path, model, 1))
    assert (built.digests, built.templates, built.cases[0].unavailable) == ([], {}, 1)
    assert built.cases[0].seconds == [0.0]


# saving and reading


def test_a_saved_report_reads_back(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    folder = tmp_path / "reports"
    path = save_report(built, folder)
    assert path == folder / NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert Report.from_json(path.read_bytes()) == built
    assert latest_report(folder) == (NAME, built)


def test_the_name_is_the_time_in_utc(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    elsewhere = NOW.astimezone(timezone(timedelta(hours=-5)))
    path = save_report(built.model_copy(update={"created": elsewhere}), tmp_path / "reports")
    assert path.name == NAME


def test_a_report_name_is_never_reused(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    path = save_report(built, tmp_path / "reports")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_report(built.model_copy(update={"runs": 9}), tmp_path / "reports")
    assert path.read_bytes() == before


def test_no_report_yet(tmp_path: Path) -> None:
    assert latest_report(tmp_path / "missing") is None
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "notes.json").write_text("{}", encoding="utf-8")
    (folder / "20261110T093015250000Z.txt").write_text("{}", encoding="utf-8")
    assert latest_report(folder) is None


def test_the_newest_name_wins(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    folder = tmp_path / "reports"
    older = built.model_copy(update={"created": NOW - timedelta(days=1), "model": "old:1b"})
    save_report(older, folder)
    save_report(built, folder)
    (folder / "zzz.json").write_text("not a report", encoding="utf-8")
    assert latest_report(folder) == (NAME, built)


def good_report(tmp_path: Path) -> dict:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    return json.loads(built.model_dump_json())


@pytest.mark.parametrize(
    "change",
    [
        "SYNTHETIC-SECRET is not JSON",
        {"version": 2},
        {"colour": "SYNTHETIC-SECRET"},
        {"created": "2026-11-10T09:30:15"},
        {"runs": "1"},
        {"cases": None},
    ],
    ids=["not-json", "version", "extra-key", "naive-time", "text-runs", "no-cases"],
)
def test_a_bad_report_is_refused(tmp_path: Path, change: str | dict) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    if isinstance(change, str):
        text = change
    else:
        base = good_report(tmp_path)
        text = json.dumps(
            {key: value for key, value in {**base, **change}.items() if value is not None}
        )
    (folder / NAME).write_text(text, encoding="utf-8")
    with pytest.raises(ReportError) as raised:
        latest_report(folder)
    assert str(raised.value) == f"{NAME} is not a report"


# comparing


def numbers(case_id: str, runs: int, *counts: int | None) -> CaseNumbers:
    consistent, route, plan, args, valid, escalated = counts
    return CaseNumbers(
        id=case_id,
        runs=runs,
        consistent=consistent,
        route_ok=route,
        plan_ok=plan,
        args_ok=args,
        valid=valid,
        escalated=escalated,
        unavailable=0,
        seconds=[1.0] * runs,
        run_ids=["a" * 32] * runs,
    )


BASE = Report(
    version=1,
    created=NOW,
    model="test-model:1b",
    digests=["1" * 64],
    templates={"plan": ["2" * 64], "route": ["3" * 64]},
    case_files={"demo.toml": "4" * 64},
    runs=5,
    cases=[numbers("say-hi", 5, 5, 5, 5, 5, 5, 0), numbers("weather", 5, 5, 5, 5, None, 5, 5)],
)


def test_nothing_changed() -> None:
    later = BASE.model_copy(update={"created": NOW + timedelta(hours=1)})
    assert compare_lines(BASE, later) == ["no change"]


def test_the_same_shares_from_more_runs_are_no_change() -> None:
    doubled = [
        numbers("say-hi", 10, 10, 10, 10, 10, 10, 0),
        numbers("weather", 10, 10, 10, 10, None, 10, 10),
    ]
    assert compare_lines(BASE, BASE.model_copy(update={"runs": 10, "cases": doubled})) == [
        "no change"
    ]


@pytest.mark.parametrize(
    ("update", "line"),
    [
        ({"model": "other:7b"}, "changed: model"),
        ({"digests": ["5" * 64]}, "changed: digest"),
        ({"templates": {**BASE.templates, "plan": ["6" * 64]}}, "changed: template plan"),
        ({"templates": {**BASE.templates, "answer": ["7" * 64]}}, "changed: template answer"),
        ({"case_files": {"demo.toml": "8" * 64}}, "changed: case file demo.toml"),
        (
            {"case_files": {**BASE.case_files, "more.toml": "9" * 64}},
            "changed: case file more.toml",
        ),
    ],
    ids=["model", "digest", "template", "new-template", "case-file", "new-case-file"],
)
def test_a_changed_fingerprint_is_named(update: dict, line: str) -> None:
    assert compare_lines(BASE, BASE.model_copy(update=update)) == [line]


def test_a_case_whose_shares_moved() -> None:
    moved = [numbers("say-hi", 5, 4, 5, 3, 3, 5, 1), BASE.cases[1]]
    assert compare_lines(BASE, BASE.model_copy(update={"cases": moved})) == [
        "say-hi  consistent 5/5 -> 4/5  plan 5/5 -> 3/5  args 5/5 -> 3/5  escalated 0/5 -> 1/5"
    ]


def test_shares_compare_across_run_counts() -> None:
    moved = [BASE.cases[0], numbers("weather", 10, 10, 9, 10, 2, 10, 10)]
    assert compare_lines(BASE, BASE.model_copy(update={"cases": moved})) == [
        "weather  route 5/5 -> 9/10  args - -> 2/10"
    ]


def test_every_kind_of_change_in_order() -> None:
    current = BASE.model_copy(
        update={
            "model": "other:7b",
            "digests": ["5" * 64],
            "templates": {"answer": ["7" * 64], "route": ["3" * 64]},
            "case_files": {"demo.toml": "8" * 64, "more.toml": "9" * 64},
            "cases": [
                numbers("new-one", 5, 5, 5, 5, None, 5, 0),
                numbers("weather", 5, 5, 5, 5, None, 4, 5),
                numbers("other-new", 5, 5, 5, 5, None, 5, 0),
            ],
        }
    )
    assert compare_lines(BASE, current) == [
        "changed: model",
        "changed: digest",
        "changed: template answer",
        "changed: template plan",
        "changed: case file demo.toml",
        "changed: case file more.toml",
        "weather  valid 5/5 -> 4/5",
        "added: case new-one",
        "added: case other-new",
        "removed: case say-hi",
    ]
