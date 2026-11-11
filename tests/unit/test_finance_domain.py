import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conductor import domains
from conductor.config import get_settings
from conductor.contracts import Route
from conductor.domains import demo, finance
from conductor.llm.points import build_request
from conductor.mcp_client.check import check_registry
from conductor.mcp_client.client import ToolInfo
from conductor.planning.plan import PLAN_CONTEXT_TOKENS, PlanInputs, plan_fields, plan_point
from conductor.registry import McpServer, Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

TESTS = Path(__file__).resolve().parents[1]
REAL = json.loads((TESTS / "finances_tools.json").read_text())
ACTIONS = {action.name: action for action in finance.READS}


def fake_module():
    spec = importlib.util.spec_from_file_location(
        "fake_finances", TESTS / "fake_finances_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(name: str, text: str):
    return ACTIONS[name].args.from_json(text)


def test_twenty_read_actions_on_one_server() -> None:
    Registry((finance.DOMAIN,))
    assert finance.SERVER == McpServer("finances", ("FIN_DATA_DIR",))
    assert finance.DOMAIN.servers == (finance.SERVER,)
    assert list(ACTIONS) == [name for name, item in REAL.items() if item["read_only"]]
    assert {
        (action.kind, action.target == action.name, action.effect, action.server)
        for action in finance.READS
    } == {("tool", True, "read", "finances")}


def test_every_action_fits_the_real_read_tools() -> None:
    tools = tuple(
        ToolInfo(name, item["input_schema"], item["output_schema"], item["read_only"])
        for name, item in REAL.items()
    )

    class Listing:
        def list_tools(self) -> tuple[ToolInfo, ...]:
            return tools

    problems = check_registry(
        Registry((finance.DOMAIN,)), get_settings(), connect=lambda server, settings: Listing()
    )
    assert problems == ()


def test_the_defaults() -> None:
    found = {
        name: action.args.from_json("{}").model_dump(mode="json")
        for name, action in ACTIONS.items()
        if name != "find_merchants"
    }
    assert found == {
        "list_accounts": {"include_inactive": False},
        "get_balances": {},
        "get_net_worth": {"months": 12},
        "list_transactions": {
            "text": "",
            "account": "",
            "person": "",
            "category": "",
            "group": "",
            "merchant": "",
            "bank": "",
            "card": "",
            "kind": "",
            "start": None,
            "end": None,
            "limit": 20,
            "offset": 0,
        },
        "get_spending": {"start": None, "end": None, "by": "category"},
        "month_over_month": {"month": "", "count": 6},
        "get_insights": {"month": ""},
        "get_recurring": {"income": False, "include_inactive": False},
        "get_upcoming": {"days": 30},
        "get_forecast": {"days": 30, "account": ""},
        "get_budgets": {"month": ""},
        "list_uncategorized": {"limit": 20},
        "list_categories": {},
        "list_rules": {},
        "list_transfers": {"limit": 10},
        "list_transfer_suggestions": {},
        "data_coverage": {},
        "list_proposals": {"status": "open", "limit": 10},
        "list_advice": {"limit": 10},
    }
    assert args("find_merchants", '{"phrase": "grocer"}').model_dump() == {
        "phrase": "grocer",
        "limit": 5,
    }


@pytest.mark.parametrize(
    ("name", "text", "field", "sent"),
    [
        ("list_transactions", '{"limit": 40}', "limit", 40),
        ("list_transactions", '{"limit": 1, "offset": 5000}', "offset", 5000),
        ("list_transactions", '{"start": "2026-10-01"}', "start", "2026-10-01"),
        ("list_transactions", '{"kind": "refund"}', "kind", "refund"),
        ("get_net_worth", '{"months": 24}', "months", 24),
        ("month_over_month", '{"month": "2026-12", "count": 12}', "month", "2026-12"),
        ("get_forecast", '{"days": 60}', "days", 60),
        ("list_transfers", '{"limit": 20}', "limit", 20),
        ("find_merchants", json.dumps({"phrase": "é" * 100}), "phrase", "é" * 100),
        ("list_proposals", '{"status": "declined", "limit": 20}', "status", "declined"),
    ],
    ids=[
        "transactions-limit-40",
        "transactions-offset-5000",
        "transactions-start",
        "transactions-kind",
        "net-worth-24",
        "months-2026-12",
        "forecast-60",
        "transfers-20",
        "merchants-100",
        "proposals-declined",
    ],
)
def test_arguments_at_their_bounds_are_sent(name: str, text: str, field: str, sent) -> None:
    assert args(name, text).model_dump(mode="json")[field] == sent


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("list_transactions", '{"limit": 41}'),
        ("list_transactions", '{"limit": 0}'),
        ("list_transactions", '{"offset": 5001}'),
        ("list_transactions", '{"start": "2026-10-32"}'),
        ("list_transactions", '{"end": "last month"}'),
        ("list_transactions", '{"kind": "purchase"}'),
        ("list_transactions", json.dumps({"merchant": "x" * 101})),
        ("get_net_worth", '{"months": 25}'),
        ("month_over_month", '{"month": "2026-13"}'),
        ("month_over_month", '{"count": 13}'),
        ("get_budgets", '{"month": "2026-11-01"}'),
        ("get_forecast", '{"days": 61}'),
        ("list_uncategorized", '{"limit": 41}'),
        ("find_merchants", '{"phrase": ""}'),
        ("list_advice", '{"limit": 21}'),
        ("get_balances", '{"account": "x"}'),
    ],
    ids=[
        "transactions-limit-41",
        "transactions-limit-0",
        "transactions-offset-5001",
        "transactions-start-32",
        "transactions-end-words",
        "transactions-kind",
        "transactions-merchant-101",
        "net-worth-25",
        "months-2026-13",
        "months-count-13",
        "budgets-day",
        "forecast-61",
        "uncategorized-41",
        "merchants-empty",
        "advice-21",
        "balances-extra",
    ],
)
def test_arguments_past_their_bounds_are_refused(name: str, text: str) -> None:
    with pytest.raises(ValidationError):
        args(name, text)


def test_results_name_the_top_fields_and_leave_the_rest_open() -> None:
    result = ACTIONS["list_transactions"].result
    found = result.from_json(
        '{"transactions": [{"id": 1, "new_field": [1, 2]}], "next_offset": 20}'
    )
    assert found.model_dump() == {
        "transactions": [{"id": 1, "new_field": [1, 2]}],
        "next_offset": 20,
    }
    with pytest.raises(ValidationError):
        result.from_json('{"transactions": []}')
    with pytest.raises(ValidationError):
        result.from_json('{"transactions": [{"amount": NaN}], "next_offset": null}')


def test_the_fake_server_returns_a_result_each_action_accepts() -> None:
    fake = fake_module()
    for name, action in ACTIONS.items():
        sent = args(name, '{"phrase": "grocer"}' if name == "find_merchants" else "{}")
        output = getattr(fake, name)(**sent.model_dump())
        action.result.from_json(json.dumps(output))


@pytest.mark.parametrize(
    ("request_text", "rule_id"),
    [
        ("How much did we spend? What was spent on food", "finance.spending"),
        ("Are we over budget", "finance.budgets"),
        ("What is our net worth", "finance.balances"),
        ("Show the uncategorized ones", "finance.transactions"),
        ("Which subscriptions renew", "finance.bills"),
        ("List the transfers", "finance.transfers"),
    ],
    ids=["spending", "budgets", "balances", "transactions", "bills", "transfers"],
)
def test_finance_words_route_by_rule(request_text: str, rule_id: str) -> None:
    found = match_rules(request_text, Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleRoute(
        Route(domain="finance", decided_by="rule", rule_id=rule_id), request_text
    )


def test_a_finance_word_and_a_demo_word_conflict() -> None:
    found = match_rules("Write down what we spent", Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleConflict(("finance.spending", "demo.note"))


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({}, ()),
        ({"CONDUCTOR_MCP__FINANCES": "fin mcp serve"}, (finance.DOMAIN,)),
        (
            {"CONDUCTOR_MCP__FINANCES": "fin mcp serve", "CONDUCTOR_DEMO": "true"},
            (finance.DOMAIN, demo.DOMAIN),
        ),
        ({"CONDUCTOR_MCP__LEDGER": "fin mcp serve", "CONDUCTOR_DEMO": "true"}, (demo.DOMAIN,)),
    ],
    ids=["none", "finance", "finance-demo", "other-server-demo"],
)
def test_finance_is_registered_when_its_command_is_set(
    monkeypatch: pytest.MonkeyPatch, variables: dict[str, str], expected: tuple
) -> None:
    for key, value in variables.items():
        monkeypatch.setenv(key, value)
    assert domains.registered(get_settings()) == expected


def test_the_plan_point_has_a_larger_context() -> None:
    point = plan_point(finance.DOMAIN)
    assert (PLAN_CONTEXT_TOKENS, point.context_tokens, point.max_reply_tokens) == (
        16384,
        16384,
        4096,
    )
    sent = build_request(
        point,
        PlanInputs(request="What did we spend?"),
        model="m",
        fields=plan_fields(finance.DOMAIN),
    )
    assert sent.options["num_ctx"] == 16384
