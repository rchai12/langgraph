import json
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.domains import demo
from conductor.evals import run as evals_run
from conductor.evals.cases import CaseFileError, EvalCase, load_cases
from conductor.evals.run import CaseResult, case_line, model_for, overall_line, run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.ollama import OllamaModel
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from tests.support import run

REGISTRY = Registry((demo.DOMAIN,))
CASE = '[[case]]\nid = "a"\nrequest = "Echo hi"\nroute = "demo"\nplan = ["echo"]\n'
ROUTE = '{"domain": "demo"}'


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.toml"
    path.write_text(text, encoding="utf-8")
    return path


def problem(tmp_path: Path, text: str, seen: set[str] | None = None) -> str:
    path = write(tmp_path, text)
    with pytest.raises(CaseFileError) as raised:
        load_cases(path, REGISTRY, seen=seen)
    prefix = f"{path}: "
    assert str(raised.value).startswith(prefix)
    return str(raised.value)[len(prefix) :]


def plan(*steps: tuple[str, dict]) -> str:
    return json.dumps({"steps": [{"action": name, "args": args} for name, args in steps]})


def scripted(*replies: tuple[str, str, float]) -> ScriptedModel:
    made = [
        ScriptedReply(point, ModelReply(content=content, total_ns=int(seconds * 1e9)))
        for point, content, seconds in replies
    ]
    return ScriptedModel(made)


def once(case: EvalCase, model: ScriptedModel, tmp_path: Path) -> CaseResult:
    return run_case(
        case,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=1,
    )


def test_an_id_from_an_earlier_file_is_used_twice(tmp_path: Path) -> None:
    assert problem(tmp_path, CASE, seen={"a"}) == "case 1: id a is used twice"


def test_a_number_plan_and_args_on_an_escalation_are_refused(tmp_path: Path) -> None:
    numbered = CASE.replace('plan = ["echo"]\n', "plan = 3\n")
    assert problem(tmp_path, numbered) == (
        "case 1: plan must be a list of the domain's actions or escalate"
    )
    listed = CASE.replace('plan = ["echo"]\n', "plan = [1]\n")
    assert problem(tmp_path, listed) == (
        "case 1: plan must be a list of the domain's actions or escalate"
    )
    escalated = CASE.replace('plan = ["echo"]\n', 'plan = "escalate"\nargs = [{ text = "hi" }]\n')
    assert problem(tmp_path, escalated) == "case 1: args must be one table per planned step"
    assert problem(tmp_path, CASE + 'args = "nope"\n') == (
        "case 1: args must be one table per planned step"
    )
    assert problem(tmp_path, CASE + 'args = ["nope"]\n') == (
        "case 1: args must be one table per planned step"
    )
    assert problem(tmp_path, "case = []\n") == "the file needs at least one [[case]]"
    assert problem(tmp_path, CASE.replace('request = "Echo hi"', "request = 1")) == (
        "case 1: request must have 1 to 2000 characters"
    )
    long = "x" * 2001
    assert problem(tmp_path, CASE.replace('request = "Echo hi"', f'request = "{long}"')) == (
        "case 1: request must have 1 to 2000 characters"
    )


def test_a_request_of_2000_characters_loads(tmp_path: Path) -> None:
    text = "y" * 2000
    case = load_cases(
        write(tmp_path, CASE.replace('request = "Echo hi"', f'request = "{text}"')),
        REGISTRY,
    )[0]
    assert case.request == text


def test_args_missing_a_key_are_not_right(tmp_path: Path) -> None:
    case = EvalCase(
        "say-hi",
        "demo: say hi",
        "demo",
        ("echo",),
        ({"text": "hi", "extra": "no"},),
    )
    result = once(case, scripted(("plan", plan(("echo", {"text": "hi"})), 1.0)), tmp_path)
    assert (result.plan_ok, result.args_ok) == (1, 0)
    longer = EvalCase("say-hi", "demo: say hi", "demo", ("echo",), ({"text": "hi"}, {"text": "x"}))
    result = once(longer, scripted(("plan", plan(("echo", {"text": "hi"})), 1.0)), tmp_path)
    assert result.args_ok == 0


def test_actions_in_another_order_are_not_right(tmp_path: Path) -> None:
    case = EvalCase("both", "demo: say hi", "demo", ("echo", "note"))
    result = once(
        case,
        scripted(("plan", plan(("note", {"title": "T"}), ("echo", {"text": "hi"})), 1.0)),
        tmp_path,
    )
    assert result.plan_ok == 0


def test_an_invalid_model_output_is_not_the_expected_escalation(tmp_path: Path) -> None:
    case = EvalCase("table", "demo: book a table", "demo", "escalate")
    result = once(
        case,
        scripted(("plan", '{"steps": [{"action": "send", "args": {}}]}', 1.0)),
        tmp_path,
    )
    assert (result.plan_ok, result.valid, result.escalated) == (0, 0, 1)


def test_a_classifier_route_and_a_plan_sum_both_times(tmp_path: Path) -> None:
    case = EvalCase("say", "Say something to me", "demo", ("echo",))
    result = once(
        case,
        scripted(("route", ROUTE, 2.0), ("plan", plan(("echo", {"text": "hi"})), 5.0)),
        tmp_path,
    )
    assert result.seconds == (7.0,)
    quiet = EvalCase("empty", "demo:", "escalate")
    result = once(quiet, ScriptedModel([]), tmp_path)
    assert (result.route_ok, result.plan_ok, result.seconds) == (1, 1, (0.0,))


def test_one_run_has_equal_percentiles_and_overall_without_args_prints_a_dash() -> None:
    only = CaseResult("a", 1, 1, 1, 1, None, 1, 0, 0, (1.5,))
    assert case_line(only).endswith("p50 1.50s  p95 1.50s")
    assert overall_line((only,)) == (
        "overall  1 cases  consistent 1/1  route 1/1  plan 1/1  args -  valid 1/1"
        "  escalated 0/1  p50 1.50s  p95 1.50s"
    )


def test_model_for_uses_the_configured_ollama() -> None:
    settings = get_settings()
    made = model_for(settings)
    assert isinstance(made, OllamaModel)
    assert (made._host, made._timeout) == (settings.ollama_host, settings.model_timeout_seconds)


def test_too_many_runs_are_refused() -> None:
    result = run("eval", "run", "--runs", "101")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        "Error: --runs must be 1 to 100\n",
    )


def test_a_folder_runs_each_file_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    replies: list[ScriptedReply] = []
    monkeypatch.setattr(evals_run, "model_for", lambda settings: ScriptedModel(replies))
    folder = tmp_path / "cases"
    folder.mkdir()
    one = '[[case]]\nid = "alpha"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'
    two = (
        '[[case]]\nid = "beta"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n\n'
        '[[case]]\nid = "gamma"\nrequest = "demo: say hi"\nroute = "demo"\nplan = ["echo"]\n'
    )
    (folder / "b.toml").write_text(two, encoding="utf-8")
    (folder / "a.toml").write_text(one, encoding="utf-8")
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    content = json.dumps({"steps": echo})
    replies.extend(
        ScriptedReply("plan", ModelReply(content=content, total_ns=10**9)) for _ in range(3)
    )
    result = run("eval", "run", "--cases", folder, "--runs", "1")
    assert result.exit_code == 0
    assert [line.split()[0] for line in result.stdout.splitlines()[:3]] == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_a_file_that_is_not_toml_is_not_a_case_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    result = run("eval", "run", "--cases", path, "--runs", "1")
    assert (result.exit_code, result.stderr) == (1, f"Error: no case files at {path}\n")
