import shlex
import sys
from pathlib import Path

import pytest

from conductor import diagnostics, domains
from conductor.config import get_settings
from conductor.contracts import Contract, Escalation
from conductor.domains import demo
from conductor.llm.scripted import ScriptedModel, ScriptError
from conductor.registry import Action, Domain, McpServer
from conductor.runtime import ask, open_runtime
from conductor.store import Store
from tests.support import fake_ollama, run

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


class Task(Contract):
    task: str


ECHO = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
SHOUT = Action("shout", "Fail on purpose.", "tool", "fail", "read", Reason, Text, "fake")
GONE = Action("gone", "Missing tool.", "tool", "nope", "read", Text, Text, "fake")
ADVISE = Action("advise", "Advise the lab.", "agent", "advisor", "implement", Task, Task)
LAB = Domain("lab", "Lab tools.", (ECHO,), servers=(McpServer("fake"),))
TWO = Domain("lab", "Lab tools.", (SHOUT, GONE), servers=(McpServer("fake"),))
QUIET = Domain("lab", "Lab tools.", (ADVISE,), servers=(McpServer("fake"),))


@pytest.fixture(autouse=True)
def python_3_12_13(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def test_registered_appends_the_demo_domain_only_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    assert domains.registered(get_settings()) == (LAB,)
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    assert domains.registered(get_settings()) == (LAB, demo.DOMAIN)


def test_open_runtime_starts_nothing_and_ask_lists_tools_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _command(monkeypatch)
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    log_path = get_settings().data_dir / "mcp" / "fake.log"
    with open_runtime(get_settings()):
        assert not log_path.exists()
    with open_runtime(get_settings(), model=ScriptedModel([])) as opened:
        with pytest.raises(ScriptError):
            ask(opened, "hello")
        with pytest.raises(ScriptError):
            ask(opened, "hello again")
    assert log_path.read_text().count("fake server started") == 1


def test_resume_and_retry_print_the_failed_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    resumed = run("resume", "3" * 32)
    stored = _escalation()
    retried = run("escalations", "retry", stored.escalation_id, "--yes")
    error = "Error: the tool check failed\n  server fake: no_command\n"
    assert (resumed.exit_code, resumed.stdout, resumed.stderr) == (1, "", error)
    assert (retried.exit_code, retried.stdout, retried.stderr) == (
        1,
        f"Retry recorded for {stored.escalation_id}.\n",
        error,
    )


def test_cancel_without_resuming_starts_no_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    stored = _escalation()
    cancelled = run("escalations", "cancel", stored.escalation_id, "--no-resume")
    assert (cancelled.exit_code, cancelled.stdout, cancelled.stderr) == (
        0,
        f"Cancelled {stored.escalation_id}.\n",
        "",
    )
    assert not (get_settings().data_dir / "mcp" / "fake.log").exists()


def test_an_unset_command_fails_the_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    result = _doctor(monkeypatch)
    assert result.exit_code == 1
    assert result.stdout.splitlines()[4:] == ["FAIL  server fake: no_command", "1 check failed."]


def test_two_problems_count_as_two_failed_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    _command(monkeypatch)
    monkeypatch.setattr(domains, "DOMAINS", (TWO,))
    result = _doctor(monkeypatch)
    assert result.exit_code == 1
    assert result.stdout.splitlines()[4:] == [
        "FAIL  server fake: action lab.shout: a read action needs a tool marked read-only",
        "FAIL  server fake: action lab.gone: no tool nope on server fake",
        "2 checks failed.",
    ]


def test_a_server_with_no_tool_action_reports_zero_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    _command(monkeypatch)
    monkeypatch.setattr(domains, "DOMAINS", (QUIET,))
    result = _doctor(monkeypatch)
    assert result.exit_code == 0
    assert result.stdout.splitlines()[4:] == [
        "ok    server fake: 5 tools, 0 actions checked",
        "All checks passed.",
    ]


def _command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CONDUCTOR_MCP__FAKE", f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    )


def _escalation():
    escalation = Escalation(kind="unknown_route", detail="no domain fits", run_id="2" * 32)
    return Store(get_settings().db_path).add_escalation(escalation)


def _doctor(monkeypatch: pytest.MonkeyPatch):
    with fake_ollama() as (fake, host):
        fake.models("qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        return run("doctor")
