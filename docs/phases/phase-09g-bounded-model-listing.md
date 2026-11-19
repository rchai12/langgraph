# Phase 9g: One bounded Ollama model listing

## Goal

`conductor doctor` and a run read Ollama's `/api/tags` listing through one parser in `conductor.llm.tags`, so they agree on the configured model. A malformed entry for another model no longer breaks the listing; it is skipped, or marked as a problem on that entry alone. Every read of a tags or chat answer is capped at 1 MiB, also when the answer sends no length or a false one. A run then escalates with the new code `too_large`, and doctor prints `answer too large`. This implements audit findings 2 (inconsistent tags parsing) and 9 (uncapped response reads).

Decided with the owner (2026-11-19):
- **Both reads are capped at 1 MiB (1,048,576 bytes).** A real listing is a few kilobytes. A chat reply is at most 8192 tokens (`MAX_REPLY_TOKENS`), well under 1 MiB even with its reasoning. The cap is a constant, not a setting.
- **An answer over the cap is a new code, `too_large`.** It is not folded into `bad_answer`, so the escalation says what happened. Doctor prints `FAIL  ollama <host>: answer too large`.
- **An entry without a usable name is skipped.** No one can configure a model by a name the listing does not give, so such an entry can hide nothing.
- **A name listed twice makes that model invalid.** The two entries may carry different digests, and the run must not guess which one is installed. A run gets `bad_answer` for it, and doctor prints `listed more than once`. Other models in the listing are unaffected.

Decided by the architect, within those answers:
- One parser, `parse_tags`, returns every named entry as a `Listed` record with its own `problem`, instead of raising for it. Each caller decides what a problem means for the configured model. The whole answer is refused only when it is not a JSON object with a `models` list.
- One lookup, `find_model`, is shared: the exact name first, else `{name}:latest` when the name has no tag. Today's doctor looks only at `{name}:latest`, so it called a model listed as plain `plain` not pulled while a run used it.
- The cap is enforced by one `read(limit + 1)` call (see Facts). A body longer than the limit raises `TooLarge`, a subclass of `OllamaBadAnswer`, so doctor's existing `except` already prints it.
- A broken chunked answer raises `http.client.HTTPException`, which is not an `OSError`. Doctor crashed on it; `fetch_models` now maps it to `unexpected answer`. A run already maps it to `bad_answer`.
- Each caller keeps its timeout: doctor `3.0` seconds (the `fetch_models` default), a run `CONDUCTOR_MODEL_TIMEOUT`. Both keep the proxy-free opener.

## Read first

- The given files below, in full: they are the contract. `tests/raw_http.py` is a helper the given tests and none of the coder's need.
- `src/conductor/llm/tags.py` (all 50 lines), `src/conductor/llm/ollama.py` (`_read`, `_info`, `_entry`, `_capabilities`, `_find`), `src/conductor/llm/model.py` (`UnavailableCode`), and `check_ollama` in `src/conductor/diagnostics.py` (from line 54).
- The existing tests edited in Scope, at the lines named there: `tests/unit/test_ollama.py` (`test_tags_that_do_not_fit`), `tests/unit/test_ollama_more.py` (`test_a_tagged_name_does_not_match_latest_and_bad_tags_are_refused`, `test_answers_outside_the_documented_shape`), `tests/e2e/test_cli_doctor.py` (`test_something_else_answering`), `tests/unit/test_diagnostics_more.py` (`test_a_bad_digest_is_missing_and_a_latest_tag_is_shown`).

## Starting state

Phase 9f is built and verified, and everything is committed: N is `1184`. **Sections: cli, core.** `tags.fetch_models` returns names mapped to digests and raises `OllamaBadAnswer` for the whole listing on any entry without a string name. `ollama.py` has its own stricter copy of the parsing, which refuses the whole listing on any bad entry, and its `_read` calls `response.read()` with no limit. `tags.py` has no cap, `Listed`, `parse_tags`, `find_model` or `read_capped`. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/llm/tags.py` | the constants, `TooLarge`, `Listed`, `parse_tags`, `find_model`, `read_capped`, a capped `fetch_models` (Part 1) |
| `src/conductor/llm/ollama.py` | capped reads, `too_large`, the listing through `parse_tags` and `find_model`; its own listing parser removed (Part 2) |
| `src/conductor/llm/model.py` | `"too_large"` added to `UnavailableCode` (Part 2) |
| `src/conductor/diagnostics.py` | `check_ollama` through `find_model`, with a line per problem (Part 3) |
| `tests/unit/test_ollama.py` | only the two edits in "Edits to existing tests" |
| `tests/unit/test_ollama_more.py` | only the two edits in "Edits to existing tests" |
| `tests/e2e/test_cli_doctor.py` | only the one edit in "Edits to existing tests" |
| `tests/unit/test_diagnostics_more.py` | only the one edit in "Edits to existing tests" |
| `tests/unit/test_tags_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

The given files are already committed; they are not in the Scope and never change.

### Edits to existing tests

Each old line matches exactly once in its file. Change it to the new text and nothing else in that file.

| File | Old line | New line | Why |
|---|---|---|---|
| `tests/unit/test_ollama.py` | `        json.dumps({"models": [{**QWEN, "digest": "4" * 63}]}).encode(),` | `        json.dumps({"models": [{**PLAIN, "digest": "a" * 63}]}).encode(),` | a bad entry for another model no longer refuses the listing; the bad digest moves to the model asked for |
| `tests/unit/test_ollama.py` | `        json.dumps({"models": [PLAIN, {**QWEN, "capabilities": "thinking"}]}).encode(),` | `        json.dumps({"models": [QWEN, {**PLAIN, "capabilities": "thinking"}]}).encode(),` | the same, for bad capabilities |
| `tests/unit/test_ollama_more.py` | `        fake.body = json.dumps({"models": [{"name": 3, "digest": "a" * 64}]}).encode()` | `        fake.body = json.dumps({"models": [PLAIN, PLAIN]}).encode()` | an entry with a number for a name is now skipped; a repeated name is the bad listing instead |
| `tests/unit/test_ollama_more.py` | `            {"models": ["x"]},` | `            {"models": [{"name": "plain:latest"}]},` | an entry that is not an object is now skipped; the model without a digest is the bad listing instead |
| `tests/e2e/test_cli_doctor.py` | `        (200, b'{"models": [{"model": "qwen3.8:27b"}]}'),` | `        (200, b'[{"model": "qwen3.8:27b"}]'),` | a listing whose only entry has no name is now a valid empty listing; an answer that is not an object stays `unexpected answer` |

In `tests/unit/test_diagnostics_more.py`, `fetch_models` now returns `Listed` records. Replace the line

```python
    assert found == {"plain:latest": None, "numbered:latest": None, "upper:latest": None}
```

with exactly these lines:

```python
    assert {name: item.digest for name, item in found.items()} == {
        "plain:latest": None,
        "numbered:latest": None,
        "upper:latest": None,
    }
```

With only these edits and today's code, two of the edited tests fail (`test_a_tagged_name_does_not_match_latest_and_bad_tags_are_refused` and `test_a_bad_digest_is_missing_and_a_latest_tag_is_shown`); after the phase every one passes.

## Out of scope

- A setting for either cap, or any change to `config.py`, `docs/configuration.md` or the doctor's timeout.
- Any change to how a chat reply is parsed (`_reply`, `_thinking`, `_counts`) beyond the capped read.
- Streaming, retries, or reading an answer in pieces to report how large it was.
- Logging or printing any part of an answer, a skipped entry or its name beyond the configured model's.
- Durable failure evidence or a changed escalation text for the run (9h), and any change to `decide.py` or `escalation_for`.
- Any change to a given file, `AGENTS.md` or the design docs, or to an existing test beyond "Edits to existing tests".

## Dependencies

None new.

## Design

### Part 1: `conductor.llm.tags`

New module constants and an exception, with exactly these values:

```python
MAX_BODY_BYTES = 1_048_576
UNEXPECTED_MESSAGE = "unexpected answer"
UNREACHABLE_MESSAGE = "not reachable"
TOO_LARGE_MESSAGE = "answer too large"


class TooLarge(OllamaBadAnswer):
    def __init__(self) -> None:
        super().__init__(TOO_LARGE_MESSAGE)
```

`OllamaUnreachable` and `OllamaBadAnswer` stay. A frozen dataclass records one listed model:

```python
Problem = Literal["no_digest", "bad_capabilities", "duplicate"]


@dataclass(frozen=True)
class Listed:
    name: str
    digest: str | None
    capabilities: tuple[str, ...]
    problem: Problem | None
```

| Function | Behaviour |
|---|---|
| `parse_tags(body: bytes) -> dict[str, Listed]` | Decodes `body` as strict UTF-8 JSON. Raises `OllamaBadAnswer(UNEXPECTED_MESSAGE)` when that fails or the result is not an object whose `models` is a list. Then each entry, in order: one that is not an object, or whose `name` is not a non-empty string, is skipped. Otherwise it gives a `Listed` as in the next table. A name seen a second time becomes `Listed(name, None, (), "duplicate")`, keeps its first place, and stays so however many more times it appears. The dict keeps first-seen order. |
| `find_model(listed: dict[str, Listed], name: str) -> Listed \| None` | `listed[name]` if present; else, when `name` has no `:`, `listed[f"{name}:latest"]` if present; else `None`. |
| `read_capped(response, limit: int = MAX_BODY_BYTES) -> bytes` | Calls `response.read(limit + 1)` once. Returns the bytes if there are at most `limit`; raises `TooLarge()` otherwise. It never reads with no size. |
| `fetch_models(host: str, *, timeout: float = 3.0) -> dict[str, Listed]` | The same proxy-free opener and `GET {host}/api/tags` as today, read through `read_capped`, then `parse_tags`. `HTTPError` and `http.client.HTTPException` raise `OllamaBadAnswer(UNEXPECTED_MESSAGE)`; any other `OSError` raises `OllamaUnreachable(UNREACHABLE_MESSAGE)`; `TooLarge` passes through as it is. |
| `fetch_model_names(host: str, *, timeout: float = 3.0) -> list[str]` | Unchanged: the sorted names `fetch_models` returns. |

One named entry gives:

| The entry | `digest` | `capabilities` | `problem` |
|---|---|---|---|
| `digest` is a string matching `^[0-9a-f]{64}$`, `capabilities` absent | that string | `()` | `None` |
| as above, `capabilities` a list of strings | that string | the strings sorted, repeats kept | `None` |
| `digest` missing or not matching (uppercase, 63 characters, a number) | `None` | `()` | `"no_digest"` |
| a valid `digest`, `capabilities` present but not a list of strings | that string | `()` | `"bad_capabilities"` |

`no_digest` wins over `bad_capabilities`: an entry with both faults is `Listed(name, None, (), "no_digest")`. Keys other than `name`, `digest` and `capabilities` are ignored.

### Part 2: model calls (`conductor.llm.ollama`, `conductor.llm.model`)

`UnavailableCode` gains `"too_large"`, so its message is `model unavailable: too_large` and its status `None`.

`OllamaModel._read` reads the answer through `tags.read_capped(response)` instead of `response.read()`, for `/api/tags` and `/api/chat` alike, and maps `TooLarge` to `ModelUnavailable("too_large")`. Every other mapping in `_read` stays as it is, and the request keeps `timeout=self._timeout`.

`OllamaModel.model_info(name)` parses the body with `tags.parse_tags` and looks the model up with `tags.find_model`:

| Outcome | Result |
|---|---|
| `parse_tags` raises `OllamaBadAnswer` | `ModelUnavailable("bad_answer")` |
| `find_model` gives `None` | `ModelUnavailable("not_installed")` |
| the found entry has a `problem` | `ModelUnavailable("bad_answer")` |
| otherwise | `ModelInfo(found.name, found.digest, found.capabilities)` |

`_info`, `_entry`, `_capabilities`, `_find` and the module's `_DIGEST` are removed: `tags.py` is the one listing parser. `_object` stays for the chat reply.

### Part 3: doctor (`conductor.diagnostics.check_ollama`)

`check_ollama(host, model)` keeps its signature, its `ollama <host>` and `model <model>` check names, and its handling of `OllamaUnreachable` and `OllamaBadAnswer` (the error's text, then `SKIP ... needs ollama`). It finds the model with `tags.find_model(listed, model)`. When the ollama check is `ok`, the model line is:

| The found entry | Model line |
|---|---|
| `None` | `FAIL  model <model>: not pulled (run: ollama pull <model>)` (unchanged) |
| problem `no_digest` | `FAIL  model <model>: listed without a valid digest` (unchanged text) |
| problem `bad_capabilities` | `FAIL  model <model>: listed with invalid capabilities` |
| problem `duplicate` | `FAIL  model <model>: listed more than once` |
| no problem | `ok    model <model>: digest <its first 12 characters>` (unchanged) |

An answer over the cap prints `FAIL  ollama <host>: answer too large`.

## Facts

Checked on 2026-11-19 with Python 3.12.16's `urllib` against small synthetic servers on 127.0.0.1:
- `response.read(n)` returns at most `n` bytes in every case tried: no length header with the connection closed, a length larger than the body, a length smaller than the body (it returns the declared bytes), a chunked body, and an unparsable length header.
- A declared length larger than the body returns the short body with no exception.
- A chunked body cut off mid-chunk raises `http.client.IncompleteRead`, a subclass of `HTTPException` and not of `OSError`. Today's `fetch_models` does not catch it, so doctor crashes with a traceback.
- A real listing is a few kilobytes; `MAX_REPLY_TOKENS` is 8192, so a chat reply cut by the model's own cap stays well under 1 MiB.

## Requirements

### Part 1: the listing

- **R1.** `MAX_BODY_BYTES`, `UNEXPECTED_MESSAGE`, `UNREACHABLE_MESSAGE`, `TOO_LARGE_MESSAGE` have exactly the values in Design; `TooLarge` is an `OllamaBadAnswer` whose text is `answer too large`.
- **R2.** `parse_tags` refuses, with `OllamaBadAnswer("unexpected answer")`, exactly an answer that is not UTF-8 JSON, or not an object with a `models` list.
- **R3.** `parse_tags` skips an entry without a usable name, keeps first-seen order, and sorts capabilities.
- **R4.** Each named entry is judged alone, by the entry table, with `no_digest` before `bad_capabilities`.
- **R5.** A name listed more than once is `Listed(name, None, (), "duplicate")` in its first place.
- **R6.** `find_model` takes the exact name first, else `{name}:latest` for a name without a tag.
- **R7.** `read_capped` reads at most `limit + 1` bytes in one call and raises `TooLarge` for more than `limit`; `fetch_models` reads through it and maps `HTTPException` to `unexpected answer`. Its default timeout stays `3.0`.

### Part 2: model calls

- **R8.** A tags or chat answer over 1 MiB, with an honest, false or missing length, escalates as `too_large` with status `None`; one of exactly 1 MiB is read.
- **R9.** `model_info` follows the outcome table: an unrelated bad entry does not hide the model, and a problem on the model's own entry is `bad_answer`. The run's timeout is the one `OllamaModel` was given.

### Part 3: doctor

- **R10.** For any listing, doctor's model line and a run's `model_info` agree: `ok` exactly when the run gets a `ModelInfo`. Doctor prints the line for each problem, and `answer too large` or `unexpected answer` for an oversized or broken answer, without a traceback.

### Part 4: the rules

- **R11.** Only the Scope's paths change; given files stay byte-identical; the existing tests change only by "Edits to existing tests". No module but `tags.py` parses a listing or reads a response body with no size.
- **R12.** `src/conductor/llm/tags.py`, `src/conductor/llm/ollama.py` and `src/conductor/diagnostics.py` keep 100% line and branch coverage.

## Given files

Committed with this spec. Do not change them; if a given test fails, the code is wrong. Before your change, `tests/unit/test_tags_parse.py` cannot be collected (its names do not exist), and every other given test fails except three that already hold: `test_a_bad_entry_for_the_model_is_a_bad_answer[caps-text]` and the `no-digest` case of `test_doctor_and_a_run_agree_on_the_model` (today's code already refuses those entries), and `test_each_caller_keeps_its_own_timeout` (a guard that the timeouts stay). With names-only stubs in `tags.py`, `test_the_limits_and_messages` and `test_an_answer_of_exactly_the_cap_is_read` also pass: the first only reads the constants, and today's uncapped read already reads 1 MiB.

| File | What it is |
|---|---|
| `tests/raw_http.py` | a helper: a 127.0.0.1 server that sends exact bytes, for false and missing lengths (no tests) |
| `tests/unit/test_tags_parse.py` | R1 to R7: the parser, the lookup and the capped read (19 tests from 8 functions) |
| `tests/unit/test_ollama_bounded.py` | R8, R9: `OllamaModel` over the fake Ollama and the raw server (8 tests from 5 functions) |
| `tests/e2e/test_cli_doctor_agrees.py` | R10: doctor against a run on the same listing (7 tests from 3 functions) |
| `docs/verification/probe-09g.py` | the probe, run by its path in Acceptance |

Given test count: **34**.

## Tests to write

In `tests/unit/test_tags_more.py` (section `core`), with `tests.support.fake_ollama`:
- R7: `fetch_models` turns a 500 answer into `OllamaBadAnswer` with the text `unexpected answer`, and a body of `MAX_BODY_BYTES + 1` spaces into `TooLarge`.
- R7: `fetch_model_names` returns the sorted names of a listing that also holds a skipped entry (`"x"`) and a duplicated name, each name once.
- R3: an entry with an empty name (`{"name": "", "digest": "a" * 64}`) is skipped.
- R12: any branch the given tests leave uncovered, tested for what it does.

## Rules for this phase

- Network only to Ollama on loopback, inside `src/conductor/llm/`, with the proxy-free opener. Tests touch only servers they start on 127.0.0.1.
- Error messages are constant text plus identifiers. Never print or keep any part of an answer body.
- Invalid model output escalates; nothing retries or repairs an answer.
- Synthetic data only. Commands start with `.venv/bin/python`. Do not commit.
- Earlier tests stay unchanged, except "Edits to existing tests".

## Acceptance

`.venv/bin/python scripts/accept.py --phase 9g` runs every row and search below in order and prints one line each; compare each with "Must show".

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --quiet --first cli,core` | last line `All checks passed.`; at least 1218 passed, 0 failed, 0 skipped, 0 xfailed; every `Sections:` row 0 failed |
| `.venv/bin/python -m coverage report --include='*/conductor/llm/tags.py,*/conductor/llm/ollama.py,*/conductor/diagnostics.py' --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_tags_parse.py tests/unit/test_ollama_bounded.py tests/e2e/test_cli_doctor_agrees.py --no-cov -q` | `34 passed` |
| `.venv/bin/python docs/verification/probe-09g.py` | every check line starts `ok`; last line `FAILURES 0` |
| `git diff HEAD --stat -- tests/raw_http.py tests/unit/test_tags_parse.py tests/unit/test_ollama_bounded.py tests/e2e/test_cli_doctor_agrees.py docs/verification/probe-09g.py src/conductor/config.py src/conductor/llm/decide.py src/conductor/llm/points.py` | no output |
| `git diff HEAD --numstat -- tests/unit/test_ollama.py tests/unit/test_ollama_more.py tests/e2e/test_cli_doctor.py tests/unit/test_diagnostics_more.py` | exactly four lines, tab-separated: `1 1 tests/e2e/test_cli_doctor.py`, `5 1 tests/unit/test_diagnostics_more.py`, `2 2 tests/unit/test_ollama.py`, `2 2 tests/unit/test_ollama_more.py` (added, removed, path) |
| `git status --short --untracked-files=all` | only the Scope paths |
| `grep -c '^## Phase 9g: ' docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9g` (after writing progress) | `Reports OK.` |

### Searches

Each prints nothing (git grep exit 1 is no match).

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

## Report

Write the entry with `scripts/progress.py` as `docs/phase-conventions.md` gives, titled `One bounded Ollama model listing`, with `--tests-before 1184 --given 34`.
