"""A stand-in for the finances MCP server's 20 read tools, for the tests.

Each tool has the real tool's signature, so its input schema is the same as the one in
tests/finances_tools.json, and returns a small invented result of the real shape.
Run it as: <python> tests/fake_finances_server.py
"""

import sys
from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

server = MCPServer("fake-finances")
READ = ToolAnnotations(readOnlyHint=True)
By = Literal["category", "group", "merchant", "person", "account", "bank", "card"]

GROCER = {
    "id": 101,
    "day": "2026-10-04",
    "posted": "2026-10-05",
    "account": "Sample Checking",
    "description": "CORNER GROCER 0042",
    "merchant": "Corner Grocer",
    "amount_cents": -4210,
    "kind": "spending",
    "refund": False,
    "category": "Groceries",
    "group": "Food",
    "person": None,
    "card": "0042",
    "pending": False,
}
BRIEF = {
    "id": 102,
    "posted": "2026-10-06",
    "account": "Sample Checking",
    "description": "TRANSFER TO SAVINGS",
    "amount_cents": -50000,
}


@server.tool(annotations=READ)
def list_accounts(include_inactive: bool = False) -> dict[str, Any]:
    """The accounts."""
    return {
        "accounts": [
            {
                "name": "Sample Checking",
                "institution": "Example Bank",
                "type": "checking",
                "currency": "USD",
                "last4": "0042",
                "active": True,
                "owner": None,
                "joint": True,
            }
        ]
    }


@server.tool(annotations=READ)
def get_balances() -> dict[str, Any]:
    """Each account's newest balance."""
    return {
        "accounts": [
            {
                "name": "Sample Checking",
                "type": "checking",
                "balance_cents": 123456,
                "as_of": "2026-11-09",
                "source": "statement",
            }
        ],
        "cash_cents": 123456,
        "cards_cents": 0,
        "other_cents": 0,
        "net_worth_cents": 123456,
        "without_balance": [],
    }


@server.tool(annotations=READ)
def get_net_worth(months: Annotated[int, Field(ge=1, le=60)] = 12) -> dict[str, Any]:
    """Net worth at each month's end."""
    return {
        "as_of": "2026-11-10",
        "points": [{"day": "2026-10-31", "net_worth_cents": 120000, "accounts": 1}],
    }


@server.tool(annotations=READ)
def list_transactions(
    text: str = "",
    account: str = "",
    person: str = "",
    category: str = "",
    group: str = "",
    merchant: str = "",
    bank: str = "",
    card: str = "",
    kind: str = "",
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0, le=5000)] = 0,
) -> dict[str, Any]:
    """Transactions, latest first."""
    return {"transactions": [GROCER], "next_offset": None}


@server.tool(annotations=READ)
def get_spending(
    start: date | None = None,
    end: date | None = None,
    by: By = "category",
) -> dict[str, Any]:
    """Spending grouped."""
    return {
        "start": "2026-10-01" if start is None else start.isoformat(),
        "end": "2026-10-31" if end is None else end.isoformat(),
        "by": by,
        "lines": [
            {
                "label": "Groceries",
                "spent_cents": 4210,
                "refunds_cents": 0,
                "net_cents": 4210,
                "count": 1,
            }
        ],
        "summary": {
            "spent_cents": 4210,
            "refunds_cents": 0,
            "net_cents": 4210,
            "income_cents": 0,
            "transfers": 1,
            "unsorted_in_cents": 0,
            "unsorted_in_count": 0,
        },
    }


@server.tool(annotations=READ)
def month_over_month(
    month: str = "", count: Annotated[int, Field(ge=1, le=24)] = 6
) -> dict[str, Any]:
    """Net spending and income by month."""
    return {
        "months": [{"month": "2026-10", "net_cents": 4210, "income_cents": 0, "uncovered": False}]
    }


@server.tool(annotations=READ)
def get_insights(month: str = "") -> dict[str, Any]:
    """Findings for a month."""
    return {"month": "2026-11", "findings": [], "merchants": [], "set_aside": []}


@server.tool(annotations=READ)
def get_recurring(income: bool = False, include_inactive: bool = False) -> dict[str, Any]:
    """Recurring charges or income."""
    return {"as_of": "2026-11-10", "income": income, "series": []}


@server.tool(annotations=READ)
def get_upcoming(days: Annotated[int, Field(ge=1, le=90)] = 30) -> dict[str, Any]:
    """Bills and income expected."""
    return {
        "start": "2026-11-10",
        "end": "2026-12-09",
        "items": [
            {
                "day": "2026-11-15",
                "kind": "bill",
                "merchant": "Example Streaming",
                "cadence": "month",
                "amount_cents": -1299,
            }
        ],
        "bills_cents": -1299,
        "income_cents": 0,
    }


@server.tool(annotations=READ)
def get_forecast(
    days: Annotated[int, Field(ge=1, le=90)] = 30, account: str = ""
) -> dict[str, Any]:
    """Balances walked forward."""
    return {"start": "2026-11-10", "end": "2026-12-09", "accounts": [], "no_balance": []}


@server.tool(annotations=READ)
def get_budgets(month: str = "") -> dict[str, Any]:
    """Budgets for a month."""
    return {"month": "2026-11", "budgets": []}


@server.tool(annotations=READ)
def list_uncategorized(limit: Annotated[int, Field(ge=1, le=500)] = 50) -> dict[str, Any]:
    """Transactions without a category."""
    return {"total": 1, "transactions": [{**BRIEF, "merchant": "Transfer To Savings"}]}


@server.tool(annotations=READ)
def list_categories() -> dict[str, Any]:
    """Every category."""
    return {
        "categories": [
            {
                "name": "Groceries",
                "group": "Food",
                "transfer": False,
                "income": False,
                "sensitive": False,
            }
        ]
    }


@server.tool(annotations=READ)
def list_rules() -> dict[str, Any]:
    """Every categorizing rule."""
    return {
        "rules": [
            {
                "id": 1,
                "priority": 10,
                "match": "contains",
                "pattern": "CORNER GROCER",
                "category": "Groceries",
            }
        ]
    }


@server.tool(annotations=READ)
def list_transfers(limit: Annotated[int, Field(ge=1, le=500)] = 100) -> dict[str, Any]:
    """Transfers already paired."""
    return {"total": 0, "pairs": []}


@server.tool(annotations=READ)
def list_transfer_suggestions() -> dict[str, Any]:
    """Possible transfers."""
    return {"suggestions": []}


@server.tool(annotations=READ)
def data_coverage() -> dict[str, Any]:
    """How far the data can be trusted."""
    return {"as_of": "2026-11-10", "accounts": [], "problems": []}


@server.tool(annotations=READ)
def find_merchants(phrase: str, limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict[str, Any]:
    """Names like a phrase."""
    return {"matches": [{"name": "Corner Grocer", "kind": "merchant", "score": 90}]}


@server.tool(annotations=READ)
def list_proposals(
    status: Literal["open", "accepted", "declined"] = "open",
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Proposals of one status."""
    return {"proposals": []}


@server.tool(annotations=READ)
def list_advice(limit: Annotated[int, Field(ge=1, le=200)] = 20) -> dict[str, Any]:
    """Kept notes."""
    return {"advice": []}


if __name__ == "__main__":
    print("fake finances started", file=sys.stderr, flush=True)
    server.run("stdio")
