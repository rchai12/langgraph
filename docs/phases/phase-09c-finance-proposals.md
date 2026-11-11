# Phase 9c: the finance proposals

## Goal

The finance domain gains the 11 write tools of the `finances` MCP server as `propose` actions: the ten `propose_*` tools and `log_advice`. Each stores something in `finances` that a person accepts, declines, or dismisses there later (`fin review`), and each stops twice in conductor before it runs: once at the plan approval, and once just before its step with its exact arguments. Their arguments are bounded so a person can read all of them at the approval.

Decided with the owner (2026-11-10):
- **Ids come from the request.** A plan is fixed before any step runs, so a proposal cannot take an id from a read in the same run. The person names the ids, seen in an earlier read run's answer, and can edit them at the step approval. Planning a second time after the reads is not part of this phase.
- **All 11 write tools, all with effect `propose`.** `log_advice` only keeps a note a person can dismiss, so it is a proposal too.
- **Tight bounds.** A reason is one line of 1 to 200 characters; names and patterns are 1 to 100; ids are at least 1; the advice text is 1 to 1000 characters.
- **One keyword rule**, `finance.proposals`: propose, proposal, proposals, categorize, recategorize.

Decided by the architect, within those answers:
- The actions are named after their tools and come after the 20 reads: `ACTIONS = (*READS, *PROPOSALS)`.
- The descriptions, the type aliases, and the rule are given, because they are prompt text that 9d will tune. The coder writes the argument and result contracts from the table under Design.
- A reason or a name has no space at either end and no line break; the advice text may span lines but has no space at either end. A blank text is refused.
- The plan point keeps its 16384 context (see Facts).
- When `finances` refuses a proposal (for example, one is already open for that transaction), the step fails as `tool_error`, as every tool error does since 6c. Its text is never read, because it can echo the arguments.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rule 7), `docs/architecture.md` ("Approvals", "Domains and actions", "MCP")
- `docs/phases/phase-09b-finance-read-actions.md` (the read actions, the fake server, the saved schemas)
- `src/conductor/domains/finance.py`, `src/conductor/policy.py` (`needs_approval`, `apply_decision`), `src/conductor/decisions.py`, `tests/integration/test_finance_more.py` (how a test starts the fake server)

## Starting state

Phase 9b is built and verified, and everything is committed: N is `908`. **Sections: cli, core.** `conductor.domains.finance` has the 20 read actions in a tuple named `ACTIONS`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/domains/finance.py` | the given parts, the contracts of the table, `READS` (Part 1) |
| `tests/finances_tools.json`, `tests/fake_finances_server.py` | given: replace both whole (Part 2) |
| `tests/unit/test_finance_domain.py`, `tests/unit/test_finance_more.py` | given edits: four lines (Part 2) |
| `tests/unit/test_finance_proposals.py`, `tests/integration/test_finance_proposal_steps.py` | given |
| `tests/unit/test_finance_proposals_more.py`, `tests/integration/test_finance_proposals_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Planning again after the reads, or arguments that refer to an earlier step's result.
- Any change to the policy, the graph, the runtime, the store, the decisions, the web pages, the MCP client, the tool check, the templates, `plan_point`, or `registered`.
- Reading a refused tool's text; a new escalation kind or cause code.
- Finance evaluation cases and prompt tuning (9d).
- Running the real `fin` in any test or probe.

## Dependencies

None new.

## Design

### Part 1: the actions

`src/conductor/domains/finance.py` changes in five places, in this order in the file:

1. **The head.** Replace everything from the first line to the line `By = Literal[...]` with the given head below. It adds the module's new docstring and the aliases `Id`, `Reason`, `Name`, `Match`, `Priority`, and `Finding`.
2. **The contracts.** After `AdviceResult`, add the 11 contracts of the table below.
3. **`_propose`.** After `_read`, add:

```python
def _propose(name: str, description: str, args: type[Contract], result: type[Contract]) -> Action:
    return Action(name, description, "tool", name, "propose", args, result, server=SERVER.name)
```

4. **`READS`.** Rename the tuple of the 20 read actions from `ACTIONS` to `READS`, and change nothing else in it.
5. **The tail.** Replace everything after `READS` with the given tail below. It declares `PROPOSALS`, `ACTIONS = (*READS, *PROPOSALS)`, the seventh rule, and `DOMAIN` with its new description.

The given head (copy it exactly):

```python
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
```

The given tail (copy it exactly):

```python
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
```

The contracts, each a `Contract` with its fields in this order (the order of the tool's own signature). "Required" means no default.

| Contract | Field | Type | Default |
|---|---|---|---|
| `CategoryProposalArgs` | `transaction_id` | `Id` | required |
| | `category` | `Name` | required |
| | `reason` | `Reason` | required |
| `TransferProposalArgs` (for both transfer tools) | `out_id`, `in_id` | `Id` | required |
| | `reason` | `Reason` | required |
| `RuleProposalArgs` | `example_id` | `Id` | required |
| | `pattern`, `category` | `Name` | required |
| | `reason` | `Reason` | required |
| | `match` | `Match` | `"contains"` |
| | `priority` | `Priority` | `0` |
| `AliasProposalArgs` | `example_id` | `Id` | required |
| | `target` | `Name` | required |
| | `reason` | `Reason` | required |
| `GroupProposalArgs` | `name` | `Name` | required |
| | `example_id` | `Id` | required |
| | `reason` | `Reason` | required |
| | `kind` | `Literal["spending", "transfer", "income"]` | `"spending"` |
| | `sensitive` | `bool` | `False` |
| `NewCategoryProposalArgs` | `name`, `group` | `Name` | required |
| | `example_id` | `Id` | required |
| | `reason` | `Reason` | required |
| | `tax` | `bool` | `False` |
| `RuleChangeProposalArgs` | `rule_id` | `Id` | required |
| | `reason` | `Reason` | required |
| | `delete` | `bool` | `False` |
| | `pattern` | `Name \| None` | `None` |
| | `match` | `Match \| None` | `None` |
| | `priority` | `Priority \| None` | `None` |
| | `category` | `Name \| None` | `None` |
| `CategoryChangeProposalArgs` | `name` | `Name` | required |
| | `reason` | `Reason` | required |
| | `rename_to` | `Name \| None` | `None` |
| | `delete` | `bool` | `False` |
| | `move_to` | `Name \| None` | `None` |
| `FindingProposalArgs` | `type` | `Finding` | required |
| | `status` | `Literal["handled", "ignored"]` | required |
| | `reason` | `Reason` | required |
| | `about` | `Label` | `""` |
| | `month` | `Month` | `""` |
| `NoteArgs` | `text` | `str`, 1 to 1000 characters, pattern `^\S([\s\S]*\S)?$` | required |
| | `subject` | `Label` | `""` |
| `ProposalResult` | `proposal` | `JsonObject` | required |
| `NoteResult` | `advice` | `JsonObject` | required |

Every proposal tool returns `{"proposal": {...}}` and `log_advice` returns `{"advice": {...}}`. As for the reads, the result contracts name only the top-level field and leave its inside open, so `finances` can add fields inside a proposal without stopping runs.

Nothing else changes for a proposal to stop twice. The policy already asks for the plan approval when a plan has any step that is not `read`, and asks again before each `propose` step. The 6b tool check accepts a `propose` action on a tool that is not read-only.

### Part 2: the fake server and the saved schemas

`tests/finances_tools.json` becomes a copy of all 31 tools of the real server, in the server's listing order: input schema, output schema, and the read-only mark, with no data. `tests/fake_finances_server.py` gains the 11 write tools with the real signatures, marked `readOnlyHint=False`. They store nothing and return invented proposals of the real shape. Its listing still equals the saved copy exactly, which the 9b test `test_the_fake_lists_the_real_read_tools` checks. That test is unchanged and now covers all 31 tools.

Two 9b test files iterate over every action of the domain and send `{}`, which a proposal refuses, because its fields are required. They change by these four lines and nothing else:

| File | Line now | Line after |
|---|---|---|
| `tests/unit/test_finance_domain.py` | `ACTIONS = {action.name: action for action in finance.DOMAIN.actions}` | `ACTIONS = {action.name: action for action in finance.READS}` |
| `tests/unit/test_finance_domain.py` | `    assert list(ACTIONS) == list(REAL)` | `    assert list(ACTIONS) == [name for name, item in REAL.items() if item["read_only"]]` |
| `tests/unit/test_finance_domain.py` | `        for action in finance.DOMAIN.actions` (in `test_twenty_read_actions_on_one_server`) | `        for action in finance.READS` |
| `tests/unit/test_finance_more.py` | `    for action in finance.DOMAIN.actions:` | `    for action in finance.READS:` |

`test_every_action_fits_the_real_read_tools` still uses every action and all of `REAL`, so it now checks the 31 actions against the 31 real tools.

## Facts

From a spike on 2026-11-10. The tool listing is the one taken for 9b, against the real `fin mcp serve` with an empty data folder, so no data was read. The plans came from the owner's model (`qwen3.8:27b`), given synthetic requests only.

- The 11 write tools are marked `readOnlyHint: false` and have open object output schemas. Each refusal is raised as a tool error (`ToolError` with the reason as its text), so conductor sees an `is_error` result.
- The real `find_finding` accepts these nine types: spike, frequent_small, subscription_overlap, price_increase, interest, fees, over_budget, duplicate, large_first_charge. The statuses are `handled` and `ignored`.
- The full module passes the 6b tool check against the real 31 tools, with no problem.
- With 31 actions, the finance plan request is a 41858-byte system message, about 11970 prompt tokens. With the 4096 reply cap that is at most 16066 of the 16384 context, so the plan point is unchanged. Replies took 168 to 263 tokens, and 4 to 30 seconds.
- Seven synthetic proposal requests all planned validly. Each used the ids and names given in the request. One request that also named a read planned `list_uncategorized` and then `propose_category`.
- Ollama accepted the patterns `^\S([^\r\n]*\S)?$` and `^\S([\s\S]*\S)?$` in the plan schema, and replies matched them. Pydantic enforces them either way, so a reason that breaks one escalates as `invalid_plan`, and an edit that breaks one is refused as `invalid_edit`.

## Requirements

### Part 1: the actions

- **R1.** `finance.py` contains the given head, `_propose`, and the given tail exactly. `READS` is the 9b tuple of 20 read actions under its new name, otherwise unchanged. `Registry((finance.DOMAIN,))` accepts the domain, and `DOMAIN.actions == ACTIONS == (*READS, *PROPOSALS)`.
- **R2.** The nine argument contracts follow the table: types, defaults, and field order. Each contract's required fields equal its tool's required fields.
- **R3.** `ProposalResult` and `NoteResult` follow the table.
- **R4.** Every proposal action has effect `propose`. No action has effect `write` or `implement`.

### Part 2: the fake server and the saved schemas

- **R5.** The given `tests/finances_tools.json` and `tests/fake_finances_server.py` are copied exactly. The four given lines in the two 9b test files are changed, and nothing else in those files.

### Part 3: a proposal run

- **R6.** A finance plan with a proposal stops at the plan approval before any step runs. After approval, its read steps run, and it stops again before the proposal with its exact arguments. A rejection ends the run with no call to the tool; an edit sends the edited arguments; an edit past a bound is refused, and the request stays open. All of this goes through the policy, the graph, and the runtime as they are, with no change to them.

### Part 4: the rules

- **R7.** Only the Scope's paths change. No earlier test changes except the four given lines.
- **R8.** No test or probe starts `fin` or reads anything from the `finances` project. The tests use only the fake and invented data.
- **R9.** `domains/finance.py` reaches 100% of lines and branches.

## Given tests

50 new tests in two files (counting each parameter set), with the replaced fake server and saved schemas and the four given lines. Do not change them; if one fails, the code is wrong. Before your change, `tests/unit/test_finance_proposals.py` and `tests/unit/test_finance_domain.py` fail to import (`finance.PROPOSALS` and `finance.READS` do not exist yet). `test_a_left_out_argument_keeps_its_default_except_the_phrase` fails the same way. Every test of `tests/integration/test_finance_proposal_steps.py` fails, because the plan's proposal step is not an action yet, so the plan escalates and no approval is made.

`tests/finances_tools.json` (given; replace the file, ending with one newline)

```json
{
  "list_accounts": {
    "input_schema": {
      "properties": {
        "include_inactive": {
          "default": false,
          "title": "Include Inactive",
          "type": "boolean"
        }
      },
      "type": "object",
      "title": "list_accountsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_accountsDictOutput"
    },
    "read_only": true
  },
  "get_balances": {
    "input_schema": {
      "properties": {},
      "type": "object",
      "title": "get_balancesArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_balancesDictOutput"
    },
    "read_only": true
  },
  "get_net_worth": {
    "input_schema": {
      "properties": {
        "months": {
          "default": 12,
          "maximum": 60,
          "minimum": 1,
          "title": "Months",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "get_net_worthArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_net_worthDictOutput"
    },
    "read_only": true
  },
  "list_transactions": {
    "input_schema": {
      "properties": {
        "text": {
          "default": "",
          "title": "Text",
          "type": "string"
        },
        "account": {
          "default": "",
          "title": "Account",
          "type": "string"
        },
        "person": {
          "default": "",
          "title": "Person",
          "type": "string"
        },
        "category": {
          "default": "",
          "title": "Category",
          "type": "string"
        },
        "group": {
          "default": "",
          "title": "Group",
          "type": "string"
        },
        "merchant": {
          "default": "",
          "title": "Merchant",
          "type": "string"
        },
        "bank": {
          "default": "",
          "title": "Bank",
          "type": "string"
        },
        "card": {
          "default": "",
          "title": "Card",
          "type": "string"
        },
        "kind": {
          "default": "",
          "title": "Kind",
          "type": "string"
        },
        "start": {
          "anyOf": [
            {
              "format": "date",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "format": "date",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "End"
        },
        "limit": {
          "default": 50,
          "maximum": 200,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "offset": {
          "default": 0,
          "maximum": 5000,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "list_transactionsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_transactionsDictOutput"
    },
    "read_only": true
  },
  "get_spending": {
    "input_schema": {
      "properties": {
        "start": {
          "anyOf": [
            {
              "format": "date",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Start"
        },
        "end": {
          "anyOf": [
            {
              "format": "date",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "End"
        },
        "by": {
          "default": "category",
          "enum": [
            "category",
            "group",
            "merchant",
            "person",
            "account",
            "bank",
            "card"
          ],
          "title": "By",
          "type": "string"
        }
      },
      "type": "object",
      "title": "get_spendingArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_spendingDictOutput"
    },
    "read_only": true
  },
  "month_over_month": {
    "input_schema": {
      "properties": {
        "month": {
          "default": "",
          "title": "Month",
          "type": "string"
        },
        "count": {
          "default": 6,
          "maximum": 24,
          "minimum": 1,
          "title": "Count",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "month_over_monthArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "month_over_monthDictOutput"
    },
    "read_only": true
  },
  "get_insights": {
    "input_schema": {
      "properties": {
        "month": {
          "default": "",
          "title": "Month",
          "type": "string"
        }
      },
      "type": "object",
      "title": "get_insightsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_insightsDictOutput"
    },
    "read_only": true
  },
  "get_recurring": {
    "input_schema": {
      "properties": {
        "income": {
          "default": false,
          "title": "Income",
          "type": "boolean"
        },
        "include_inactive": {
          "default": false,
          "title": "Include Inactive",
          "type": "boolean"
        }
      },
      "type": "object",
      "title": "get_recurringArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_recurringDictOutput"
    },
    "read_only": true
  },
  "get_upcoming": {
    "input_schema": {
      "properties": {
        "days": {
          "default": 30,
          "maximum": 90,
          "minimum": 1,
          "title": "Days",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "get_upcomingArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_upcomingDictOutput"
    },
    "read_only": true
  },
  "get_forecast": {
    "input_schema": {
      "properties": {
        "days": {
          "default": 30,
          "maximum": 90,
          "minimum": 1,
          "title": "Days",
          "type": "integer"
        },
        "account": {
          "default": "",
          "title": "Account",
          "type": "string"
        }
      },
      "type": "object",
      "title": "get_forecastArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_forecastDictOutput"
    },
    "read_only": true
  },
  "get_budgets": {
    "input_schema": {
      "properties": {
        "month": {
          "default": "",
          "title": "Month",
          "type": "string"
        }
      },
      "type": "object",
      "title": "get_budgetsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "get_budgetsDictOutput"
    },
    "read_only": true
  },
  "list_uncategorized": {
    "input_schema": {
      "properties": {
        "limit": {
          "default": 50,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "list_uncategorizedArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_uncategorizedDictOutput"
    },
    "read_only": true
  },
  "list_categories": {
    "input_schema": {
      "properties": {},
      "type": "object",
      "title": "list_categoriesArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_categoriesDictOutput"
    },
    "read_only": true
  },
  "list_rules": {
    "input_schema": {
      "properties": {},
      "type": "object",
      "title": "list_rulesArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_rulesDictOutput"
    },
    "read_only": true
  },
  "list_transfers": {
    "input_schema": {
      "properties": {
        "limit": {
          "default": 100,
          "maximum": 500,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "list_transfersArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_transfersDictOutput"
    },
    "read_only": true
  },
  "list_transfer_suggestions": {
    "input_schema": {
      "properties": {},
      "type": "object",
      "title": "list_transfer_suggestionsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_transfer_suggestionsDictOutput"
    },
    "read_only": true
  },
  "data_coverage": {
    "input_schema": {
      "properties": {},
      "type": "object",
      "title": "data_coverageArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "data_coverageDictOutput"
    },
    "read_only": true
  },
  "find_merchants": {
    "input_schema": {
      "properties": {
        "phrase": {
          "title": "Phrase",
          "type": "string"
        },
        "limit": {
          "default": 5,
          "maximum": 20,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        }
      },
      "required": [
        "phrase"
      ],
      "type": "object",
      "title": "find_merchantsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "find_merchantsDictOutput"
    },
    "read_only": true
  },
  "propose_category": {
    "input_schema": {
      "properties": {
        "transaction_id": {
          "title": "Transaction Id",
          "type": "integer"
        },
        "category": {
          "title": "Category",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        }
      },
      "required": [
        "transaction_id",
        "category",
        "reason"
      ],
      "type": "object",
      "title": "propose_categoryArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_categoryDictOutput"
    },
    "read_only": false
  },
  "propose_transfer": {
    "input_schema": {
      "properties": {
        "out_id": {
          "title": "Out Id",
          "type": "integer"
        },
        "in_id": {
          "title": "In Id",
          "type": "integer"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        }
      },
      "required": [
        "out_id",
        "in_id",
        "reason"
      ],
      "type": "object",
      "title": "propose_transferArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_transferDictOutput"
    },
    "read_only": false
  },
  "propose_not_transfer": {
    "input_schema": {
      "properties": {
        "out_id": {
          "title": "Out Id",
          "type": "integer"
        },
        "in_id": {
          "title": "In Id",
          "type": "integer"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        }
      },
      "required": [
        "out_id",
        "in_id",
        "reason"
      ],
      "type": "object",
      "title": "propose_not_transferArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_not_transferDictOutput"
    },
    "read_only": false
  },
  "propose_rule": {
    "input_schema": {
      "properties": {
        "example_id": {
          "title": "Example Id",
          "type": "integer"
        },
        "pattern": {
          "title": "Pattern",
          "type": "string"
        },
        "category": {
          "title": "Category",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "match": {
          "default": "contains",
          "enum": [
            "contains",
            "starts_with",
            "equals"
          ],
          "title": "Match",
          "type": "string"
        },
        "priority": {
          "default": 0,
          "maximum": 1000,
          "minimum": -1000,
          "title": "Priority",
          "type": "integer"
        }
      },
      "required": [
        "example_id",
        "pattern",
        "category",
        "reason"
      ],
      "type": "object",
      "title": "propose_ruleArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_ruleDictOutput"
    },
    "read_only": false
  },
  "propose_merchant_alias": {
    "input_schema": {
      "properties": {
        "example_id": {
          "title": "Example Id",
          "type": "integer"
        },
        "target": {
          "title": "Target",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        }
      },
      "required": [
        "example_id",
        "target",
        "reason"
      ],
      "type": "object",
      "title": "propose_merchant_aliasArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_merchant_aliasDictOutput"
    },
    "read_only": false
  },
  "propose_group": {
    "input_schema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "example_id": {
          "title": "Example Id",
          "type": "integer"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "kind": {
          "default": "spending",
          "enum": [
            "spending",
            "transfer",
            "income"
          ],
          "title": "Kind",
          "type": "string"
        },
        "sensitive": {
          "default": false,
          "title": "Sensitive",
          "type": "boolean"
        }
      },
      "required": [
        "name",
        "example_id",
        "reason"
      ],
      "type": "object",
      "title": "propose_groupArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_groupDictOutput"
    },
    "read_only": false
  },
  "propose_new_category": {
    "input_schema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "group": {
          "title": "Group",
          "type": "string"
        },
        "example_id": {
          "title": "Example Id",
          "type": "integer"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "tax": {
          "default": false,
          "title": "Tax",
          "type": "boolean"
        }
      },
      "required": [
        "name",
        "group",
        "example_id",
        "reason"
      ],
      "type": "object",
      "title": "propose_new_categoryArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_new_categoryDictOutput"
    },
    "read_only": false
  },
  "propose_rule_change": {
    "input_schema": {
      "properties": {
        "rule_id": {
          "title": "Rule Id",
          "type": "integer"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "delete": {
          "default": false,
          "title": "Delete",
          "type": "boolean"
        },
        "pattern": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pattern"
        },
        "match": {
          "anyOf": [
            {
              "enum": [
                "contains",
                "starts_with",
                "equals"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Match"
        },
        "priority": {
          "anyOf": [
            {
              "maximum": 1000,
              "minimum": -1000,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Priority"
        },
        "category": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Category"
        }
      },
      "required": [
        "rule_id",
        "reason"
      ],
      "type": "object",
      "title": "propose_rule_changeArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_rule_changeDictOutput"
    },
    "read_only": false
  },
  "propose_category_change": {
    "input_schema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "rename_to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Rename To"
        },
        "delete": {
          "default": false,
          "title": "Delete",
          "type": "boolean"
        },
        "move_to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Move To"
        }
      },
      "required": [
        "name",
        "reason"
      ],
      "type": "object",
      "title": "propose_category_changeArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_category_changeDictOutput"
    },
    "read_only": false
  },
  "propose_finding_status": {
    "input_schema": {
      "properties": {
        "type": {
          "title": "Type",
          "type": "string"
        },
        "status": {
          "title": "Status",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        },
        "about": {
          "default": "",
          "title": "About",
          "type": "string"
        },
        "month": {
          "default": "",
          "title": "Month",
          "type": "string"
        }
      },
      "required": [
        "type",
        "status",
        "reason"
      ],
      "type": "object",
      "title": "propose_finding_statusArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "propose_finding_statusDictOutput"
    },
    "read_only": false
  },
  "list_proposals": {
    "input_schema": {
      "properties": {
        "status": {
          "default": "open",
          "enum": [
            "open",
            "accepted",
            "declined"
          ],
          "title": "Status",
          "type": "string"
        },
        "limit": {
          "default": 50,
          "maximum": 200,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "list_proposalsArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_proposalsDictOutput"
    },
    "read_only": true
  },
  "log_advice": {
    "input_schema": {
      "properties": {
        "text": {
          "title": "Text",
          "type": "string"
        },
        "subject": {
          "default": "",
          "title": "Subject",
          "type": "string"
        }
      },
      "required": [
        "text"
      ],
      "type": "object",
      "title": "log_adviceArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "log_adviceDictOutput"
    },
    "read_only": false
  },
  "list_advice": {
    "input_schema": {
      "properties": {
        "limit": {
          "default": 20,
          "maximum": 200,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        }
      },
      "type": "object",
      "title": "list_adviceArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "list_adviceDictOutput"
    },
    "read_only": true
  }
}
```

`tests/fake_finances_server.py` (given; replace the file)

```python
"""A stand-in for the finances MCP server's 31 tools, for the tests.

Each tool has the real tool's signature, so its input schema is the same as the one in
tests/finances_tools.json, and returns a small invented result of the real shape. The
proposal tools store nothing.
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
WRITE = ToolAnnotations(readOnlyHint=False)
By = Literal["category", "group", "merchant", "person", "account", "bank", "card"]
Match = Literal["contains", "starts_with", "equals"]

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


def proposal(kind: str, reason: str, **fields: Any) -> dict[str, Any]:
    item = {
        "id": 7,
        "kind": kind,
        "transaction_id": None,
        "in_id": None,
        "category": None,
        "rule": None,
        "alias": None,
        "new": None,
        "waits_for": None,
        "rule_change": None,
        "finding": None,
        "category_change": None,
        "reason": reason,
        "status": "open",
        "created_at": "2026-11-10T09:00:00+00:00",
        "decided_at": None,
        "out_of_date": False,
    }
    return {"proposal": {**item, **fields}}


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


@server.tool(annotations=WRITE)
def propose_category(transaction_id: int, category: str, reason: str) -> dict[str, Any]:
    """Propose a category."""
    return proposal("category", reason, transaction_id=transaction_id, category=category)


@server.tool(annotations=WRITE)
def propose_transfer(out_id: int, in_id: int, reason: str) -> dict[str, Any]:
    """Propose a transfer."""
    return proposal("transfer", reason, transaction_id=out_id, in_id=in_id)


@server.tool(annotations=WRITE)
def propose_not_transfer(out_id: int, in_id: int, reason: str) -> dict[str, Any]:
    """Propose not a transfer."""
    return proposal("not_transfer", reason, transaction_id=out_id, in_id=in_id)


@server.tool(annotations=WRITE)
def propose_rule(
    example_id: int,
    pattern: str,
    category: str,
    reason: str,
    match: Match = "contains",
    priority: Annotated[int, Field(ge=-1000, le=1000)] = 0,
) -> dict[str, Any]:
    """Propose a rule."""
    rule = {"match": match, "pattern": pattern, "priority": priority}
    return proposal("rule", reason, transaction_id=example_id, category=category, rule=rule)


@server.tool(annotations=WRITE)
def propose_merchant_alias(example_id: int, target: str, reason: str) -> dict[str, Any]:
    """Propose a merchant alias."""
    alias = {"source": "Corner Grocer 42", "target": target}
    return proposal("alias", reason, transaction_id=example_id, alias=alias)


@server.tool(annotations=WRITE)
def propose_group(
    name: str,
    example_id: int,
    reason: str,
    kind: Literal["spending", "transfer", "income"] = "spending",
    sensitive: bool = False,
) -> dict[str, Any]:
    """Propose a group."""
    new = {"name": name, "group": None, "kind": kind, "sensitive": sensitive, "tax": None}
    return proposal("group", reason, transaction_id=example_id, new=new)


@server.tool(annotations=WRITE)
def propose_new_category(
    name: str,
    group: str,
    example_id: int,
    reason: str,
    tax: bool = False,
) -> dict[str, Any]:
    """Propose a category."""
    new = {"name": name, "group": group, "kind": None, "sensitive": None, "tax": tax}
    return proposal("new_category", reason, transaction_id=example_id, new=new)


@server.tool(annotations=WRITE)
def propose_rule_change(
    rule_id: int,
    reason: str,
    delete: bool = False,
    pattern: str | None = None,
    match: Match | None = None,
    priority: Annotated[int | None, Field(ge=-1000, le=1000)] = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Propose a rule change."""
    change = {"rule_id": rule_id, "before": None, "delete": delete}
    kind = "rule_delete" if delete else "rule_edit"
    return proposal(kind, reason, category=category, rule_change=change)


@server.tool(annotations=WRITE)
def propose_category_change(
    name: str,
    reason: str,
    rename_to: str | None = None,
    delete: bool = False,
    move_to: str | None = None,
) -> dict[str, Any]:
    """Propose a category change."""
    change = {"name": name, "rename_to": rename_to, "delete": delete, "move_to": move_to}
    kind = "category_delete" if delete else "category_rename"
    return proposal(kind, reason, category_change=change)


@server.tool(annotations=WRITE)
def propose_finding_status(
    type: str, status: str, reason: str, about: str = "", month: str = ""
) -> dict[str, Any]:
    """Propose a finding status."""
    finding = {"type": type, "about": about, "month": month or "2026-11", "status": status}
    return proposal("finding_status", reason, finding=finding)


@server.tool(annotations=READ)
def list_proposals(
    status: Literal["open", "accepted", "declined"] = "open",
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Proposals of one status."""
    return {"proposals": []}


@server.tool(annotations=WRITE)
def log_advice(text: str, subject: str = "") -> dict[str, Any]:
    """Keep a note."""
    note = {
        "id": 3,
        "created_at": "2026-11-10T09:00:00+00:00",
        "subject": subject,
        "text": text,
        "dismissed_at": None,
    }
    return {"advice": note}


@server.tool(annotations=READ)
def list_advice(limit: Annotated[int, Field(ge=1, le=200)] = 20) -> dict[str, Any]:
    """Kept notes."""
    return {"advice": []}


if __name__ == "__main__":
    print("fake finances started", file=sys.stderr, flush=True)
    server.run("stdio")
```

`tests/unit/test_finance_proposals.py` (44 tests)

```python
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from conductor.contracts import Route
from conductor.domains import demo, finance
from conductor.policy import needs_approval
from conductor.registry import Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

TESTS = Path(__file__).resolve().parents[1]
REAL = json.loads((TESTS / "finances_tools.json").read_text())
PROPOSALS = {action.name: action for action in finance.PROPOSALS}
REASON = "Corner Grocer sells food"
MINIMAL = {
    "propose_category": {"transaction_id": 101, "category": "Groceries", "reason": REASON},
    "propose_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_not_transfer": {"out_id": 205, "in_id": 318, "reason": REASON},
    "propose_rule": {
        "example_id": 101,
        "pattern": "CORNER GROCER",
        "category": "Groceries",
        "reason": REASON,
    },
    "propose_merchant_alias": {"example_id": 101, "target": "Corner Grocer", "reason": REASON},
    "propose_group": {"name": "Household", "example_id": 101, "reason": REASON},
    "propose_new_category": {
        "name": "Pet food",
        "group": "Food",
        "example_id": 101,
        "reason": REASON,
    },
    "propose_rule_change": {"rule_id": 1, "reason": REASON},
    "propose_category_change": {"name": "Groceries", "reason": REASON},
    "propose_finding_status": {"type": "spike", "status": "handled", "reason": REASON},
    "log_advice": {"text": "Review the streaming subscriptions in December."},
}
DEFAULTS = {
    "propose_rule": {"match": "contains", "priority": 0},
    "propose_group": {"kind": "spending", "sensitive": False},
    "propose_new_category": {"tax": False},
    "propose_rule_change": {
        "delete": False,
        "pattern": None,
        "match": None,
        "priority": None,
        "category": None,
    },
    "propose_category_change": {"rename_to": None, "delete": False, "move_to": None},
    "propose_finding_status": {"about": "", "month": ""},
    "log_advice": {"subject": ""},
}


def fake_module():
    spec = importlib.util.spec_from_file_location(
        "fake_finances", TESTS / "fake_finances_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(name: str, **changes: object):
    return PROPOSALS[name].args.from_json(json.dumps({**MINIMAL[name], **changes}))


def test_eleven_proposal_actions_after_the_reads() -> None:
    assert list(PROPOSALS) == [name for name, item in REAL.items() if not item["read_only"]]
    assert finance.ACTIONS == (*finance.READS, *finance.PROPOSALS)
    assert finance.DOMAIN.actions == finance.ACTIONS
    assert {
        (action.kind, action.target == action.name, action.effect, action.server)
        for action in finance.PROPOSALS
    } == {("tool", True, "propose", "finances")}
    assert all(needs_approval(action) for action in finance.PROPOSALS)


@pytest.mark.parametrize("name", list(MINIMAL))
def test_the_required_fields_and_the_defaults(name: str) -> None:
    contract = PROPOSALS[name].args
    assert sorted(contract.model_json_schema()["required"]) == sorted(
        REAL[name]["input_schema"]["required"]
    )
    assert args(name).model_dump(mode="json") == {**MINIMAL[name], **DEFAULTS.get(name, {})}


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("propose_category", "reason", "x" * 200),
        ("propose_category", "reason", "x"),
        ("propose_category", "category", "é" * 100),
        ("propose_category", "transaction_id", 1),
        ("propose_rule", "priority", -1000),
        ("propose_rule", "priority", 1000),
        ("propose_finding_status", "month", "2026-10"),
        ("log_advice", "text", "a\n" * 499 + "ab"),
    ],
    ids=[
        "reason-200",
        "reason-1",
        "category-100",
        "id-1",
        "priority-low",
        "priority-high",
        "month",
        "text-1000",
    ],
)
def test_arguments_at_their_bounds_are_sent(name: str, field: str, value: object) -> None:
    assert args(name, **{field: value}).model_dump(mode="json")[field] == value


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("propose_category", "reason", ""),
        ("propose_category", "reason", "x" * 201),
        ("propose_category", "reason", "two\nlines"),
        ("propose_category", "reason", " leading"),
        ("propose_category", "reason", "trailing "),
        ("propose_category", "category", "x" * 101),
        ("propose_category", "transaction_id", 0),
        ("propose_category", "transaction_id", "101"),
        ("propose_category", "amount_cents", 4210),
        ("propose_rule", "priority", 1001),
        ("propose_rule", "match", "regex"),
        ("propose_rule_change", "priority", -1001),
        ("propose_finding_status", "type", "unknown"),
        ("propose_finding_status", "status", "open"),
        ("propose_finding_status", "month", "2026-13"),
        ("log_advice", "text", "x" * 1001),
        ("log_advice", "text", "   "),
    ],
    ids=[
        "reason-empty",
        "reason-201",
        "reason-two-lines",
        "reason-leading",
        "reason-trailing",
        "category-101",
        "id-0",
        "id-text",
        "extra-field",
        "priority-1001",
        "match",
        "change-priority",
        "finding-type",
        "finding-status",
        "finding-month",
        "text-1001",
        "text-blank",
    ],
)
def test_arguments_past_their_bounds_are_refused(name: str, field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        args(name, **{field: value})


def test_the_fake_server_returns_a_result_each_proposal_accepts() -> None:
    fake = fake_module()
    for name, action in PROPOSALS.items():
        output = getattr(fake, name)(**args(name).model_dump())
        action.result.from_json(json.dumps(output))
    for result in (finance.ProposalResult, finance.NoteResult):
        with pytest.raises(ValidationError):
            result.from_json("{}")


@pytest.mark.parametrize(
    ("request_text", "rule_id"),
    [
        ("Propose Groceries for transaction 101", "finance.proposals"),
        ("Recategorize transaction 77 as Dining", "finance.proposals"),
        ("Show my open proposals", "finance.proposals"),
        ("Categorize the coffee shop as Dining", "finance.proposals"),
        ("Categorize the uncategorized transactions", "finance.transactions"),
    ],
    ids=["propose", "recategorize", "proposals", "categorize", "transactions-first"],
)
def test_proposal_words_route_by_rule(request_text: str, rule_id: str) -> None:
    found = match_rules(request_text, Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleRoute(
        Route(domain="finance", decided_by="rule", rule_id=rule_id), request_text
    )


def test_a_proposal_word_and_a_demo_word_conflict() -> None:
    found = match_rules("Propose a note", Registry((finance.DOMAIN, demo.DOMAIN)))
    assert found == RuleConflict(("finance.proposals", "demo.note"))
```

`tests/integration/test_finance_proposal_steps.py` (6 tests)

```python
import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.events import EventKind
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.policy import DecisionRefused
from conductor.runtime import Runtime, ask, open_runtime, resume

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"
PROPOSAL = {"transaction_id": 101, "category": "Groceries", "reason": "Corner Grocer sells food"}
READ_STEP = {"action": "list_uncategorized", "args": {}}
PROPOSE_STEP = {"action": "propose_category", "args": PROPOSAL}
REPLY = '{"reply": "Proposed."}'


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def scripted(*steps: dict, answer: bool = True) -> ScriptedModel:
    replies = [ScriptedReply("plan", ModelReply(content=json.dumps({"steps": list(steps)})))]
    if answer:
        replies.append(ScriptedReply("answer", ModelReply(content=REPLY)))
    return ScriptedModel(replies)


def decide(runtime: Runtime, approval_id: str, verdict: str, **more: object) -> None:
    decide_approval(
        runtime.store,
        runtime.registry,
        approval_id,
        verdict,
        channel="terminal",
        decided_by="owner",
        **more,
    )


def kinds(runtime: Runtime, run_id: str) -> list[str]:
    return [event.kind for event in runtime.log.read(run_id)]


def payloads(runtime: Runtime, run_id: str, kind: EventKind) -> list[dict]:
    return [event.payload for event in runtime.log.read(run_id) if event.kind == kind]


def test_a_proposal_waits_for_both_approvals_and_then_runs() -> None:
    model = scripted(READ_STEP, PROPOSE_STEP)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        plan = runtime.store.approval(first.approval_id).request
        assert (first.status, plan.stage) == ("waiting", "plan")
        assert [(step.action, step.effect) for step in plan.steps] == [
            ("finance.list_uncategorized", "read"),
            ("finance.propose_category", "propose"),
        ]
        assert EventKind.TOOL_CALL not in kinds(runtime, first.run_id)
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        step = runtime.store.approval(second.approval_id).request
        assert (second.status, step.stage) == ("waiting", "step")
        assert [(item.number, item.action, item.args) for item in step.steps] == [
            (2, "finance.propose_category", PROPOSAL)
        ]
        assert [call["step"] for call in payloads(runtime, first.run_id, EventKind.TOOL_CALL)] == [
            1
        ]
        decide(runtime, second.approval_id, "approve")
        done = resume(runtime, first.run_id)
        results = payloads(runtime, first.run_id, EventKind.TOOL_RESULT)
    assert done == RunState(run_id=first.run_id, status="done", reply="Proposed.")
    assert [request.point for request in model.requests] == ["plan", "answer"]
    proposal = results[1]["output"]["proposal"]
    assert (results[1]["step"], proposal["kind"], proposal["transaction_id"]) == (
        2,
        "category",
        101,
    )


def test_a_rejected_proposal_never_reaches_the_server() -> None:
    model = scripted(PROPOSE_STEP, answer=False)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        decide(runtime, second.approval_id, "reject", note="Not groceries")
        ended = resume(runtime, first.run_id)
        found = kinds(runtime, first.run_id)
    assert (ended.status, ended.note) == ("rejected", "Not groceries")
    assert EventKind.TOOL_CALL not in found
    assert [request.point for request in model.requests] == ["plan"]


def test_an_edited_proposal_sends_the_edited_arguments() -> None:
    edited = {"transaction_id": 102, "category": "Dining", "reason": "A cafe"}
    model = scripted(PROPOSE_STEP)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        decide(runtime, second.approval_id, "edit", edited_args=edited)
        done = resume(runtime, first.run_id)
        calls = payloads(runtime, first.run_id, EventKind.TOOL_CALL)
        results = payloads(runtime, first.run_id, EventKind.TOOL_RESULT)
    assert done.status == "done"
    assert [call["args"] for call in calls] == [edited]
    proposal = results[0]["output"]["proposal"]
    assert (proposal["transaction_id"], proposal["category"], proposal["reason"]) == (
        102,
        "Dining",
        "A cafe",
    )


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        ({"reason": "two\nlines"}, "reason"),
        ({"transaction_id": 0}, "transaction_id"),
        ({"category": "x" * 101}, "category"),
    ],
    ids=["reason-two-lines", "id-0", "category-101"],
)
def test_an_edit_past_a_bound_is_refused_and_the_request_stays_open(change: dict, loc: str) -> None:
    model = scripted(PROPOSE_STEP, answer=False)
    with open_runtime(get_settings(), model=model) as runtime:
        first = ask(runtime, "finance: propose Groceries for transaction 101")
        decide(runtime, first.approval_id, "approve")
        second = resume(runtime, first.run_id)
        with pytest.raises(DecisionRefused) as refused:
            decide(runtime, second.approval_id, "edit", edited_args={**PROPOSAL, **change})
        stored = runtime.store.approval(second.approval_id)
    assert (refused.value.code, [problem.loc for problem in refused.value.problems]) == (
        "invalid_edit",
        [loc],
    )
    assert stored.decision is None
```

## Tests to write

Each with its deciding input:

- In `tests/unit/test_finance_proposals_more.py`:
  - R2: `propose_finding_status` accepts each of the nine `Finding` types with status `ignored` (one parameter case per type).
  - R2: `propose_rule_change` with only `rule_id`, `reason`, and `delete: true` sends `delete` true and the four other optional fields `None`. `propose_category_change` with a `rename_to` of 101 characters is refused.
  - R2: `log_advice` with a `subject` of 101 characters is refused; a `text` of `"Check the bills\nin December."` is sent unchanged.
- In `tests/integration/test_finance_proposals_more.py` (with the fake server, as in the given file):
  - R6: a plan of one `log_advice` step stops at the plan approval and then at the step approval; after both are approved, the run is `done` and its `TOOL_RESULT` output's `advice.text` equals the text sent.
  - R6: a plan of `get_balances` then `propose_category` whose plan approval is rejected ends `rejected`, with no `TOOL_CALL` event at all, not even for the read step.

## Rules for this phase

- **Side effects need approval** (AGENTS.md rule 7). Every new action has effect `propose`, so it waits for both approvals. Nothing in this phase may let a proposal run without them.
- **Synthetic data only.** The saved schemas hold no data, and the fake's results are invented. Never copy anything from `finances/data` or run `fin` in a test.
- **Code decides.** Bounds, defaults, and the rule are code. The model only fills a plan that the grammar holds to these contracts.
- Earlier tests stay unchanged except the four given lines.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 50 = 958 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_finance_proposals.py tests/integration/test_finance_proposal_steps.py --no-cov`, exactly `50 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/domains/finance.py" --fail-under=100`;
- `grep -c "^## Phase 9c: " docs/progress.md` prints `1`, and then `.venv/bin/python scripts/check_reports.py --phase 9c` prints `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "\"(write|implement)\"" -- src/conductor/domains/finance.py`
  - `git grep --untracked -n -E "Projects/finances|finances/(data|\.venv)|bin/fin([^a-z_]|$)" -- tests src`
- `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/runtime.py src/conductor/graph src/conductor/store.py src/conductor/policy.py src/conductor/decisions.py src/conductor/web src/conductor/evals src/conductor/prompts src/conductor/llm src/conductor/planning src/conductor/routing src/conductor/domains/__init__.py src/conductor/domains/demo.py src/conductor/config.py src/conductor/diagnostics.py tests/support.py tests/conftest.py tests/mcp_fake_server.py tests/integration` prints nothing;
- `git diff --stat HEAD -- tests` lists exactly `tests/fake_finances_server.py`, `tests/finances_tools.json`, `tests/unit/test_finance_domain.py`, and `tests/unit/test_finance_more.py` (the new test files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 9c: the finance proposals (YYYY-MM-DD)`, with `Tests: 908 -> <passed> (given 50)`.
