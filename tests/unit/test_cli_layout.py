import ast
from pathlib import Path

import pytest
import typer
import typer.main

from conductor import runtime
from conductor.cli import common, main
from conductor.graph.supervisor import RunState

CLI = Path(main.__file__).parent
GROUPS = ["approvals", "escalations", "evals", "runs", "web"]
SHARED = {
    "bail",
    "load_settings",
    "report",
    "with_store",
    "with_runtime",
    "dump",
    "state_text",
    "emit",
    "decide_then_resume",
}
JSON = ("json_output", ("--json",), False, False)
NOTE = ("note", ("--note",), "", False)
YES = ("yes", ("--yes",), False, False)
NO_RESUME = ("no_resume", ("--no-resume",), False, False)
APPROVAL = ("approval_id", ("approval_id",), None, True)
ESCALATION = ("escalation_id", ("escalation_id",), None, True)
COMMANDS = {
    ("doctor",): ("main", []),
    ("ask",): ("main", [("request", ("request",), None, True), JSON]),
    ("resume",): ("main", [("run_id", ("run_id",), None, True), JSON]),
    ("web",): ("web", []),
    ("runs", "list"): ("runs", []),
    ("runs", "show"): (
        "runs",
        [("run_id", ("run_id",), None, True), ("payload", ("--payload",), False, False)],
    ),
    ("eval", "run"): (
        "evals",
        [("cases", ("--cases",), "evals/cases", False), ("runs", ("--runs",), 5, False)],
    ),
    ("approvals", "list"): ("approvals", [JSON]),
    ("approvals", "show"): ("approvals", [APPROVAL, JSON]),
    ("approvals", "approve"): ("approvals", [APPROVAL, NOTE, YES, NO_RESUME]),
    ("approvals", "reject"): ("approvals", [APPROVAL, NOTE, NO_RESUME]),
    ("approvals", "edit"): (
        "approvals",
        [APPROVAL, ("args_text", ("--args",), None, True), NOTE, YES, NO_RESUME],
    ),
    ("escalations", "list"): ("escalations", [JSON]),
    ("escalations", "show"): ("escalations", [ESCALATION, JSON]),
    ("escalations", "retry"): ("escalations", [ESCALATION, NOTE, YES, NO_RESUME]),
    ("escalations", "cancel"): ("escalations", [ESCALATION, NOTE, NO_RESUME]),
}
ORDER = {
    (): ["doctor", "ask", "resume", "web", "runs", "eval", "approvals", "escalations"],
    ("runs",): ["list", "show"],
    ("eval",): ["run"],
    ("approvals",): ["list", "show", "approve", "reject", "edit"],
    ("escalations",): ["list", "show", "retry", "cancel"],
}
OPENED = object()
PREVIEW = ("Approve?", "approval a1  plan  pending")


def command(path: tuple[str, ...]):
    found = typer.main.get_command(main.app)
    for name in path:
        found = found.commands[name]
    return found


def tree(name: str) -> ast.Module:
    return ast.parse((CLI / f"{name}.py").read_text(encoding="utf-8"))


def cli_imports(name: str) -> set[str]:
    found = set()
    for node in ast.walk(tree(name)):
        if isinstance(node, ast.ImportFrom) and node.module == "conductor.cli":
            found.update(f"conductor.cli.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {item for item in found if item.startswith("conductor.cli")}


def functions(name: str) -> set[str]:
    return {node.name for node in tree(name).body if isinstance(node, ast.FunctionDef)}


class Refused(Exception):
    pass


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What happened, in order: the confirmation asked, the decision recorded, the run resumed."""
    happened: list[str] = []

    def resume(_opened: object, run_id: str) -> RunState:
        happened.append(f"resume {run_id}")
        return RunState(run_id=run_id, status="done", reply="All set.")

    def confirm(text: str, **options: object) -> bool:
        happened.append(f"confirm {text} {options}")
        return "refuse" not in happened

    monkeypatch.setattr(runtime, "resume", resume)
    monkeypatch.setattr(typer, "confirm", confirm)
    return happened


def test_the_cli_package_holds_one_module_per_group() -> None:
    assert sorted(path.name for path in CLI.glob("*.py")) == [
        "__init__.py",
        "approvals.py",
        "common.py",
        "escalations.py",
        "evals.py",
        "main.py",
        "runs.py",
        "web.py",
    ]


def test_commands_and_groups_are_listed_in_todays_order() -> None:
    listed = {path: list(command(path).list_commands(None)) for path in ORDER}
    assert listed == ORDER


@pytest.mark.parametrize("path", list(COMMANDS), ids=[" ".join(path) for path in COMMANDS])
def test_each_command_lives_in_its_group_module_with_todays_options(
    path: tuple[str, ...],
) -> None:
    module, params = COMMANDS[path]
    found = command(path)
    assert found.callback.__module__ == f"conductor.cli.{module}"
    assert [(p.name, tuple(p.opts), p.default, p.required) for p in found.params] == params


@pytest.mark.parametrize("name", ["common", *GROUPS])
def test_each_module_imports_only_common_from_the_cli(name: str) -> None:
    assert cli_imports(name) == (set() if name == "common" else {"conductor.cli.common"})


def test_main_wires_every_group_module() -> None:
    assert cli_imports("main") == {f"conductor.cli.{name}" for name in ["common", *GROUPS]}
    assert functions("main") == {"doctor", "ask", "resume"}


def test_common_holds_the_shared_plumbing() -> None:
    assert {name for name in functions("common") if not name.startswith("_")} == SHARED
    assert {name for name in SHARED if not callable(getattr(common, name))} == set()
    assert isinstance(common.CAUGHT, tuple)


def test_a_refused_confirmation_records_nothing(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    seen.append("refuse")
    common.decide_then_resume(
        OPENED,
        "r1",
        lambda: seen.append("record"),
        "Approved a1.",
        no_resume=False,
        confirm=PREVIEW,
    )
    assert capsys.readouterr().out == "approval a1  plan  pending\nNothing recorded.\n"
    assert seen == ["refuse", "confirm Approve? {'default': False}"]


def test_an_accepted_confirmation_records_then_resumes(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    common.decide_then_resume(
        OPENED,
        "r1",
        lambda: seen.append("record"),
        "Approved a1.",
        no_resume=False,
        confirm=PREVIEW,
    )
    out = capsys.readouterr().out
    assert out == "approval a1  plan  pending\nApproved a1.\nrun r1  done\nAll set.\n"
    assert seen == ["confirm Approve? {'default': False}", "record", "resume r1"]


def test_yes_skips_the_confirmation_and_its_preview(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    common.decide_then_resume(
        OPENED,
        "r1",
        lambda: seen.append("record"),
        "Approved a1.",
        no_resume=False,
        confirm=PREVIEW,
        yes=True,
    )
    assert capsys.readouterr().out == "Approved a1.\nrun r1  done\nAll set.\n"
    assert seen == ["record", "resume r1"]


def test_without_a_confirmation_it_records_at_once(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    common.decide_then_resume(
        OPENED, "r2", lambda: seen.append("record"), "Rejected a2.", no_resume=False
    )
    assert capsys.readouterr().out == "Rejected a2.\nrun r2  done\nAll set.\n"
    assert seen == ["record", "resume r2"]


def test_no_resume_stops_after_the_line(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    common.decide_then_resume(
        OPENED, "r2", lambda: seen.append("record"), "Rejected a2.", no_resume=True
    )
    assert capsys.readouterr().out == "Rejected a2.\n"
    assert seen == ["record"]


def test_a_refused_decision_prints_no_line_and_does_not_resume(
    seen: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    def record() -> None:
        raise Refused

    with pytest.raises(Refused):
        common.decide_then_resume(OPENED, "r2", record, "Rejected a2.", no_resume=False)
    assert capsys.readouterr().out == ""
    assert seen == []
