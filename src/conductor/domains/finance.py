"""The finance domain: the read and proposal tools of the finances MCP server (`fin mcp serve`).

A proposal changes nothing in finances until a person accepts it there with `fin review`.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from conductor.contracts.base import Contract, JsonObject
from conductor.registry import Action, Domain, McpServer, Rule

SERVER = McpServer("finances", env=("FIN_DATA_DIR",))

Month = Annotated[str, Field(pattern=r"^([0-9]{4}-(0[1-9]|1[0-2]))?$")]
Label = Annotated[str, Field(max_length=100)]
Rows = list[JsonObject]
Names = list[str]
Kind = Literal["", "spending", "income", "transfer", "unsorted_in", "pending", "refund"]
By = Literal["category", "group", "merchant", "person", "account", "bank", "card"]
Id = Annotated[int, Field(ge=1)]
Reason = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S([^\r\n]*\S)?$")]
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^\S([^\r\n]*\S)?$")]
Match = Literal["contains", "starts_with", "equals"]
Priority = Annotated[int, Field(ge=-1000, le=1000)]
Finding = Literal[
    "spike",
    "frequent_small",
    "subscription_overlap",
    "price_increase",
    "interest",
    "fees",
    "over_budget",
    "duplicate",
    "large_first_charge",
]


class NoArgs(Contract):
    pass


class AccountsArgs(Contract):
    include_inactive: bool = False


class AccountsResult(Contract):
    accounts: Rows


class BalancesResult(Contract):
    accounts: Rows
    cash_cents: int
    cards_cents: int
    other_cents: int
    net_worth_cents: int
    without_balance: Names


class NetWorthArgs(Contract):
    months: int = Field(default=12, ge=1, le=24)


class NetWorthResult(Contract):
    as_of: str
    points: Rows


class TransactionsArgs(Contract):
    text: Label = ""
    account: Label = ""
    person: Label = ""
    category: Label = ""
    group: Label = ""
    merchant: Label = ""
    bank: Label = ""
    card: Label = ""
    kind: Kind = ""
    start: date | None = None
    end: date | None = None
    limit: int = Field(default=20, ge=1, le=40)
    offset: int = Field(default=0, ge=0, le=5000)


class TransactionsResult(Contract):
    transactions: Rows
    next_offset: int | None


class SpendingArgs(Contract):
    start: date | None = None
    end: date | None = None
    by: By = "category"


class SpendingResult(Contract):
    start: str
    end: str
    by: str
    lines: Rows
    summary: JsonObject


class MonthsArgs(Contract):
    month: Month = ""
    count: int = Field(default=6, ge=1, le=12)


class MonthsResult(Contract):
    months: Rows


class MonthArgs(Contract):
    month: Month = ""


class InsightsResult(Contract):
    month: str
    findings: Rows
    merchants: Rows
    set_aside: Rows


class RecurringArgs(Contract):
    income: bool = False
    include_inactive: bool = False


class RecurringResult(Contract):
    as_of: str
    income: bool
    series: Rows


class UpcomingArgs(Contract):
    days: int = Field(default=30, ge=1, le=90)


class UpcomingResult(Contract):
    start: str
    end: str
    items: Rows
    bills_cents: int
    income_cents: int


class ForecastArgs(Contract):
    days: int = Field(default=30, ge=1, le=60)
    account: Label = ""


class ForecastResult(Contract):
    start: str
    end: str
    accounts: Rows
    no_balance: Names


class BudgetsResult(Contract):
    month: str
    budgets: Rows


class LimitArgs(Contract):
    limit: int = Field(default=20, ge=1, le=40)


class UncategorizedResult(Contract):
    total: int
    transactions: Rows


class CategoriesResult(Contract):
    categories: Rows


class RulesResult(Contract):
    rules: Rows


class TransfersArgs(Contract):
    limit: int = Field(default=10, ge=1, le=20)


class TransfersResult(Contract):
    total: int
    pairs: Rows


class SuggestionsResult(Contract):
    suggestions: Rows


class CoverageResult(Contract):
    as_of: str
    accounts: Rows
    problems: Rows


class MerchantsArgs(Contract):
    phrase: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=5, ge=1, le=20)


class MerchantsResult(Contract):
    matches: Rows


class ProposalsArgs(Contract):
    status: Literal["open", "accepted", "declined"] = "open"
    limit: int = Field(default=10, ge=1, le=20)


class ProposalsResult(Contract):
    proposals: Rows


class AdviceArgs(Contract):
    limit: int = Field(default=10, ge=1, le=20)


class AdviceResult(Contract):
    advice: Rows


class CategoryProposalArgs(Contract):
    transaction_id: Id
    category: Name
    reason: Reason


class TransferProposalArgs(Contract):
    out_id: Id
    in_id: Id
    reason: Reason


class RuleProposalArgs(Contract):
    example_id: Id
    pattern: Name
    category: Name
    reason: Reason
    match: Match = "contains"
    priority: Priority = 0


class AliasProposalArgs(Contract):
    example_id: Id
    target: Name
    reason: Reason


class GroupProposalArgs(Contract):
    name: Name
    example_id: Id
    reason: Reason
    kind: Literal["spending", "transfer", "income"] = "spending"
    sensitive: bool = False


class NewCategoryProposalArgs(Contract):
    name: Name
    group: Name
    example_id: Id
    reason: Reason
    tax: bool = False


class RuleChangeProposalArgs(Contract):
    rule_id: Id
    reason: Reason
    delete: bool = False
    pattern: Name | None = None
    match: Match | None = None
    priority: Priority | None = None
    category: Name | None = None


class CategoryChangeProposalArgs(Contract):
    name: Name
    reason: Reason
    rename_to: Name | None = None
    delete: bool = False
    move_to: Name | None = None


class FindingProposalArgs(Contract):
    type: Finding
    status: Literal["handled", "ignored"]
    reason: Reason
    about: Label = ""
    month: Month = ""


class NoteArgs(Contract):
    text: str = Field(min_length=1, max_length=1000, pattern=r"^\S([\s\S]*\S)?$")
    subject: Label = ""


class ProposalResult(Contract):
    proposal: JsonObject


class NoteResult(Contract):
    advice: JsonObject


def _read(name: str, description: str, args: type[Contract], result: type[Contract]) -> Action:
    return Action(name, description, "tool", name, "read", args, result, server=SERVER.name)


def _propose(name: str, description: str, args: type[Contract], result: type[Contract]) -> Action:
    return Action(name, description, "tool", name, "propose", args, result, server=SERVER.name)


READS = (
    _read(
        "list_accounts",
        "The household's accounts: name, bank, type, currency, last 4 digits, owner; closed ones "
        "only when include_inactive is true.",
        AccountsArgs,
        AccountsResult,
    ),
    _read(
        "get_balances",
        "Each open account's newest balance in cents with its date, and the cash, card, other, "
        "and net worth totals.",
        NoArgs,
        BalancesResult,
    ),
    _read(
        "get_net_worth",
        "Net worth in cents at the end of each of the last months (1 to 24), this month ending "
        "today.",
        NetWorthArgs,
        NetWorthResult,
    ),
    _read(
        "list_transactions",
        "Transactions, latest first, filtered by description text, account, person, category, "
        "group, merchant, bank, card, kind, and days; at most 40 per call, then next_offset.",
        TransactionsArgs,
        TransactionsResult,
    ),
    _read(
        "get_spending",
        "Spending in cents from start to end (both or neither; default this month), grouped by "
        "category, group, merchant, person, account, bank, or card, with a summary.",
        SpendingArgs,
        SpendingResult,
    ),
    _read(
        "month_over_month",
        "Net spending and income in cents for each of the last months (1 to 12) ending with the "
        "given month (YYYY-MM, default this month).",
        MonthsArgs,
        MonthsResult,
    ),
    _read(
        "get_insights",
        "Findings about a month's spending (YYYY-MM, default this month): unusual charges, "
        "merchants that changed, possible savings.",
        MonthArgs,
        InsightsResult,
    ),
    _read(
        "get_recurring",
        "Recurring charges such as subscriptions and bills, or recurring income when income is "
        "true: cadence, amount, and next day.",
        RecurringArgs,
        RecurringResult,
    ),
    _read(
        "get_upcoming",
        "Bills and income expected in the next days (1 to 90, default 30), today the first.",
        UpcomingArgs,
        UpcomingResult,
    ),
    _read(
        "get_forecast",
        "Each account's balance walked forward through its expected bills and income for the "
        "next days (1 to 60), with its lowest point.",
        ForecastArgs,
        ForecastResult,
    ),
    _read(
        "get_budgets",
        "Each budget for a month (YYYY-MM, default this month): target, net spending so far, "
        "and what is left, in cents.",
        MonthArgs,
        BudgetsResult,
    ),
    _read(
        "list_uncategorized",
        "Transactions without a category, latest first (at most 40), with the total count.",
        LimitArgs,
        UncategorizedResult,
    ),
    _read(
        "list_categories",
        "Every category with its group, and whether it counts as a transfer, income, or sensitive.",
        NoArgs,
        CategoriesResult,
    ),
    _read(
        "list_rules",
        "Every categorizing rule in the order rules are tried: match, pattern, category.",
        NoArgs,
        RulesResult,
    ),
    _read(
        "list_transfers",
        "Transfers already paired between accounts, newest first (at most 20), with the total.",
        TransfersArgs,
        TransfersResult,
    ),
    _read(
        "list_transfer_suggestions",
        "Possible transfers waiting for a person to decide which pairing is right.",
        NoArgs,
        SuggestionsResult,
    ),
    _read(
        "data_coverage",
        "How far the data can be trusted: each account's first and last day, covered "
        "statements, gaps, and problems to fix.",
        NoArgs,
        CoverageResult,
    ),
    _read(
        "find_merchants",
        "Merchant and category names that look like a phrase (a misspelling or part of a "
        "name), best first; use it before filtering by a name the request may misspell.",
        MerchantsArgs,
        MerchantsResult,
    ),
    _read(
        "list_proposals",
        "The assistant's proposals of one status (open, accepted, or declined), newest first, "
        "at most 20.",
        ProposalsArgs,
        ProposalsResult,
    ),
    _read(
        "list_advice",
        "Notes the assistant kept for the household, newest first, at most 20.",
        AdviceArgs,
        AdviceResult,
    ),
)

PROPOSALS = (
    _propose(
        "propose_category",
        "Propose a category for one transaction (transaction_id from the request), with a "
        "one-line reason the person reads.",
        CategoryProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_transfer",
        "Propose that money out (out_id) and money in (in_id) on another account are one "
        "transfer, with a one-line reason.",
        TransferProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_not_transfer",
        "Propose that money out (out_id) and money in (in_id) are not one transfer though they "
        "look like one, with a one-line reason.",
        TransferProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_rule",
        "Propose a rule putting every transaction whose merchant matches pattern (contains, "
        "starts_with, or equals) in a category, with an example transaction it matches and a "
        "one-line reason.",
        RuleProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_merchant_alias",
        "Propose merging the merchant of an example transaction into another merchant (target), "
        "with a one-line reason.",
        AliasProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_group",
        "Propose a new group of categories (spending, transfer, or income), with an example "
        "transaction it is for and a one-line reason.",
        GroupProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_new_category",
        "Propose a new category in a group, with an example transaction it is for and a "
        "one-line reason.",
        NewCategoryProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_rule_change",
        "Propose changing a rule (rule_id from the request): its pattern, match, priority, or "
        "category, or delete it, with a one-line reason.",
        RuleChangeProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_category_change",
        "Propose renaming a category or group (rename_to), or deleting one (delete, with move_to "
        "for a category in use), with a one-line reason.",
        CategoryChangeProposalArgs,
        ProposalResult,
    ),
    _propose(
        "propose_finding_status",
        "Propose marking a finding of get_insights handled (that month) or ignored (every "
        "month), named by type, about, and month, with a one-line reason.",
        FindingProposalArgs,
        ProposalResult,
    ),
    _propose(
        "log_advice",
        "Keep a note of advice for the household (up to 1000 characters, with an optional "
        "subject); a person can dismiss it later.",
        NoteArgs,
        NoteResult,
    ),
)
ACTIONS = (*READS, *PROPOSALS)

RULES = (
    Rule("spending", ("spending", "spent")),
    Rule("budgets", ("budget", "budgets")),
    Rule("balances", ("balance", "balances", "net worth")),
    Rule("transactions", ("transactions", "uncategorized")),
    Rule("bills", ("bills", "subscriptions", "recurring")),
    Rule("transfers", ("transfers",)),
    Rule("proposals", ("propose", "proposal", "proposals", "categorize", "recategorize")),
)

DOMAIN = Domain(
    name="finance",
    description="The household's money in the finances app: accounts, balances, transactions, "
    "spending, budgets, bills, and forecasts, and proposals a person accepts or declines there.",
    actions=ACTIONS,
    rules=RULES,
    servers=(SERVER,),
)
