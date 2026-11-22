"""The Ruff rule selection, and where an unused-argument noqa may stand (Phase 9r)."""

import ast
import io
import re
import tokenize
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TREES = ("src", "tests", "scripts", ".claude")
NOQA = re.compile(r"#\s*noqa(?P<colon>:\s*(?P<codes>[A-Za-z0-9, ]+))?", re.IGNORECASE)
FILE_NOQA = re.compile(r"#\s*(ruff|flake8)\s*:\s*noqa", re.IGNORECASE)


def comments(source: str) -> list[tuple[int, str]]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [(token.start[0], token.string) for token in tokens if token.type == tokenize.COMMENT]


def keywords_in(tree: ast.AST) -> set[str]:
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    return {word.arg for call in calls for word in call.keywords if word.arg is not None}


def is_contract(function: ast.AST, parameter: ast.arg, called: set[str]) -> bool:
    decorators = [ast.unparse(node) for node in getattr(function, "decorator_list", [])]
    if any(text.startswith(("server.tool", "pytest.fixture")) for text in decorators):
        return True
    return parameter in function.args.kwonlyargs or parameter.arg in called


def names_read(function: ast.AST) -> set[str]:
    body = function.body if isinstance(function.body, list) else [function.body]
    return {node.id for part in body for node in ast.walk(part) if isinstance(node, ast.Name)}


def unused_on(tree: ast.AST, line: int) -> list[tuple[ast.AST, ast.arg]]:
    """The parameters on a line that Ruff would call unused: not read, not _-named, not self."""
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    methods = {id(item) for node in classes for item in node.body}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = node.args
            every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
            every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
            quiet = names_read(node) | {arg.arg for arg in every if arg.arg.startswith("_")}
            if id(node) in methods and every:
                quiet.add(every[0].arg)
            found += [(node, arg) for arg in every if arg.lineno == line and arg.arg not in quiet]
    return found


def misplaced(source: str, called: set[str]) -> list[int]:
    """Lines whose noqa hides more than an unused name that is a contract."""
    tree = ast.parse(source)
    called = called | keywords_in(tree)
    lines = []
    for line, text in comments(source):
        if FILE_NOQA.search(text):
            lines.append(line)
            continue
        match = NOQA.search(text)
        if match is None:
            continue
        if match["colon"] is None:
            lines.append(line)
            continue
        codes = [code.strip().upper() for code in match["codes"].split(",") if code.strip()]
        if not any(code.startswith("ARG") for code in codes):
            continue
        pairs = unused_on(tree, line)
        allowed = all(code.startswith("ARG") for code in codes) and pairs != []
        if not allowed or not all(is_contract(node, arg, called) for node, arg in pairs):
            lines.append(line)
    return lines


def python_files() -> list[Path]:
    found = [path for tree in TREES for path in (ROOT / tree).rglob("*.py")]
    return sorted(path for path in found if "__pycache__" not in path.parts)


def production_keywords() -> set[str]:
    trees = [ast.parse(path.read_text(encoding="utf-8")) for path in (ROOT / "src").rglob("*.py")]
    return {word for tree in trees for word in keywords_in(tree)}


def test_the_rule_selection_is_exact() -> None:
    settings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert settings["tool"]["ruff"] == {
        "line-length": 100,
        "target-version": "py312",
        "extend-exclude": ["docs"],
        "lint": {"select": ["E", "F", "I", "B", "UP", "ARG"]},
    }


def test_every_noqa_in_the_tree_stands_where_it_may() -> None:
    called = production_keywords()
    found = {}
    for path in python_files():
        lines = misplaced(path.read_text(encoding="utf-8"), called)
        if lines:
            found[str(path.relative_to(ROOT))] = lines
    assert found == {}


TOOL = "@server.tool(annotations=READ)\ndef tool(limit: int = 5):  # noqa: ARG001\n    return 1\n"
FIXTURE = "@pytest.fixture\ndef db(time):  # noqa: ARG001\n    return 1\n"
KEYWORD_ONLY = "def fake(a, *, model=None):  # noqa: ARG001\n    return a\n"
CALLED = "def fake(a, timeout):  # noqa: ARG001\n    return a\n\nfake(1, timeout=2)\n"
PLAIN = "def fake(a, run_id):  # noqa: ARG001\n    return a\n"
MIXED = "def fake(a, run_id):  # noqa: ARG001, E501\n    return a\n"
BARE = "def fake(a, run_id):  # noqa\n    return a\n"
WHOLE_FILE = "# ruff: noqa: ARG001\ndef fake(a, run_id):\n    return a\n"
NO_PARAMETER = "x = 1  # noqa: ARG001\n"
OTHER_CODE = "from m import x  # noqa: F401\n"
QUIET = "def fake(_settings, *, model=None):  # noqa: ARG001\n    return 1\n"
USED_ONLY = "def fake(a):  # noqa: ARG001\n    return a\n"
METHOD = "class F:\n    def open(self, timeout):  # noqa: ARG002\n        return 1\n"


@pytest.mark.parametrize(
    ("source", "called", "lines"),
    [
        (TOOL, set(), []),
        (FIXTURE, set(), []),
        (KEYWORD_ONLY, set(), []),
        (CALLED, set(), []),
        (PLAIN, {"run_id"}, []),
        (PLAIN, set(), [1]),
        (MIXED, {"run_id"}, [1]),
        (BARE, {"run_id"}, [1]),
        (WHOLE_FILE, set(), [1]),
        (NO_PARAMETER, set(), [1]),
        (OTHER_CODE, set(), []),
        (QUIET, set(), []),
        (USED_ONLY, set(), [1]),
        (METHOD, {"timeout"}, []),
        (METHOD, set(), [2]),
    ],
    ids=[
        "tool",
        "fixture",
        "keyword_only",
        "called_in_file",
        "called_in_src",
        "plain",
        "mixed",
        "bare",
        "whole_file",
        "no_parameter",
        "other_code",
        "underscored",
        "used_only",
        "method_called",
        "method_plain",
    ],
)
def test_where_a_noqa_may_stand(source: str, called: set[str], lines: list[int]) -> None:
    assert misplaced(source, called) == lines
