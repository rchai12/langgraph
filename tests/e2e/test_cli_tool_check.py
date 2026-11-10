import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import diagnostics, domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.mcp_client.check import ToolCheckFailed
from conductor.registry import Action, Domain, McpServer
from conductor.runtime import ask, check_tools, open_runtime, resume
from conductor.store import Store
from tests.support import fake_ollama, run

FAKE = Path(__file__).resolve().parents[1] / "mcp_fake_server.py"


class Text(Contract):
    text: str


class Reason(Contract):
    reason: str


ECHO = Action("echo", "Echo text.", "tool", "echo", "read", Text, Text, "fake")
SHOUT = Action("shout", "Fail on purpose.", "tool", "fail", "read", Reason, Text, "fake")
LAB = Domain("lab", "Lab tools.", (ECHO,), servers=(McpServer("fake"),))
BROKEN = Domain("lab", "Lab tools.", (ECHO, SHOUT), servers=(McpServer("fake"),))
PROBLEM = "action lab.shout: a read action needs a tool marked read-only"


@pytest.fixture(autouse=True)
def fake_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CONDUCTOR_MCP__FAKE", f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    )
    monkeypatch.setattr(diagnostics, "python_version", lambda: (3, 12, 13))


def test_the_check_passes_when_the_tools_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    with open_runtime(get_settings()) as opened:
        assert opened.registry.names == ("lab",)
        check_tools(opened)


def test_a_run_is_refused_when_the_tools_do_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    with open_runtime(get_settings()) as opened:
        with pytest.raises(ToolCheckFailed) as raised:
            ask(opened, "lab: echo hi")
        assert opened.log.runs() == []
    assert str(raised.value) == "the tool check failed"
    assert [problem.text for problem in raised.value.problems] == [PROBLEM]


def test_a_server_without_a_command_line_refuses_a_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (LAB,))
    monkeypatch.delenv("CONDUCTOR_MCP__FAKE")
    with open_runtime(get_settings()) as opened:
        with pytest.raises(ToolCheckFailed) as raised:
            resume(opened, "3" * 32)
    assert [problem.text for problem in raised.value.problems] == ["server fake: no_command"]


def test_ask_prints_every_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    result = run("ask", "lab: echo hi")
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        f"Error: the tool check failed\n  {PROBLEM}\n",
    )


def test_recording_without_resuming_skips_the_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
    step = PlannedStep(number=1, action="lab.echo", effect="read", args={"text": "hi"})
    request = ApprovalRequest(
        approval_id="1" * 32,
        run_id="2" * 32,
        stage="step",
        steps=(step,),
        args_sha256=steps_digest((step,)),
        requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
    )
    Store(tmp_path / "data" / "conductor.db").add_request(request)
    rejected = run("approvals", "reject", "1" * 32, "--no-resume")
    assert (rejected.exit_code, rejected.stdout) == (0, f"Rejected {'1' * 32}.\n")
    resumed = run("approvals", "approve", "1" * 32, "--yes")
    assert resumed.exit_code == 1


def test_the_doctor_checks_each_server(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_ollama() as (fake, host):
        fake.models("qwen3.8:27b")
        monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", host)
        monkeypatch.setattr(domains, "DOMAINS", (LAB,))
        good = run("doctor")
        monkeypatch.setattr(domains, "DOMAINS", (BROKEN,))
        bad = run("doctor")
    assert good.stdout.splitlines()[4:] == [
        "ok    server fake: 5 tools, 1 action checked",
        "All checks passed.",
    ]
    assert bad.stdout.splitlines()[4:] == [f"FAIL  server fake: {PROBLEM}", "1 check failed."]
    assert (good.exit_code, bad.exit_code) == (0, 1)
