import pytest
from pydantic import ValidationError

from conductor.domains import finance

REASON = "Corner Grocer sells food"
FINDINGS = (
    "spike",
    "frequent_small",
    "subscription_overlap",
    "price_increase",
    "interest",
    "fees",
    "over_budget",
    "duplicate",
    "large_first_charge",
)


@pytest.mark.parametrize("kind", FINDINGS)
def test_each_finding_type_can_be_ignored(kind: str) -> None:
    found = finance.FindingProposalArgs.model_validate(
        {"type": kind, "status": "ignored", "reason": REASON}
    )
    assert (found.type, found.status, found.reason) == (kind, "ignored", REASON)


def test_a_deleted_rule_sends_no_other_change_and_a_long_rename_is_refused() -> None:
    deleted = finance.RuleChangeProposalArgs(rule_id=4, reason=REASON, delete=True)
    assert deleted.model_dump(mode="json") == {
        "rule_id": 4,
        "reason": REASON,
        "delete": True,
        "pattern": None,
        "match": None,
        "priority": None,
        "category": None,
    }
    with pytest.raises(ValidationError):
        finance.CategoryChangeProposalArgs(name="Groceries", reason=REASON, rename_to="x" * 101)


def test_advice_keeps_a_line_break_and_refuses_a_long_subject() -> None:
    text = "Check the bills\nin December."
    kept = finance.NoteArgs(text=text)
    assert kept.model_dump(mode="json") == {"text": text, "subject": ""}
    with pytest.raises(ValidationError):
        finance.NoteArgs(text=text, subject="x" * 101)
