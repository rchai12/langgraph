"""Probe for Phase 9o: settings load as before, are frozen, and never crash on a bad mapping.

The oracle is the predecessor's `config.py`, read from commit 1725edc with git and loaded as its
own module. Random environments (a valid base with one change) are loaded by the old and the new
`get_settings`. Where the old one accepted or refused, the new one must give the same values,
properties and message. Where the old one crashed (pydantic-settings could not decode
`CONDUCTOR_MCP`), the new one must refuse with the fixed `CONDUCTOR_MCP` message. Every accepted
setting must refuse assignment, and its server mapping must refuse changes. Run from the
repository root with .venv/bin/python docs/verification/probe-09o.py. The last line is FAILURES <n>.
"""

import importlib.util
import os
import random
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError as DecodeError

failures = 0
rng = random.Random(15)
BEFORE = "1725edc"
TRIALS = 1500


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


def load_before():
    text = subprocess.run(
        ["git", "show", f"{BEFORE}:src/conductor/config.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    path = Path(tempfile.mkdtemp()) / "config_before.py"
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("conductor_config_before", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load_before()
os.chdir(tempfile.mkdtemp())

MCP_REFUSED = "CONDUCTOR_MCP: must map server names to command lines"
FIELDS = (
    "data_dir",
    "ollama_host",
    "model",
    "model_timeout",
    "decided_by",
    "demo",
    "mcp_timeout",
    "web_port",
    "mcp",
)
PROPERTIES = (
    "runs_dir",
    "db_path",
    "checkpoints_path",
    "demo_on",
    "model_timeout_seconds",
    "mcp_timeout_seconds",
    "web_port_number",
)
DROP = None
BASE = {
    "CONDUCTOR_DATA_DIR": "data",
    "CONDUCTOR_OLLAMA_HOST": "http://127.0.0.1:11434",
    "CONDUCTOR_MODEL": "qwen3.8:27b",
    "CONDUCTOR_MODEL_TIMEOUT": "300",
    "CONDUCTOR_DECIDED_BY": "owner",
    "CONDUCTOR_DEMO": "false",
    "CONDUCTOR_MCP_TIMEOUT": "60",
    "CONDUCTOR_WEB_PORT": "8766",
    "CONDUCTOR_MCP__LEDGER": "ledger serve --stdio",
}
CHANGES = {
    "CONDUCTOR_DATA_DIR": ["a/../b", "", "/srv/conductor", DROP],
    "CONDUCTOR_OLLAMA_HOST": [
        "http://localhost:11434",
        "http://[::1]:11434/",
        "http://127.0.0.1:11434///",
        "https://127.0.0.1:11434",
        "http://10.0.0.5:11434",
        "127.0.0.1:11434",
        DROP,
    ],
    "CONDUCTOR_MODEL": ["   ", "", "other:1b", DROP],
    "CONDUCTOR_MODEL_TIMEOUT": ["0", "1", "3600", "3601", "01", "abc", DROP],
    "CONDUCTOR_DECIDED_BY": ["Owner", "a" * 32, "a" * 33, "_x", "x_1", DROP],
    "CONDUCTOR_DEMO": ["true", "TRUE", "yes", DROP],
    "CONDUCTOR_MCP_TIMEOUT": ["600", "601", "0", DROP],
    "CONDUCTOR_WEB_PORT": ["1024", "1023", "65535", "65536", "08766", DROP],
    "CONDUCTOR_MCP": [
        '{"bank": "bank serve"}',
        '{"bank": 1}',
        "[1]",
        "null",
        '"bank"',
        '{"9x": "a"}',
        '{"bank": "\'b"}',
        "notjson",
        '{"bank": ',
        "[1",
    ],
    "CONDUCTOR_MCP__LEDGER": ["   ", "'/opt/ledger", DROP],
    "CONDUCTOR_MCP__9X": ["nine serve"],
    "CONDUCTOR_MCP__LEDGER__BIN": ["ledger"],
}


def environment() -> dict:
    env = dict(BASE)
    name = rng.choice(list(CHANGES))
    value = rng.choice(CHANGES[name])
    if value is DROP:
        env.pop(name, None)
    else:
        env[name] = value
    return env


def use(env: dict) -> None:
    for key in list(os.environ):
        if key.startswith("CONDUCTOR_"):
            del os.environ[key]
    os.environ.update(env)


def seen(settings) -> dict:
    found = {name: getattr(settings, name) for name in FIELDS}
    found["mcp"] = dict(found["mcp"])
    found.update({name: getattr(settings, name) for name in PROPERTIES})
    names = [*sorted(found["mcp"]), "missing"]
    found["commands"] = {name: settings.mcp_command(name) for name in names}
    return found


def outcome(load: Callable, errors: tuple[type, ...]) -> tuple:
    try:
        settings = load()
    except errors as error:
        return ("refused", str(error))
    except DecodeError:
        return ("crashed",)
    return ("accepted", seen(settings))


def old_outcome() -> tuple:
    return outcome(old.get_settings, (old.SettingsError,))


def expected(before: tuple) -> tuple:
    """The new outcome: the old one, except that a decoding crash becomes the fixed refusal."""
    return ("refused", MCP_REFUSED) if before == ("crashed",) else before


# The oracle on known cases.
use(BASE)
assert old_outcome()[0] == "accepted"
use({**BASE, "CONDUCTOR_MCP": "notjson"})
assert old_outcome() == ("crashed",) and expected(("crashed",)) == ("refused", MCP_REFUSED)
use({**BASE, "CONDUCTOR_MCP": "[1]"})
assert old_outcome() == ("refused", MCP_REFUSED)
use({**BASE, "CONDUCTOR_OLLAMA_HOST": "http://[::1]:11434/"})
assert old_outcome()[1]["ollama_host"] == "http://[::1]:11434"

reach = {"accepted": 0, "refused": 0, "crashed": 0}
plays: list[tuple[dict, tuple]] = []
for _ in range(TRIALS):
    env = environment()
    use(env)
    before = old_outcome()
    reach[before[0]] += 1
    plays.append((env, before))
assert reach["accepted"] >= 400 and reach["refused"] >= 400 and reach["crashed"] >= 30, reach


def new_outcome() -> tuple:
    from conductor import config

    return outcome(config.get_settings, (config.SettingsError,))


def frozen(settings) -> bool:
    for name in FIELDS:
        before = getattr(settings, name)
        try:
            setattr(settings, name, before)
        except ValidationError as error:
            if [item["type"] for item in error.errors()] != ["frozen_instance"]:
                return False
        else:
            return False
    try:
        settings.mcp["probe"] = "probe serve"
    except TypeError:
        return "probe" not in settings.mcp
    return False


def check_frozen() -> bool:
    from conductor import config

    agree = True
    for env, before in plays:
        if before[0] == "accepted":
            use(env)
            agree &= frozen(config.get_settings())
    return agree


def check_same(kind: set[str]) -> Callable[[], bool]:
    def body() -> bool:
        agree = True
        for env, before in plays:
            if before[0] in kind:
                use(env)
                agree &= new_outcome() == expected(before)
        return agree

    return body


print(f"     reach {reach}")
section("every accepted setting refuses assignment and changes to its servers", check_frozen)
section(
    f"{reach['accepted'] + reach['refused']} environments: the same values and refusals",
    check_same({"accepted", "refused"}),
)
section(
    f"{reach['crashed']} environments that crashed: refused with the CONDUCTOR_MCP message",
    check_same({"crashed"}),
)

print(f"FAILURES {failures}")
