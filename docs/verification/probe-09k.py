"""Probe for Phase 9k: the split graph runs as before, and a failed step records its cause.

Run from the repository root with .venv/bin/python docs/verification/probe-09k.py.
The last line is FAILURES <n>.
"""

import json
import os
import random
import tempfile
from collections.abc import Callable
from pathlib import Path

failures = 0
rng = random.Random(11)


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def section(label: str, body: Callable[[], bool]) -> None:
    try:
        ok = body()
    except Exception as error:  # noqa: BLE001
        print(f"     {label}: raised {type(error).__name__}")
        ok = False
    check(label, ok)


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()

# The oracle's own tables: written from the spec, never read from the code.
EFFECTS = {"echo": "read", "note": "write", "delegate": "implement"}
ARGS = {"echo": {"text": "hi"}, "note": {"title": "Milk"}, "delegate": {"task": "Sweep"}}
GOOD = {"echo": {"text": "hi"}, "note": {"note_id": "e" * 32}, "delegate": {"summary": "done"}}
CODES = ("tool_error", "no_command", "start_failed", "timeout", "closed", "no_result", "too_large")
NOT_DONE = {"no_command", "start_failed", "tool_error"}
ALL_EFFECTS = ("read", "propose", "write", "implement")
NODE_NAMES = (
    "route",
    "plan",
    "ask_plan",
    "ask_step",
    "wait_approval",
    "run_step",
    "answer",
    "record_escalation",
    "wait_escalation",
    "finish",
)
RUN = "b" * 32


def oracle_fields(effect: str, code: str | None) -> dict:
    unknown = effect != "read" and code not in NOT_DONE
    return {"code": code, "effect": effect, "unknown_outcome": unknown}


def oracle_detail(number: int, name: str, code: str | None) -> str:
    if code == "invalid_result":
        return f"step {number} demo.{name}: the result does not fit the action"
    reason = "the step failed" if code is None else f"the step failed ({code})"
    return f"step {number} demo.{name}: {reason}"


def needs_approval(name: str) -> bool:
    return EFFECTS[name] != "read"


# The oracle on known cases.
assert oracle_fields("write", "closed")["unknown_outcome"] is True
assert oracle_fields("write", "tool_error")["unknown_outcome"] is False
assert oracle_fields("read", None)["unknown_outcome"] is False
assert oracle_fields("implement", None)["unknown_outcome"] is True
assert oracle_detail(2, "note", "timeout") == "step 2 demo.note: the step failed (timeout)"
assert oracle_detail(1, "echo", None) == "step 1 demo.echo: the step failed"


def check_fields() -> bool:
    from conductor.graph.steps import failure_fields

    agree = True
    for effect in ALL_EFFECTS:
        for code in (*CODES, "invalid_result", None):
            agree &= failure_fields(effect, code) == oracle_fields(effect, code)
    return agree


def check_nodes() -> bool:
    from conductor.domains import demo
    from conductor.events import EventLog
    from conductor.graph import nodes, supervisor
    from conductor.llm.scripted import ScriptedModel
    from conductor.registry import Registry
    from conductor.store import Store

    folder = Path(tempfile.mkdtemp())
    services = nodes.Services(
        registry=Registry((demo.DOMAIN,)),
        store=Store(folder / "conductor.db"),
        log=EventLog(folder / "runs"),
        model=ScriptedModel([]),
        model_name="m",
        runner=None,
    )
    built = nodes.build_nodes(services)
    names_ok = tuple(built) == NODE_NAMES
    homes = {node.__module__ for node in built.values()}
    left = [name for name in vars(supervisor) if name.lstrip("_") in NODE_NAMES]
    return names_ok and homes == {"conductor.graph.nodes"} and left == []


class Runner:
    """Fails the first run of one step, with a code or a result that does not fit."""

    def __init__(self, failing: int | None, failure: str | None) -> None:
        self.failing = failing
        self.failure = failure
        self.calls: list[str] = []
        self.failed = False

    def run(self, action, args):
        from conductor.graph.supervisor import StepFailed

        self.calls.append(action.name)
        if not self.failed and len(self.calls) == self.failing:
            self.failed = True
            if self.failure == "invalid_result":
                return {}
            raise StepFailed("SYNTHETIC-SECRET", code=self.failure)
        return GOOD[action.name]


def one_run(names: list[str], failing: int | None, failure: str | None) -> tuple[bool, bool]:
    from langgraph.checkpoint.memory import InMemorySaver

    from conductor.decisions import answer_escalation, decide_approval
    from conductor.domains import demo
    from conductor.events import EventKind, EventLog
    from conductor.graph.supervisor import Services, build_graph, resume_run, start_run
    from conductor.llm.model import ModelReply
    from conductor.llm.scripted import ScriptedModel, ScriptedReply
    from conductor.registry import Registry
    from conductor.store import Store

    folder = Path(tempfile.mkdtemp())
    store, log = Store(folder / "conductor.db"), EventLog(folder / "runs")
    registry = Registry((demo.DOMAIN,))
    plan = json.dumps({"steps": [{"action": name, "args": ARGS[name]} for name in names]})
    replies = [("plan", plan), ("answer", '{"reply": "Done."}')]
    runner = Runner(failing, failure)
    graph = build_graph(
        Services(
            registry=registry,
            store=store,
            log=log,
            model=ScriptedModel([ScriptedReply(p, ModelReply(content=c)) for p, c in replies]),
            model_name="m",
            runner=runner,
        ),
        InMemorySaver(),
    )
    state = start_run(graph, "demo: do it", run_id=RUN, log=log)
    approvals = 0
    details: list[str] = []
    for _ in range(40):
        if state.status != "waiting":
            break
        if state.approval_id is not None:
            approvals += 1
            decide_approval(
                store, registry, state.approval_id, "approve", channel="terminal", decided_by="o"
            )
        else:
            details.append(store.escalation(state.escalation_id).escalation.detail)
            answer_escalation(
                store, state.escalation_id, "retry", channel="terminal", decided_by="o"
            )
        state = resume_run(graph, store, RUN)
    events = log.read(RUN)
    errors = [(e.node, e.payload) for e in events if e.kind == EventKind.ERROR]
    visits = list(range(1, len(names) + 1))
    if failing is not None:
        visits.insert(failing, failing)
    want_calls = [names[number - 1] for number in visits]
    want_approvals = int(any(needs_approval(name) for name in names)) + sum(
        needs_approval(names[number - 1]) for number in visits
    )
    if failing is None:
        want_errors, want_details, unknown = [], [], False
    else:
        name = names[failing - 1]
        fields = oracle_fields(EFFECTS[name], failure)
        problems = [{"loc": "note_id", "code": "missing"}] if failure == "invalid_result" else []
        if failure == "invalid_result" and name != "note":
            loc = {"echo": "text", "delegate": "summary"}[name]
            problems = [{"loc": loc, "code": "missing"}]
        payload = {"step": failing, "error": "tool_error", **fields, "problems": problems}
        want_errors = [("run_step", payload)]
        want_details = [oracle_detail(failing, name, failure)]
        unknown = fields["unknown_outcome"]
    results = sum(1 for e in events if e.kind == EventKind.TOOL_RESULT)
    secret = "SYNTHETIC-SECRET" not in (folder / "runs" / f"{RUN}.jsonl").read_text()
    ok = (
        state.status == "done"
        and errors == want_errors
        and details == want_details
        and runner.calls == want_calls
        and approvals == want_approvals
        and results == len(names)
        and secret
    )
    return ok, unknown


def check_runs() -> bool:
    agree = True
    reached = {True: 0, False: 0, "clean": 0}
    for _ in range(120):
        names = [rng.choice(list(EFFECTS)) for _ in range(rng.randint(1, 3))]
        if rng.random() < 0.15:
            failing, failure = None, None
        else:
            failing = rng.randint(1, len(names))
            failure = rng.choice([*CODES, "invalid_result", None])
        ok, unknown = one_run(names, failing, failure)
        agree &= ok
        reached["clean" if failing is None else unknown] += 1
    return agree and reached[True] >= 25 and reached[False] >= 25 and reached["clean"] >= 5


section("36 effect and code pairs: unknown outcome exactly as the table says", check_fields)
section("build_nodes makes the ten nodes in order, all in graph/nodes.py", check_nodes)
section("120 random runs: causes, details, approvals and retries as before", check_runs)

print(f"FAILURES {failures}")
