import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.evals import run as evals_run
from conductor.evals.report import Report
from conductor.llm.model import ModelReply
from conductor.llm.prompts import load_template
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run

CASES = """[[case]]
id = "say-hi"
request = "demo: say hi"
route = "demo"
plan = ["echo"]
args = [{ text = "hi" }]

[[case]]
id = "weather"
request = "demo: what is the weather"
route = "demo"
plan = "escalate"
"""
MORE = """
[[case]]
id = "say-bye"
request = "demo: say bye"
route = "demo"
plan = ["echo"]
"""
FIRST = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
SECOND = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
ECHO = [{"action": "echo", "args": {"text": "hi"}}]


@pytest.fixture
def cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases"
    path.mkdir()
    (path / "demo.toml").write_text(CASES, encoding="utf-8")
    return path


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[ScriptedReply]:
    replies: list[ScriptedReply] = []
    monkeypatch.setattr(evals_run, "model_for", lambda settings: ScriptedModel(replies))
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    return replies


def plan_reply(steps: list) -> ScriptedReply:
    content = json.dumps({"steps": steps})
    return ScriptedReply("plan", ModelReply(content=content, total_ns=10**9))


def eval_at(monkeypatch, moment: datetime, cases: Path, model: list, plans: list, *args: str):
    monkeypatch.setattr(clock, "now", lambda: moment)
    model[:] = [plan_reply(steps) for steps in plans]
    result = run("eval", "run", "--cases", cases, *args)
    assert (result.exit_code, result.stderr) == (0, "")
    return result.stdout.splitlines()


def test_the_first_run_saves_a_report(
    monkeypatch, cases: Path, model: list, tmp_path: Path
) -> None:
    lines = eval_at(monkeypatch, FIRST, cases, model, [ECHO, ECHO, [], []], "--runs", "2")
    assert len(lines) == 4
    assert lines[3] == "report 20261110T090000000000Z.json"
    saved = tmp_path / "data" / "evals" / "reports" / "20261110T090000000000Z.json"
    report = Report.from_json(saved.read_bytes())
    assert [case.id for case in report.cases] == ["say-hi", "weather"]
    assert (report.runs, report.created, report.digests) == (2, FIRST, ["0" * 64])
    assert report.templates == {"plan": [load_template("plan.v1").sha256]}
    assert report.case_files == {"demo.toml": hashlib.sha256(CASES.encode()).hexdigest()}


def test_a_second_run_names_what_moved(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, ECHO, [], []], "--runs", "2")
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, ECHO, ECHO, ECHO], "--runs", "2")
    assert lines[3:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "weather  plan 2/2 -> 0/2  escalated 2/2 -> 0/2",
    ]


def test_an_unchanged_second_run(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, []], "--runs", "1")
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, []], "--runs", "1")
    assert lines[3:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "no change",
    ]


def test_an_edited_case_file_is_named(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, []], "--runs", "1")
    with (cases / "demo.toml").open("a", encoding="utf-8") as handle:
        handle.write(MORE)
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, [], ECHO], "--runs", "1")
    assert lines[4:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "changed: case file demo.toml",
        "added: case say-bye",
    ]


def test_a_bad_previous_report_stops_before_any_run(
    cases: Path, model: list, tmp_path: Path
) -> None:
    folder = tmp_path / "data" / "evals" / "reports"
    folder.mkdir(parents=True)
    (folder / "20261109T000000000000Z.json").write_text("SYNTHETIC-SECRET", encoding="utf-8")
    model.append(plan_reply(ECHO))
    result = run("eval", "run", "--cases", cases, "--runs", "1")
    assert (result.exit_code, result.stdout) == (1, "")
    assert result.stderr == "Error: 20261109T000000000000Z.json is not a report\n"
    assert not (tmp_path / "data" / "evals" / "runs").exists()
