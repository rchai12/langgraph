import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conductor.contracts import Route
from conductor.domains import demo, finance
from conductor.policy import needs_approval
from conductor.registry import Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

TESTS = Path(__file__).resolve().parents[1]
REAL = json.loads((TESTS / "finances_tools.json").read_text())
PROPOSALS = {action.name: action for action in finance.PROPOSALS}
REASON = "Corner Grocer sells food"
MINIMAL = {
    "propose_category": {"transaction_id": 101, "category": "Groceries", "reason": REASON},
    "propose_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_not_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_rule": {
        "example_id": 101,
        "pattern": "CORNER GROCER",
        "category": "Groceries",
        "reason": REASON,
    },
    "propose_merchant_alias": {"example_id": 101, "target": "Corner Grocer", "reason": REASON},
    "propose_group": {"name": "Household", "example_id": 101, "reason": REASON},
    "propose_new_category": {
        "name": "Pet food",
        "group": "Food",
        "example_id": 101,
        "reason": REASON,
    },
    "propose_rule_change": {"rule_id": 1, "reason": REASON},
    "propose_category_change": {"name": "Groceries", "reason": REASON},
    "propose_finding_status": {"type": "spike", "status": "handled", "reason": REASON},
    "log_advice": {"text": "Review the streaming subscriptions in December."},
}
DEFAULTS = {
    "propose_rule": {"match": "contains", "priority": 0},
    "propose_group": {"kind": "spending", "sensitive": False},
    "propose_new_category": {"tax": False},
    "propose_rule_change": {
        "delete": False,
        "pattern": None,
        "match": None,
        "priority": None,
        "category": None,
    },
    "propose_category_change": {"rename_to": None, "delete": False, "move_to": None},
    "propose_finding_status": {"about": "", "month": ""},
    "log_advice": {"subject": ""},
}


def fake_module():
    spec = importlib.util.spec_from_file_location(
        "fake_finances", TESTS / "fake_finances_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(name: str, **changes: object):
    return PROPOSALS[name].args.from_json(json.dumps({**MINIMAL[name], **changes}))


def test_eleven_proposal_actions_after_the_reads() -> None:
    assert list(PROPOSALS) == [name for name, item in REAL.items() if not item["read_only"]]
    assert finance.ACTIONS == (*finance.READS, *finance.PROPOSALS)
    assert finance.DOMAIN.actions == finance.ACTIONS
    assert {
        (action.kind, action.target == action.name, action.effect, action.server)
        for action in finance.PROPOSALS
    } == {("tool", True, "propose", "finances")}
    assert all(needs_approval(action) for action in finance.PROPOSALS)


@pytest.mark.parametrize("name", list(MINIMAL))
def test_the_required_fields_and_the_defaults(name: str) -> None:
    contract = PROPOSALS[name].args
    assert sorted(contract.model_json_schema()["required"]) == sorted(
        REAL[name]["input_schema"]["required"]
    )
    assert args(name).model_dump(mode="json") == {**MINIMAL[name], **DEFAULTS.get(name, {})}


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("propose_category", "reason", "x" * 200),
        ("propose_category", "reason", "x"),
        ("propose_category", "category", "é" * 100),
        ("propose_category", "transaction_id", 1),
        ("propose_rule", "priority", -1000),
        ("propose_rule", "priority", 1000),
        ("propose_finding_status", "month", "2026-10"),
        ("log_advice", "text", "a\n" * 499 + "ab"),
    ],
    ids=[
        "reason-200",
        "reason-1",
        "category-100",
        "id-1",
        "priority-low",
        "priority-high",
        "month",
        "text-1000",
    ],
)
def test_arguments_at_their_bounds_are_sent(name: str, field: str, value: object) -> None:
    assert args(name, **{field: value}).model_dump(mode="json")[field] == value


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("propose_category", "reason", ""),
        ("propose_category", "reason", "x" * 201),
        ("propose_category", "reason", "two\nlines"),
        ("propose_category", "reason", " leading"),
        ("propose_category", "reason", "trailing "),
        ("propose_category", "category", "x" * 101),
        ("propose_category", "transaction_id", 0),
        ("propose_category", "transaction_id", "101"),
        ("propose_category", "amount_cents", 4210),
        ("propose_rule", "priority", 1001),
        ("propose_rule", "match", "regex"),
        ("propose_rule_change", "priority", -1001),
        ("propose_finding_status", "type", "unknown"),
        ("propose_finding_status", "status", "open"),
        ("propose_finding_status", "month", "2026-13"),
        ("log_advice", "text", "x" * 1001),
        ("log_advice", "text", "   "),
    ],
    ids=[
        "reason-empty",
        "reason-201",
        "reason-two-lines",
        "reason-leading",
        "reason-trailing",
        "category-101",
        "id-0",
        "id-text",
        "extra-field",
        "priority-1001",
        "match",
        "change-priority",
        "finding-type",
        "finding-status",
        "finding-month",
        "text-1001",
        "text-blank",
    ],
)
def test_arguments_past_their_bounds_are_refused(name: str, field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        args(name, **{field: value})


def test_the_fake_server_returns_a_result_each_proposal_accepts() -> None:
    fake = fake_module()
    for name, action in PROPOSALS.items():
        output = getattr(fake, name)(**args(name).model_dump())
        action.result.from_json(json.dumps(output))
    for result in (finance.ProposalResult, finance.NoteResult):
        with pytest.raises(ValidationError):
            result.from_json("{}")


@pytest.mark.parametrize(
    ("request_text", "rule_id"),
    [
        ("Propose Groceries for transaction 101", "finance.proposals"),
        ("Recategorize transaction 77 as Dining", "finance.proposals"),
        ("Show my open proposals", "finance.proposals"),
        ("Categorize the coffee shop as Dining", "finance.proposals"),
        ("Categorize the uncategorized transactions", "finance.transactions"),
    ],
    ids=["propose", "recategorize", "proposals", "categorize", "transactions-first"],
)
def test_proposal_words_route_by_rule(request_text: str, rule_id: str) -> None:
    found = match_rules(request_text, Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleRoute(
        Route(domain="finance", decided_by="rule", rule_id=rule_id), request_text
    )


def test_a_proposal_word_and_a_demo_word_conflict() -> None:
    found = match_rules("Propose a note", Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleConflict(("finance.proposals", "demo.note"))
