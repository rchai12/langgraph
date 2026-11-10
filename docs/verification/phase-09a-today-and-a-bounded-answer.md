# Verify Phase 9a: today in the planner, and a bounded answer

Spec: `docs/phases/phase-09a-today-and-a-bounded-answer.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 9a` on your own report.

The coder added `clock.today`, the `plan.v2` template and today's fields, a context size per decision point, the answer's larger context and its 24000-byte bound with the `answer_too_large` kind, copied four given test files (28 tests) and the edits to six earlier test files, and wrote `tests/unit/test_groundwork_more.py`.

## 1. Gates

N is `827`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 855 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/clock.py,*/conductor/llm/points.py,*/conductor/planning/plan.py,*/conductor/planning/answer.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_plan_today.py tests/unit/test_point_context.py tests/unit/test_answer_bound.py tests/integration/test_answer_too_large.py tests/unit/test_plan.py tests/unit/test_plan_more.py tests/unit/test_answer.py tests/unit/test_contracts_tasks.py tests/unit/test_eval_report.py tests/e2e/test_cli_eval_report.py --no-cov` | exactly `101 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 9a` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/prompts/plan.v1.md src/conductor/prompts/route.v1.md src/conductor/prompts/answer.v1.md src/conductor/graph src/conductor/runtime.py src/conductor/web src/conductor/mcp_client src/conductor/evals src/conductor/routing src/conductor/domains tests/support.py tests/conftest.py tests/e2e/test_cli_eval.py` | no output |
| `git diff HEAD -- tests` | only the edits the spec lists, in the six files it names |
| `git diff HEAD -- src/conductor/contracts` | only `"answer_too_large"` added last to `EscalationKind` |

Searches, each with no output:

1. `git grep --untracked -n -E "datetime\.now|date\.today|time\.time|strftime" -- src/conductor/planning src/conductor/llm`
2. `git grep --untracked -n -E "from conductor\.clock import" -- src tests`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks: the template, the four new test files, and the six edited ones.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_today_is_the_local_day_of_now`; the coder's `+14:00` test; probe "400 random moments ..." | pass; ok |
| R2 | `test_plan_fields_name_today_and_its_weekday` (7 cases), `test_the_plan_point_uses_plan_v2_and_keeps_v1`, `test_each_plan_request_reads_today_again`, the edited `test_the_plan_point_and_its_prompt` and `test_fields_list_every_action_and_the_union_keeps_declaration_order`; the coder's counting and 2028-02-29 tests | pass |
| R3 | `test_a_point_keeps_the_default_context`, `test_a_context_in_range_is_sent` (3 cases), `test_a_context_out_of_range_is_refused` (6 cases), `test_the_reply_cap_is_checked_before_the_context`; the earlier `tests/unit/test_points.py` unchanged; the coder's 8192/8192 and `None` tests; probe "context_tokens ..." | pass; ok |
| R4 | `test_the_answer_point_has_a_larger_context`, the edited `test_the_answer_point_and_its_prompt` | pass |
| R5 | `test_results_at_the_bound_are_answered`, `test_results_past_the_bound_escalate_without_asking` (3 cases); the coder's results-count and two-results tests; probe "300 random results ..." | pass; ok |
| R6 | the edited `test_the_closed_sets`, `test_a_too_large_answer_waits_for_the_person_and_can_be_cancelled` | pass |
| R7 | the `git diff HEAD -- tests` gate | as in the Gates |
| R8 | searches 1 and 2; the protected diff | no output |
| R9 | the coverage gate | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It sets `clock.now` to 400 random moments in random offsets and compares today and its weekday with `time.localtime` and a weekday counted from a known Monday; sends 300 random results (ASCII, two-, three-, and four-byte characters, newlines, quotes) and compares the outcome with its own byte count of the message; and tries `context_tokens` around both ends of its range and of the wrong types. A stop at its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 9a. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import tempfile
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

from conductor import clock
from conductor.contracts import Escalation
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.points import build_request
from conductor.llm.prompts import PromptError
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import Answered, StepOutcome, answer_request
from conductor.planning.plan import plan_fields

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(91)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
folder = Path(tempfile.mkdtemp())
NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ANCHOR = date(2026, 11, 9)  # a Monday


def weekday_of(day: date) -> str:
    return NAMES[(day - ANCHOR).days % 7]


def local_day(moment: datetime) -> date:
    parts = time.localtime(moment.timestamp())
    return date(parts.tm_year, parts.tm_mon, parts.tm_mday)


def message_bytes(request: str, outputs: list[dict]) -> int:
    body = {
        "request": request,
        "results": [
            {"step": i, "action": "demo.echo", "output": out} for i, out in enumerate(outputs, 1)
        ],
    }
    return len(json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8"))


# the oracle on known cases
assert weekday_of(date(2026, 11, 10)) == "Tuesday" and weekday_of(date(2024, 2, 29)) == "Thursday"
assert weekday_of(date(2000, 1, 1)) == "Saturday"
assert local_day(datetime(2031, 3, 4, 12, 0, tzinfo=UTC)) in (date(2031, 3, 4), date(2031, 3, 5))
assert message_bytes("r", [{"text": "é"}]) == len(
    '{\n  "request": "r",\n  "results": [\n    {\n      "step": 1,\n      "action": "demo.echo",'
    '\n      "output": {\n        "text": "é"\n      }\n    }\n  ]\n}'.encode()
)

# 1. today and its weekday from random moments
agree = True
saved_now = clock.now
for _ in range(400):
    moment = datetime(1990, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randint(0, 60 * 365 * 86400))
    moment = moment.astimezone(timezone(timedelta(minutes=rng.randint(-12 * 60, 14 * 60))))
    clock.now = lambda moment=moment: moment
    fields = plan_fields(demo.DOMAIN)
    want = local_day(moment)
    agree &= clock.today() == want
    agree &= (fields["today"], fields["weekday"]) == (want.isoformat(), weekday_of(want))
clock.now = saved_now
check("400 random moments give the local day and its weekday", agree)

# 2. the answer bound, by the bytes of the message sent
agree = True
for trial in range(300):
    outputs = []
    for _ in range(rng.randint(1, 4)):
        char = rng.choice(["x", "é", "€", "𝄞", "\n", '"'])
        outputs.append({"text": char * rng.randint(0, 7000), "n": rng.randint(-(10**6), 10**6)})
    size = message_bytes("Say hi", outputs)
    model = ScriptedModel([ScriptedReply("answer", ModelReply(content='{"reply": "Hi."}'))])
    found = answer_request(
        "Say hi",
        [StepOutcome(step=i, action="demo.echo", output=out) for i, out in enumerate(outputs, 1)],
        model=model,
        model_name="m",
        log=EventLog(folder / f"answer{trial}"),
        run_id="a" * 32,
    )
    if size > 24_000:
        agree &= found == Escalation(
            kind="answer_too_large",
            detail=f"the step results are {size} bytes, more than 24000; ask for less",
            run_id="a" * 32,
        )
        agree &= model.requests == []
    else:
        agree &= isinstance(found, Answered) and len(model.requests[0].user.encode()) == size
check("300 random results escalate exactly when the message passes 24000 bytes", agree)

# 3. the context bound
agree = True
for tokens in [*range(8180, 8200), *range(32760, 32780), 0, -1, 16384, True, False, "8192", 8192.0]:
    point = replace(demo.PICK, context_tokens=tokens)
    try:
        sent = build_request(
            point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields()
        )
        ok = type(tokens) is int and 8192 <= tokens <= 32768 and sent.options["num_ctx"] == tokens
    except PromptError as error:
        ok = not (type(tokens) is int and 8192 <= tokens <= 32768) and str(error) == (
            "point demo_pick: context_tokens must be 8192 to 32768"
        )
    agree &= ok
check("context_tokens is sent from 8192 to 32768 and refused outside", agree)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The new test file covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1` and `-vv`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the day from `datetime.now().astimezone().date()` instead of `now()` (`clock.today`) | `test_today_is_the_local_day_of_now` | a day in March 2031 | today's real date |
| 2 | the weekday taken at `day.isoweekday()` instead of `day.weekday()` (`plan_fields`) | `test_plan_fields_name_today_and_its_weekday`, `day0-Monday` | `Monday` | `Tuesday` |
| 3 | today kept in a module variable after the first call (`plan_fields`) | `test_each_plan_request_reads_today_again` | the second prompt names 2027-01-01 | the second prompt names 2026-12-31 too |
| 4 | the upper end checked with `<` (`build_request`) | `test_a_context_in_range_is_sent`, `32768` | sent | `PromptError: point demo_pick: context_tokens must be 8192 to 32768` |
| 5 | `num_ctx` left at `CONTEXT_TOKENS` (`build_request`) | `test_the_answer_point_has_a_larger_context` | `num_ctx` 16384 | `num_ctx` 8192 |
| 6 | the size taken as the message's characters, not its bytes (`answer_request`) | `test_results_past_the_bound_escalate_without_asking`, `24002-é` | the `answer_too_large` escalation | an `Answered` with `Hi.` |
| 7 | the bound checked with `>=` (`answer_request`) | `test_results_at_the_bound_are_answered` | an `Answered` | an `answer_too_large` escalation for 24000 bytes |
| 8 | the size checked after `decide` instead of before it (`answer_request`) | `test_results_past_the_bound_escalate_without_asking`, `24001-x` | `model.requests == []` | one request was sent (and, if the escalation still comes back, the log has events) |
| 9 | `answer_too_large` placed before `model_unavailable` (`EscalationKind`) | `test_the_closed_sets` | `answer_too_large` last | the two kinds in the other order |

Reasonable variations that are correct: the weekday names as a module constant; the size check in a private helper; `context_tokens` checked through a shared helper with `max_reply_tokens` as long as the messages and their order stay.

## 6. Project rules

- Searches 1 and 2.
- Time comes only from `clock`, called through the module; the weekday never from the locale.
- The escalation's detail is constant text and two numbers; no result appears in it.
- No test opens a connection; the model in tests is `ScriptedModel`.

## 7. Out of scope

Each must be absent: a finance domain, actions, or server; bounds on any action's arguments or results; a time zone setting; changes to the route or answer templates, the graph, the runtime, the store, the web pages, MCP, or the evaluation harness; `plan.v1.md` changed or removed.

## 8. Progress log

The entry exists, headed `## Phase 9a: today in the planner, and a bounded answer (...)`, with `Tests: 827 -> <passed> (given 28)`, and each deviation it lists is real and justified.
