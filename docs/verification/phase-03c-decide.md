# Verify Phase 3c: decide()

Spec: `docs/phases/phase-03c-decide.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.llm.decide` (critical), added `model_unavailable` to `EscalationKind`, made the one-line given edit to `tests/unit/test_contracts_tasks.py`, added `llm/decide.py` to the critical modules, copied the given `tests/unit/test_decide.py` (19 tests), and wrote `tests/unit/test_decide_more.py`.

## 1. Gates

N is `282`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 301 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `llm/decide.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/llm/decide.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_decide.py --no-cov` | exactly `19 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff HEAD -- tests` | one added line, `"model_unavailable",`, in `test_the_closed_sets` of `tests/unit/test_contracts_tasks.py`; nothing else |
| `git diff HEAD -- src/conductor/contracts` | one added line, `"model_unavailable",`, last in `EscalationKind` |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/llm/decide.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|dataclasses|typing|collections\.abc|pydantic|conductor\.contracts|conductor\.events|conductor\.llm\.[a-z_]+|conductor import ids)( |$)"`
2. `git grep --untracked -n -E "model_validate\(|get_settings|clock\.|os\.environ|getenv|import ids as|from conductor\.ids import" -- src/conductor/llm/decide.py`
3. `git grep --untracked -n -E "\.chat\(" -- src/conductor | grep -v -E "^src/conductor/llm/decide\.py:"`

## 2. Scope paths

`git status --short` lists only: `src/conductor/llm/decide.py`, `src/conductor/contracts/escalations.py`, `tests/unit/test_contracts_tasks.py`, `scripts/critical_modules.txt`, `docs/testing.md`, `tests/unit/test_decide.py`, `tests/unit/test_decide_more.py`, `docs/progress.md`. The given file equals the spec's block; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's lines.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_prompt_error_is_raised_before_anything_is_logged` | pass |
| R2 | `test_the_digest_is_read_for_every_decision`; read `decide` for the order: build, id, `model_info` | pass; the same |
| R3 | `test_a_decision`, `test_thinking_needs_the_point_and_the_model`; the coder's request-on-disk test; probe "the logged body is what the model was sent" | pass; ok |
| R4 | `test_a_reply_that_does_not_fit_raises` (`content` in the reply event); the coder's `ScriptError` test; probe "every raw reply is logged as it came" | pass; ok |
| R5 | `test_a_reply_that_does_not_fit_raises`; the coder's `cut_off` and two-field tests; probe "a reply is accepted exactly when it stopped and parses strictly" | pass; ok |
| R6 | `test_a_model_that_is_not_installed`, `test_a_model_that_fails_while_answering`; the coder's `timeout` test | pass |
| R7 | `test_a_decision`; the coder's one-chat test; probe "each decision logs request, reply, and an error only on failure" | pass; ok |
| R8 | `test_an_escalation_for_invalid_output`, `test_an_escalation_for_a_model_that_is_unavailable`, `test_the_closed_sets`; the coder's every-code test; probes "every escalation is a valid contract that round-trips", "model failures escalate as model_unavailable" | pass; ok |
| R9 | `test_no_reply_value_reaches_the_error`; probes "problems hold only codes and safe locations, never a value", "no error event holds a reply value" | pass; ok |
| R10 | searches 1, 2, 3 | no output |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It plays 304 scripted replies (random fragments, a quarter of them cut off) through `decide` into one log.

```python
"""Independent probe for Phase 3c. Run from the repository root with .venv/bin/python."""

import json
import random
import re
import tempfile
from pathlib import Path

from conductor.contracts import Escalation
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.decide import Decision, InvalidModelOutput, decide, escalation_for
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


RUN = "c" * 32
rng = random.Random(11)
pieces = [
    '{"action": ',
    '"echo"',
    '"note"',
    '"none"',
    '"SECRETVALUE"',
    "}",
    ', "x": 1',
    "[",
    "]",
    " ",
    "null",
    "7",
]
contents = [
    "".join(rng.choice(pieces) for _ in range(rng.randint(0, 6))) for _ in range(300)
]
contents += [json.dumps({"action": a}) for a in ("echo", "note", "delegate", "none")]
reasons = [rng.choice(["stop", "stop", "stop", "length"]) for _ in contents]

folder = Path(tempfile.mkdtemp())
log = EventLog(folder)
model = ScriptedModel(
    [
        ScriptedReply("demo_pick", ModelReply(content=c, done_reason=r))
        for c, r in zip(contents, reasons, strict=True)
    ]
)
outcomes = []
for _ in contents:
    try:
        outcomes.append(
            decide(
                demo.PICK,
                demo.PickInputs(request="probe"),
                fields=demo.pick_fields(),
                model=model,
                model_name="probe:1b",
                log=log,
                run_id=RUN,
            )
        )
    except InvalidModelOutput as error:
        outcomes.append(error)
    except Exception as error:  # noqa: BLE001
        outcomes.append(("other", type(error).__name__))

check(
    "every reply either decides or raises InvalidModelOutput",
    all(not isinstance(o, tuple) for o in outcomes),
)
expected_ok = []
for c, r in zip(contents, reasons, strict=True):
    try:
        parsed = demo.PickOutput.model_validate_json(c, strict=True)
    except Exception:  # noqa: BLE001
        parsed = None
    expected_ok.append(parsed if r == "stop" else None)
got_ok = [o.output if isinstance(o, Decision) else None for o in outcomes]
check(
    "a reply is accepted exactly when it stopped and parses strictly",
    got_ok == expected_ok,
)

safe = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
problems = [
    p for o in outcomes if isinstance(o, InvalidModelOutput) for p in o.problems
]
check(
    "problems hold only codes and safe locations, never a value",
    all(safe.fullmatch(p.code) and "SECRET" not in p.loc for p in problems),
)

events = log.read(RUN)
check(
    "the log reads back whole",
    [e.seq for e in events] == list(range(1, len(events) + 1)),
)
by_decision: dict[str, list] = {}
for event in events:
    by_decision.setdefault(event.payload["decision_id"], []).append(event)
shapes = {tuple(e.kind for e in group) for group in by_decision.values()}
check(
    "each decision logs request, reply, and an error only on failure",
    len(by_decision) == len(contents)
    and shapes
    <= {
        (EventKind.MODEL_REQUEST, EventKind.MODEL_REPLY),
        (EventKind.MODEL_REQUEST, EventKind.MODEL_REPLY, EventKind.ERROR),
    },
)
replies = [g[1].payload["content"] for g in by_decision.values()]
check("every raw reply is logged as it came", replies == contents)
sent = [g[0].payload["body"] for g in by_decision.values()]
check(
    "the logged body is what the model was sent",
    sent == [json.loads(json.dumps(r.body())) for r in model.requests],
)
errors = [g[2].payload for g in by_decision.values() if len(g) == 3]
check(
    "no error event holds a reply value",
    all("SECRET" not in json.dumps(e) for e in errors),
)

escalations = [
    escalation_for(o, RUN) for o in outcomes if isinstance(o, InvalidModelOutput)
]
for code in ("unreachable", "timeout", "bad_answer", "not_installed"):
    escalations.append(escalation_for(ModelUnavailable(code), RUN))
escalations.append(escalation_for(ModelUnavailable("http_error", 599), RUN))
check(
    "every escalation is a valid contract that round-trips",
    all(Escalation.from_json(e.model_dump_json()) == e for e in escalations),
)
check(
    "model failures escalate as model_unavailable",
    [e.kind for e in escalations[-5:]] == ["model_unavailable"] * 5,
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_decide_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in `decide` (or the named function), run the deciding test, see it fail, restore.

| # | Change | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the `MODEL_REPLY` event appended after the check instead of before | `test_a_reply_that_does_not_fit_raises`, `not json` | request, reply, error | request, error |
| 2 | `think = point.think` (capabilities ignored) | `test_thinking_needs_the_point_and_the_model`, `(True, ("completion",))` | sent `False` | sent `True` |
| 3 | the `done_reason` check removed | `test_a_reply_that_does_not_fit_raises`, `"length"` | `reply` `cut_off` | a `Decision` |
| 4 | parsing with `point.output.model_validate_json(content)` (not strict) | the coder's two-field test, `{"a": "1", "b": "2"}` | two `int_type` | accepted |
| 5 | a second `chat` after a reply that does not fit | `test_a_reply_that_does_not_fit_raises` (one scripted reply) | `InvalidModelOutput` | `ScriptError` |
| 6 | `ModelUnavailable` re-raised without its event | `test_a_model_that_is_not_installed` | one `ERROR` event | no run |
| 7 | `model_info` cached across calls (for example `functools.lru_cache` on a helper) | `test_the_digest_is_read_for_every_decision` | `1…`, `2…` | `1…`, `1…` |
| 8 | `RETRY_HINT` left out of the detail (`escalation_for`) | `test_an_escalation_for_a_model_that_is_unavailable` | `...; retry when Ollama answers` | without it |

Reasonable variations that are correct: private helpers for each event; the request built, then `replace`d inside a helper; `Decision` with `slots=True`; `escalation_for` dispatching with `isinstance` or `match`.

## 6. Project rules

- Searches 1 to 3; only `decide.py` calls `.chat(`.
- No loop, sleep, or second `chat` in `decide.py`; no `except Exception`.
- Every message and `ERROR` payload holds only ids, point names, codes, locations, and the HTTP status.

## 7. Out of scope

Each must be absent: retries, repair, defaults for a bad reply, a fallback model, a new `EventKind` or other change to `conductor.events`, a success event, reading settings, a command, graph or routing code, changes to the 3a or 3b modules, any contract change beyond the one value.

## 8. Progress log

The entry exists, headed `## Phase 3c: decide() (...)`, with `Tests: 282 -> <passed> (given 19)`, and each deviation it lists is real and justified.
