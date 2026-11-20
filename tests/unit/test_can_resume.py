from types import SimpleNamespace

import pytest

from conductor.graph.status import RunState
from conductor.graph.supervisor import can_resume
from conductor.store import NotFound, StoreError

RUN = "1" * 32
APPROVAL = "2" * 32
ESCALATION = "3" * 32


class Lookups:
    """A store that answers only the lookups a test allows."""

    def __init__(self, approval=None, escalation=None) -> None:
        self._approval = approval
        self._escalation = escalation
        self.asked: list[str] = []

    def approval(self, approval_id: str):
        self.asked.append(approval_id)
        return _answer(self._approval)

    def escalation(self, escalation_id: str):
        self.asked.append(escalation_id)
        return _answer(self._escalation)


def _answer(value):
    if value is None:
        raise AssertionError("an unexpected lookup")
    if isinstance(value, Exception):
        raise value
    return value


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ("route", True),
        ("plan", True),
        ("answer", True),
        ("run_step", False),
        ("ask_step", False),
        (None, False),
    ],
)
def test_a_stopped_run_by_its_node(node: str | None, expected: bool) -> None:
    store = Lookups()
    assert can_resume(RunState(RUN, "stopped", stopped_at=node), store) is expected
    assert store.asked == []


@pytest.mark.parametrize("status", ["done", "rejected", "cancelled"])
def test_a_finished_run_is_never_resumed(status: str) -> None:
    store = Lookups()
    assert can_resume(RunState(RUN, status), store) is False
    assert store.asked == []


@pytest.mark.parametrize(
    ("found", "expected"),
    [
        (SimpleNamespace(decision=object()), True),
        (SimpleNamespace(decision=None), False),
        (NotFound("x"), False),
    ],
    ids=["decided", "undecided", "missing"],
)
def test_a_run_waiting_on_an_approval(found: object, expected: bool) -> None:
    store = Lookups(approval=found)
    waiting = RunState(RUN, "waiting", approval_id=APPROVAL)
    assert can_resume(waiting, store) is expected
    assert store.asked == [APPROVAL]


@pytest.mark.parametrize(
    ("found", "expected"),
    [
        (SimpleNamespace(answer=object()), True),
        (SimpleNamespace(answer=None), False),
        (NotFound("x"), False),
    ],
    ids=["answered", "open", "missing"],
)
def test_a_run_waiting_on_an_escalation(found: object, expected: bool) -> None:
    store = Lookups(escalation=found)
    waiting = RunState(RUN, "waiting", escalation_id=ESCALATION)
    assert can_resume(waiting, store) is expected
    assert store.asked == [ESCALATION]


def test_a_store_that_fails_is_not_hidden() -> None:
    store = Lookups(approval=StoreError("conductor.db: busy"))
    with pytest.raises(StoreError):
        can_resume(RunState(RUN, "waiting", approval_id=APPROVAL), store)
