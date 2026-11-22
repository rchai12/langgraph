"""Phase 9w probe: the refactored functions answer exactly as they did at BASE.

Run from the repository root with .venv/bin/python docs/verification/probe-09w.py.
The last line is FAILURES <n>.

The oracle is each function as it was at BASE, loaded from git under another module name.
Each check gives the old and the new function the same inputs and compares the results,
or the exception type and message. The inputs are a valid base with at most one change.
route_request is left to its tests and to the critical-module coverage gate.
"""

import importlib
import os
import random
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable
from pathlib import Path

BASE = "a838223"
ROOT = Path.cwd()
TRIALS = 2000

failures = 0
rng = random.Random(9)


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


def old_module(path: str, name: str) -> types.ModuleType:
    """The module as it was at BASE, registered as conductor._old_<name>."""
    source = subprocess.run(
        ["git", "show", f"{BASE}:{path}"], capture_output=True, text=True, check=True
    ).stdout
    module = types.ModuleType(f"conductor._old_{name}")
    module.__file__ = f"<{BASE}:{path}>"
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def outcome(function: Callable[..., object], *args: object) -> str:
    try:
        return "value " + repr(function(*args))
    except Exception as error:  # noqa: BLE001
        return f"raises {type(error).__name__} {error}"


def one_change(lines: list[str]) -> list[str]:
    """A copy of lines with one line dropped, doubled, blanked, swapped or edited."""
    changed = list(lines)
    if not changed:
        return [""]
    at = rng.randrange(len(changed))
    move = rng.choice(["drop", "double", "blank", "swap", "edit", "edit"])
    if move == "drop":
        del changed[at]
    elif move == "double":
        changed.insert(at, changed[at])
    elif move == "blank":
        changed[at] = ""
    elif move == "swap" and at + 1 < len(changed):
        changed[at], changed[at + 1] = changed[at + 1], changed[at]
    elif move == "edit":
        line = changed[at]
        spot = rng.randrange(len(line) + 1)
        piece = rng.choice(["", " ", "x", "0", "-", "#", ":", "`", "  - "])
        changed[at] = line[:spot] + piece + line[spot + rng.choice([0, 1]) :]
    return changed


# The oracle's own helper on known cases.
assert outcome(int, "3") == "value 3"
assert outcome(int, "x").startswith("raises ValueError")
assert one_change([]) == [""]
assert all(len(one_change(["a", "b"])) in (1, 2, 3) for _ in range(50))


def differ(label: str, pairs: list[tuple[str, str]]) -> bool:
    bad = [index for index, (old, new) in enumerate(pairs) if old != new]
    for index in bad[:3]:
        print(f"     {label} case {index}: old {pairs[index][0][:90]!r}")
        print(f"     {label} case {index}: new {pairs[index][1][:90]!r}")
    return bad == []


def messages(answer: str) -> list[str]:
    """The message of each Problem in an answer's repr."""
    return [part.split("'")[0] for part in answer.split("message='")[1:]]


def reviews() -> list[tuple[str, str]]:
    found = sorted((ROOT / "docs" / "reviews").glob("*.md"))
    return [(path.read_text(encoding="utf-8"), f"docs/reviews/{path.name}") for path in found]


def same_reviews() -> bool:
    new = importlib.import_module("conductor.reports")
    old = old_module("src/conductor/reports.py", "reports")
    pairs, kinds = [], set()
    corpus = reviews()
    for trial in range(TRIALS):
        text, path = corpus[trial % len(corpus)]
        lines = text.split("\n") if trial < len(corpus) else one_change(text.split("\n"))
        sent = "\n".join(lines)
        was = outcome(old.parse_review, sent, path)
        pairs.append((was, outcome(new.parse_review, sent, path)))
        kinds.add(messages(was)[0] if messages(was) else "accepted")
    print(f"     {len(corpus)} reviews, {len(kinds)} distinct first answers")
    return differ("review", pairs) and len(kinds) >= 15


def same_progress() -> bool:
    new = importlib.import_module("conductor.reports")
    old = old_module("src/conductor/reports.py", "reports_progress")
    text = (ROOT / "docs" / "progress.md").read_text(encoding="utf-8")
    entries = text.split("\n## ")
    pairs, kinds = [], set()
    for trial in range(TRIALS):
        start = rng.randrange(1, len(entries) - 2)
        chunk = "## " + "\n## ".join(entries[start : start + 2])
        lines = chunk.split("\n") if trial % 10 == 0 else one_change(chunk.split("\n"))
        sent = "\n".join(lines)
        was = outcome(old.parse_progress, sent)
        pairs.append((was, outcome(new.parse_progress, sent)))
        kinds |= set(messages(was))
    print(f"     {len(kinds)} distinct problem messages")
    return differ("progress", pairs) and len(kinds) >= 8


OUTPUTS = [
    "",
    "1 passed",
    "E   assert 1 == 2\n1 failed",
    "tests/unit/test_x.py:12: AssertionError: boom\nE   assert 1 == 2",
    "ERROR tests/unit/test_x.py - ImportError: no module\nE   ImportError: no module",
    "E   " + "y" * 300,
    "nothing useful",
]


def same_verdicts() -> bool:
    new = importlib.import_module("conductor.spotcheck")
    old = old_module("src/conductor/spotcheck.py", "spotcheck")
    cases = [(text, code) for text in OUTPUTS for code in range(-1, 8)]
    pairs = [(outcome(old.verdict, *case), outcome(new.verdict, *case)) for case in cases]
    answers = {old for old, _new in pairs}
    print(f"     {len(cases)} cases, {len(answers)} distinct answers")
    return differ("verdict", pairs) and len(answers) >= 6


def same_actions() -> bool:
    new = importlib.import_module("conductor.registry")
    old = old_module("src/conductor/registry.py", "registry")
    demo = importlib.import_module("conductor.domains.demo")
    contracts = importlib.import_module("conductor.contracts")
    base = demo.DOMAIN.actions[0]
    values = {
        "name": ["echo", "Echo", "", "a" * 80, "note", "x-y"],
        "description": ["", "d", "d" * 200, "d" * 201],
        "kind": ["tool", "agent", "other"],
        "target": ["demo", "", "Bad Target", "a.b"],
        "effect": ["read", "propose", "write", "implement", "delete"],
        "args": [base.args, contracts.Contract, dict, None],
        "result": [base.result, contracts.Contract, int],
        "server": [None, "files", "other"],
    }
    pairs, kinds = [], set()
    for _ in range(TRIALS):
        field = rng.choice(sorted(values))
        action = new.Action(**{**base.__dict__, field: rng.choice(values[field])})
        seen = rng.choice([set(), {"note"}, {action.name}])
        servers = rng.choice([set(), {"files"}])
        domain = rng.choice(["demo", "other"])
        was = outcome(old._check_action, domain, action, set(seen), set(servers))
        kinds.add(was.split(":")[-1][:30])
        pairs.append((was, outcome(new._check_action, domain, action, set(seen), set(servers))))
    print(f"     {len(kinds)} distinct answers")
    return differ("action", pairs) and len(kinds) >= 12


def same_state_text() -> bool:
    new = importlib.import_module("conductor.cli.common")
    old = old_module("src/conductor/cli/common.py", "common")
    for module in (new, old):
        module.request_lines = lambda stored: [f"approval {stored}"]
        module.escalation_lines = lambda stored: [f"escalation {stored}"]
    store = types.SimpleNamespace(approval=lambda key: key, escalation=lambda key: key)
    opened = types.SimpleNamespace(store=store)
    pairs = []
    for status in ["waiting", "done", "rejected", "cancelled", "failed", "running"]:
        for approval in [None, "a" * 32]:
            for escalation in [None, "e" * 32]:
                for note in [None, "", "a note"]:
                    found = types.SimpleNamespace(
                        status=status,
                        approval_id=approval,
                        escalation_id=escalation,
                        run_id="r" * 32,
                        reply="the reply",
                        note=note,
                        stopped_at="plan",
                    )
                    case = (opened, found)
                    pairs.append((outcome(old.state_text, *case), outcome(new.state_text, *case)))
    print(f"     {len(pairs)} cases, {len({old for old, _ in pairs})} distinct answers")
    return differ("state", pairs) and len({old for old, _ in pairs}) >= 6


section(
    "parse_review answers as at BASE on every review and 2000 one-change variants", same_reviews
)
section("parse_progress answers as at BASE on 2000 entry pairs and variants", same_progress)
section("spotcheck.verdict answers as at BASE on every output and exit code", same_verdicts)
section("registry._check_action answers as at BASE on 2000 one-change actions", same_actions)
section("cli.common.state_text answers as at BASE for every status shape", same_state_text)


def under_limits() -> bool:
    test = "tests/unit/test_complexity_limits.py"
    command = [sys.executable, "-m", "pytest", test, "--no-cov", "-q", "-p", "no:cacheprovider"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"     {done.stdout.strip().splitlines()[-1]}")
    return done.returncode == 0


section("the five files have no function over the limits", under_limits)

print(f"FAILURES {failures}")
