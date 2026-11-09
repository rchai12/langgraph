from dataclasses import replace

import pytest

from conductor.contracts import Contract, Route
from conductor.domains import demo
from conductor.registry import Action, Domain, Registry, RegistryError, Rule
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules, words


class PingArgs(Contract):
    target: str


class PingResult(Contract):
    ok: bool


PING = Action("ping", "Check that a host answers.", "tool", "ping", "read", PingArgs, PingResult)
LAB = Domain(
    "lab",
    "Lab checks.",
    (PING,),
    (Rule("ping", ("ping", "echo test")), Rule("trace", ("trace route",))),
)
BOTH = Registry((demo.DOMAIN, LAB))
PHRASE = "phrase 1 must be 1 to 6 lowercase words of at most 64 characters"


def _refused(domain: Domain) -> str:
    with pytest.raises(RegistryError) as raised:
        Registry((domain,))
    return str(raised.value)


def test_a_bad_rule_is_named_after_a_bad_action() -> None:
    bad = Action("Ping", "Check that a host answers.", "tool", "ping", "read", PingArgs, PingResult)
    domain = Domain("lab", "Lab checks.", (bad,), (Rule("ping", ()),))
    assert _refused(domain) == "action lab.Ping: not a valid name"
    assert _refused(replace(LAB, rules=(Rule("Ping", ("ping",)),))) == (
        "rule lab.Ping: not a valid name"
    )
    assert _refused(replace(LAB, rules=(Rule("ping", ("ping",)), Rule("ping", ("pong",))))) == (
        "rule lab.ping: declared twice"
    )
    assert _refused(replace(LAB, rules=(Rule("ping", ()),))) == (
        "rule lab.ping: needs 1 to 20 phrases"
    )
    phrases = tuple(f"p{number}" for number in range(21))
    assert _refused(replace(LAB, rules=(Rule("ping", phrases),))) == (
        "rule lab.ping: needs 1 to 20 phrases"
    )
    assert _refused(replace(LAB, rules=(Rule("ping", ("a" * 65,)),))) == f"rule lab.ping: {PHRASE}"
    assert _refused(replace(LAB, rules=(Rule("ping", ("a b c d e f g",)),))) == (
        f"rule lab.ping: {PHRASE}"
    )


def test_words_keep_only_ascii_letters_and_digits() -> None:
    assert words("ÉCHO café_2") == ("cho", "caf", "2")


def test_an_empty_prefix_routes_and_an_unknown_name_does_not() -> None:
    assert match_rules("demo:", BOTH) == RuleRoute(
        Route(domain="demo", decided_by="rule", rule_id="demo.prefix"), ""
    )
    assert match_rules("unknown: x", BOTH) is None
    assert match_rules(f"{'a' * 33}: x", BOTH) is None


def test_a_conflict_lists_every_matching_rule_in_registry_order() -> None:
    assert match_rules("write down the echo test and ping", BOTH) == RuleConflict(
        ("demo.echo", "demo.note", "lab.ping")
    )
