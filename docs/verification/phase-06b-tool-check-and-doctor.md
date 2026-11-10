# Verify Phase 6b: the tool check and the doctor

Spec: `docs/phases/phase-06b-tool-check-and-doctor.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 6b` on your own report.

The coder created `conductor.mcp_client.check` (critical), added `domains.registered`, `runtime.check_tools` and the check before `ask` and `resume`, the printing of a failed check in the commands, and the server lines of `conductor doctor`, copied two test files (26 tests), and wrote two of their own.

The first attempt stopped on a mistake in one given test case (see the spec's "Corrections"). The first verification then failed on three spot-check rows of this guide that could not fail as written (rows 1, 2, and 5, corrected 2026-11-09; the architect ran each corrected change against the committed code and the named test failed). The code is unchanged: verify the phase in full again and write a new report over the old one.

## 1. Gates

N is `600`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 626 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `mcp_client/check.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/runtime.py,*/conductor/cli/main.py,*/conductor/diagnostics.py,*/conductor/domains/__init__.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_tool_check.py tests/e2e/test_cli_tool_check.py --no-cov` | exactly `26 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 6b` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/mcp_client/client.py src/conductor/registry.py src/conductor/contracts src/conductor/graph tests/unit tests/integration tests/e2e/test_cli_doctor.py tests/e2e/test_cli_ask.py tests/support.py tests/mcp_fake_server.py` | no output |
| `git diff HEAD -- src/conductor/runtime.py` | `open_runtime` keeps its 5d signature; only the registry line, the kept settings, `check_tools`, and its two calls change |
| `pgrep -f mcp_fake_server` (after the whole check) | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/mcp_client/check.py | grep -v -E ":(from conductor\.config|from conductor\.mcp_client\.client|from conductor\.registry) import "`
2. `git grep --untracked -n -E "call_tool" -- src/conductor/mcp_client/check.py src/conductor/diagnostics.py src/conductor/runtime.py`
3. `git grep --untracked -n -E "domains\.DOMAINS" -- src | grep -v "^src/conductor/domains/__init__.py:"`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_json_types_of_a_field` (5 cases); the coder's nested and repeat tests | pass |
| R2 | `test_a_domain_that_fits_its_server`, `test_a_registry_without_servers_starts_nothing`, `test_problems_come_in_declaration_order`; the coder's two-domain and no-action tests | pass |
| R3 | `test_what_the_check_refuses` (10 cases), `test_a_write_action_may_use_a_read_only_tool`; the coder's stop and two-problem tests; probe "input problems match the probe's reading of the rules", "only a read action on a tool not marked read-only is refused" | pass; ok |
| R4 | `test_a_server_that_cannot_be_reached_is_one_problem`; the coder's next-server test | pass |
| R5 | the coder's `SYNTHETIC-SECRET` test; read every message in `check.py` | pass; Design texts only |
| R6 | `test_the_check_passes_when_the_tools_fit`, `test_a_run_is_refused_when_the_tools_do_not_fit`, `test_a_server_without_a_command_line_refuses_a_resume`; the coder's `registered`, once-per-runtime, and no-server tests; probe "the runtime opens exactly when no action has a problem" | pass; ok |
| R7 | `test_ask_prints_every_problem`, `test_recording_without_resuming_skips_the_check`; the coder's `resume`, `retry`, and `cancel --no-resume` tests | pass |
| R8 | `test_the_doctor_checks_each_server`; the coder's unreachable, two-problem, and no-action tests | pass |
| R9 | searches 1 and 2 | no output |
| R10 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It checks 600 random pairs of argument contracts and tool input schemas against its own reading of the input rules (which checks itself on known cases first), every effect against every read-only hint, and six random sets of actions against the real fake server through `check_tools`. A stop at its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 6b. Run from the repository root with .venv/bin/python."""

import os
import random
import shlex
import sys
from pathlib import Path
import tempfile

from pydantic import create_model

from conductor import domains
from conductor.config import get_settings
from conductor.contracts import Contract
from conductor.mcp_client.check import ToolCheckFailed, check_registry
from conductor.mcp_client.client import ToolInfo
from conductor.registry import Action, Domain, McpServer, Registry
from conductor.runtime import check_tools, open_runtime

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(53)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "data")
TYPES = {"string": str, "integer": int, "boolean": bool, "number": float}
OPEN = {"type": "object", "additionalProperties": True}
RESULT_OK = create_model("Res", __base__=Contract, ok=(bool, ...))


def oracle(fields: dict, tool_props: dict, tool_required: set) -> set[str]:
    """The probe's own reading of the input rules: the problems' field names and kinds."""
    found = set()
    for name, (kind, _required) in fields.items():
        if name not in tool_props:
            found.add(f"missing:{name}")
        elif tool_props[name] != kind:
            found.add(f"type:{name}")
    for name in tool_required:
        if name not in fields:
            found.add(f"requires:{name}")
    return found


def kinds(texts: list[str]) -> set[str]:
    out = set()
    for text in texts:
        if " is not in the tool's input" in text:
            out.add("missing:" + text.split("field ")[1].split(" ")[0])
        elif " has types " in text:
            out.add("type:" + text.split("field ")[1].split(" ")[0])
        elif "the tool requires " in text:
            out.add("requires:" + text.split("requires ")[1].split(",")[0])
        else:
            out.add("other:" + text)
    return out


assert oracle({"a": ("string", True)}, {"a": "string"}, {"a"}) == set()
assert oracle({"a": ("string", True)}, {"a": "integer", "b": "string"}, {"b"}) == {
    "type:a",
    "requires:b",
}
assert kinds(["action d.x: field a is not in the tool's input"]) == {"missing:a"}

# 1. input fields against the probe's reading
agree = True
for i in range(600):
    names = rng.sample(["a", "b", "c", "d", "e"], rng.randint(1, 4))
    fields = {n: (rng.choice(list(TYPES)), rng.random() < 0.5) for n in names}
    model = create_model(
        f"Args{i}",
        __base__=Contract,
        **{n: (TYPES[k], ...) if req else (TYPES[k], TYPES[k]()) for n, (k, req) in fields.items()},
    )
    props = {n: k for n, (k, _) in fields.items()}
    roll = rng.random()
    if roll < 0.2 and props:
        props.pop(rng.choice(list(props)))
    elif roll < 0.4 and props:
        victim = rng.choice(list(props))
        props[victim] = rng.choice([t for t in TYPES if t != props[victim]])
    extra = rng.random() < 0.3
    if extra:
        props["z"] = "string"
    required = {n for n in props if rng.random() < 0.4}
    tool = ToolInfo(
        name="t",
        input_schema={
            "type": "object",
            "properties": {n: {"type": k} for n, k in props.items()},
            "required": sorted(required),
        },
        output_schema=OPEN,
        read_only=True,
    )
    action = Action("x", "An action.", "tool", "t", "read", model, RESULT_OK, "s")
    registry = Registry((Domain("d", "A domain.", (action,), servers=(McpServer("s"),)),))

    class One:
        def list_tools(self, tool=tool):
            return (tool,)

    texts = [p.text for p in check_registry(registry, get_settings(), connect=lambda s, st: One())]
    agree &= kinds(texts) == oracle(fields, props, required)
check("input problems match the probe's reading of the rules (600 pairs)", agree)

# 2. effects against read-only hints
matrix_ok = True
for effect in ("read", "propose", "write", "implement"):
    for hint in (True, False, None):
        if effect == "implement":
            continue
        action = Action("x", "An action.", "tool", "t", effect, RESULT_OK, RESULT_OK, "s")
        registry = Registry((Domain("d", "A domain.", (action,), servers=(McpServer("s"),)),))
        tool = ToolInfo(
            "t",
            {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            OPEN,
            hint,
        )

        class Two:
            def list_tools(self, tool=tool):
                return (tool,)

        texts = [
            p.text for p in check_registry(registry, get_settings(), connect=lambda s, st: Two())
        ]
        refused = any("read-only" in t for t in texts)
        matrix_ok &= refused == (effect == "read" and hint is not True)
check("only a read action on a tool not marked read-only is refused (9 cases)", matrix_ok)

# 3. the real runtime refuses exactly when a problem exists
FAKE = Path("tests/mcp_fake_server.py").resolve()
os.environ["CONDUCTOR_MCP__FAKE"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}"
Text = create_model("Text", __base__=Contract, text=(str, ...))
Reason = create_model("Reason", __base__=Contract, reason=(str, ...))
choices = [
    (Action("echo", "Echo.", "tool", "echo", "read", Text, Text, "fake"), 0),
    (Action("fails", "Fails.", "tool", "fail", "write", Reason, Text, "fake"), 0),
    (Action("bad_read", "Bad.", "tool", "fail", "read", Reason, Text, "fake"), 1),
    (Action("missing", "Missing.", "tool", "nope", "read", Text, Text, "fake"), 1),
    (Action("wrong", "Wrong.", "tool", "echo", "read", Reason, Text, "fake"), 2),
]
runtime_ok = True
for _ in range(6):
    picked = rng.sample(choices, rng.randint(1, 3))
    domains.DOMAINS = (
        Domain("lab", "Lab.", tuple(a for a, _ in picked), servers=(McpServer("fake"),)),
    )
    expected = sum(n for _, n in picked)
    with open_runtime(get_settings()) as opened:
        try:
            check_tools(opened)
            got = 0
        except ToolCheckFailed as error:
            got = len(error.problems)
    runtime_ok &= got == expected
check("the runtime opens exactly when no action has a problem (6 sets, a real server)", runtime_ok)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | rule 5 refuses only `read_only is False` (so a tool with no hint passes) | `test_what_the_check_refuses`, `read_only=None` | the read-only problem | no problem |
| 2 | the read-only rule applied to every effect (the `effect == "read"` condition removed) | `test_a_domain_that_fits_its_server` (its `note` action is `write`, on a tool marked `False`) | no problem | a read-only problem for `finance.note` |
| 3 | `anyOf` members ignored in `json_types` | `test_the_json_types_of_a_field`, the date-or-null case | `("null", "string")` | `("any",)` |
| 4 | rule 4 (the tool's required fields) removed | `test_what_the_check_refuses`, `by` | the requires problem | no problem |
| 5 | rules 7 to 9 run on an output schema without `properties` as if it listed none | the coder's `test_an_output_schema_without_properties_passes` (its result requires `note_id`) | no problem | `the tool does not promise result field note_id` |
| 6 | `check_tools` not called in `resume` | `test_a_server_without_a_command_line_refuses_a_resume` | `ToolCheckFailed` | `RunError` |
| 7 | the check moved into `open_runtime` | `test_recording_without_resuming_skips_the_check` | `Rejected` | exit 1 |
| 8 | each `FAIL` line not counted (`diagnostics`) | `test_the_doctor_checks_each_server` | `1 check failed.` | `All checks passed.` |

Reasonable variations that are correct: the nine rules split into private helpers for input and output; a `ServerCheck` built per server and flattened for `check_registry`; the once-per-runtime flag on the runtime's existing mutable focus object; `check_tools` reading the settings kept on `Runtime`.

## 6. Project rules

- Searches 1 to 3.
- A `read` action, which runs without approval, can pass the check only on a tool whose `readOnlyHint` is `true`.
- No tool is called by the check or the doctor; servers are started only to list their tools, once per server per check.
- Every message is the Design's text with names, types, and codes only.

## 7. Out of scope

Each must be absent: calling tools, a step runner, result checks per call, caching the check beyond one runtime, leaving a domain out, comparing descriptions, defaults, bounds, formats, enums, or nested fields, changes to `client.py`, the registry, contracts, the graph, or earlier given tests.

## 8. Progress log

The entry exists, headed `## Phase 6b: the tool check and the doctor (...)`, with `Tests: 600 -> <passed> (given 26)`, and each deviation it lists is real and justified.
