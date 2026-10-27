from dataclasses import replace

import pytest
from pydantic import BaseModel

from conductor.contracts import Contract
from conductor.domains import DOMAINS, demo
from conductor.registry import Action, Domain, NotRegistered, Registry, RegistryError


class PingArgs(Contract):
    target: str


class PingResult(Contract):
    ok: bool


PING = Action(
    name="ping",
    description="Check that a host answers.",
    kind="tool",
    target="ping",
    effect="read",
    args=PingArgs,
    result=PingResult,
)
NET = Domain(name="net", description="Network checks.", actions=(PING,))


def test_the_demo_domain() -> None:
    assert demo.DOMAIN.name == "demo"
    assert [
        (action.name, action.kind, action.target, action.effect) for action in demo.DOMAIN.actions
    ] == [
        ("echo", "tool", "echo", "read"),
        ("note", "tool", "write_note", "write"),
        ("delegate", "agent", "demo_agent", "implement"),
    ]
    assert DOMAINS == ()


def test_lookups() -> None:
    registry = Registry((demo.DOMAIN, NET))
    assert registry.names == ("demo", "net")
    assert registry.domain("net") is NET
    assert registry.action("net.ping") is PING
    assert registry.action("demo.note").effect == "write"
    assert Registry(()).names == ()


@pytest.mark.parametrize(
    ("lookup", "message"),
    [
        (lambda registry: registry.domain("mail"), "no domain mail"),
        (lambda registry: registry.action("net.trace"), "no action net.trace"),
        (lambda registry: registry.action("mail.send"), "no action mail.send"),
        (lambda registry: registry.action("ping"), "no action ping"),
    ],
)
def test_a_lookup_of_something_not_registered(lookup, message: str) -> None:
    with pytest.raises(NotRegistered) as raised:
        lookup(Registry((NET,)))
    assert str(raised.value) == message
    assert isinstance(raised.value, LookupError)


class LooseArgs(BaseModel):
    target: str


@pytest.mark.parametrize(
    ("domains", "message"),
    [
        ((replace(NET, name="Net"),), "domain Net: not a valid name"),
        ((NET, replace(NET, description="Other checks.")), "domain net: declared twice"),
        ((replace(NET, description=""),), "domain net: description must be 1 to 200 characters"),
        ((replace(NET, actions=()),), "domain net: has no actions"),
        (
            (replace(NET, actions=(replace(PING, name="Ping"),)),),
            "action net.Ping: not a valid name",
        ),
        ((replace(NET, actions=(PING, PING)),), "action net.ping: declared twice"),
        (
            (replace(NET, actions=(replace(PING, description="x" * 201),)),),
            "action net.ping: description must be 1 to 200 characters",
        ),
        (
            (replace(NET, actions=(replace(PING, kind="script"),)),),
            "action net.ping: kind must be tool or agent",
        ),
        (
            (replace(NET, actions=(replace(PING, effect="delete"),)),),
            "action net.ping: effect must be read, propose, write, or implement",
        ),
        (
            (replace(NET, actions=(replace(PING, target="ping now"),)),),
            "action net.ping: target is not a valid name",
        ),
        (
            (replace(NET, actions=(replace(PING, args=LooseArgs),)),),
            "action net.ping: args must be a Contract",
        ),
        (
            (replace(NET, actions=(replace(PING, result=dict),)),),
            "action net.ping: result must be a Contract",
        ),
        (
            (replace(NET, actions=(replace(PING, effect="implement"),)),),
            "action net.ping: implement needs an agent action",
        ),
    ],
)
def test_a_registry_refuses_a_bad_declaration(domains: tuple[Domain, ...], message: str) -> None:
    with pytest.raises(RegistryError) as raised:
        Registry(domains)
    assert str(raised.value) == message


def test_the_first_problem_in_declaration_order_is_named() -> None:
    bad_action = replace(PING, name="Ping")
    second = replace(NET, name="later", actions=(replace(PING, kind="script"),))
    with pytest.raises(RegistryError) as raised:
        Registry((replace(NET, actions=(PING, bad_action)), second))
    assert str(raised.value) == "action net.Ping: not a valid name"
