import ast
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from conductor.domains import finance
from conductor.domains.finance import common, proposals, reads
from conductor.planning.plan import plan_fields

PACKAGE = Path(finance.__file__).parent
SHARED = {"conductor.contracts.base", "conductor.registry"}
IN_USE = {
    "DOMAIN": finance,
    "ACTIONS": finance,
    "RULES": finance,
    "SERVER": common,
    "READS": reads,
    "PROPOSALS": proposals,
    "NoteArgs": proposals,
    "NoteResult": proposals,
    "ProposalResult": proposals,
    "CategoryChangeProposalArgs": proposals,
    "RuleChangeProposalArgs": proposals,
    "FindingProposalArgs": proposals,
}


def tree(module: ModuleType) -> ast.Module:
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def classes(module: ModuleType) -> set[str]:
    return {node.name for node in tree(module).body if isinstance(node, ast.ClassDef)}


def assigned(module: ModuleType) -> set[str]:
    return {
        target.id
        for node in tree(module).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def project_imports(module: ModuleType) -> set[str]:
    found = set()
    for node in ast.walk(tree(module)):
        if isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = "conductor.domains.finance" + (f".{name}" if name else "")
            found.add(name)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {name for name in found if name.split(".")[0] == "conductor"}


def contracts_of(actions) -> set[str]:
    return {action.args.__name__ for action in actions} | {
        action.result.__name__ for action in actions
    }


def test_finance_is_a_package_of_three_modules() -> None:
    assert Path(finance.__file__).name == "__init__.py"
    assert not (PACKAGE.parent / "finance.py").exists()
    assert sorted(path.name for path in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "common.py",
        "proposals.py",
        "reads.py",
    ]


def test_each_half_holds_its_own_actions() -> None:
    assert (finance.READS is reads.READS, finance.PROPOSALS is proposals.PROPOSALS) == (True, True)
    assert finance.SERVER is common.SERVER
    assert (len(reads.READS), len(proposals.PROPOSALS)) == (20, 11)
    assert finance.ACTIONS == (*reads.READS, *proposals.PROPOSALS)
    assert finance.DOMAIN.actions is finance.ACTIONS


@pytest.mark.parametrize(
    ("module", "name"), [(reads, "READS"), (proposals, "PROPOSALS")], ids=["reads", "proposals"]
)
def test_a_half_defines_exactly_the_contracts_of_its_actions(module: ModuleType, name: str) -> None:
    actions = getattr(module, name)
    assert classes(module) == contracts_of(actions)
    homes = {action.args.__module__ for action in actions}
    homes |= {action.result.__module__ for action in actions}
    assert homes == {module.__name__}


def test_common_holds_only_what_both_halves_share() -> None:
    assert (classes(common), assigned(common)) == (set(), {"SERVER", "Month", "Label"})


def test_the_package_defines_no_contract() -> None:
    assert classes(finance) == set()


@pytest.mark.parametrize(
    ("module", "allowed"),
    [
        (common, SHARED),
        (reads, {*SHARED, "conductor.domains.finance.common"}),
        (proposals, {*SHARED, "conductor.domains.finance.common"}),
    ],
    ids=["common", "reads", "proposals"],
)
def test_each_module_imports_only_the_layer_below(module: ModuleType, allowed: set[str]) -> None:
    assert project_imports(module) <= allowed


@pytest.mark.parametrize("name", list(IN_USE))
def test_a_name_in_use_today_still_imports_from_finance(name: str) -> None:
    home = IN_USE[name]
    assert getattr(finance, name) is getattr(home, name)
    assert name in classes(home) | assigned(home)


def test_the_planner_lists_every_finance_action_in_order() -> None:
    lines = plan_fields(finance.DOMAIN, today=date(2026, 11, 20))["actions"].splitlines()
    assert len(lines) == 31
    assert lines[0].startswith("- list_accounts: ")
    assert lines[-1].startswith("- log_advice: ")
    assert [line.split(": ", 1)[0] for line in lines] == [
        f"- {action.name}" for action in finance.ACTIONS
    ]


def test_a_transaction_limit_and_a_note_subject_keep_their_bounds() -> None:
    sent = finance.reads.TransactionsArgs(limit=40)
    assert sent.limit == 40
    with pytest.raises(ValidationError) as raised:
        finance.reads.TransactionsArgs(limit=41)
    assert raised.value.errors()[0]["loc"] == ("limit",)
    with pytest.raises(ValidationError) as raised:
        finance.proposals.NoteArgs(text="A note.", subject="x" * 101)
    assert raised.value.errors()[0]["loc"] == ("subject",)
