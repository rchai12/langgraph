# Verify Phase 9l: Finance catalog split

Spec: `docs/phases/phase-09l-finance-catalog-split.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09l-finance-catalog-split.md`.

## First: establish that the coder ran

- No `## Phase 9l: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09l-finance-catalog-split.md docs/verification/phase-09l-finance-catalog-split.md tests/unit/test_finance_catalog.py docs/verification/probe-09l.py` must succeed: the gates judge against a committed baseline.

The coder:
- removed `src/conductor/domains/finance.py` and wrote the package `src/conductor/domains/finance/` (`__init__.py`, `common.py`, `reads.py`, `proposals.py`) from its content;
- kept the twelve names in `__all__` importable from `conductor.domains.finance`;
- pointed the package docstring to the checklist in `docs/architecture.md`.

## 1. Gates

N is `1381`. Given count: 21. `.venv/bin/python scripts/accept.py --phase 9l --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1402 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/domains/finance/*' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_finance_catalog.py --no-cov -q` | `21 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09l.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/unit/test_finance_catalog.py docs/verification/probe-09l.py tests/fake_finances_server.py tests/finances_tools.json src/conductor/domains/__init__.py src/conductor/domains/demo.py src/conductor/registry.py src/conductor/planning src/conductor/mcp_client evals` | no output |
| G6 | `git diff 02162d5 --stat -- tests ':!tests/unit/test_finance_catalog.py' ':!tests/unit/test_finance_catalog_more.py'` | no output |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9l: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9l` | `Reports OK.` |

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_finance_is_a_package_of_three_modules`; probe check 1 | pass; `ok` |
| R2 | `test_each_half_holds_its_own_actions`; `tests/unit/test_finance_proposals.py::test_eleven_proposal_actions_after_the_reads` (in G1) | pass |
| R3 | `test_a_half_defines_exactly_the_contracts_of_its_actions` (2 cases), `test_the_package_defines_no_contract` | pass |
| R4 | `test_common_holds_only_what_both_halves_share` | pass |
| R5 | `test_each_module_imports_only_the_layer_below` (3 cases); search 9 | pass; silent |
| R6 | `test_a_name_in_use_today_still_imports_from_finance` (12 cases); read `__all__` in `__init__.py` | pass; the twelve names in the spec's order |
| R7 | probe check 2; `tests/unit/test_finance_domain.py` and `tests/unit/test_finance_proposals.py` (in G1) | `ok`; pass |
| R8 | probe check 3; the bound tests of both finance test files (in G1); the coder's submodule bound test | `ok`; pass |
| R9 | `tests/integration/test_finance_steps.py::test_the_fake_lists_the_real_read_tools` and the other finance tests (in G1); the coder's `plan_fields` test; G5 | pass; no output |
| R10 | G2, G5, G6, G7; searches 7 and 8 | as given; silent |

The coder's test file covers each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09l.py` (G4). Its oracle is the predecessor's `domains/finance.py`, read from commit 02162d5 with `git show` and loaded as a separate module. It checks:
- the layout: `finance` is a package, and its `READS`, `PROPOSALS` and `SERVER` are the objects of `reads`, `proposals` and `common`;
- the catalog: every action's name, description, kind, target, effect, server, contract class names and JSON schemas, in order, plus `RULES`, `SERVER` and the domain's name, description and servers, equal the predecessor's;
- 2000 random arguments (a valid base for the action with one field changed or dropped, from a pool of boundary and wrong-type values): each is sent with the same values, or refused with the same problems, by the new contract and the predecessor's; at least 250 of each.

Before handover the architect ran it on the predecessor: the layout check printed `FAIL` and the other two `ok`, since both sides were the same file. So a catalog or argument check that fails on the build points at a changed action, bound or default.

A stop at its own `assert` lines, or a `git show` failure, is the probe's fault (or a missing commit): report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names.

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

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09l`, then copy in the uncommitted Scope files, delete `src/conductor/domains/finance.py` there, and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09l`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (module) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | move `class NoArgs` from `reads.py` to `common.py` (and import it in `reads.py`) | `tests/unit/test_finance_catalog.py::test_common_holds_only_what_both_halves_share` | `set()` | `{'NoArgs'}` |
| S2 | `proposals.py` imports `Label` from `conductor.domains.finance.reads` instead of `common` | `tests/unit/test_finance_catalog.py::test_each_module_imports_only_the_layer_below[proposals]` | no extra module | `'conductor.domains.finance.reads'` |
| S3 | `ACTIONS = (*PROPOSALS, *READS)` (`__init__.py`) | `tests/unit/test_finance_catalog.py::test_each_half_holds_its_own_actions` | first action `list_accounts` | first action `propose_category` |
| S4 | drop `FindingProposalArgs` from the package's import and `__all__` (`__init__.py`) | `tests/unit/test_finance_catalog.py::test_a_name_in_use_today_still_imports_from_finance[FindingProposalArgs]` | the same class | `AttributeError` |
| S5 | add an unused `class SpareArgs(Contract): pass` to `reads.py` | `tests/unit/test_finance_catalog.py::test_a_half_defines_exactly_the_contracts_of_its_actions[reads]` | 35 names | `'SpareArgs'` extra |

Notes for tracing. S1: `classes(common)` reads `common.py`'s top-level class definitions, so the moved class shows there even though `reads` still uses it. S2: `reads.py` itself imports `Label`, so the import works at run time; only the layer rule sees it. S3: the identity checks and lengths come first and still pass; the `ACTIONS` comparison is the first to fail. S4: `getattr(finance, "FindingProposalArgs")` raises. S5: the class is defined but no action uses it. Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- The six proposal models imported into `__init__.py` in one statement or several.
- `reads.py` and `proposals.py` importing `Contract`, `JsonObject` and `Action` directly as today.
- A blank line or comment heading between groups of contracts in a half.
- Extra behaviour tests in `tests/unit/test_finance_catalog_more.py`.

## 7. Out of scope

Each must be absent:
- Any changed action, description, kind, target, effect, server, contract name, bound, default, rule, domain text or order.
- A new, removed or renamed tool; a contract built from a schema.
- Any change to `tests/fake_finances_server.py`, `tests/finances_tools.json`, `domains/__init__.py`, `domains/demo.py`, `registry.py`, `planning/`, `mcp_client/` or the eval cases.
- Re-exports beyond the twelve names, or a compatibility `domains/finance.py`.
- Any change to a given file, `AGENTS.md`, the design docs or an existing test.

## 8. Verdict

Write `docs/reviews/phase-09l-finance-catalog-split.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9l`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9l` must print `Reports OK.`
