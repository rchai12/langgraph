"""Probe for Phase 9h: recover a failed web resume.

Run from the repository root with .venv/bin/python docs/verification/probe-09h.py.
The last line is FAILURES <n>. It uses fakes and ScriptedModel only: no model,
server or real data is involved.
"""

import itertools
import os
import random
import tempfile
from collections.abc import Callable
from types import SimpleNamespace

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
os.environ["CONDUCTOR_DEMO"] = "true"

# The oracle's own tables: written from the spec, never read from the code.
RESUMABLE = ("route", "plan", "answer")
NODES = ("route", "plan", "answer", "run_step", "ask_step", "note", None)
STATUSES = ("waiting", "stopped", "done", "rejected", "cancelled")
FIXED = "the resume failed"
PREFIX = "The last resume failed: "
BUTTON = '<button type="submit">Resume</button>'
TOKEN = "c" * 64
BASE_URL = "http://127.0.0.1:8766"
SECRET = "SYNTHETIC-SECRET"
APPROVAL = "2" * 32
ESCALATION = "3" * 32


def oracle_can_resume(case: dict) -> bool:
    if case["status"] == "stopped":
        return case["stopped_at"] in RESUMABLE
    if case["status"] != "waiting":
        return False
    found = case["approval"] if case["waits_on"] == "approval" else case["escalation"]
    return found == "yes"


def oracle_message(kept: str | None, busy: bool, tail: str) -> str | None:
    """tail is 'record:<Type>', 'record-int', 'node-record', 'other-error', 'event',
    'corrupt' or 'none'."""
    if kept is not None and kept != FIXED:
        return kept
    if not busy and tail.startswith("record:"):
        return f"{FIXED} ({tail.removeprefix('record:')})"
    return kept


BASE = {
    "status": "waiting",
    "stopped_at": None,
    "waits_on": "approval",
    "approval": "yes",
    "escalation": "yes",
}
CHANGES = {
    "status": STATUSES,
    "stopped_at": NODES,
    "waits_on": ("approval", "escalation"),
    "approval": ("yes", "no", "missing"),
    "escalation": ("yes", "no", "missing"),
}

# The oracle on known cases.
assert oracle_can_resume(BASE)
assert not oracle_can_resume({**BASE, "approval": "missing"})
assert oracle_can_resume({**BASE, "status": "stopped", "stopped_at": "answer"})
assert not oracle_can_resume({**BASE, "status": "stopped", "stopped_at": "run_step"})
assert not oracle_can_resume({**BASE, "status": "done"})
assert oracle_message(None, False, "record:Boom") == "the resume failed (Boom)"
assert oracle_message(FIXED, True, "record:Boom") == FIXED
assert oracle_message("run x is busy", False, "record:Boom") == "run x is busy"
assert oracle_message(None, False, "record-int") is None


def run_id() -> str:
    return f"{rng.getrandbits(128):032x}"


def as_state(case: dict, run: str):
    from conductor.graph.status import RunState

    if case["status"] == "waiting" and case["waits_on"] == "approval":
        return RunState(run, "waiting", approval_id=APPROVAL)
    if case["status"] == "waiting":
        return RunState(run, "waiting", escalation_id=ESCALATION)
    return RunState(run, case["status"], stopped_at=case["stopped_at"])


class FakeStore:
    def __init__(self, case: dict) -> None:
        self.case = case

    def approval(self, approval_id: str):
        return self._found(self.case["approval"], decision=object())

    def escalation(self, escalation_id: str):
        return self._found(self.case["escalation"], answer=object())

    def _found(self, value: str, **present: object):
        from conductor.store import NotFound

        if value == "missing":
            raise NotFound("missing")
        if value == "no":
            return SimpleNamespace(**dict.fromkeys(present))
        return SimpleNamespace(**present)


def random_cases(count: int) -> list[dict]:
    cases = []
    for _ in range(count):
        field = rng.choice(list(CHANGES))
        changed = {**BASE, field: rng.choice(CHANGES[field])}
        if field == "stopped_at":
            changed["status"] = "stopped"
        cases.append(changed)
    return cases


def check_can_resume_table() -> bool:
    from conductor.graph.supervisor import can_resume

    agree = True
    for case in random_cases(300):
        agree &= can_resume(as_state(case, run_id()), FakeStore(case)) is oracle_can_resume(case)
    return agree


def check_can_resume_matches_resume_run() -> bool:
    from conductor.graph import supervisor

    real_state, real_invoke = supervisor.run_state, supervisor._invoke
    agree, reached = True, {True: 0, False: 0}
    try:
        for case in random_cases(300):
            run = run_id()
            invoked: list[str] = []
            supervisor.run_state = lambda graph, run_id, case=case: as_state(case, run_id)
            supervisor._invoke = lambda graph, value, run_id, seen=invoked: seen.append(run_id)
            try:
                supervisor.resume_run(None, FakeStore(case), run)
            except Exception:  # noqa: BLE001, S110
                pass
            supervisor.run_state, supervisor._invoke = real_state, real_invoke
            expected = supervisor.can_resume(as_state(case, run), FakeStore(case))
            agree &= bool(invoked) is expected
            reached[expected] += 1
    finally:
        supervisor.run_state, supervisor._invoke = real_state, real_invoke
    return agree and min(reached.values()) >= 50


class Still:
    def __init__(self, busy: bool, kept: str | None) -> None:
        self.busy, self.kept, self.started = busy, kept, []

    def start(self, run: str) -> None:
        self.started.append(run)

    def running(self, run: str) -> bool:
        return self.busy

    def error(self, run: str) -> str | None:
        return self.kept


def write_tail(run: str, tail: str) -> None:
    from conductor.config import get_settings
    from conductor.events import EventKind, EventLog

    if tail == "none":
        return
    log = EventLog(get_settings().runs_dir)
    log.append(run, EventKind.RUN_STARTED, payload={"request": "demo: say hi"})
    record = {"error": "resume_failed", "type": "Boom"}
    if tail.startswith("record:"):
        record["type"] = tail.removeprefix("record:")
        log.append(run, EventKind.ERROR, payload=record)
    elif tail == "record-int":
        log.append(run, EventKind.ERROR, payload={"error": "resume_failed", "type": 5})
    elif tail == "node-record":
        log.append(run, EventKind.ERROR, node="plan", payload=record)
    elif tail == "other-error":
        log.append(run, EventKind.ERROR, payload={"error": "other", "type": "Boom"})
    elif tail == "event":
        log.append(run, EventKind.ERROR, payload=record)
        log.append(run, EventKind.NODE_STARTED, node="plan")
    elif tail == "corrupt":
        log.append(run, EventKind.ERROR, payload=record)
        path = get_settings().runs_dir / f"{run}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{\n")


def check_page_message() -> bool:
    from fastapi.testclient import TestClient

    from conductor import runtime
    from conductor.config import get_settings
    from conductor.graph.status import RunState
    from conductor.web.app import create_app

    tails = ["record:Boom", "record:ValueError", "record-int", "node-record"]
    tails += ["other-error", "event", "corrupt", "none"]
    real_read = runtime.read_state
    runtime.read_state = lambda settings, run: RunState(run, "stopped", stopped_at="plan")
    agree, reached = True, 0
    try:
        for kept, busy, tail in itertools.product(
            [None, FIXED, "run x is busy"], [False, True], tails
        ):
            run = run_id()
            write_tail(run, tail)
            page = TestClient(
                create_app(get_settings(), resumer=Still(busy, kept)), base_url=BASE_URL
            )
            response = page.get(f"/runs/{run}")
            want = oracle_message(kept, busy, tail)
            text = response.text
            shown = text.count(PREFIX) == 0 if want is None else (PREFIX + want) in text
            agree &= response.status_code == 200 and shown and text.count(PREFIX) <= 1
            agree &= (BUTTON in text) is (not busy)
            reached += want is not None and want.endswith(")")
    finally:
        runtime.read_state = real_read
    return agree and reached == 4


class Boom(Exception):
    pass


def check_restart_shows_the_record() -> bool:
    from fastapi.testclient import TestClient

    from conductor import runtime
    from conductor.config import get_settings
    from conductor.llm.scripted import ScriptedModel, ScriptError
    from conductor.web.app import FORM_COOKIE, create_app
    from conductor.web.jobs import Resumer

    class Raising(ScriptedModel):
        def chat(self, request):
            raise Boom(SECRET)

    settings = get_settings()
    known = set(settings.runs_dir.glob("*.jsonl"))
    with runtime.open_runtime(settings, model=ScriptedModel([])) as opened:
        try:
            runtime.ask(opened, "demo: say hi")
        except ScriptError:
            pass
    [path] = set(settings.runs_dir.glob("*.jsonl")) - known
    run = path.stem
    real_open = runtime.open_runtime
    runtime.open_runtime = lambda settings: real_open(settings, model=Raising([]))
    try:
        resumer = Resumer(settings)
        page = TestClient(create_app(settings, resumer=resumer), base_url=BASE_URL)
        page.cookies.set(FORM_COOKIE, TOKEN)
        posted = page.post(f"/runs/{run}/resume", data={"token": TOKEN}, follow_redirects=False)
        resumer.join(run, 10)
        before = page.get(f"/runs/{run}").text
    finally:
        runtime.open_runtime = real_open
    after = TestClient(create_app(settings, resumer=Resumer(settings)), base_url=BASE_URL)
    text = after.get(f"/runs/{run}").text
    wanted = PREFIX + "the resume failed (Boom)"
    stored = (settings.runs_dir / f"{run}.jsonl").read_text(encoding="utf-8")
    return (
        posted.status_code == 303
        and wanted in before
        and wanted in text
        and BUTTON in text
        and SECRET not in stored + before + text
        and stored.count('"resume_failed"') == 1
    )


section("300 random states: can_resume matches the table", check_can_resume_table)
section(
    "300 random states: can_resume is exactly when resume_run invokes",
    check_can_resume_matches_resume_run,
)
section("48 page cases: the shown failure matches the table", check_page_message)
section("a failed page resume is still shown after a restart", check_restart_shows_the_record)

print(f"FAILURES {failures}")
