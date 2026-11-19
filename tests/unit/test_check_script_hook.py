import importlib.util
import io
import json
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "no_reference_build.py"
SCRATCH = "/private/tmp/claude-501/x/scratchpad"


def _hook():
    spec = importlib.util.spec_from_file_location("no_reference_build", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file(tool: str, path: str) -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": path}}


def _bash(command: str, cwd: str = "") -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}


@pytest.mark.parametrize(
    ("event", "tripped"),
    [
        (_file("Write", f"{SCRATCH}/ref/src/conductor/a.py"), True),
        (_file("Edit", f"{SCRATCH}/fail10a/src/conductor/a.py"), False),
        (_file("Write", f"{SCRATCH}/spot10a/src/conductor/a.py"), False),
        (_file("Write", f"{SCRATCH}/ref/tests/unit/test_a.py"), False),
        (_file("Write", "/repo/src/conductor/a.py"), False),
        (_bash(f"cat > {SCRATCH}/ref/src/conductor/a.py"), True),
        (_bash(f"cp x.py {SCRATCH}/fail9/src/conductor/"), False),
        (_bash("sed -i '' s/a/b/ src/conductor/a.py", cwd=f"{SCRATCH}/ref"), True),
        (_bash(f"cat {SCRATCH}/ref/src/conductor/a.py"), False),
        (_file("Read", f"{SCRATCH}/ref/src/conductor/a.py"), False),
        ({"tool_name": "Bash"}, False),
    ],
    ids=[
        "write-reference",
        "edit-fail-clone",
        "write-spot-copy",
        "write-test",
        "write-repository",
        "bash-redirect",
        "bash-fail-clone",
        "bash-cwd",
        "bash-read",
        "read",
        "no-input",
    ],
)
def test_tripped(event: dict, tripped: bool) -> None:
    assert _hook().tripped(event) is tripped


def test_main_asks_the_owner_only_when_tripped(monkeypatch, capsys) -> None:
    hook = _hook()
    event = {"tool_name": "Write", "tool_input": {"file_path": f"{SCRATCH}/r/src/conductor/a.py"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    hook.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Read"})))
    hook.main()
    assert capsys.readouterr().out == ""
