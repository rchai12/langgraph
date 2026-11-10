import json
from pathlib import Path

import pytest

from conductor.evals import run as evals_run
from conductor.llm.model import ModelReply
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


def plan_reply(steps: list, seconds: float) -> ScriptedReply:
    content = json.dumps({"steps": steps})
    return ScriptedReply("plan", ModelReply(content=content, total_ns=int(seconds * 1e9)))


def test_eval_run_prints_a_line_per_case_and_overall(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend(
        [plan_reply(echo, 1.0), plan_reply(echo, 1.0), plan_reply([], 2.0), plan_reply([], 2.0)]
    )
    result = run("eval", "run", "--cases", cases, "--runs", "2")
    assert (result.exit_code, result.stderr) == (0, "")
    assert result.stdout.splitlines() == [
        "say-hi  consistent 2/2  route 2/2  plan 2/2  args 2/2  valid 2/2  escalated 0/2"
        "  p50 1.00s  p95 1.00s",
        "weather  consistent 2/2  route 2/2  plan 2/2  args -  valid 2/2  escalated 2/2"
        "  p50 2.00s  p95 2.00s",
        "overall  2 cases  consistent 4/4  route 4/4  plan 4/4  args 2/2  valid 4/4"
        "  escalated 2/4  p50 1.00s  p95 2.00s",
    ]


def test_five_runs_by_default_from_one_file(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0)] * 5)
    single = cases / "only.toml"
    single.write_text(CASES.split("\n\n")[0] + "\n", encoding="utf-8")
    result = run("eval", "run", "--cases", single)
    assert result.stdout.splitlines()[0].startswith("say-hi  consistent 5/5")


def test_runs_are_logged_under_the_data_folder(cases: Path, model: list, tmp_path: Path) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0), plan_reply([], 1.0)])
    run("eval", "run", "--cases", cases, "--runs", "1")
    assert len(list((tmp_path / "data" / "evals" / "runs").glob("*.jsonl"))) == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--runs", "0"), "Error: --runs must be 1 to 100\n"),
        (("--cases", "nowhere"), "Error: no case files at nowhere\n"),
    ],
)
def test_errors(cases: Path, model: list, args: tuple[str, ...], message: str) -> None:
    result = run("eval", "run", *args)
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", message)


def test_a_bad_case_file_names_itself(cases: Path, model: list) -> None:
    bad = cases / "bad.toml"
    bad.write_text('[[case]]\nid = "x"\nrequest = "hi"\nroute = "travel"\n', encoding="utf-8")
    result = run("eval", "run", "--cases", cases)
    assert (result.exit_code, result.stdout) == (1, "")
    assert result.stderr == f"Error: {bad}: case 1: route must be a registered domain or escalate\n"
