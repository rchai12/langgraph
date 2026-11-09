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


def by_rule(domain: str, rule_id: str) -> Route:
    return Route(domain=domain, decided_by="rule", rule_id=rule_id)


def test_the_demo_rules() -> None:
    assert demo.DOMAIN.rules == (
        Rule("echo", ("echo", "repeat after me")),
        Rule("note", ("note", "write down")),
    )
    assert Domain("x", "No rules.", (PING,)).rules == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Echo: Write   DOWN! note's tag_2", ("echo", "write", "down", "note", "s", "tag", "2")),
    ],
)
def test_words(text: str, expected: tuple[str, ...]) -> None:
    assert words(text) == expected


@pytest.mark.parametrize(
    ("request_text", "domain", "rest"),
    [
        ("demo: say hello", "demo", "say hello"),
        ("LAB:\n  trace route\n", "lab", "trace route"),
    ],
)
def test_a_prefix_routes_and_is_stripped(request_text: str, domain: str, rest: str) -> None:
    assert match_rules(request_text, BOTH) == RuleRoute(by_rule(domain, f"{domain}.prefix"), rest)


def test_a_prefix_wins_over_keyword_rules() -> None:
    assert match_rules("lab: echo and note", BOTH) == RuleRoute(
        by_rule("lab", "lab.prefix"), "echo and note"
    )


@pytest.mark.parametrize(
    "request_text",
    ["notes: buy milk", "lab : ping it"],
)
def test_only_a_registered_name_and_a_colon_make_a_prefix(request_text: str) -> None:
    found = match_rules(request_text, BOTH)
    assert not (isinstance(found, RuleRoute) and found.route.rule_id.endswith(".prefix"))


@pytest.mark.parametrize(
    ("request_text", "rule_id"),
    [
        ("repeat after me: hello", "demo.echo"),
        ("Write  down: call the plumber", "demo.note"),
    ],
)
def test_a_keyword_rule_routes_and_keeps_the_request(request_text: str, rule_id: str) -> None:
    domain = rule_id.split(".")[0]
    assert match_rules(request_text, BOTH) == RuleRoute(by_rule(domain, rule_id), request_text)


@pytest.mark.parametrize(
    "request_text",
    ["echoes of the past", "write it down"],
)
def test_phrases_match_whole_words_in_order(request_text: str) -> None:
    assert match_rules(request_text, BOTH) is None


def test_the_first_rule_of_the_domain_decides() -> None:
    assert match_rules("note that I said echo", BOTH) == RuleRoute(
        by_rule("demo", "demo.echo"), "note that I said echo"
    )


def test_rules_of_two_domains_conflict() -> None:
    assert match_rules("write down the echo test and ping", BOTH) == RuleConflict(
        ("demo.echo", "demo.note", "lab.ping")
    )


def test_no_domains_no_rules() -> None:
    assert match_rules("demo: echo", Registry(())) is None


@pytest.mark.parametrize(
    ("domain", "message"),
    [
        (Domain("unknown", "Reserved.", (PING,)), "domain unknown: the name is reserved"),
        (replace(LAB, rules=(Rule("prefix", ("ping",)),)), "rule lab.prefix: the name is reserved"),
        (
            Domain("d" * 32, "Long name.", (PING,), (Rule("r" * 32, ("ping",)),)),
            f"rule {'d' * 32}.{'r' * 32}: the id is longer than 64 characters",
        ),
        (
            replace(LAB, rules=(Rule("ping", ("ping", "Pong")),)),
            "rule lab.ping: phrase 2 must be 1 to 6 lowercase words of at most 64 characters",
        ),
    ],
)
def test_rule_declarations_are_checked(domain: Domain, message: str) -> None:
    with pytest.raises(RegistryError) as raised:
        Registry((domain,))
    assert str(raised.value) == message
