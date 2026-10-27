from dataclasses import replace
from typing import Self

import pytest
from pydantic import model_validator

from conductor.contracts import Contract, FieldProblem, Plan, Route, Step
from conductor.domains import demo
from conductor.plancheck import PlanRejected, check_plan
from conductor.registry import Action, Domain, NotRegistered, Registry, RegistryError


class PingArgs(Contract):
    target: str


class PingResult(Contract):
    ok: bool


def _ping(target: str = "ping") -> Action:
    return Action(
        name="ping",
        description="Check that a host answers.",
        kind="tool",
        target=target,
        effect="read",
        args=PingArgs,
        result=PingResult,
    )


def _plan(*steps: tuple[str, dict]) -> Plan:
    return Plan(steps=tuple(Step(action=action, args=args) for action, args in steps))


def test_a_registry_keeps_the_names_it_was_built_with() -> None:
    domains = [demo.DOMAIN]
    registry = Registry(domains)
    domains.append(demo.DOMAIN)
    assert registry.names == ("demo",)


def test_an_action_name_without_a_dot() -> None:
    with pytest.raises(NotRegistered) as raised:
        Registry((demo.DOMAIN,)).action("demo")
    assert str(raised.value) == "no action demo"


def test_a_target_of_64_characters_is_accepted() -> None:
    registry = Registry((Domain("net", "Network checks.", (_ping("a" * 64),)),))
    assert registry.action("net.ping").target == "a" * 64


def test_a_target_of_65_characters_is_refused() -> None:
    with pytest.raises(RegistryError) as raised:
        Registry((Domain("net", "Network checks.", (_ping("a" * 65),)),))
    assert str(raised.value) == "action net.ping: target is not a valid name"


def test_args_must_be_the_contract_class() -> None:
    echo = replace(demo.DOMAIN.actions[0], args=demo.EchoArgs(text="x"))
    domain = replace(demo.DOMAIN, actions=(echo,))
    with pytest.raises(RegistryError) as raised:
        Registry((domain,))
    assert str(raised.value) == "action demo.echo: args must be a Contract"


def test_true_is_not_an_int() -> None:
    route = Route(domain="demo", decided_by="model")
    registry = Registry((demo.DOMAIN,))
    with pytest.raises(PlanRejected) as raised:
        check_plan(_plan(("demo.delegate", {"task": "tidy", "max_minutes": True})), route, registry)
    assert raised.value.problems == (FieldProblem(loc="steps.0.args.max_minutes", code="int_type"),)


def test_a_json_array_is_accepted_for_a_tuple() -> None:
    route = Route(domain="demo", decided_by="model")
    checked = check_plan(
        _plan(("demo.note", {"title": "Groceries", "tags": ["home"]})),
        route,
        Registry((demo.DOMAIN,)),
    )
    assert checked[0].args == demo.NoteArgs(title="Groceries", body="", tags=("home",))


def test_only_the_last_step_is_named() -> None:
    route = Route(domain="demo", decided_by="model")
    steps = [("demo.echo", {"text": "ok"})] * 7 + [("demo.echo", {})]
    with pytest.raises(PlanRejected) as raised:
        check_plan(_plan(*steps), route, Registry((demo.DOMAIN,)))
    assert raised.value.problems == (FieldProblem(loc="steps.7.args.text", code="missing"),)


def test_parsed_args_are_the_actions_own_class() -> None:
    route = Route(domain="demo", decided_by="model")
    checked = check_plan(
        _plan(
            ("demo.echo", {"text": "hello"}),
            ("demo.note", {"title": "Groceries"}),
            ("demo.delegate", {"task": "tidy the notes"}),
        ),
        route,
        Registry((demo.DOMAIN,)),
    )
    assert isinstance(checked[0].args, demo.EchoArgs)
    assert isinstance(checked[1].args, demo.NoteArgs)
    assert isinstance(checked[2].args, demo.DelegateArgs)


def test_an_empty_argument_location_is_the_prefix_only() -> None:
    class Whole(Contract):
        text: str

        @model_validator(mode="after")
        def reject(self) -> Self:
            raise ValueError("nope")

    action = Action("echo", "Repeat the text back.", "tool", "echo", "read", Whole, Whole)
    registry = Registry((Domain("lab", "Whole-object checks.", (action,)),))
    route = Route(domain="lab", decided_by="model")
    with pytest.raises(PlanRejected) as raised:
        check_plan(_plan(("lab.echo", {"text": "hi"})), route, registry)
    assert raised.value.problems == (FieldProblem(loc="steps.0.args", code="value_error"),)
    assert "nope" not in repr(raised.value.problems)
