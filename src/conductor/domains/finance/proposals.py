from typing import Annotated, Literal

from pydantic import Field

from conductor.contracts.base import Contract, JsonObject
from conductor.domains.finance.common import SERVER, Label, Month
from conductor.registry import Action

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


def _propose(name: str, description: str, args: type[Contract], result: type[Contract]) -> Action:
    return Action(name, description, "tool", name, "propose", args, result, server=SERVER.name)


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
