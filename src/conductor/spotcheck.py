"""Change one exact text in a module, run the deciding test, and restore the module's bytes.

Phase tooling for `scripts/spot_check.py`; it never runs as part of the agent.
"""

import re
from collections.abc import Callable
from pathlib import Path

MATCH_MESSAGE = "the old text must match exactly once"
BASELINE_MESSAGE = "the deciding test does not pass before the change"
_PATH_LINE = re.compile(r"\.py:\d+: (.*)")
_LIMIT = 140


class SpotError(Exception):
    pass


def mutate(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SpotError(f"{MATCH_MESSAGE}: found {count}")
    return text.replace(old, new, 1)


def spot_check(path: Path, old: str, new: str, run: Callable[[], tuple[int, str]]) -> str:
    """Run the test on the original, then on the changed module; always restore the bytes."""
    original = path.read_bytes()
    changed = mutate(original.decode("utf-8"), old, new)
    code, _output = run()
    if code != 0:
        raise SpotError(BASELINE_MESSAGE)
    try:
        path.write_bytes(changed.encode("utf-8"))
        code, output = run()
    finally:
        path.write_bytes(original)
    return verdict(output, code)


def verdict(output: str, code: int) -> str:
    if code == 0:
        return "passes"
    if code == 1:
        message = _failure(output)
        if message is None:
            return "fails"
        return f"fails: {message}"
    if code == 2:
        message = _error_line(output)
        if message is None:
            return "error: collection"
        return f"error: {message}"
    if code == 4 or code == 5:
        return "no test ran"
    return f"error: exit {code}"


def _failure(output: str) -> str | None:
    for line in output.splitlines():
        found = _PATH_LINE.search(line)
        if found is not None:
            return _cut(found.group(1))
    return _error_line(output)


def _error_line(output: str) -> str | None:
    for line in output.splitlines():
        if line.startswith("E   "):
            return _cut(line.removeprefix("E   "))
    return None


def _cut(message: str) -> str:
    message = message.rstrip()
    if len(message) > _LIMIT:
        return message[:_LIMIT] + "..."
    return message
