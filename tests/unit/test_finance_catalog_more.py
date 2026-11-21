from datetime import date

import pytest
from pydantic import ValidationError

from conductor.domains import finance
from conductor.planning.plan import plan_fields


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
