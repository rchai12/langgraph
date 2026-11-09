# Verify Phase 5b: planning and answering

Spec: `docs/phases/phase-05b-planning-and-answering.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 5b` on your own report.

The coder created `conductor.planning.plan` and `conductor.planning.answer` (both critical), copied the two given prompt templates and two test files (20 tests), added both modules to the critical modules, and wrote `tests/unit/test_plan_more.py` and `tests/unit/test_answer_more.py`.

## 1. Gates

N is `472`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 492 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `planning/plan.py` and `planning/answer.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/planning/*.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_plan.py tests/unit/test_answer.py --no-cov` | exactly `20 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 5b` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/contracts src/conductor/plancheck.py src/conductor/llm src/conductor/registry.py src/conductor/routing src/conductor/domains src/conductor/events.py tests/support.py tests/unit/test_plancheck.py tests/unit/test_route.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/planning/plan.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (dataclasses|typing|pydantic|conductor import plancheck|conductor\.contracts|conductor\.events|conductor\.llm\.decide|conductor\.llm\.model|conductor\.llm\.points|conductor\.plancheck|conductor\.registry|conductor\.routing\.route)( |$)"`
2. `git grep --untracked -n -E "^(from|import) " -- src/conductor/planning/answer.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (collections\.abc|dataclasses|pydantic|conductor\.contracts|conductor\.contracts\.base|conductor\.contracts\.plans|conductor\.events|conductor\.llm\.decide|conductor\.llm\.model|conductor\.llm\.points|conductor\.routing\.route)( |$)"`
3. `git grep --untracked -n -E "get_settings|clock|new_id|OllamaModel|urllib|from conductor\.plancheck import .*check_plan" -- src/conductor/planning`
4. `git grep --untracked -n -E "langgraph|langchain" -- src pyproject.toml`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_plan_point_and_its_prompt`, `test_a_domain_of_one_action`; the coder's fields and order tests; probe "the planner's schema offers exactly the domain's actions" | pass; ok |
| R2 | `test_a_model_that_cannot_answer_escalates` (plan), `test_a_route_to_an_unregistered_domain_is_a_mistake`, `test_the_output_holds_each_action_to_its_own_arguments`; the coder's `ScriptError` and `model_info` tests | pass |
| R3 | `test_a_plan`, `test_an_empty_plan_escalates`, `test_a_check_in_the_arguments_counts_as_invalid_output`, `test_a_plan_the_check_refuses_escalates`; the coder's defaults and eight-step tests; probes "every planner reply ...", "every plan goes through plancheck.check_plan exactly once" | pass; ok |
| R4 | `test_an_answer_needs_1_to_8_results`, `test_the_request_is_checked_as_in_routing`; the coder's limits and order tests | pass |
| R5 | `test_the_answer_point_and_its_prompt`, `test_an_answer`, `test_a_model_that_cannot_answer_escalates` (answer) | pass |
| R6 | `test_a_blank_reply_escalates`; the coder's 2000 and 2001 tests; probe "a reply is kept exactly when ..." | pass; ok |
| R7 | searches 1 to 3 | no output |
| R8 | the coder's `SYNTHETIC-SECRET` test; probe "no escalation carries the request or the reply's text"; read every `raise` and `Escalation(` in both modules | pass; ok; constant texts and ids only |
| R9 | the event checks of `test_a_plan` and `test_an_answer`; the coder's routed-request test | pass |
| R10 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It plays 1500 random planner replies against its own reading of the demo arguments (which checks itself on known cases before it starts), replaces `plancheck.check_plan` with a spy for one check, and plays 500 answer replies. If it stops at one of its own `assert` lines, the probe is wrong, not the code: report that under "For the architect" and do not count it as a finding.

```python
"""Independent probe for Phase 5b. Run from the repository root with .venv/bin/python."""

import json
import random
import re
import tempfile
from dataclasses import replace
from pathlib import Path

from conductor import plancheck
from conductor.contracts import Escalation, Route
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.planning.answer import Answered, StepOutcome, answer_request
from conductor.planning.plan import Planned, plan_point, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(11)
folder = Path(tempfile.mkdtemp())
REGISTRY = Registry((demo.DOMAIN,))
ROUTE = Route(domain="demo", decided_by="rule", rule_id="demo.prefix")
TAG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DEFAULTS = {"echo": {}, "note": {"body": "", "tags": []}, "delegate": {"max_minutes": 10}}
counter = 0


def run_id() -> str:
    global counter
    counter += 1
    return f"{counter:032x}"


def text_ok(value: object, low: int, high: int) -> bool:
    return isinstance(value, str) and low <= len(value) <= high


def args_ok(action: str, args: dict) -> bool:
    """The probe's own reading of the demo arguments, independent of the code."""
    allowed = {
        "echo": {"text"},
        "note": {"title", "body", "tags"},
        "delegate": {"task", "max_minutes"},
    }[action]
    if not set(args) <= allowed:
        return False
    if action == "echo":
        return text_ok(args.get("text"), 1, 200)
    if action == "note":
        tags = args.get("tags", [])
        return (
            text_ok(args.get("title"), 1, 80)
            and text_ok(args.get("body", ""), 0, 2000)
            and isinstance(tags, list)
            and len(tags) <= 5
            and all(isinstance(t, str) and TAG.fullmatch(t) for t in tags)
        )
    minutes = args.get("max_minutes", 10)
    return (
        text_ok(args.get("task"), 1, 500)
        and type(minutes) is int
        and 1 <= minutes <= 60
    )


def reply_ok(steps: list) -> bool:
    return len(steps) <= 8 and all(
        s["action"] in DEFAULTS and args_ok(s["action"], s["args"]) for s in steps
    )


# The probe's checker checks itself first, so a bug in it cannot pass for a bug in the code.
assert args_ok("note", {"title": "Milk", "tags": ["shopping"]})
assert not args_ok("note", {"title": "x" * 81})
assert not args_ok("note", {"title": "Milk", "tags": ["Shop"]})
assert not args_ok("echo", {"text": "hi", "to": "bob"})
assert not args_ok("delegate", {"task": "t", "max_minutes": True})
assert args_ok("delegate", {"task": "t", "max_minutes": 60})
assert reply_ok([]) and not reply_ok([{"action": "echo", "args": {"text": "a"}}] * 9)
assert not reply_ok([{"action": "send", "args": {}}])


def random_args(action: str) -> dict:
    pick = rng.random
    if action == "echo":
        args = {"text": "e" * rng.choice([0, 1, 5, 200, 201])}
    elif action == "note":
        args = {"title": "t" * rng.choice([0, 1, 40, 80, 81])}
        if pick() < 0.5:
            args["body"] = "b" * rng.choice([0, 10, 2000, 2001])
        if pick() < 0.5:
            args["tags"] = rng.choice([[], ["home"], ["Home"], ["a", "b", "c", "d", "e", "f"]])
    elif action == "delegate":
        args = {"task": "k" * rng.choice([0, 1, 500, 501])}
        if pick() < 0.5:
            args["max_minutes"] = rng.choice([0, 1, 60, 61, "5", True])
    else:
        args = {}
    if pick() < 0.1:
        args["extra"] = 1
    return args


def scripted(point: str, content: str) -> ScriptedModel:
    return ScriptedModel([ScriptedReply(point, ModelReply(content=content))])


# 1. every planner reply
ok = True
seen = {"planned": 0, "empty": 0, "invalid": 0}
for _ in range(1500):
    steps = []
    for _ in range(rng.choice([0, 1, 2, 3, 8, 9])):
        action = rng.choice(["echo", "note", "delegate", "echo", "note", "send"])
        steps.append({"action": action, "args": random_args(action)})
    model = scripted("plan", json.dumps({"steps": steps}))
    log = EventLog(folder)
    rid = run_id()
    found = plan_request(
        Routed(ROUTE, "Do it"), REGISTRY, model=model, model_name="m", log=log, run_id=rid
    )
    if not reply_ok(steps):
        ok &= isinstance(found, Escalation) and found.kind == "invalid_model_output"
        seen["invalid"] += 1
    elif not steps:
        ok &= isinstance(found, Escalation) and found.kind == "invalid_plan"
        ok &= found.problems == ()
        seen["empty"] += 1
    else:
        expected = [
            (f"demo.{s['action']}", DEFAULTS[s["action"]] | s["args"]) for s in steps
        ]
        ok &= isinstance(found, Planned)
        ok &= [(s.action, s.args) for s in found.plan.steps] == expected
        ok &= [c.number for c in found.steps] == list(range(1, len(steps) + 1))
        seen["planned"] += 1
    ok &= [e.kind for e in log.read(rid)][:2] == [EventKind.MODEL_REQUEST, EventKind.MODEL_REPLY]
    ok &= all(e.node == "plan" for e in log.read(rid))
check(f"every planner reply is planned, or escalates, as the arguments say ({seen})", ok)

# 2. the schema follows the domain's actions
ok = True
for _ in range(50):
    chosen = rng.sample(demo.DOMAIN.actions, rng.randint(1, 3))
    domain = replace(demo.DOMAIN, actions=tuple(chosen))
    schema = plan_point(domain).output.model_json_schema()
    mapping = schema["properties"]["steps"]["items"]["discriminator"]["mapping"]
    ok &= list(mapping) == sorted(a.name for a in chosen)
    ok &= [x["$ref"] for x in schema["properties"]["steps"]["items"]["oneOf"]] == [
        f"#/$defs/{a.name}_step" for a in chosen
    ]
check("the planner's schema offers exactly the domain's actions, in order", ok)

# 3. the plan reaches the plan check unchanged, once
seen_plans = []
real_check = plancheck.check_plan


def spy(plan, route, registry):
    seen_plans.append((plan, route))
    return real_check(plan, route, registry)


plancheck.check_plan = spy
ok = True
for _ in range(100):
    steps = [{"action": "echo", "args": {"text": f"t{rng.randint(1, 99)}"}}]
    seen_plans.clear()
    found = plan_request(
        Routed(ROUTE, "Echo"),
        REGISTRY,
        model=scripted("plan", json.dumps({"steps": steps})),
        model_name="m",
        log=EventLog(folder),
        run_id=run_id(),
    )
    ok &= isinstance(found, Planned) and seen_plans == [(found.plan, ROUTE)]
plancheck.check_plan = real_check
check("every plan goes through plancheck.check_plan exactly once", ok)

# 4. answers
ok = True
for _ in range(500):
    reply = rng.choice(["", " ", "\n\t", "Done.", "x" * 2000, "x" * 2001, " ok "])
    found = answer_request(
        "Echo hi",
        (StepOutcome(step=1, action="demo.echo", output={"text": "hi"}),),
        model=scripted("answer", json.dumps({"reply": reply})),
        model_name="m",
        log=EventLog(folder),
        run_id=run_id(),
    )
    good = 1 <= len(reply) <= 2000 and reply.strip() != ""
    if good:
        ok &= isinstance(found, Answered) and found.reply == reply
    else:
        ok &= isinstance(found, Escalation) and found.kind == "invalid_model_output"
check("a reply is kept exactly when it has 1 to 2000 characters and is not blank", ok)

# 5. no request text in any escalation
ok = True
for i in range(200):
    secret = f"SYNTHETIC-SECRET-{i}"
    content = rng.choice(
        [
            '{"steps": []}',
            '{"steps": [{"action": "send", "args": {}}]}',
            f'{{"steps": [{{"action": "echo", "args": {{"text": "{secret}", "x": 1}}}}]}}',
            "not json",
        ]
    )
    found = plan_request(
        Routed(ROUTE, f"Please {secret}"),
        REGISTRY,
        model=scripted("plan", content),
        model_name="m",
        log=EventLog(folder),
        run_id=run_id(),
    )
    ok &= isinstance(found, Escalation) and secret not in found.model_dump_json()
check("no escalation carries the request or the reply's text", ok)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the union not discriminated (`plan_output`) | `test_the_output_holds_each_action_to_its_own_arguments`, the empty title | one problem at `steps.0.note.args.title` | several problems |
| 2 | `Field(min_length=1)` on the steps (`plan_output`) | `test_an_empty_plan_escalates` | `invalid_plan` | `invalid_model_output` |
| 3 | the step type named after the action without `_step` (`plan_output`) | `test_the_plan_point_and_its_prompt` | the pinned `$defs` | other names |
| 4 | the plan's actions left without the domain (`plan_request`) | `test_a_plan` | `demo.echo` | a `ValidationError` from `Step` |
| 5 | `exclude_defaults=True` in the args dump (`plan_request`) | `test_a_plan`, the note step | `"body": ""` present | absent |
| 6 | `check_plan` imported by name (`plan_request`) | `test_a_plan_the_check_refuses_escalates` | `invalid_plan` | `Planned` |
| 7 | `InvalidModelOutput` passed through instead of escalated (`plan_request`) | `test_the_output_holds_each_action_to_its_own_arguments`, `send` | an `invalid_model_output` escalation | `InvalidModelOutput` raised |
| 8 | the blank check removed (`AnswerOutput`) | `test_a_blank_reply_escalates`, `" \n "` | `value_error` | `Answered` |
| 9 | the results counted after the model is asked (`answer_request`) | `test_an_answer_needs_1_to_8_results`, `0` | `RESULTS_MESSAGE` | `AssertionError("the model was asked")` |

Reasonable variations that are correct: the step types built in a private helper and cached per domain; `typing.Union[...]` written as `Union.__getitem__`; the plan steps built in a comprehension; `Answered` and `Planned` with `slots=True`; the request check shared through a private function.

## 6. Project rules

- Searches 1 to 4.
- Each of `plan_request` and `answer_request` calls `decide` at most once and catches only `InvalidModelOutput`, `ModelUnavailable`, and (`plan_request`) `PlanRejected`.
- Every escalation's `detail` is a Design text plus a decision id, or `escalation_for`'s; nothing echoes the request, the arguments, or the reply.
- No real data: tests and the probe build their own domains and replies.

## 7. Out of scope

Each must be absent: a graph or node, `interrupt`, approval requests, running a step, results passed between steps, replanning or repair, a limit on result size, changes to contracts, `plancheck`, `decide`, `points`, the registry, routing, or the demo domain, new event or escalation kinds, a dependency, settings read in `conductor.planning`.

## 8. Progress log

The entry exists, headed `## Phase 5b: planning and answering (...)`, with `Tests: 472 -> <passed> (given 20)`, and each deviation it lists is real and justified.
