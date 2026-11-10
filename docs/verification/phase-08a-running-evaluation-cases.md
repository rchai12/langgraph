# Verify Phase 8a: running evaluation cases

Spec: `docs/phases/phase-08a-running-evaluation-cases.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 8a` on your own report.

The coder created `conductor.evals.cases` and `conductor.evals.run`, added `conductor eval run`, labelled the approvals page's buttons and fields, copied the given case file and four test files (32 tests), and wrote `tests/unit/test_eval_more.py`.

## 1. Gates

N is `744`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 776 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/evals/*.py,*/conductor/cli/main.py,*/conductor/web/app.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_eval_cases.py tests/unit/test_eval_run.py tests/e2e/test_cli_eval.py tests/e2e/test_web_labels.py --no-cov` | exactly `32 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 8a` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/routing src/conductor/planning src/conductor/llm src/conductor/graph src/conductor/runtime.py tests/e2e/test_web_pages.py tests/e2e/test_web_decide.py tests/e2e/test_web_runs.py tests/support.py` | no output |
| `git diff HEAD -- src/conductor/web` | only the button texts and the labels |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/evals | grep -v -E ":from conductor(\.config|\.contracts|\.events|\.llm\.model|\.llm\.ollama|\.planning\.plan|\.registry|\.routing\.route)? import "`
2. `git grep --untracked -n -E "eval" -- scripts/check.py`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks, the case file included.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_given_demo_cases_load`, `test_what_a_case_file_may_not_hold` (13 cases), `test_a_problem_never_quotes_the_request`; the coder's `seen`, plan-type, and 2000-character tests; probe "the given evals/cases/demo.toml loads" | pass; ok |
| R2 | `test_runs_are_1_to_100` (2 cases), `test_a_rule_route_asks_the_model_only_to_plan`; search 1 | pass; no output |
| R3 | `test_three_runs_that_agree`, `test_runs_that_disagree`, `test_a_case_that_expects_escalations`; the coder's args, order, and escalation-kind tests; probe "200 random cases give the metrics the probe computes" | pass; ok |
| R4 | `test_an_invalid_reply_and_an_unavailable_model`, the seconds in `test_runs_that_disagree`; the coder's two-replies test; `test_runs_are_logged_under_the_data_folder` | pass |
| R5 | the line checks in `test_three_runs_that_agree`, `test_runs_that_disagree`, `test_the_overall_line`; the coder's one-run and no-args tests | pass |
| R6 | `test_eval_run_prints_a_line_per_case_and_overall`, `test_five_runs_by_default_from_one_file`, `test_errors` (2 cases), `test_a_bad_case_file_names_itself`; the coder's `--runs 101` and two-file tests | pass |
| R7 | `test_each_approval_form_says_what_it_does` (2 cases), `test_each_escalation_form_says_what_it_does`; the 7a and 7b web tests unchanged | pass |
| R8 | search 1 | no output |
| R9 | search 2 | no output |
| R10 | the coverage gate | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It runs 200 random cases (each 1 to 6 runs of scripted replies: unavailable, `unknown`, right and wrong plans, empty plans, invalid replies, with random times) and compares every number with its own computation, which checks itself on known cases first. A stop at its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 8a. Run from the repository root with .venv/bin/python."""

import json
import math
import os
import random
import tempfile
from collections import Counter
from pathlib import Path

from conductor.domains import demo
from conductor.evals.cases import EvalCase, load_cases
from conductor.evals.run import case_line, run_case
from conductor.events import EventLog
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(83)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
folder = Path(tempfile.mkdtemp())
REGISTRY = Registry((demo.DOMAIN,))


def nearest(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(share * len(ordered))) - 1]


def expect(case: EvalCase, outcomes: list[dict]) -> dict:
    """The probe's own reading of the metrics, from what each run produced."""
    keys = [json.dumps(o["key"], sort_keys=True) for o in outcomes]
    route_ok = plan_ok = args_ok = 0
    for o in outcomes:
        r = o["route"] == case.route
        route_ok += r
        if case.route == "escalate":
            plan_ok += r
        elif r and case.plan == "escalate":
            plan_ok += o["plan"] == "escalate"
        elif r:
            plan_ok += isinstance(o["plan"], list) and [a for a, _ in o["plan"]] == list(case.plan)
        planned = isinstance(o["plan"], list) and isinstance(case.plan, tuple)
        if case.args is not None and r and planned and [a for a, _ in o["plan"]] == list(case.plan):
            steps = o["plan"]
            args_ok += len(steps) == len(case.args) and all(
                all(s.get(k) == v for k, v in want.items())
                for (_, s), want in zip(steps, case.args, strict=False)
            )
    return {
        "consistent": Counter(keys).most_common(1)[0][1],
        "route_ok": route_ok,
        "plan_ok": plan_ok,
        "args_ok": None if case.args is None else args_ok,
        "valid": sum(o["valid"] for o in outcomes),
        "escalated": sum(o["escalated"] for o in outcomes),
        "seconds": sorted(o["seconds"] for o in outcomes),
        "p50": nearest([o["seconds"] for o in outcomes], 0.5),
        "p95": nearest([o["seconds"] for o in outcomes], 0.95),
    }


assert nearest([0.5, 2.0, 3.0, 4.0], 0.5) == 2.0 and nearest([0.5, 2.0, 3.0, 4.0], 0.95) == 4.0
assert nearest([7.0], 0.95) == 7.0
_case = EvalCase("x", "r", "demo", ("echo",), ({"text": "hi"},))
_runs = [
    {
        "route": "demo",
        "plan": [("echo", {"text": "hi"})],
        "valid": True,
        "escalated": False,
        "seconds": 2.0,
        "key": "a",
    },
    {
        "route": "demo",
        "plan": "invalid",
        "valid": False,
        "escalated": True,
        "seconds": 1.0,
        "key": "b",
    },
    {"route": None, "plan": None, "valid": True, "escalated": True, "seconds": 0.0, "key": "c"},
]
_got = expect(_case, _runs)
assert (_got["route_ok"], _got["plan_ok"], _got["args_ok"], _got["valid"], _got["escalated"]) == (
    2,
    1,
    1,
    2,
    2,
)

# 1. random cases and replies against the probe's metrics
agree = True
for i in range(200):
    case = EvalCase(
        id=f"c{i}",
        request="Say something to me",
        route=rng.choice(["demo", "demo", "escalate"]),
        plan=None,
        args=None,
    )
    if case.route == "demo":
        plan = rng.choice([("echo",), ("note",), ("echo", "note"), "escalate"])
        args = ({"text": "hi"},) if plan == ("echo",) and rng.random() < 0.5 else None
        case = EvalCase(case.id, case.request, "demo", plan, args)
    runs = rng.randint(1, 6)
    replies, outcomes = [], []
    for _ in range(runs):
        r = rng.random()
        if r < 0.15:
            replies.append(ScriptedReply("route", ModelUnavailable("timeout")))
            outcomes.append(
                {
                    "route": None,
                    "plan": None,
                    "valid": True,
                    "escalated": True,
                    "seconds": 0.0,
                    "key": "unavailable",
                }
            )
            continue
        if r < 0.3:
            replies.append(
                ScriptedReply("route", ModelReply(content='{"domain": "unknown"}', total_ns=10**9))
            )
            outcomes.append(
                {
                    "route": "escalate",
                    "plan": None,
                    "valid": True,
                    "escalated": True,
                    "seconds": 1.0,
                    "key": "unknown",
                }
            )
            continue
        replies.append(
            ScriptedReply("route", ModelReply(content='{"domain": "demo"}', total_ns=10**9))
        )
        choice = rng.choice(["echo-hi", "echo-yo", "note", "both", "empty", "bad"])
        steps = {
            "echo-hi": [("echo", {"text": "hi"})],
            "echo-yo": [("echo", {"text": "yo"})],
            "note": [("note", {"title": "T"})],
            "both": [("echo", {"text": "hi"}), ("note", {"title": "T"})],
            "empty": [],
            "bad": [("send", {})],
        }[choice]
        seconds = rng.choice([1, 2, 3])
        content = json.dumps({"steps": [{"action": a, "args": g} for a, g in steps]})
        replies.append(ScriptedReply("plan", ModelReply(content=content, total_ns=seconds * 10**9)))
        if choice in ("empty", "bad"):
            outcomes.append(
                {
                    "route": "demo",
                    "plan": "escalate" if choice == "empty" else "invalid",
                    "valid": choice != "bad",
                    "escalated": True,
                    "seconds": 1.0 + seconds,
                    "key": choice,
                }
            )
        else:
            outcomes.append(
                {
                    "route": "demo",
                    "plan": steps,
                    "valid": True,
                    "escalated": False,
                    "seconds": 1.0 + seconds,
                    "key": choice,
                }
            )
    result = run_case(
        case,
        REGISTRY,
        model=ScriptedModel(replies),
        model_name="m",
        log=EventLog(folder / "runs"),
        runs=runs,
    )
    want = expect(case, outcomes)
    got = {
        "consistent": result.consistent,
        "route_ok": result.route_ok,
        "plan_ok": result.plan_ok,
        "args_ok": result.args_ok,
        "valid": result.valid,
        "escalated": result.escalated,
        "seconds": sorted(result.seconds),
        "p50": nearest(list(result.seconds), 0.5),
        "p95": nearest(list(result.seconds), 0.95),
    }
    agree &= got == want and case_line(result).startswith(
        f"c{i}  consistent {want['consistent']}/{runs}"
    )
check("200 random cases give the metrics the probe computes", agree)

# 2. the given demo cases load against the demo registry
check(
    "the given evals/cases/demo.toml loads (5 cases)",
    len(load_cases(Path("evals/cases/demo.toml"), REGISTRY)) == 5,
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The new test file covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `consistent` counted as the number of different outcomes (`run_case`) | `test_runs_that_disagree` | `1` | `4` |
| 2 | for a `route = "escalate"` case, the plan counted right only when a plan exists (`run_case`) | `test_a_case_that_expects_escalations`, `weather` | `plan_ok` `1` | `0` |
| 3 | a run's seconds summed over every `MODEL_REPLY` event of the log, not only its own run id | `test_runs_that_disagree` | `(2.0, 4.0, 0.5, 3.0)` | larger, growing values |
| 4 | the percentile taken at position `ceil(q × n)` counted from 0 (no minus one) | `test_runs_that_disagree` | `p50 2.00s` | `p50 3.00s` (or an `IndexError` at p95: record which) |
| 5 | `runs` checked after the runs (`run_case`) | `test_runs_are_1_to_100`, `0` | `ValueError: runs must be 1 to 100` | another result or error |
| 6 | the command builds `OllamaModel` itself instead of calling `run.model_for` | `test_eval_run_prints_a_line_per_case_and_overall` | the pinned lines | `escalated` runs from the closed port |
| 7 | the edit button labelled `Edit` | `test_each_approval_form_says_what_it_does`, `step` | `Edit and approve` | `Edit` |
| 8 | the route problem's message includes the request (`load_cases`) | `test_a_problem_never_quotes_the_request` | no `SYNTHETIC-SECRET` | it appears |

Reasonable variations that are correct: the outcome built as a small frozen dataclass and turned into the same JSON for comparison; the percentile in a private helper; the case checks as one function per key; the command's loop printing as each case finishes.

## 6. Project rules

- Searches 1 and 2.
- An evaluation reaches only `route_request` and `plan_request`; nothing in `conductor.evals` can run a step, record an approval, or start an MCP server.
- Every case is synthetic; no message quotes a request.
- No test opens a connection; the model in tests is `ScriptedModel`.

## 7. Out of scope

Each must be absent: saved reports, digests, prompt hashes, comparisons, the answer point, the graph, approvals, steps, tools, parallel runs, changes to routing, planning, or `decide`, evaluations in `scripts/check.py`.

## 8. Progress log

The entry exists, headed `## Phase 8a: running evaluation cases (...)`, with `Tests: 744 -> <passed> (given 32)`, and each deviation it lists is real and justified.
