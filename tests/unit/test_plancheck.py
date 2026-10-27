import pytest

from conductor.contracts import FieldProblem, Plan, Route, Step
from conductor.domains import demo
from conductor.plancheck import PLAN_REJECTED_MESSAGE, CheckedStep, PlanRejected, check_plan
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
DEMO = Route(domain="demo", decided_by="rule", rule_id="demo.prefix")


def plan(*steps: tuple[str, dict]) -> Plan:
    return Plan(steps=tuple(Step(action=action, args=args) for action, args in steps))


def rejected(checked_plan: Plan, route: Route = DEMO) -> tuple[FieldProblem, ...]:
    with pytest.raises(PlanRejected) as raised:
        check_plan(checked_plan, route, REGISTRY)
    assert str(raised.value) == PLAN_REJECTED_MESSAGE
    return raised.value.problems


def test_a_plan_that_fits() -> None:
    steps = check_plan(
        plan(
            ("demo.echo", {"text": "hello"}),
            ("demo.note", {"title": "Groceries", "tags": ["home", "weekly"]}),
            ("demo.delegate", {"task": "tidy the notes"}),
        ),
        DEMO,
        REGISTRY,
    )
    assert steps == (
        CheckedStep(
            number=1,
            action=REGISTRY.action("demo.echo"),
            args=demo.EchoArgs(text="hello"),
        ),
        CheckedStep(
            number=2,
            action=REGISTRY.action("demo.note"),
            args=demo.NoteArgs(title="Groceries", body="", tags=("home", "weekly")),
        ),
        CheckedStep(
            number=3,
            action=REGISTRY.action("demo.delegate"),
            args=demo.DelegateArgs(task="tidy the notes", max_minutes=10),
        ),
    )
    assert [step.action.effect for step in steps] == ["read", "write", "implement"]
    assert PLAN_REJECTED_MESSAGE == "the plan does not fit the registry"


def test_arguments_are_checked_strictly() -> None:
    assert rejected(plan(("demo.delegate", {"task": "tidy", "max_minutes": "10"}))) == (
        FieldProblem(loc="steps.0.args.max_minutes", code="int_type"),
    )
    assert rejected(plan(("demo.delegate", {"task": "tidy", "max_minutes": 10.0}))) == (
        FieldProblem(loc="steps.0.args.max_minutes", code="int_type"),
    )


def test_every_bad_step_is_named() -> None:
    assert rejected(
        plan(
            ("demo.echo", {"text": "fine"}),
            ("demo.shout", {"text": "HELLO"}),
            ("demo.note", {"title": ""}),
            ("demo.echo", {}),
        )
    ) == (
        FieldProblem(loc="steps.1.action", code="unknown_action"),
        FieldProblem(loc="steps.2.args.title", code="string_too_short"),
        FieldProblem(loc="steps.3.args.text", code="missing"),
    )


def test_a_plan_for_another_domain() -> None:
    other = Route(domain="mail", decided_by="model")
    assert rejected(plan(("demo.echo", {"text": "hi"})), other) == (
        FieldProblem(loc="route.domain", code="unknown_domain"),
    )
    assert rejected(plan(("mail.send", {"to": "sam"}))) == (
        FieldProblem(loc="steps", code="wrong_domain"),
    )


def test_problems_stop_at_twenty() -> None:
    steps = [("demo.note", {"title": "", "body": "x" * 2001, "tags": ["A", "B", "C"]})] * 8
    problems = rejected(plan(*steps))
    assert len(problems) == 20
    assert problems[:5] == (
        FieldProblem(loc="steps.0.args.title", code="string_too_short"),
        FieldProblem(loc="steps.0.args.body", code="string_too_long"),
        FieldProblem(loc="steps.0.args.tags.0", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.0.args.tags.1", code="string_pattern_mismatch"),
        FieldProblem(loc="steps.0.args.tags.2", code="string_pattern_mismatch"),
    )
    assert problems[19] == FieldProblem(loc="steps.3.args.tags.2", code="string_pattern_mismatch")


def test_no_argument_value_reaches_a_problem() -> None:
    problems = rejected(plan(("demo.note", {"title": "card 4417-1234", "card 4417-1234": 1})))
    assert problems == (FieldProblem(loc="steps.0.args.*", code="extra_forbidden"),)
    assert "4417" not in repr(problems)
