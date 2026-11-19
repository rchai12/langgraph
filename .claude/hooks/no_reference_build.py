"""PreToolUse tripwire: the architect writing the phase's source in a scratch clone.

A scratch copy of the phase's source is a reference build, whatever it is called (the
phase-architect skill, "Never build the feature in the clone"; the owner's decision of
2026-11-10). Writes into `src/conductor/` under the scratchpad ask the owner first. Clones
named `fail*` (the fail check, which needs names-only stubs) and `spot*` (a verifier's spot
check copy) are allowed.
"""

import json
import re
import sys

WRITES = re.compile(
    r"(>>?\s*|sed\s+-i[^|;&]*|cp\s[^|;&]*|mv\s[^|;&]*|tee\s[^|;&]*|write_text|git\s+apply)"
    r"[^|;&]*src/conductor/"
)
CLONES = re.compile(r"(?:scratchpad|\$S|\$\{S\})/([A-Za-z0-9_.-]+)")
ALLOWED = ("fail", "spot")


def scratch_names(text: str) -> list[str]:
    return CLONES.findall(text)


def _allowed(name: str) -> bool:
    return name.startswith(ALLOWED)


def tripped(event: dict) -> bool:
    tool = event.get("tool_name", "")
    data = event.get("tool_input", {}) or {}
    cwd = event.get("cwd", "")
    if tool in ("Write", "Edit", "NotebookEdit"):
        path = data.get("file_path", "") or data.get("notebook_path", "")
        names = scratch_names(path)
        return "/src/conductor/" in path and bool(names) and not _allowed(names[0])
    if tool == "Bash":
        command = data.get("command", "")
        names = scratch_names(command) + scratch_names(cwd)
        if not names or not WRITES.search(command):
            return False
        return not all(_allowed(name) for name in names)
    return False


def answer(event: dict) -> dict | None:
    if not tripped(event):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "Architect tripwire: this writes the phase's source in a scratch clone, "
                "which is a reference build. Spikes answer one question in a few lines; "
                "names-only stubs belong in a clone named fail*."
            ),
        }
    }


def main() -> None:
    found = answer(json.load(sys.stdin))
    if found is not None:
        json.dump(found, sys.stdout)


if __name__ == "__main__":
    main()
