# Verify Phase 9g: One bounded Ollama model listing

Spec: `docs/phases/phase-09g-bounded-model-listing.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict. Write only `docs/reviews/phase-09g-bounded-model-listing.md`.

## First: establish that the coder ran

- No `## Phase 9g: ` entry in `docs/progress.md` and no Scope path changed: the coder did not run. Report it to the owner and write no review.
- An entry whose first Follow-ups item starts `Stopped:`: write the FAIL review the conventions describe, run the given tests once for `Passed`, and stop.
- `git ls-files --error-unmatch docs/phases/phase-09g-bounded-model-listing.md docs/verification/phase-09g-bounded-model-listing.md tests/raw_http.py tests/unit/test_tags_parse.py tests/unit/test_ollama_bounded.py tests/e2e/test_cli_doctor_agrees.py docs/verification/probe-09g.py` must succeed: the gates judge against a committed baseline.

The coder:
- changed `src/conductor/llm/tags.py`: the constants, `TooLarge`, `Listed`, `parse_tags`, `find_model`, `read_capped`, a capped `fetch_models`;
- changed `src/conductor/llm/ollama.py` to read through `read_capped`, map `TooLarge` to `too_large`, and find the model through `parse_tags` and `find_model`, removing its own listing parser; added `"too_large"` to `UnavailableCode` in `src/conductor/llm/model.py`;
- changed `check_ollama` in `src/conductor/diagnostics.py` to use `find_model` and print a line per problem;
- made the six one-line edits to four existing test files that the spec lists, and added `tests/unit/test_tags_more.py` and one progress entry.

## 1. Gates

N is `1184`. Given count: 34. `.venv/bin/python scripts/accept.py --phase 9g --guide` runs every gate and search in order and prints one line each; compare each with "Must show".

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1218 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='*/conductor/llm/tags.py,*/conductor/llm/ollama.py,*/conductor/diagnostics.py' --fail-under=100` | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_tags_parse.py tests/unit/test_ollama_bounded.py tests/e2e/test_cli_doctor_agrees.py --no-cov -q` | `34 passed` |
| G4 | `.venv/bin/python docs/verification/probe-09g.py` | every check line starts `ok`; last line `FAILURES 0` |
| G5 | `git diff HEAD --stat -- tests/raw_http.py tests/unit/test_tags_parse.py tests/unit/test_ollama_bounded.py tests/e2e/test_cli_doctor_agrees.py docs/verification/probe-09g.py src/conductor/config.py src/conductor/llm/decide.py src/conductor/llm/points.py` | no output |
| G6 | `git diff HEAD --numstat -- tests/unit/test_ollama.py tests/unit/test_ollama_more.py tests/e2e/test_cli_doctor.py tests/unit/test_diagnostics_more.py` | exactly four lines, tab-separated: `1 1 tests/e2e/test_cli_doctor.py`, `5 1 tests/unit/test_diagnostics_more.py`, `2 2 tests/unit/test_ollama.py`, `2 2 tests/unit/test_ollama_more.py` (added, removed, path) |
| G7 | `git status --short --untracked-files=all` | only the Scope paths |
| G8 | `grep -c '^## Phase 9g: ' docs/progress.md` | `1` |
| G9 | `.venv/bin/python scripts/check_reports.py --phase 9g` | `Reports OK.` |

G6 counts lines only. Read `git diff HEAD` on those four files too: each changed line must be exactly the spec's new text ("Edits to existing tests"), and nothing else in the file may change. Any other change is a finding against R11.

## 2. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_limits_and_messages` | passes |
| R2 | `test_an_answer_that_is_not_a_listing` (3 cases) | pass |
| R3 | `test_an_entry_without_a_usable_name_is_skipped` (3 cases), `test_a_listing_keeps_its_order_and_sorts_capabilities`; the coder's empty-name test | pass |
| R4 | `test_each_entry_is_judged_alone` (5 cases); probe check 1 | pass; `ok` |
| R5 | `test_a_repeated_name_is_refused`; probe check 1 | pass; `ok` |
| R6 | `test_finding_the_configured_model` (3 cases); probe check 1 | pass; `ok` |
| R7 | `test_a_read_stops_one_byte_past_the_limit` (2 cases), `test_doctor_survives_a_broken_chunked_answer`, `test_each_caller_keeps_its_own_timeout`; the coder's `fetch_models` tests; read `fetch_models` | pass; `read_capped` is the only read, and `HTTPException` maps to `UNEXPECTED_MESSAGE` |
| R8 | `test_an_answer_over_the_cap_is_too_large` (3 cases), `test_an_answer_of_exactly_the_cap_is_read`; probe checks 2 and 3 | pass; `ok` |
| R9 | `test_an_unrelated_bad_entry_does_not_hide_the_model`, `test_a_bad_entry_for_the_model_is_a_bad_answer` (2 cases), `test_each_caller_keeps_its_own_timeout`; probe check 1 | pass; `ok` |
| R10 | `test_doctor_and_a_run_agree_on_the_model` (5 cases), `test_doctor_names_an_answer_too_large`, `test_doctor_survives_a_broken_chunked_answer`; probe checks 1 and 4 | pass; `ok` |
| R11 | G5, G6, G7, the searches; read the four edited tests' diffs | as given |
| R12 | G2 | as given |

The coder's test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet; a missing one is a finding.

## 3. Probe

The probe is the given file `docs/verification/probe-09g.py` (G4). It checks:
- 150 random listings, each a valid base with at most one change (a junk entry, a bad digest, bad capabilities, a repeated name, a tag change, a missing model), against its own tables: `parse_tags`, `find_model`, `OllamaModel.model_info` and doctor's `check_ollama` lines must all match. Each outcome (`ok`, `bad_answer`, `not_installed`) is reached at least 10 times;
- a 64 MiB answer to tags and to chat is `too_large`, and the server sends less than 16 MiB before the client stops;
- a run against lying lengths: a length larger than the body (`ok`), `Content-Length: 5` (`bad_answer`), a larger length on an oversized body (`too_large`), a chunked body of 1 MiB plus one byte (`too_large`), exactly 1 MiB (`ok`);
- doctor against a broken chunked answer (`unexpected answer`), an oversized body and an oversized body with a larger length (`answer too large`).

A stop at its own `assert` lines, before its first check prints, is the probe's fault: report it under "For the architect", not as a finding.

## 4. Searches

Each prints nothing. A match is a finding against the rule it names. The last two find a second listing parser or an unbounded read outside `tags.py` (R11).

```sh
git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)|urllib\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'
git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model|BaseChatModel|bedrock|vertexai' -- src pyproject.toml
git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src ':!src/conductor/llm'
git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\.Client' -- src pyproject.toml
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid\.uuid[0-9]|from conductor\.(clock|ids) import' -- src ':!src/conductor/clock.py' ':!src/conductor/ids.py'
git grep --untracked -n -E 'print\(' -- src ':!src/conductor/cli'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/conductor/llm/tags.py src/conductor/llm/ollama.py src/conductor/diagnostics.py
git grep --untracked -n -E '_DIGEST|"models"|:latest|\.read\(\)' -- src ':!src/conductor/llm/tags.py'
git grep --untracked -n -E '\.read\((-1)?\)' -- src/conductor/llm
```

## 5. Spot checks

Make a scratch copy of the reviewed bytes (`git clone -q . <scratch>/spot09g`, then copy in the uncommitted Scope files and link `.venv`). For each row, write the change as exact old and new text in the coder's code (one match), and run `.venv/bin/python scripts/spot_check.py <module> --old '<old>' --new '<new>' --test '<deciding test>' --row S<n> --root <scratch>/spot09g`. It runs the test unchanged (it must pass), applies the one exact change, runs it again, restores the bytes, and prints one line. Rerun by hand with `-vv` only when that line is not the "Broken" value.

A different failure from "Broken" is a note for the architect; a pass is a finding unless you trace it to a test that cannot see the change (say which in "For the architect").

| # | Change (function) | Deciding test (full node id) | Correct | Broken |
|---|---|---|---|---|
| S1 | raise `OllamaBadAnswer` for an entry that is not an object, instead of skipping it (`parse_tags`) | `tests/unit/test_tags_parse.py::test_an_entry_without_a_usable_name_is_skipped[text]` | `{'plain:latest': …}` | `OllamaBadAnswer` raised |
| S2 | ignore a repeated name, keeping the first entry as it was (`parse_tags`) | `tests/unit/test_tags_parse.py::test_a_repeated_name_is_refused` | problem `'duplicate'` | `Listed('m:1', 'aaa…', (), None)` |
| S3 | let the digest pattern accept uppercase, `[0-9a-fA-F]` (`parse_tags`) | `tests/unit/test_tags_parse.py::test_each_entry_is_judged_alone[upper]` | problem `'no_digest'` | digest `'AAA…'`, problem `None` |
| S4 | check capabilities before the digest (`parse_tags`) | `tests/unit/test_tags_parse.py::test_each_entry_is_judged_alone[both]` | `'no_digest'` | `'bad_capabilities'` |
| S5 | try `{name}:latest` before the exact name (`find_model`) | `tests/unit/test_tags_parse.py::test_finding_the_configured_model[exact]` | `'plain'` | `'plain:latest'` |
| S6 | read `limit` bytes instead of `limit + 1` (`read_capped`) | `tests/unit/test_tags_parse.py::test_a_read_stops_one_byte_past_the_limit[11-False]` | `TooLarge` raised | no `TooLarge` (10 bytes returned) |
| S7 | refuse at `>= limit` instead of `> limit` (`read_capped`) | `tests/unit/test_tags_parse.py::test_a_read_stops_one_byte_past_the_limit[10-True]` | 10 bytes returned | `TooLarge` raised |
| S8 | map `TooLarge` to `bad_answer` (`OllamaModel._read`) | `tests/unit/test_ollama_bounded.py::test_an_answer_over_the_cap_is_too_large[chat]` | `'too_large'` | `'bad_answer'` |
| S9 | ignore the found entry's `problem` (`OllamaModel.model_info`) | `tests/unit/test_ollama_bounded.py::test_a_bad_entry_for_the_model_is_a_bad_answer[caps-text]` | `bad_answer` raised | no `ModelUnavailable` (a `ModelInfo` returned) |
| S10 | stop catching `HTTPException` (`fetch_models`) | `tests/e2e/test_cli_doctor_agrees.py::test_doctor_survives_a_broken_chunked_answer` | the three lines | `[]` |
| S11 | look the model up as `{model}:latest` only, as today (`check_ollama`) | `tests/e2e/test_cli_doctor_agrees.py::test_doctor_and_a_run_agree_on_the_model[untagged]` | `ok    model plain: digest aaaaaaaaaaaa` | `FAIL  model plain: not pulled (run: ollama pull plain)` |

Notes for tracing. S2: with the first entry kept, the dict is `{'m:1': Listed('m:1', 'a'*64, (), None), 'plain:latest': …}`, and the order assertion is never reached. S4: the entry has digest `1` and capabilities `"x"`, so only the order of the two checks decides. S6: the `Strict` reader returns the first 10 of 11 bytes, which fit. S7: `[10-True]` reads 10 bytes from a body of 10, and `10 >= 10` refuses it. S8 is written against whatever handler the coder gives `TooLarge` in `_read`: the change is the code it raises. S9: the entry's digest is valid, so the run would get `ModelInfo('plain:latest', 'aaa…', ())`. S10: the doctor raises `IncompleteRead` before it prints anything, so stdout is empty and `splitlines()[2:]` is `[]`. S11: the listing holds `plain`, not `plain:latest`. If the coder's doctor already reaches `find_model` through another name, write the change at the call instead. Spot rows that do the same thing in a different place are notes, not findings.

## 6. Reasonable variations

These are correct even though the spec does not spell them out:
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.
- `Problem` as a module-level alias or written inline in `Listed`'s annotation.
- `parse_tags` tracking repeated names with a set or by checking the dict, as long as a third repeat stays `duplicate` and the first place is kept.
- `_read` mapping `TooLarge` in its own `except` clause placed anywhere before a clause that would catch it, or catching it around the `read_capped` call.
- `check_ollama` mapping problems to text with a dict or a chain of conditions.
- `fetch_models` catching `HTTPError` and `HTTPException` in one clause or two, as long as `HTTPError` is caught before `OSError`.

## 7. Out of scope

Each must be absent:
- a setting for either cap, or any change to `config.py`, `docs/configuration.md` or the doctor's timeout;
- any change to chat-reply parsing (`_reply`, `_thinking`, `_counts`) beyond the capped read;
- streaming, retries, or reading an answer in pieces to report its size;
- logging or printing any part of an answer, a skipped entry or another model's name;
- durable failure evidence, a changed escalation text, or any change to `decide.py` or `escalation_for`;
- any change to a given file, `AGENTS.md` or the design docs, or to an existing test beyond the spec's "Edits to existing tests".

## 8. Verdict

Write `docs/reviews/phase-09g-bounded-model-listing.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 9g`), with a digest: one line per gate, one per spot check, `searches: silent`. Then `.venv/bin/python scripts/check_reports.py --phase 9g` must print `Reports OK.`
