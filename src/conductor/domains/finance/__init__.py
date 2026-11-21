"""The finance domain: the read and proposal tools of the finances MCP server (`fin mcp serve`).

A proposal changes nothing in finances until a person accepts it there with `fin review`.
Adding a finances tool follows the checklist in docs/architecture.md.
"""

from conductor.domains.finance.common import SERVER
from conductor.domains.finance.proposals import (
    PROPOSALS,
    CategoryChangeProposalArgs,
    FindingProposalArgs,
    NoteArgs,
    NoteResult,
    ProposalResult,
    RuleChangeProposalArgs,
)
from conductor.domains.finance.reads import READS
from conductor.registry import Domain, Rule

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

__all__ = [
    "ACTIONS",
    "DOMAIN",
    "PROPOSALS",
    "READS",
    "RULES",
    "SERVER",
    "CategoryChangeProposalArgs",
    "FindingProposalArgs",
    "NoteArgs",
    "NoteResult",
    "ProposalResult",
    "RuleChangeProposalArgs",
]
