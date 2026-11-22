# Phase 9w: Guard-chain refactors for the complexity limits

## Goal

Six functions that check their input as long chains of `if …: return` or `if …: raise` are brought under the complexity limits Phase 9x will turn on, and none of them answers any differently. Afterwards no function in `src/conductor/reports.py`, `spotcheck.py`, `registry.py`, `cli/common.py` or `routing/route.py` is over the limits. Ruff's selection does not change yet: 9x refactors the other functions over the limits and then adds the rules.

| Function | Today | Over |
|---|---|---|
| `reports.parse_review` | complexity 18, 17 returns, 17 branches | C901, PLR0911, PLR0912 |
| `reports._one_entry` | complexity 12, 10 returns | C901, PLR0911 |
| `registry._check_action` | complexity 13 | C901 |
| `spotcheck.verdict` | 7 returns | PLR0911 |
| `cli.common.state_text` | 7 returns | PLR0911 |
| `routing.route.route_request` | 7 returns | PLR0911 |

The limits are `C901` 10 (McCabe complexity), `PLR0911` 6 returns, `PLR0912` 12 branches and `PLR0915` 50 statements.

Decided with the owner (2026-11-22, for Phase 9r):
- **Complexity joins the gates at Ruff's defaults:** `C901` at 10, and `PLR0911`, `PLR0912` and `PLR0915` at 6, 12 and 50. Argument-count rules stay out.

Decided with the owner (2026-11-22, for this phase):
- **Two slices.** 9w does the six guard-chain functions. 9x does `config.get_settings`, `evals.report.compare_lines`, `web.app.create_app`, `scripts/check.py` `main` and one integration test, and then adds the rules to `pyproject.toml`.
- **The architect refactors the three functions in its own tools** (`.claude/skills/phase-architect/phase_tools.py`) with the 9x spec. The coder never edits `.claude/`.

Decided by the architect, within those answers:
- The coder chooses the shape of each refactor, for example a table of checks walked in order or a private helper per part. The probe judges only behaviour, and the given test only the limits.
- Every public name, signature, message constant and message text stays as it is. New private helpers (`_`-named) are allowed in the same module, and nowhere else.
- The checks keep their order. Where two checks could both fail, the first one in today's order still wins, so each input gets the same `Problem`, exception or text as before.
- `route_request` is left out of the probe. Its model path needs a scripted model, a log and ids. Its twelve tests in `tests/unit/test_route.py` and the critical-module coverage gate cover every branch.

## Read first

- The given files below, in full: they are the contract.
- The six functions, and the private helpers they call: `_at`, `_fullmatch`, `_blank`, `_findings`, `_closing`, `_heading`, `_take`, `_items` in `reports.py`; `_failure`, `_error_line` in `spotcheck.py`.
- `tests/unit/test_reports*.py`, `tests/unit/test_spotcheck.py`, `tests/unit/test_route.py`, and the registry tests (`git grep -l RegistryError -- tests`).
- `docs/testing.md` ("Critical modules"): `reports.py`, `spotcheck.py` and `routing/route.py` are on the list.

## Starting state

Phase 9r is built and verified, and everything is committed at a838223: N is `1614`. **Sections: scripts 30, cli 122, core 1462.** No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/reports.py` | `parse_review` and `_one_entry` refactored (Part 1) |
| `src/conductor/registry.py` | `_check_action` refactored (Part 2) |
| `src/conductor/spotcheck.py` | `verdict` refactored (Part 2) |
| `src/conductor/cli/common.py` | `state_text` refactored (Part 2) |
| `src/conductor/routing/route.py` | `route_request` refactored (Part 2) |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

## Out of scope

- 9x's functions (`config.get_settings`, `evals.report.compare_lines`, `web.app.create_app`, `scripts/check.py` `main`, `test_the_read_begins_before_both_selects_and_closes`) and the architect's tools.
- Any change to `pyproject.toml`: the rules go on in 9x.
- A new module, a new public name, or a changed signature, message or exception type.
- A `noqa` or `pragma: no cover` anywhere.
- Fixing anything the probe shows as odd but unchanged. Behaviour stays as it is, even where it looks wrong.
- New or edited tests. The existing tests must pass unchanged.
- Any change to `scripts/`, `.claude/`, `tests/`, a given file, `AGENTS.md` or the design docs.

## Dependencies

None new.

## Design

### Part 1: the report parsers

`parse_review` reads a fixed header (the heading, blank line, `Verdict`, `Passed`, `Findings`, `Approved deviations`, `For the architect`, blank, `## Findings`, blank), then the findings, then two closing sections. It stops at the first problem. Each header line is one pattern with one message and one line number. A table of those rows, walked in order, is one way to bring it under the limits. The count check (`Findings says …`) and the two verdict checks stay after the findings and before the closing sections.

`_one_entry` reads a heading, then `Tests`, `New public names`, `Changed files`, the `Deviations` items and the `Follow-ups` items, then refuses any non-blank line before the next `## ` heading. Each read returns either a `Problem` or a value and the next index.

### Part 2: the other four

- `_check_action` raises the first of its twelve `RegistryError` messages that applies, in today's order. It adds `action.name` to `seen` after the name and twice checks and before the rest.
- `verdict` maps a pytest exit code and output to `passes`, `fails`, `fails: …`, `error: collection`, `error: …`, `no test ran` or `error: exit N`.
- `state_text` gives the waiting-approval, waiting-escalation, done, rejected (with or without a note), cancelled and stopped texts.
- `route_request` returns the rule route, the empty-request escalation, the conflict escalation, the no-domains escalation, the model's escalation, the no-fit escalation or the model route.

## Facts

Checked on 2026-11-22 with the project's Python 3.12 and Ruff 0.17.2, outside the repository:
- `ruff check --select C901,PLR0911,PLR0912,PLR0915` reports the six functions above in these five files and nothing else in them. 9x's eight findings (five functions) and the architect's three are elsewhere.
- Ruff's defaults are the limits above. The given test passes them with `--config` anyway, so a later `pyproject.toml` setting cannot change what it checks.
- The probe loads each module as it was at a838223 under another name and compares answers. On today's code its five comparisons print `ok`, and its last check (the given test) prints `FAIL`, so the run reaches `FAILURES 1`.
- Reach on today's code: 32 distinct first answers over the 43 reviews and their variants, 9 distinct progress problem messages, 15 distinct verdicts, 13 distinct registry answers, and 7 distinct `state_text` answers. The probe's floors are 15, 8, 6, 12 and 6.
- Five one-line mutations of today's code each turned exactly their own comparison to `FAIL`: a moved line number in `parse_review`, a whitespace-only line taken as blank in `_one_entry`, exit code 5 in `verdict`, swapping the name and twice checks in `_check_action`, and `note is not None` in `state_text`.

## Requirements

### Part 1: the limits

- **R1.** No function in the five Scope files is over `C901` 10, `PLR0911` 6, `PLR0912` 12 or `PLR0915` 50 (the given test).

### Part 2: the same answers

- **R2.** `parse_review` gives the same `(Review | None, problems)` as at a838223 for every review in `docs/reviews/` and their one-change variants (probe check 1).
- **R3.** `parse_progress` gives the same entries and problems as at a838223 for entry pairs from `docs/progress.md` and their one-change variants (probe check 2).
- **R4.** `verdict`, `_check_action` and `state_text` give the same answer, exception or text as at a838223 for every probe input (probe checks 3 to 5).
- **R5.** `route_request` keeps every answer its tests pin: the tests in `tests/unit/test_route.py` pass unchanged.

### Part 3: the rules

- **R6.** The suite collects N + 5 tests and every one passes. Sections: `scripts 30`, `cli 122`, `core 1467`. Every line and branch of `reports.py`, `spotcheck.py` and `routing/route.py` stays covered.
- **R7.** Only the Scope's paths change; given files stay byte-identical. No public name is added or removed. There is no `noqa` or `pragma: no cover` in the five files.

## Given files

Committed with this spec. Do not change them; if a given test fails, the refactor is not finished. Before your change, all 5 given tests fail: each file has a function over the limits.

| File | What it is |
|---|---|
| `tests/unit/test_complexity_limits.py` | R1: Ruff finds no complexity finding in each of the five files (5 tests from 1 function) |
| `docs/verification/probe-09w.py` | the probe, run by its path in Acceptance |

Given test count: **5**.

## Tests to write

None. This phase changes no behaviour. R2 to R7 are checked by the probe, the existing tests, the coverage gate, the protected diffs and the searches.

## Rules for this phase

- A refactor changes no answer. If an existing test or a probe comparison fails, the refactor is wrong. Find the input from the lines the probe prints, and keep today's order of checks.
- When a probe check prints `FAIL`, the lines above it give up to three cases with the old and the new answer.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9w` runs every row and search below in order and prints one line each; compare each with "Must show". The protected rows compare against the commit that added this spec, or against a838223 (the commit before it), so they stay true whether or not the build has been committed.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first core` | last line `All checks passed.`; at least 1619 passed, 0 failed, 0 skipped, 0 xfailed; `Sections:` rows `scripts 30`, `cli 122`, `core 1467`, each 0 failed |
| `.venv/bin/python -m pytest --collect-only -q --no-cov` | last line starts `1619 tests collected` |
| `.venv/bin/python -m pytest tests/unit/test_complexity_limits.py --no-cov -q` | `5 passed` |
| `.venv/bin/python docs/verification/probe-09w.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff $(git log -1 --format=%h -- docs/phases/phase-09w-guard-chain-refactors.md) --stat -- tests/unit/test_complexity_limits.py docs/verification/probe-09w.py` | no output |
| `git diff a838223 --stat -- src scripts tests pyproject.toml .claude ':!src/conductor/reports.py' ':!src/conductor/registry.py' ':!src/conductor/spotcheck.py' ':!src/conductor/cli/common.py' ':!src/conductor/routing/route.py' ':!tests/unit/test_complexity_limits.py' ':!.claude/skills/phase-architect/history.md' ':!.claude/skills/phase-architect/phase_status.py'` | no output |
| `git status --short --untracked-files=all` | only the Scope paths (nothing, if the build is committed) |
| `grep -c '^## Phase 9w: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9w` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/web.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/reports.py src/conductor/registry.py src/conductor/spotcheck.py src/conductor/cli/common.py src/conductor/routing/route.py
```

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `Guard-chain refactors for the complexity limits`, with `--tests-before 1614 --given 5`.
