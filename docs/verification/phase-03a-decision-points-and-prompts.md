# Verify Phase 3a: decision points and prompts

Spec: `docs/phases/phase-03a-decision-points-and-prompts.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.llm.prompts` and `conductor.llm.points`, the given template `src/conductor/prompts/demo_pick.v1.md`, the demo point in `conductor.domains.demo`, the package-data lines in `pyproject.toml`, copied two given test files (32 tests), and wrote `tests/unit/test_points_more.py`.

## 1. Gates

N is `202`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 234 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/llm/prompts.py,*/conductor/llm/points.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_prompts.py tests/unit/test_points.py --no-cov` | exactly `32 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- tests src/conductor/contracts src/conductor/registry.py src/conductor/events.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/llm/prompts.py src/conductor/llm/points.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|dataclasses|hashlib|json|pathlib|re|string|typing|collections\.abc|pydantic|conductor\.contracts|conductor\.llm\.prompts)( |$)"`
2. `git grep --untracked -n -E "^(from|import) .*(urllib|http|ollama|socket)" -- src/conductor/llm/prompts.py src/conductor/llm/points.py`

## 2. Scope paths

`git status --short` lists only: `src/conductor/llm/prompts.py`, `src/conductor/llm/points.py`, `src/conductor/prompts/`, `src/conductor/domains/demo.py`, `pyproject.toml`, the two given test files, `tests/unit/test_points_more.py`, `docs/progress.md`. The given files equal the spec's blocks (the template byte for byte: `diff` it against the spec's block, which ends with one newline). `git diff HEAD -- pyproject.toml` shows only the two package-data lines; `git diff HEAD -- src/conductor/domains/demo.py` only adds (imports and the four names after `DOMAIN`).

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_template_name_needs_a_name_and_a_version`, `test_a_missing_template`, `test_a_template_that_is_not_utf8`, `test_a_template_with_a_stray_dollar`; the coder's 32/33-character and name-before-file tests | pass |
| R2 | `test_the_demo_template_loads`, `test_fields_are_sorted_and_named_once`; probe "one more byte changes the hash" | pass; ok |
| R3 | `test_a_bad_point_is_refused`, `test_inputs_of_another_class_are_refused`; the coder's order and 1/8192 tests | pass |
| R4 | `test_fields_must_match_the_template` | pass |
| R5 | `test_the_demo_request_is_pinned`, `test_a_field_value_is_not_substituted_again`; probe "the schema in the system message is the format sent" | pass; ok |
| R6 | `test_the_request_stays_data`; probes "no input ever reaches the system message", "every user message is the input as JSON" | pass; ok |
| R7 | `test_the_demo_request_is_pinned`; probe "the seed and context are the pinned values" | pass; ok |
| R8 | `test_the_chat_body`; the coder's body-copy test; probe "the body is plain JSON and round-trips" | pass; ok |
| R9 | `test_the_demo_point`; read `demo.py` against the Design; the coder's `pick_fields` test | the same |
| R10 | searches 1 and 2; the `pyproject.toml` diff; probe "building a request opens no connection" | no output; the two lines; ok |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`.

```python
"""Independent probe for Phase 3a. Run from the repository root with .venv/bin/python."""

import json
import random
import socket
import tempfile
from pathlib import Path

from conductor.domains import demo
from conductor.llm import points
from conductor.llm.points import SCHEMA_INTRO, build_request
from conductor.llm.prompts import PROMPTS_DIR, load_template

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def pick(text: str):
    return build_request(
        demo.PICK,
        demo.PickInputs(request=text),
        model="probe:1b",
        fields=demo.pick_fields(),
    )


files = sorted(path.name for path in PROMPTS_DIR.iterdir())
check("the prompts folder holds only demo_pick.v1.md", files == ["demo_pick.v1.md"])

rng = random.Random(3)
alphabet = 'ab $"\\\n\t<>/{}é漢 ' + "\x00"
texts = [
    "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60))) for _ in range(500)
]
built = [pick(text) for text in texts]
check(
    "no input ever reaches the system message",
    len({request.system for request in built}) == 1,
)
check(
    "every user message is the input as JSON",
    all(
        json.loads(r.user) == {"request": t} for r, t in zip(built, texts, strict=True)
    ),
)

first = pick("same")
check("building twice gives the same request and body", first == pick("same"))
encoded = json.dumps(first.body(), allow_nan=False)
check("the body is plain JSON and round-trips", json.loads(encoded) == first.body())

tail = first.system.split(SCHEMA_INTRO + "\n", 1)[1]
check(
    "the schema in the system message is the format sent",
    json.loads(tail) == first.schema,
)

with tempfile.TemporaryDirectory() as folder:
    raw = (PROMPTS_DIR / "demo_pick.v1.md").read_bytes()
    (Path(folder) / "demo_pick.v1.md").write_bytes(raw + b" ")
    copy = load_template("demo_pick.v1", Path(folder))
check(
    "one more byte changes the hash",
    copy.sha256 != load_template("demo_pick.v1").sha256,
)


def refuse(*args: object, **kwargs: object) -> None:
    raise AssertionError("network")


real = socket.socket.connect
socket.socket.connect = refuse  # type: ignore[method-assign]
try:
    pick("offline")
    offline = True
except AssertionError:
    offline = False
finally:
    socket.socket.connect = real  # type: ignore[method-assign]
check("building a request opens no connection", offline)
pinned = (points.SEED, points.CONTEXT_TOKENS)
check("the seed and context are the pinned values", pinned == (7, 8192))

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_points_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `user` from `inputs.model_dump_json()` without `indent` (`build_request`) | `test_the_demo_request_is_pinned` | `'{\n  "request": ...'` | `'{"request":...'` |
| 2 | the schema written with `json.dumps(schema)`, no `indent` (`build_request`) | `test_the_demo_request_is_pinned` | the pinned `SYSTEM` | one-line schema |
| 3 | no `rstrip()` on the filled template (`build_request`) | `test_a_field_value_is_not_substituted_again` | `$5\n\nAnswer` | `$5\n\n\nAnswer` |
| 4 | `isinstance(inputs, point.inputs)` for the input check (`build_request`) | `test_inputs_of_another_class_are_refused`, `LongerInputs` | refused | accepted |
| 5 | `bool` allowed for `max_reply_tokens` (`build_request`) | `test_a_bad_point_is_refused`, `max_reply_tokens=True` | refused | accepted |
| 6 | fields in order of appearance, not sorted (`load_template`) | `test_fields_are_sorted_and_named_once` | `("a", "b")` | `("b", "a")` |
| 7 | the name pattern matched without its end anchor (`load_template`) | `test_a_template_name_needs_a_name_and_a_version`, `demo_pick.v1.md` | `not a valid template name` | `not found` |
| 8 | `body()` returns `self.options` itself (`ModelRequest.body`) | the coder's R8 test, `body()["options"]["seed"]` changed | `request.options` unchanged | changed |

Reasonable variations that are correct: the patterns compiled once at module level; `fields` checked with sets or with sorted tuples; private helpers for the point checks; `ModelRequest` with `slots=True`; `PROMPTS_DIR` built with `resolve()`.

## 6. Project rules

- Searches 1 and 2.
- Prompt text exists only in `src/conductor/prompts/demo_pick.v1.md`: no instruction text for the model inside `points.py` other than `SCHEMA_INTRO`.
- Every `PromptError` message is one of the spec's, with only point or template names in it.

## 7. Out of scope

Each must be absent: an HTTP call or `urllib` anywhere new, the `ollama` package, `decide`, `ScriptedModel`, event logging, a digest or capability lookup, routing or planner points or templates, settings for the seed, context, or per-point model, any change to `conductor.contracts`, `conductor.registry`, or `conductor.events`.

## 8. Progress log

The entry exists, headed `## Phase 3a: decision points and prompts (...)`, with `Tests: 202 -> <passed> (given 32)`, and each deviation it lists is real and justified.
