# Phase 9b: the finance read actions

## Goal

The finance domain, `conductor.domains.finance`: the 20 read tools of the `finances` MCP server (`fin mcp serve`) as 20 `read` actions, with arguments bounded so their results fit the answer's 24000-byte bound, result contracts that name each tool's top-level fields, and keyword rules. It is registered only when its server command is set, and its plans get a larger context.

Decided with the owner (2026-11-10):
- Finance is **registered only when `CONDUCTOR_MCP__FINANCES` is set**. There is no new setting, so a machine without `finances` (and every earlier test) runs as before.
- **Result contracts name the top-level fields**: scalars are typed, and lists and objects are plain JSON. So `finances` can add a field inside a transaction without stopping runs.
- **Argument limits are tighter than the server's**, sized to the answer bound (for example at most 40 transactions, 20 by default). Results are never cut; a larger one still escalates as `answer_too_large` (9a).
- **A short list of finance-only keyword rules.**

Decided by the architect, within those answers:
- The actions are named after their tools.
- The domain module is given whole, because its descriptions are prompt text that 9d will tune.
- The server passes `FIN_DATA_DIR` through, because `fin` finds its database relative to the folder it starts in.
- Tests use a fake server with the real tools' signatures, checked against a saved copy of the real schemas.
- The plan point gets 16384 context tokens for every domain (see Facts).
- `conductor doctor` gets no new line when finance is off. Its output is pinned whole by many earlier tests, and with the command set it already prints `server finances`.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Domains and actions", "MCP")
- `src/conductor/domains/__init__.py`, `src/conductor/domains/demo.py`, `src/conductor/registry.py`, `src/conductor/planning/plan.py` (`plan_point`), `src/conductor/mcp_client/check.py`, `src/conductor/runtime.py` (`McpRunner`, which keeps only the result fields the contract names), `tests/integration/test_mcp_steps.py` (how a test starts a fake server)

## Starting state

Phase 9a is built and verified, and everything is committed: N is `859`. **Sections: cli, core.** No `conductor.domains.finance` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/domains/finance.py` | given (Part 1) |
| `src/conductor/domains/__init__.py` | `registered` adds finance when its command is set (Part 1) |
| `src/conductor/planning/plan.py` | `PLAN_CONTEXT_TOKENS` and the plan point's context (Part 2) |
| `tests/finances_tools.json`, `tests/fake_finances_server.py` | given (Part 3) |
| `tests/unit/test_finance_domain.py`, `tests/integration/test_finance_steps.py` | given |
| `tests/unit/test_finance_more.py`, `tests/integration/test_finance_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- The proposal tools and `log_advice` as actions (9c); finance evaluation cases and prompt tuning (9d).
- Any change to the tool check, `McpRunner`, the MCP client, the graph, the runtime, the store, the web pages, the evaluation harness, the templates, or the answer bound.
- A doctor line for a domain that is off; a setting to turn finance on other than its command; cutting or summarising results.
- Running the real `fin` in any test or probe.

## Dependencies

None new.

## Design

### Part 1: the domain

`src/conductor/domains/finance.py` is given below; copy it exactly. It declares `SERVER = McpServer("finances", ("FIN_DATA_DIR",))` and the 20 actions in the server's own listing order. Each action is a `tool` action with effect `read` on server `finances`, and its target is its own name. It also declares six rules and `DOMAIN`.

`domains.registered(settings)` returns `DOMAINS`, then `finance.DOMAIN` when `settings.mcp_command("finances") is not None`, then `demo.DOMAIN` when the demo is on, in that order. `DOMAINS` stays `()`, as an earlier test pins. Settings already refuse an empty command, so a set command always has a program.

When finance is registered, the 6b tool check runs before each runtime's first `ask` or `resume`, as for any domain with a server. So a wrong or missing `fin` refuses runs, and `conductor doctor` names the cause on its `server finances` line.

### Part 2: the plan context

`planning/plan.py` gains `PLAN_CONTEXT_TOKENS = 16384`, and `plan_point` sets `context_tokens=PLAN_CONTEXT_TOKENS` for every domain. Its reply cap stays `PLAN_REPLY_TOKENS` (4096), and the template stays `plan.v2`.

### Part 3: the fake server

`tests/finances_tools.json` is a copy of the real server's 20 read tools: input schema, output schema, and the read-only mark, with no data. `tests/fake_finances_server.py` declares the same 20 tools, with the same signatures, through the same SDK, and returns small invented results of the real shapes. A given test checks that the fake's listing equals the saved copy, so the fake cannot drift from the real schemas without a test failing. No test or probe starts `fin`.

## Facts

From a spike on 2026-11-10. The tool listing ran against the real `fin mcp serve` with an empty data folder, so it read no data. The plans came from the owner's model (`qwen3.8:27b`), given synthetic requests only.

- The real server lists 31 tools. The 20 read tools are marked `readOnlyHint: true`, and each output schema is an open object (`{"type": "object", "additionalProperties": true}`). Both projects use `mcp` 2.3.0, and the fake's listing equals the saved copy exactly.
- The given domain passes the 6b tool check against the real schemas with no problem. A `Literal` field's schema carries `"type": "string"`, and `date | None` gives `null|string`, as the tools' own schemas do.
- `finances` reads `FIN_` settings and an `.env` from the folder it starts in, and its data folder defaults to the relative path `data`. Conductor starts servers without setting a folder, so the owner sets `FIN_DATA_DIR`, which `SERVER` passes through.
- The plan request for the finance domain is a 22899-byte system message, about 6520 prompt tokens. Planning took from 94 to 1084 reply tokens (thinking included) and 2 to 42 seconds. 6520 + 1084 is close to 8192, so the plan point gets 16384.
- Ollama accepted the schema with `format: date` and `pattern`, and every reply validated. Ollama may not enforce `pattern`, but Pydantic does, so a bad month escalates as `invalid_plan` either way.
- With today given (9a), "last month" was planned as `2026-10-01` to `2026-10-31`.

## Requirements

### Part 1: the domain

- **R1.** `src/conductor/domains/finance.py` equals the given file, and `Registry((finance.DOMAIN,))` accepts it.
- **R2.** `registered` adds `finance.DOMAIN` exactly when `CONDUCTOR_MCP__FINANCES` is set, after `DOMAINS` and before the demo, as under Design. `DOMAINS` stays `()`.

### Part 2: the plan context

- **R3.** `PLAN_CONTEXT_TOKENS` is 16384, and every plan request sends `num_ctx` 16384. No other point changes.

### Part 3: the fake server and a run

- **R4.** The given `tests/finances_tools.json` and `tests/fake_finances_server.py` are copied exactly, and the fake lists exactly the saved schemas.
- **R5.** A finance request routed by a rule runs its read steps over the fake server with no approval, and its answer is given the steps' results. This goes through the runtime as it is, with no change to it.

### Part 4: the rules

- **R6.** Only the Scope's paths change. No earlier test changes.
- **R7.** No test or probe starts `fin` or reads anything from the `finances` project. The tests use only the fake and invented data.
- **R8.** `domains/__init__.py`, `domains/finance.py`, and `planning/plan.py` reach 100% of lines and branches.

## Given tests

45 new tests in two files (counting each parameter set), with the given domain, the saved schemas, and the fake server. Do not change them; if one fails, the code is wrong. Before your change, the tests of the given module already pass, and four fail: `test_finance_is_registered_when_its_command_is_set` `[finance]` and `[finance-demo]`, `test_the_plan_point_has_a_larger_context`, and `test_a_finance_request_runs_its_reads_without_asking`.

`src/conductor/domains/finance.py` (given; copy it exactly)

```python
"""The finance domain: the read tools of the finances MCP server (`fin mcp serve`)."""

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


def _read(name: str, description: str, args: type[Contract], result: type[Contract]) -> Action:
    return Action(name, description, "tool", name, "read", args, result, server=SERVER.name)


ACTIONS = (
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

RULES = (
    Rule("spending", ("spending", "spent")),
    Rule("budgets", ("budget", "budgets")),
    Rule("balances", ("balance", "balances", "net worth")),
    Rule("transactions", ("transactions", "uncategorized")),
    Rule("bills", ("bills", "subscriptions", "recurring")),
    Rule("transfers", ("transfers",)),
)

DOMAIN = Domain(
    name="finance",
    description="The household's money in the finances app: accounts, balances, transactions, "
    "spending, budgets, bills, forecasts, and data coverage. Read only.",
    actions=ACTIONS,
    rules=RULES,
    servers=(SERVER,),
)
```

`tests/finances_tools.json` (given; copy it exactly, ending with one newline)

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

`tests/fake_finances_server.py` (given; copy it exactly)

```python
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
```

`tests/unit/test_finance_domain.py` (43 tests)

```python
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
ACTIONS = {action.name: action for action in finance.DOMAIN.actions}


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
    assert list(ACTIONS) == list(REAL)
    assert {
        (action.kind, action.target == action.name, action.effect, action.server)
        for action in finance.DOMAIN.actions
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
```

`tests/integration/test_finance_steps.py` (2 tests)

```python
import json
import shlex
import sys
from pathlib import Path

import pytest

from conductor.config import get_settings
from conductor.domains import finance
from conductor.events import EventKind
from conductor.graph.supervisor import RunState
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.mcp_client.client import McpClient
from conductor.runtime import ask, open_runtime

TESTS = Path(__file__).resolve().parents[1]
FAKE = TESTS / "fake_finances_server.py"


@pytest.fixture(autouse=True)
def fake_finances(monkeypatch: pytest.MonkeyPatch) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", command)
    monkeypatch.setenv("CONDUCTOR_MCP_TIMEOUT", "5")


def test_the_fake_lists_the_real_read_tools() -> None:
    listed = McpClient(finance.SERVER, get_settings()).list_tools()
    found = {
        tool.name: {
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "read_only": tool.read_only,
        }
        for tool in listed
    }
    assert found == json.loads((TESTS / "finances_tools.json").read_text())


def test_a_finance_request_runs_its_reads_without_asking() -> None:
    steps = [
        {
            "action": "get_spending",
            "args": {"start": "2026-10-01", "end": "2026-10-31", "by": "merchant"},
        },
        {"action": "list_transactions", "args": {"merchant": "Corner Grocer", "limit": 5}},
    ]
    model = ScriptedModel(
        [
            ScriptedReply("plan", ModelReply(content=json.dumps({"steps": steps}))),
            ScriptedReply("answer", ModelReply(content='{"reply": "You spent $42.10."}')),
        ]
    )
    with open_runtime(get_settings(), model=model) as runtime:
        assert runtime.registry.names == ("finance",)
        done = ask(runtime, "What have we spent at Corner Grocer in October?")
        assert done == RunState(run_id=done.run_id, status="done", reply="You spent $42.10.")
        events = runtime.log.read(done.run_id)
    kinds = [event.kind for event in events]
    assert EventKind.APPROVAL_REQUESTED not in kinds
    results = [event.payload for event in events if event.kind == EventKind.TOOL_RESULT]
    assert [item["step"] for item in results] == [1, 2]
    assert results[0]["output"]["start"] == "2026-10-01"
    assert results[0]["output"]["by"] == "merchant"
    assert results[1]["output"]["transactions"][0]["merchant"] == "Corner Grocer"
    assert results[1]["output"]["next_offset"] is None
    assert [request.point for request in model.requests] == ["plan", "answer"]
    assert '"action": "finance.list_transactions"' in model.requests[1].user
```

## Tests to write

Each with its deciding input:

- In `tests/unit/test_finance_more.py`:
  - R1: every argument field of every action has a default, except `find_merchants.phrase`, because the planner may leave a field out.
  - R2: with `CONDUCTOR_MCP__FINANCES` naming a program that does not exist (under `tmp_path`), `registered` still includes finance, and `diagnostics.server_lines(settings)` gives one `FAIL` line for `server finances` with the detail `start_failed`.
  - R3: the demo domain's plan point also sends `num_ctx` 16384.
- In `tests/integration/test_finance_more.py`:
  - R5: a request with the `finance:` prefix and one `get_balances` step runs to `done`. The scripted model gets no `route` request, the log has no `APPROVAL_REQUESTED` event, and the step's `TOOL_RESULT` output has `net_worth_cents` 123456.

## Rules for this phase

- **Read actions only.** Every finance action has effect `read`. A write tool is never declared here, so nothing in this phase can change the household's data.
- **Synthetic data only.** The saved schemas hold no data; the fake's results are invented. Never copy anything from `finances/data` or run `fin` in a test.
- **Code decides.** Bounds, defaults, and rules are code; the model only fills a plan the grammar holds to these contracts.
- Earlier tests stay unchanged.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 45 = 904 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_finance_domain.py tests/integration/test_finance_steps.py --no-cov`, exactly `45 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/domains/__init__.py,*/conductor/domains/finance.py,*/conductor/planning/plan.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 9b`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "\"effect\"|, \"(propose|write|implement)\"" -- src/conductor/domains/finance.py`
  - `git grep --untracked -n -E "Projects/finances|finances/(data|\.venv)|bin/fin\b" -- tests src`
- `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/runtime.py src/conductor/graph src/conductor/store.py src/conductor/web src/conductor/evals src/conductor/prompts src/conductor/llm src/conductor/planning/answer.py src/conductor/routing src/conductor/domains/demo.py src/conductor/config.py src/conductor/diagnostics.py tests/support.py tests/conftest.py tests/mcp_fake_server.py` prints nothing;
- `git diff --stat HEAD -- tests` prints nothing (the new test files are untracked).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 9b: the finance read actions (YYYY-MM-DD)`, with `Tests: 859 -> <passed> (given 45)`.
