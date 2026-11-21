# Phase 9l: Finance catalog split

## Goal

`src/conductor/domains/finance.py` is 552 lines: the shared field types, 35 read contracts and 20 read actions, 12 proposal contracts and 11 proposal actions, the rules and the domain. Every new `finances` tool lands in that one file. This phase turns it into a package of three modules plus the package itself: shared types, reads and proposals. No action, description, bound, schema, rule or order changes, and no tool is added. The models stay hand-written, and the fake server and the captured schemas stay separate, independent checks.

Decided with the owner (2026-11-20):
- **Layout.** `domains/finance/` is a package: `__init__.py` (the domain), `common.py` (what both halves share), `reads.py` (the read contracts and `READS`), `proposals.py` (the proposal contracts and `PROPOSALS`). `from conductor.domains import finance` keeps working, and `domains/finance.py` is gone.
- **Old imports.** The names code imports from `conductor.domains.finance` today stay importable from it: `DOMAIN`, `ACTIONS`, `RULES`, `SERVER`, `READS`, `PROPOSALS`, `NoteArgs`, `NoteResult`, `ProposalResult`, `CategoryChangeProposalArgs`, `RuleChangeProposalArgs`, `FindingProposalArgs`. Any other model is reached as `finance.reads.X` or `finance.proposals.X`. No existing test changes, and a new tool touches only its own module.
- **The update checklist.** The steps for adding a `finances` tool (its contract and action, the fake server, the captured schemas) are written in `docs/architecture.md`, beside the finance domain. The architect writes them with this spec; the package docstring points there.

Decided by the architect, within those answers:
- `common.py` holds exactly `SERVER`, `Month` and `Label`, the only names both halves use. A field type used by one half lives in that half: `Rows`, `Names`, `Kind` and `By` in `reads.py`; `Id`, `Reason`, `Name`, `Match`, `Priority` and `Finding` in `proposals.py`. `NoArgs` is a read contract.
- Layers: `common.py` imports only `conductor.contracts.base` and `conductor.registry` from the project; `reads.py` and `proposals.py` import those and `conductor.domains.finance.common`, never each other or the package. `__init__.py` imports the three. No import cycle.
- `__init__.py` declares `__all__` with the twelve names, so `ruff` accepts the re-exports without `noqa`. It defines no contract.
- The helpers move with their half: `_read` to `reads.py`, `_propose` to `proposals.py`.

## Read first

- The given files below, in full: they are the contract.
- `src/conductor/domains/finance.py` (all of it) and `src/conductor/domains/__init__.py` (how finance is registered).
- `tests/unit/test_finance_domain.py`, `tests/unit/test_finance_proposals.py` and `tests/integration/test_finance_steps.py`: they compare the actions, the fake server and `tests/finances_tools.json`, and must keep passing unchanged.

## Starting state

Phase 9k is built and verified, and everything is committed: N is `1381`. **Sections: core.** `domains/finance.py` is one module; the package does not exist. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/domains/finance.py` | removed: its content moves into the package |
| `src/conductor/domains/finance/__init__.py` | new: `ACTIONS`, `RULES`, `DOMAIN`, the re-exports and `__all__` (Part 1) |
| `src/conductor/domains/finance/common.py` | new: `SERVER`, `Month`, `Label` (Part 1) |
| `src/conductor/domains/finance/reads.py` | new: the read field types, contracts, `_read` and `READS` (Part 1) |
| `src/conductor/domains/finance/proposals.py` | new: the proposal field types, contracts, `_propose` and `PROPOSALS` (Part 1) |
| `tests/unit/test_finance_catalog_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change. No existing test changes.

## Out of scope

- Any change to an action's name, description, kind, target, effect, server, args or result contract, to a field's bounds or default, to a contract's class name, to `RULES`, to `DOMAIN`, or to the order of `READS`, `PROPOSALS` or `ACTIONS`.
- Adding, removing or renaming a tool; generating contracts from `tests/finances_tools.json` or from the server's schemas (`create_model` and the like).
- Any change to `tests/fake_finances_server.py`, `tests/finances_tools.json`, `domains/__init__.py`, `domains/demo.py`, `registry.py`, `planning/`, `mcp_client/` or the eval cases.
- Re-exporting any model beyond the twelve names, or a compatibility module at `domains/finance.py`.
- Splitting the fake server or the finance tests.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## Dependencies

None new.

## Design

### Part 1: the package

```
src/conductor/domains/finance/
    __init__.py    the docstring, ACTIONS, RULES, DOMAIN, the re-exports, __all__
    common.py      SERVER, Month, Label
    reads.py       Rows, Names, Kind, By, the 35 read contracts, _read, READS
    proposals.py   Id, Reason, Name, Match, Priority, Finding, the 12 proposal contracts, _propose, PROPOSALS
```

- Each definition moves unchanged, as plain top-level assignments and classes, in today's order within its module. `READS` and `PROPOSALS` keep today's actions in today's order.
- `__init__.py` keeps today's docstring, adds one sentence pointing to the checklist in `docs/architecture.md`, and defines `ACTIONS = (*READS, *PROPOSALS)`, `RULES` and `DOMAIN` as today. It imports `SERVER` from `common`, `READS` from `reads`, and `PROPOSALS` and the six proposal models from `proposals`, and sets:

```python
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
```

- Imports are absolute (`from conductor.domains.finance.common import SERVER, Label, Month`), never relative or `*`.

After this, the package defines no contract outside `reads.py` and `proposals.py`, `common.py` defines only its three names, and no domain module builds a contract from a schema (searches in Acceptance).

### Part 2: the checklist

Written by the architect in `docs/architecture.md` ("Adding a finances tool"). The coder only points to it from the package docstring.

## Facts

Checked on 2026-11-20 with the project's Python 3.12.16 and pydantic 2, on today's code:
- Outside `finance.py`, code imports only the twelve names above from it: `domains/__init__.py` imports `DOMAIN`; tests use `DOMAIN`, `SERVER`, `READS`, `PROPOSALS`, `ACTIONS` and the six proposal models. The `finance.Ledger` strings in `test_mcp_declarations*.py` are server-name text, not imports.
- Of the twelve field types, only `Month` and `Label` are used by both halves. No contract is shared: the 35 read contracts serve only reads, and the 12 proposal contracts only proposals. Every contract is used by an action.
- A package directory and a module of the same name cannot both serve `conductor.domains.finance`; the package wins, so `finance.py` must be removed, not kept beside it.
- The probe loads the predecessor's `finance.py` from commit 02162d5 with `git show` and compares it with the code under test. On today's code its catalog and argument checks print `ok` (the two copies are the same file), and its layout check fails.

## Requirements

### Part 1: the package

- **R1.** `conductor.domains.finance` is a package of `__init__.py`, `common.py`, `reads.py` and `proposals.py`, and `domains/finance.py` does not exist.
- **R2.** `reads.READS` and `proposals.PROPOSALS` are the package's `READS` and `PROPOSALS`, with 20 and 11 actions; `ACTIONS` is `(*READS, *PROPOSALS)` and is `DOMAIN.actions`.
- **R3.** Each half defines exactly the contracts its actions use, and every one of its actions' contracts is defined there. The package defines no contract.
- **R4.** `common.py` defines `SERVER`, `Month` and `Label` and nothing else.
- **R5.** `common.py` imports only `conductor.contracts.base` and `conductor.registry` from the project; `reads.py` and `proposals.py` import only those and `conductor.domains.finance.common`.
- **R6.** The twelve names in `__all__` import from `conductor.domains.finance` and are the objects defined in their home module.

### Part 2: the same catalog

- **R7.** Every action's name, description, kind, target, effect, server, contract names and JSON schemas, `RULES`, `SERVER` and the domain's name, description and servers are as before, in the same order.
- **R8.** Every argument a contract sent before is sent with the same values, and every argument it refused is refused with the same problems.
- **R9.** The existing finance tests, the fake server and the captured schemas pass unchanged, and the planner's list of finance actions is unchanged.

### Part 3: the rules

- **R10.** Only the Scope's paths change, given files and existing tests stay byte-identical, no `noqa` or `pragma: no cover` is in the package, and the package is covered 100% (lines and branches).

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `test_finance_catalog.py` fails to import (`cannot import name 'common'`). With names-only stubs in a package of empty modules, 14 tests fail and 7 pass: the layout test, the three import-rule cases and the three in-use cases for `DOMAIN`, `ACTIONS` and `RULES`. They are guards: an empty module imports nothing, and those three names are already defined where they belong.

| File | What it is |
|---|---|
| `tests/unit/test_finance_catalog.py` | R1 to R6: the layout, the halves, their contracts, the shared module, the import layers and the names in use (21 tests from 7 functions) |
| `docs/verification/probe-09l.py` | the probe, run by its path in Acceptance |

Given test count: **21**.

## Tests to write

In `tests/unit/test_finance_catalog_more.py` (section `core`):
- R9: `plan_fields(finance.DOMAIN)["actions"]` has 31 lines, one per action in `ACTIONS` order, the first starting `- list_accounts: ` and the last `- log_advice: `.
- R8: `finance.reads.TransactionsArgs` sends a `limit` of 40 and refuses 41, and `finance.proposals.NoteArgs` refuses a `subject` of 101 characters, reached through the submodules rather than the package.
- R10: any branch of the package that the given and existing tests leave uncovered, tested for what it does.

## Rules for this phase

- Contracts stay hand-written. Never build one from a captured or listed schema.
- A `propose` action still waits for its approval: no action's effect changes.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9l` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1402 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/domains/finance/*' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_finance_catalog.py --no-cov -q` | `21 passed` |
| `.venv/bin/python docs/verification/probe-09l.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/unit/test_finance_catalog.py docs/verification/probe-09l.py tests/fake_finances_server.py tests/finances_tools.json src/conductor/domains/__init__.py src/conductor/domains/demo.py src/conductor/registry.py src/conductor/planning src/conductor/mcp_client evals` | no output |
| `git diff 02162d5 --stat -- tests ':!tests/unit/test_finance_catalog.py' ':!tests/unit/test_finance_catalog_more.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9l: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9l` (after writing progress) | `Reports OK.` |

The second diff row compares against 02162d5 (the commit before this spec), excluding the given and the coder's test files, so it does not depend on what the owner commits between passes.

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/domains/finance
git grep --untracked -n -E 'create_model\(|finances_tools|model_validate_json\(.*schema|json_schema_to' -- src/conductor/domains
git grep --untracked -n -E '^from \.|import \*' -- src/conductor/domains/finance
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Finance catalog split`, with `--tests-before 1381 --given 21`.
