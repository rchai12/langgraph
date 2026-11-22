"""Phase 9x probe: the refactored functions answer exactly as they did at BASE.

Run from the repository root with .venv/bin/python docs/verification/probe-09x.py.
The last line is FAILURES <n>.

The oracle is each module as it was at BASE, loaded from git under another module name.
Each check gives the old and the new function the same inputs and compares the results,
the exception type and message, or the printed output. Inputs are a valid base with a few
changes. The refactored test is compared by its assertions, then run.
"""

import ast
import contextlib
import importlib
import importlib.util
import inspect
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

BASE = "e92eadd"
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
DATA = tempfile.mkdtemp()
os.environ["CONDUCTOR_DATA_DIR"] = DATA


def old_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{BASE}:{path}"], capture_output=True, text=True, check=True
    ).stdout


def old_module(path: str, name: str, package: str = "") -> types.ModuleType:
    """The module as it was at BASE, registered as conductor._old_<name>."""
    module = types.ModuleType(f"conductor._old_{name}")
    module.__file__ = str(ROOT / path)  # paths next to the module resolve as today
    module.__package__ = package
    sys.modules[module.__name__] = module
    exec(compile(old_source(path), f"<{BASE}:{path}>", "exec"), module.__dict__)
    return module


def outcome(function: Callable[..., object], *args: object) -> str:
    try:
        return "value " + repr(function(*args))
    except Exception as error:  # noqa: BLE001
        return f"raises {type(error).__name__} {error}"


def differ(label: str, pairs: list[tuple[str, str]]) -> bool:
    bad = [index for index, (old, new) in enumerate(pairs) if old != new]
    for index in bad[:3]:
        print(f"     {label} case {index}: old {pairs[index][0][:200]!r}")
        print(f"     {label} case {index}: new {pairs[index][1][:200]!r}")
    return bad == []


# The oracle's own helpers on known cases.
assert outcome(int, "3") == "value 3"
assert outcome(int, "x").startswith("raises ValueError")


# 1. config.get_settings

ENV = {
    "CONDUCTOR_OLLAMA_HOST": [
        "http://127.0.0.1:11434",
        "http://localhost:11434/",
        "http://[::1]:11434",
        "https://127.0.0.1:11434",
        "http://192.0.2.1:11434",
        "127.0.0.1:11434",
        "",
    ],
    "CONDUCTOR_MODEL": ["m:1", "", "   "],
    "CONDUCTOR_MODEL_TIMEOUT": ["300", "1", "3600", "3601", "0", "01", "x", "99999"],
    "CONDUCTOR_DECIDED_BY": ["owner", "a_1", "Owner", "", "1a", "a" * 32, "a" * 33],
    "CONDUCTOR_DEMO": ["true", "false", "True", "yes", ""],
    "CONDUCTOR_MCP_TIMEOUT": ["60", "600", "601", "0", "x", "1000"],
    "CONDUCTOR_WEB_PORT": ["8766", "1024", "65535", "65536", "80", "x", "99999"],
    "CONDUCTOR_MCP__FILES": ["server --flag", "", "   ", "'unclosed", "a 'b c'"],
    "CONDUCTOR_MCP__9X": ["server"],
    "CONDUCTOR_MCP__NOTES": ["notes-server"],
    "CONDUCTOR_MCP": ['{"files": "a b"}', "not json", '{"files": 3}', "[]"],
    "CONDUCTOR_DATA_DIR": [DATA, "relative/folder", ""],
}
VALID = {key: values[0] for key, values in ENV.items() if key.startswith("CONDUCTOR_MCP") is False}


def with_env(env: dict[str, str], function: Callable[[], object]) -> str:
    for key in list(os.environ):
        if key.startswith("CONDUCTOR_"):
            del os.environ[key]
    os.environ.update(env)
    try:
        return outcome(function)
    finally:
        for key in env:
            del os.environ[key]
        os.environ["CONDUCTOR_DATA_DIR"] = DATA


def same_settings() -> bool:
    new = importlib.import_module("conductor.config")
    old = old_module("src/conductor/config.py", "config", "conductor")
    pairs, kinds = [], set()
    for trial in range(TRIALS):
        env = dict(VALID)
        for key in rng.sample(sorted(ENV), 0 if trial == 0 else rng.choice([1, 1, 2, 3])):
            env[key] = rng.choice(ENV[key])
        was = with_env(env, old.get_settings)
        pairs.append((was, with_env(env, new.get_settings)))
        kinds.add(was if was.startswith("raises") else "accepted")
    print(f"     {TRIALS} environments, {len(kinds)} distinct answers")
    return differ("settings", pairs) and len(kinds) >= 60


# 2. evals.report.compare_lines


def case(name: str, **changed: object) -> dict:
    base = {
        "id": name,
        "runs": 4,
        "consistent": 4,
        "route_ok": 4,
        "plan_ok": 3,
        "args_ok": 2,
        "valid": 4,
        "escalated": 0,
        "unavailable": 0,
        "seconds": [1.0, 1.5],
        "run_ids": ["r" * 32],
    }
    return {**base, **changed}


REPORT = {
    "version": 1,
    "created": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    "model": "m:1",
    "digests": ["d1"],
    "templates": {"plan": ["t1"], "answer": ["t2"]},
    "case_files": {"a.json": "h1", "b.json": "h2"},
    "runs": 4,
    "cases": [case("alpha"), case("beta"), case("gamma", args_ok=None)],
}


def changed_report(report: dict) -> dict:
    """A copy of a report's fields with one change."""
    found = json.loads(json.dumps(report, default=str))
    found["created"] = report["created"]
    move = rng.choice(
        [
            "model",
            "digest",
            "template",
            "template",
            "file",
            "file",
            "case",
            "case",
            "case",
            "add",
            "remove",
            "order",
            "runs",
        ]
    )
    if move == "model":
        found["model"] = rng.choice(["m:2", "m:1 "])
    elif move == "digest":
        found["digests"] = rng.choice([[], ["d2"], ["d1", "d2"]])
    elif move == "template":
        point = rng.choice(["plan", "answer", "route", "zeta"])
        found["templates"][point] = rng.choice([["t9"], [], ["t1", "t9"]])
        if rng.random() < 0.3:
            found["templates"].pop(rng.choice(sorted(found["templates"])))
    elif move == "file":
        name = rng.choice(["a.json", "b.json", "c.json"])
        if rng.random() < 0.5:
            found["case_files"][name] = "h9"
        else:
            found["case_files"].pop(name, None)
    elif move == "case" and found["cases"]:
        chosen = rng.choice(found["cases"])
        field = rng.choice(["consistent", "route_ok", "plan_ok", "args_ok", "valid", "escalated"])
        chosen[field] = rng.choice([0, 1, 2, 4, 8] + ([None] if field == "args_ok" else []))
        if rng.random() < 0.3:
            chosen["runs"] = rng.choice([2, 8])
    elif move == "add":
        found["cases"].insert(
            rng.randrange(len(found["cases"]) + 1), case(rng.choice(["delta", "eps"]))
        )
    elif move == "remove" and found["cases"]:
        found["cases"].pop(rng.randrange(len(found["cases"])))
    elif move == "order":
        rng.shuffle(found["cases"])
    elif move == "runs":
        found["runs"] = 8
    return found


def same_comparisons() -> bool:
    new = importlib.import_module("conductor.evals.report")
    old = old_module("src/conductor/evals/report.py", "report", "conductor.evals")
    pairs, kinds = [], set()
    for trial in range(TRIALS):
        previous, current = dict(REPORT), dict(REPORT)
        for _ in range(0 if trial == 0 else rng.choice([1, 1, 2, 3])):
            if rng.random() < 0.7:
                current = changed_report(current)
            else:
                previous = changed_report(previous)
        sent = (new.Report.model_validate(previous), new.Report.model_validate(current))
        was = outcome(old.compare_lines, *sent)
        pairs.append((was, outcome(new.compare_lines, *sent)))
        kinds |= {re.sub(r"[0-9]+", "N", line) for line in ast.literal_eval(was[6:])}
    print(f"     {TRIALS} report pairs, {len(kinds)} distinct line shapes")
    return differ("compare", pairs) and len(kinds) >= 20


section("config.get_settings answers as at BASE on 2000 environments", same_settings)
section("evals.report.compare_lines answers as at BASE on 2000 report pairs", same_comparisons)


# 3. scripts/check.py main


def current_check() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("conductor._new_check", ROOT / "scripts/check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


JUNIT_PASS = (
    '<testsuites><testsuite><testcase classname="tests.unit.test_check_scripts" name="test_a"/>'
    '<testcase classname="tests.e2e.test_cli_x" name="test_b"/>'
    '<testcase classname="tests.unit.test_x" name="test_c"><skipped/></testcase>'
    "</testsuite></testsuites>"
)
JUNIT_FAIL = JUNIT_PASS.replace('name="test_a"/>', 'name="test_a"><failure/></testcase>')
ARGVS = [
    [],
    ["--quiet"],
    ["--quiet", "--log-dir", "LOGS"],
    ["--first", "core"],
    ["--first", "scripts,cli", "--quiet", "--log-dir", "LOGS"],
    ["--first", "nope"],
    ["--first", "core,nope"],
    ["--first", ""],
    ["--section", "scripts"],
    ["--section", "cli", "--quiet", "--log-dir", "LOGS"],
    ["--section", "nope"],
    ["--section", "core", "--first", "core"],
]


def check_run(module: types.ModuleType, argv: list[str], codes: list[int], gap: bool, junit: str):
    logs = Path(tempfile.mkdtemp())
    argv = [str(logs / "logs") if part == "LOGS" else part for part in argv]
    calls: list[str] = []

    def run(command: list[str], _cwd: Path, log: Path | None) -> int:
        for part in command:
            if part.startswith("--junitxml="):
                Path(part.removeprefix("--junitxml=")).write_text(junit, encoding="utf-8")
            if part.startswith("--cov-report=json:"):
                files = (
                    {}
                    if gap
                    else {
                        f"src/conductor/{name}": {
                            "summary": {"missing_lines": 0, "missing_branches": 0}
                        }
                        for name in module.read_critical(
                            module.CRITICAL_FILE.read_text(encoding="utf-8")
                        )
                    }
                )
                Path(part.removeprefix("--cov-report=json:")).write_text(
                    json.dumps({"files": files}), encoding="utf-8"
                )
        if log is not None:
            log.write_text("\n".join(f"line {n}" for n in range(25)) + "\n", encoding="utf-8")
        shown = re.sub(r"(?<=[=:])/\S*/", "TMP/", " ".join(command[2:]))
        calls.append(f"{shown} {None if log is None else log.name}")
        return codes[len(calls) - 1] if len(calls) <= len(codes) else 0

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            answer = f"returns {module.main(argv, run)}"
        except SystemExit as stop:
            answer = f"exits {stop.code}"
        except Exception as error:  # noqa: BLE001
            answer = f"raises {type(error).__name__} {error}"
    text = (out.getvalue() + err.getvalue()).replace(str(logs), "TMP")
    return f"{answer} | {calls} | {text}"


def same_check_main() -> bool:
    new = current_check()
    old = old_module("scripts/check.py", "check")
    pairs = []
    for argv in ARGVS:
        for codes in ([], [1], [0, 1], [0, 0, 1], [0, 0, 0, 1], [2, 0]):
            for gap in (False, True):
                for junit in (JUNIT_PASS, JUNIT_FAIL):
                    sent = (argv, codes, gap, junit)
                    pairs.append((check_run(old, *sent), check_run(new, *sent)))
    answers = {old.split(" | ")[0] + old[-40:] for old, _new in pairs}
    print(f"     {len(pairs)} runs, {len(answers)} distinct endings")
    return differ("check", pairs) and len(answers) >= 15


section(
    "scripts/check.py main prints and returns as at BASE for every argv and run", same_check_main
)


# 4. web.app.create_app


class Resumer:
    pass


def routes(module: types.ModuleType, settings: object) -> list[str]:
    guard = module.create_app(settings, resumer=Resumer())
    api = guard._app
    found = [type(guard).__name__, repr(sorted(guard._hosts))]
    found += [repr((api.docs_url, api.redoc_url, api.openapi_url))]
    for route in api.routes:
        found.append(
            f"{route.path} {sorted(route.methods)} {route.name} "
            f"{inspect.signature(route.endpoint)} {inspect.iscoroutinefunction(route.endpoint)}"
        )
    return found


def same_routes() -> bool:
    new = importlib.import_module("conductor.web.app")
    old = old_module("src/conductor/web/app.py", "app", "conductor.web")
    settings = importlib.import_module("conductor.config").get_settings()
    was, now = routes(old, settings), routes(new, settings)
    print(f"     {len(was) - 3} routes")
    return differ("routes", [(repr(was), repr(now))]) and len(was) - 3 == 10


section("web.app.create_app registers the same routes, guard and settings as at BASE", same_routes)


# 5. the refactored integration test

TEST_FILE = "tests/integration/test_run_status_cases.py"
TEST_NAME = "test_the_read_begins_before_both_selects_and_closes"


def assertions(source: str) -> list[str]:
    tree = ast.parse(source)
    found = [node for node in ast.walk(tree) if getattr(node, "name", None) == TEST_NAME]
    assert len(found) == 1, "the test is missing or doubled"
    return [ast.unparse(node) for node in ast.walk(found[0]) if isinstance(node, ast.Assert)]


def same_test() -> bool:
    was = assertions(old_source(TEST_FILE))
    now = assertions((ROOT / TEST_FILE).read_text(encoding="utf-8"))
    command = [sys.executable, "-m", "pytest", f"{TEST_FILE}::{TEST_NAME}", "--no-cov", "-q"]
    command += ["-p", "no:cacheprovider"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"     {len(was)} assertions; {done.stdout.strip().splitlines()[-1]}")
    return differ("asserts", [(repr(was), repr(now))]) and len(was) == 7 and done.returncode == 0


section("the read test keeps its seven assertions and passes", same_test)


# 6. the given test


def under_limits() -> bool:
    test = "tests/unit/test_complexity_rules.py"
    command = [sys.executable, "-m", "pytest", test, "--no-cov", "-q", "-p", "no:cacheprovider"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"     {done.stdout.strip().splitlines()[-1]}")
    return done.returncode == 0


section("the rules are on and nothing in the tree is over the limits", under_limits)

print(f"FAILURES {failures}")
