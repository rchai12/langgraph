# Verify Phase 6a: MCP servers and the client

Spec: `docs/phases/phase-06a-mcp-servers-and-client.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 6a` on your own report.

The coder added `mcp` to the dependencies and installed it, added `McpServer`, `Domain.servers`, and `Action.server` to the registry and the MCP settings to `conductor.config`, created `conductor.mcp_client.client` (critical), copied the fake server and two test files (24 tests), and wrote two test files of their own.

## 1. Gates

N is `564`. Sections: core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; the summary lists `tests (core): passed`; at least 588 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `mcp_client/client.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/registry.py,*/conductor/config.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_mcp_declarations.py tests/integration/test_mcp_client.py --no-cov` | exactly `24 passed` |
| `.venv/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"` | `2.3.0` or a later `2.3.x` |
| `.venv/bin/python -c "import importlib.util as u; print(u.find_spec('opentelemetry.sdk'))"` | `None` |
| `.venv/bin/python scripts/check_reports.py --phase 6a` (before writing your report) | `Reports OK.` |
| `git diff HEAD -- pyproject.toml` | exactly one added line, `"mcp>=2.3,<2.4",` |
| `git diff --stat HEAD -- src/conductor/contracts src/conductor/domains src/conductor/graph src/conductor/runtime.py src/conductor/cli tests/unit/test_registry.py tests/unit/test_registry_more.py tests/unit/test_config.py tests/support.py tests/conftest.py` | no output |
| `pgrep -f mcp_fake_server` (after the whole check) | no output: no server left running |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) mcp|^(from|import) anyio" -- src | grep -v "^src/conductor/mcp_client/"`
2. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/mcp_client | grep -v -E ":(from conductor\.config|from conductor\.registry) import "`
3. `git grep --untracked -n -E "conductor\.mcp_client" -- src | grep -v "^src/conductor/mcp_client/"`
4. `git grep --untracked -n -E "\.content\b|\.text\b|logging|print\(" -- src/conductor/mcp_client`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_declarations`; the full check (every earlier declaration still builds) | pass |
| R2 | `test_server_declarations_are_checked` (8 cases); the coder's length, order, and demo tests; probe "the registry accepts exactly the declarations the rules allow" | pass; ok |
| R3 | `test_the_mcp_settings`, `test_bad_mcp_settings` (5 cases); the coder's key and order tests | pass |
| R4 | `test_a_call_and_a_failed_call`, `test_a_server_that_takes_too_long_is_ended`; the coder's two-calls and thread tests; probe "four calls at once all succeed", "no server process is left behind"; read `McpClient`: `asyncio.run` per call, nothing kept between calls | pass; ok; the same |
| R5 | `test_the_server_sees_only_safe_and_declared_variables`; the coder's unset test; probe "the server sees exactly the declared variables" | pass; ok |
| R6 | `test_the_server_log_is_private_and_appended`; the coder's umask test | pass |
| R7 | `test_the_tools_of_a_server`, `test_a_call_and_a_failed_call`; the coder's `str` test | pass |
| R8 | `test_a_server_without_a_command_line`, `test_a_command_that_cannot_start`, `test_a_server_that_stops`, `test_a_server_that_takes_too_long_is_ended`; the coder's not-executable and pass-through tests; probe "bad commands give start_failed, closed, or timeout" | pass; ok |
| R9 | searches 1 to 4; `test_the_sdk_and_no_telemetry`; probe "no OpenTelemetry SDK was loaded" | no output; pass; ok |
| R10 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It starts `tests/mcp_fake_server.py` as a child process about 25 times (it takes about 15 seconds), sets 16 variables and declares 6, runs four calls in threads at once, tries four command lines that cannot serve MCP, and checks 400 random sets of declarations against its own reading of the rules. That reading checks itself on known cases first; a stop at those `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 6a. Run from the repository root with .venv/bin/python."""

import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.mcp_client.client import McpUnavailable, client_for
from conductor.registry import Action, Domain, McpServer, Registry, RegistryError

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(41)
folder = Path(tempfile.mkdtemp())
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(folder / "data")
FAKE = Path("tests/mcp_fake_server.py").resolve()
os.environ["CONDUCTOR_MCP__FAKE"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"

# 1. no variable reaches the server unless it is safe or declared
names = [f"PROBE_VAR_{i}" for i in range(16)]
declared = tuple(rng.sample(names, 6))
for name in names:
    os.environ[name] = f"value-{name}"
client = client_for(McpServer("fake", env=declared), get_settings())
seen = {name: client.call_tool("env", {"name": name}).structured["result"] for name in names}
check(
    "the server sees exactly the declared variables (16 set, 6 declared)",
    all((seen[n] == f"value-{n}") == (n in declared) for n in names)
    and all(seen[n] == "<unset>" for n in names if n not in declared),
)

# 2. calls from several threads at once
results: list[object] = []


def call(i: int) -> None:
    try:
        results.append(client.call_tool("echo", {"text": f"t{i}"}).structured["text"])
    except Exception as error:  # noqa: BLE001
        results.append(type(error).__name__)


threads = [threading.Thread(target=call, args=(i,)) for i in range(4)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
check(
    f"four calls at once all succeed ({sorted(map(str, results))})",
    sorted(results) == [f"t{i}" for i in range(4)],
)

# 3. bad command lines map to the four codes, with no command text in the message
codes: dict[str, str] = {}
cases = {
    "missing": str(folder / "no-such-program"),
    "exits": shutil.which("true") or "/usr/bin/true",
    "fails": shutil.which("false") or "/usr/bin/false",
    "not executable": str(FAKE),
}
os.environ["CONDUCTOR_MCP_TIMEOUT"] = "3"
for label, command in cases.items():
    os.environ["CONDUCTOR_MCP__FAKE"] = shlex.quote(command)
    try:
        client_for(McpServer("fake"), get_settings()).list_tools()
        codes[label] = "no error"
    except McpUnavailable as error:
        ok_text = str(error) == f"server fake: {error.code}" and command not in str(error)
        codes[label] = error.code if ok_text else "bad message"
check(
    f"bad commands give start_failed, closed, or timeout ({codes})",
    all(code in ("start_failed", "closed", "timeout") for code in codes.values()),
)
leftover = subprocess.run(
    ["pgrep", "-f", str(FAKE)], capture_output=True, text=True, check=False
).stdout.split()
check("no server process is left behind", leftover == [])


# 4. server declarations against the probe's own reading of the rules
class Args(Contract):
    x: str


def oracle(domains: list[dict]) -> bool:
    owners: set[str] = set()
    for spec in domains:
        if len(set(spec["servers"])) != len(spec["servers"]):
            return False
        if owners & set(spec["servers"]):
            return False
        owners |= set(spec["servers"])
        for kind, server in spec["actions"]:
            if kind == "agent" and server is not None:
                return False
            if kind == "tool" and spec["servers"] and server is None:
                return False
            if server is not None and server not in spec["servers"]:
                return False
    return True


def build(domains: list[dict]) -> list[Domain]:
    built = []
    for d, spec in enumerate(domains):
        actions = tuple(
            Action(f"a{i}", "An action.", kind, "tool_x", "read", Args, Args, server)
            for i, (kind, server) in enumerate(spec["actions"])
        )
        built.append(
            Domain(
                f"d{d}", "A domain.", actions, servers=tuple(McpServer(s) for s in spec["servers"])
            )
        )
    return built


assert oracle([{"servers": ["s1"], "actions": [("tool", "s1")]}])
assert not oracle([{"servers": ["s1"], "actions": [("tool", None)]}])
assert not oracle(
    [
        {"servers": ["s1"], "actions": [("tool", "s1")]},
        {"servers": ["s1"], "actions": [("tool", "s1")]},
    ]
)
assert oracle([{"servers": [], "actions": [("tool", None), ("agent", None)]}])

agree = True
for _ in range(400):
    domains = []
    for _ in range(rng.randint(1, 3)):
        servers = rng.sample(["s1", "s2", "s3"], rng.randint(0, 2))
        if rng.random() < 0.1 and servers:
            servers.append(servers[0])
        actions = [
            (rng.choice(["tool", "agent"]), rng.choice([None, "s1", "s2", "s3"]))
            for _ in range(rng.randint(1, 3))
        ]
        domains.append({"servers": servers, "actions": actions})
    try:
        Registry(build(domains))
        accepted = True
    except RegistryError:
        accepted = False
    agree &= accepted == oracle(domains)
check("the registry accepts exactly the declarations the rules allow (400 sets)", agree)

check(
    "no OpenTelemetry SDK was loaded",
    not any(m.startswith("opentelemetry.sdk") for m in sys.modules),
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `env=None` passed to `StdioServerParameters` (the SDK's default) | `test_the_server_sees_only_safe_and_declared_variables` | `yes` for `FAKE_PASSED` | `<unset>` |
| 2 | `os.environ` copied whole into the server's environment | the same test | `<unset>` for the others | their values |
| 3 | the timeout applied to the request only, not to start-up and initialization (`ClientSession` timeout alone, no `fail_after`) | `test_a_server_that_takes_too_long_is_ended` | `timeout` within 10 s | the same code, or a different failure (record which) |
| 4 | an `ExceptionGroup` passed through instead of flattened | `test_a_server_that_stops` | `closed` | an `ExceptionGroup` |
| 5 | `raise ... from error` instead of `from None` | `test_a_server_that_stops` | `__cause__` is `None` | an `MCPError` |
| 6 | `read_only` taken as `False` when a tool has no annotations (`list_tools`) | `test_the_tools_of_a_server`, `fail` | `None` | `False` |
| 7 | the log file left for `open()` to create | `test_the_server_log_is_private_and_appended` | `0o600` | `0o644` |
| 8 | the `CONDUCTOR_` prefix allowed in `McpServer.env` | `test_server_declarations_are_checked`, `("HOME", "CONDUCTOR_MODEL")` | refused | accepted |
| 9 | `Settings()` errors passed through (`get_settings`) | `test_bad_mcp_settings`, `CONDUCTOR_MCP` | the mapping message | a `ValidationError` with `input_value=1` |

Reasonable variations that are correct: one private async function shared by both calls; `anyio.run` instead of `asyncio.run`; the flattening of exception groups in a private helper (`except*` is fine too); the environment built in a private function; `ToolInfo` and `ToolOutcome` with `slots=True`.

## 6. Project rules

- Searches 1 to 4.
- A server receives only the SDK's safe variables plus its declared ones; nothing from conductor's own settings.
- No tool argument, result, or error text is logged, printed, or kept by conductor; only the server writes its log.
- No test or probe opens a network connection; servers are child processes over stdio, and none is left running.

## 7. Out of scope

Each must be absent: the start-up check, `conductor doctor` changes, a step runner, runtime or graph changes, commands, the finance domain, long-lived sessions, a background loop or thread, resources, prompts, sampling, other transports, reading text content, changes to the demo domain, contracts, the graph, the runtime, or the CLI.

## 8. Progress log

The entry exists, headed `## Phase 6a: MCP servers and the client (...)`, with `Tests: 564 -> <passed> (given 24)`, and each deviation it lists is real and justified.
