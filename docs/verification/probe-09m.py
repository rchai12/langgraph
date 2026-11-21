"""Probe for Phase 9m: the split command line behaves exactly as the single module did.

The oracle is the predecessor's `cli/main.py`, read from commit a9c5485 with git and loaded as its
own module. Random sessions of commands run on the old and the new app, each in a fresh data
directory with the same fixed clock, ids and scripted model; every exit code, output, error and the
stored state afterwards must agree. Run from the repository root with
.venv/bin/python docs/verification/probe-09m.py. The last line is FAILURES <n>.
"""

import importlib.util
import itertools
import os
import random
import socket
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import typer.main
import uvicorn
from typer.testing import CliRunner

from conductor import clock, ids, runtime
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply

failures = 0
rng = random.Random(13)
BEFORE = "a9c5485"


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
os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"


def ID(n: int) -> str:
    return f"{n:032x}"


PLAN = ("plan", '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}')
ANSWER = ("answer", '{"reply": "Done."}')
GROUPS = {
    "runs": ["list", "show"],
    "eval": ["run"],
    "approvals": ["list", "show", "approve", "reject", "edit"],
    "escalations": ["list", "show", "retry", "cancel"],
}
STATE = (
    ["approvals", "list", "--json"],
    ["escalations", "list", "--json"],
    ["runs", "list"],
    ["runs", "show", ID(2), "--payload"],
)
QUEUE: list[tuple[str, str]] = []
counter = itertools.count(1)
runner = CliRunner(env={"COLUMNS": "200"})
real_open = runtime.open_runtime


@contextmanager
def scripted(settings, *, model=None):
    answers = [ScriptedReply(point, ModelReply(content=text)) for point, text in QUEUE]
    QUEUE.clear()
    with real_open(settings, model=ScriptedModel(answers)) as opened:
        yield opened


runtime.open_runtime = scripted
clock.now = lambda: datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
ids.new_id = lambda: f"{next(counter):032x}"
uvicorn.run = lambda app, **options: None


def load_before():
    text = subprocess.run(
        ["git", "show", f"{BEFORE}:src/conductor/cli/main.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    path = Path(tempfile.mkdtemp()) / "main_before.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("main_before", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    chosen = probe.getsockname()[1]
    probe.close()
    return chosen


def outcome(app, step: dict, data: str) -> tuple:
    QUEUE[:] = step["queue"]
    os.environ["CONDUCTOR_DEMO"] = step["demo"]
    taken = None
    if step.get("taken"):
        taken = socket.socket()
        taken.bind(("127.0.0.1", int(os.environ["CONDUCTOR_WEB_PORT"])))
        taken.listen()
    try:
        result = runner.invoke(app, step["args"], input=step["typed"])
    finally:
        if taken is not None:
            taken.close()
    error = result.exception
    raised = None if error is None or isinstance(error, SystemExit) else type(error).__name__
    texts = (result.stdout.replace(data, "<data>"), result.stderr.replace(data, "<data>"))
    return (result.exit_code, *texts, raised)


def play(app, steps: list[dict], port: int = 8766) -> list[tuple]:
    """A session on a fresh world: each step's outcome, then the state the oracle reads back."""
    global counter
    data = tempfile.mkdtemp()
    os.environ["CONDUCTOR_DATA_DIR"] = data
    os.environ["CONDUCTOR_WEB_PORT"] = str(port)
    counter = itertools.count(1)
    seen = [outcome(app, item, data) for item in steps]
    os.environ["CONDUCTOR_DEMO"] = "true"
    state = [step(args) for args in STATE]
    return seen + [outcome(before.app, item, data) for item in state]


def step(args: list[str], *, queue=(), demo="true", typed=None, taken=False) -> dict:
    return {"args": args, "queue": list(queue), "demo": demo, "typed": typed, "taken": taken}


def base_step(demo: str) -> dict:
    approval = rng.choice([ID(4), ID(6), ID(6), ID(7)])
    escalation = rng.choice([ID(3), ID(3), ID(5)])
    group = rng.choice(list(GROUPS))
    decisions = [
        step(["approvals", "approve", approval, "--yes"], queue=[ANSWER]),
        step(["approvals", "approve", approval], typed="y\n"),
        step(["approvals", "reject", approval, "--note", "not now"]),
        step(["approvals", "edit", approval, "--args", '{"title": "Eggs"}', "--yes"]),
        step(["approvals", "edit", approval, "--args", '{"title": "Eggs"}'], typed="y\n"),
        step(["approvals", "list"]),
        step(["approvals", "show", approval]),
        step(["escalations", "retry", escalation, "--yes"]),
        step(["escalations", "retry", escalation], typed="y\n"),
        step(["escalations", "cancel", escalation, "--note", "not now"]),
    ]
    others = [
        step(["escalations", "list"]),
        step(["escalations", "show", escalation]),
        step(["resume", ID(2)], queue=[ANSWER]),
        step(["runs", "show", ID(2), "--payload"]),
        step(["ask", "demo: note Milk"], queue=[PLAN]),
        step(["eval", "run", "--runs", rng.choice(["0", "101"])]),
        step(["eval", "run", "--cases", "nowhere/cases"]),
        step(["web"], taken=rng.random() < 0.5),
        step([group, "--help"]),
        step([group, rng.choice(GROUPS[group]), "--help"]),
        step(["--help"]),
    ]
    chosen = rng.choice(decisions if rng.random() < 0.7 else others)
    chosen["demo"] = demo
    if chosen["typed"] is not None and rng.random() < 0.4:
        chosen["typed"] = "n\n"
    return chosen


def one_change(chosen: dict) -> dict:
    """The base step, or a copy with one change to its words, its typed answer or its replies."""
    args = list(chosen["args"])
    kinds = ["none", "none", "wrong_id", "drop"]
    if args[-1] in ("list", "show") or args[0] in ("ask", "resume") or args[1:2] == ["show"]:
        kinds.append("json")
    if args[0] in ("approvals", "escalations") and args[1] not in ("list", "show"):
        kinds += ["no_resume", "no_resume"]
    if "--args" in args:
        kinds += ["bad_args", "bad_args"]
    if chosen["typed"] is not None:
        kinds += ["no", "no"]
    if rng.random() < 0.1:
        kinds = ["flag"]
    kind = rng.choice(kinds)
    if kind == "json":
        args.append("--json")
    elif kind == "no_resume":
        args.append("--no-resume")
    elif kind == "drop" and len(args) > 1:
        args.pop()
    elif kind == "wrong_id" and len(args) > 2:
        args[2] = rng.choice(["nope", ID(99), "x" * 33])
    elif kind == "bad_args" and "--args" in args:
        args[args.index("--args") + 1] = rng.choice(["[1]", "{bad", '{"title": ""}', '{"x": 1}'])
    elif kind == "no":
        return {**chosen, "typed": rng.choice(["n\n", ""])}
    elif kind == "flag":
        args.append("--bogus")
    return {**chosen, "args": args}


def session() -> list[dict]:
    start = rng.choice(["empty", "plan", "step", "step", "escalation", "escalation"])
    demo = "false" if start == "escalation" else "true"
    steps = []
    if start in ("plan", "step"):
        steps.append(step(["ask", "demo: note Milk"], queue=[PLAN], demo=demo))
    if start == "step":
        steps.append(step(["approvals", "approve", ID(4), "--yes"]))
    if start == "escalation":
        steps.append(step(["ask", "Say hi back to me"], demo=demo))
    for _ in range(rng.randint(1, 3)):
        steps.append(one_change(base_step(demo)))
    return steps


ASK_PLAN = step(["ask", "demo: note Milk"], queue=[PLAN])
TO_STEP = [ASK_PLAN, step(["approvals", "approve", ID(4), "--yes"])]
ASK_HI = step(["ask", "Say hi back to me"], demo="false")
EGGS = '{"title": "Eggs"}'
# Sessions that force every decision path once, before the random ones.
FORCED = [
    [ASK_PLAN, step(["approvals", "approve", ID(4)], typed="n\n")],
    [ASK_PLAN, step(["approvals", "approve", ID(4)], typed="y\n")],
    [
        ASK_PLAN,
        step(["approvals", "approve", ID(4), "--yes", "--no-resume"]),
        step(["resume", ID(2)]),
    ],
    [ASK_PLAN, step(["approvals", "edit", ID(4), "--args", EGGS, "--yes"])],
    [*TO_STEP, step(["approvals", "edit", ID(6), "--args", EGGS, "--yes"], queue=[ANSWER])],
    [*TO_STEP, step(["approvals", "edit", ID(6), "--args", EGGS], typed="n\n")],
    [*TO_STEP, step(["approvals", "edit", ID(6), "--args", EGGS, "--no-resume"], typed="y\n")],
    [*TO_STEP, step(["approvals", "edit", ID(6), "--args", "[1]"])],
    [*TO_STEP, step(["approvals", "edit", ID(6), "--args", '{"title": ""}', "--yes"])],
    [*TO_STEP, step(["approvals", "reject", ID(6), "--note", "not now"])],
    [*TO_STEP, step(["approvals", "approve", ID(6), "--yes"], queue=[ANSWER])],
    [ASK_HI, step(["escalations", "retry", ID(3)], typed="n\n", demo="false")],
    [ASK_HI, step(["escalations", "retry", ID(3), "--yes"], demo="false")],
    [ASK_HI, step(["escalations", "retry", ID(3), "--yes", "--no-resume"], demo="false")],
    [ASK_HI, step(["escalations", "cancel", ID(3), "--note", "not now"], demo="false")],
    [ASK_HI, step(["escalations", "cancel", ID(3), "--no-resume"], demo="false")],
    [ASK_HI, step(["escalations", "show", ID(3), "--json"]), step(["resume", ID(2), "--json"])],
    [step(["ask", "demo: note Milk", "--json"], queue=[PLAN]), step(["approvals", "show", ID(4)])],
    [step(["web"]), step(["web"], taken=True)],
]

before = load_before()
# The oracle on known cases: the predecessor asks, stops at the plan and records the approval.
known = play(
    before.app,
    [
        step(["ask", "demo: note Milk"], queue=[PLAN]),
        step(["approvals", "approve", ID(4)], typed="n\n"),
        step(["approvals", "approve", ID(4), "--yes", "--no-resume"]),
    ],
)
assert known[0][0] == 0 and known[0][1].startswith(f"approval {ID(4)}  plan  pending\n")
assert known[1][1].endswith("Approve? [y/N]: n\nNothing recorded.\n")
assert known[2][:3] == (0, f"Approved {ID(4)}.\n", "")
assert known[3][0] == 0 and ID(4) not in known[3][1]


def check_layout() -> bool:
    from conductor.cli import main

    root = typer.main.get_command(main.app)
    homes = {
        root.commands["web"].callback.__module__,
        root.commands["runs"].commands["show"].callback.__module__,
        root.commands["eval"].commands["run"].callback.__module__,
        root.commands["approvals"].commands["edit"].callback.__module__,
        root.commands["escalations"].commands["retry"].callback.__module__,
    }
    return homes == {
        "conductor.cli.web",
        "conductor.cli.runs",
        "conductor.cli.evals",
        "conductor.cli.approvals",
        "conductor.cli.escalations",
    }


def check_help() -> bool:
    from conductor.cli import main

    paths = [[], *([group] for group in GROUPS)]
    paths += [[group, name] for group, names in GROUPS.items() for name in names]
    paths += [[name] for name in ("doctor", "ask", "resume", "web")]
    for path in paths:
        old = play(before.app, [step([*path, "--help"])])[0]
        if play(main.app, [step([*path, "--help"])])[0] != old:
            return False
    return True


def check_sessions() -> bool:
    from conductor.cli import main

    reached = {"recorded": 0, "nothing": 0, "refused": 0, "usage": 0, "edited": 0, "retry": 0}
    agree = True
    for steps in FORCED + [session() for _ in range(300)]:
        port = free_port()
        old = play(before.app, steps, port)
        agree &= play(main.app, steps, port) == old
        for code, out, err, _ in old[: len(steps)]:
            reached["recorded"] += out.startswith(("Approved ", "Rejected ", "Cancelled "))
            reached["nothing"] += out.endswith("Nothing recorded.\n")
            reached["refused"] += code == 1 and err.startswith("Error:")
            reached["usage"] += code == 2
            reached["edited"] += "with edited arguments" in out
            reached["retry"] += out.startswith(("Retry recorded", "escalation "))
    print(f"     reached {reached}")
    return agree and min(reached.values()) >= 5


section("the command groups live in their own modules", check_layout)
section("every --help text is as before", check_help)
section(
    "19 forced and 300 random sessions: outputs, exit codes and stored state as before",
    check_sessions,
)

print(f"FAILURES {failures}")
