"""Probe for Phase 9q: the CLI test families moved to their new files without changing a test.

The oracle is the test tree at 3983234, the commit before the spec. Each test function is reduced
to a canonical form: its code, with every module-level name it uses replaced by the canonical form
of that name's definition (a helper, constant or fixture, whatever it is now called) and every
imported name by what it imports. A moved test must have the same canonical form, run under the
same autouse fixtures and module marks, and the whole suite must collect the same node ids with
only the moved files' paths changed.
Run from the repository root with .venv/bin/python docs/verification/probe-09q.py. The last line is
FAILURES <n>.
"""

import ast
import fnmatch
import hashlib
import io
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

failures = 0
BASE = "3983234"
GIVEN = "tests/unit/test_suite_layout.py"
MOVES = {
    "e2e/test_cli_approvals.py": "e2e/test_cli_approvals.py",
    "e2e/test_cli_approvals_more.py": "e2e/test_cli_approvals.py",
    "e2e/test_cli_ask.py": "e2e/test_cli_ask.py",
    "e2e/test_cli_ask_more.py": "e2e/test_cli_ask.py",
    "e2e/test_cli_doctor_private_more.py": "e2e/test_cli_doctor_not_writable.py",
    "e2e/test_cli_tool_check_more.py": "e2e/test_cli_tool_check_commands.py",
    "e2e/test_cli_groups_more.py": "e2e/test_cli_decide_without_asking.py",
}
MOVED_TESTS = 56


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


def is_fixture(node: ast.AST) -> bool:
    return isinstance(node, ast.FunctionDef) and any(
        "fixture" in ast.unparse(decorator) for decorator in node.decorator_list
    )


def without_docstring(node: ast.AST) -> ast.AST:
    body = getattr(node, "body", None)
    if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
        if isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return node


class Canon:
    """Canonical forms of the definitions and tests of one test module."""

    def __init__(self, source: str) -> None:
        self.defs: dict[str, ast.AST] = {}
        self.imports: dict[str, str] = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                self.defs[node.name] = node
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                self.defs[node.targets[0].id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.defs[node.target.id] = node
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    self.imports[bound] = alias.name if alias.asname else bound
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        self.memo: dict[str, str] = {}

    def ref(self, name: str) -> str:
        if name not in self.memo:
            self.memo[name] = "REC"
            node = without_docstring(ast.parse(ast.unparse(self.defs[name])).body[0])
            if hasattr(node, "name"):
                node.name = "_"
            elif isinstance(node, ast.Assign):
                node.targets = [ast.Name(id="_", ctx=ast.Store())]
            else:
                node.target = ast.Name(id="_", ctx=ast.Store())
            text = self.normal(node)
            self.memo[name] = "D" + hashlib.sha256(text.encode()).hexdigest()[:16]
        return self.memo[name]

    def normal(self, node: ast.AST) -> str:
        fixtures = {
            arg.arg
            for arg in ast.walk(node)
            if isinstance(arg, ast.arg) and is_fixture(self.defs.get(arg.arg))
        }
        local = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and not isinstance(inner.ctx, ast.Load):
                local.add(inner.id)
            elif isinstance(inner, ast.arg) and inner.arg not in fixtures:
                local.add(inner.arg)
            elif isinstance(inner, ast.alias):
                local.add(inner.asname or inner.name.split(".")[0])
            elif isinstance(inner, ast.ExceptHandler) and inner.name:
                local.add(inner.name)
        for inner in ast.walk(node):
            if isinstance(inner, ast.arg) and inner.arg in fixtures:
                inner.arg = self.ref(inner.arg)
            elif isinstance(inner, ast.Name) and inner.id not in local:
                if inner.id in self.defs:
                    inner.id = self.ref(inner.id)
                elif inner.id in self.imports:
                    inner.id = "I:" + self.imports[inner.id]
        return ast.dump(node)

    def test(self, name: str) -> str:
        node = ast.parse(ast.unparse(self.defs[name])).body[0]
        return self.normal(node)

    def tests(self) -> list[str]:
        return [name for name in self.defs if name.startswith("test_")]

    def context(self) -> list[str]:
        autouse = [
            self.ref(name)
            for name, node in self.defs.items()
            if is_fixture(node) and "autouse" in ast.unparse(node.decorator_list[0])
        ]
        marks = [self.ref("pytestmark")] if "pytestmark" in self.defs else []
        return sorted(autouse) + marks


# The oracle on known cases: a renamed helper or fixture with the same code is the same test.
ORIGINAL = (
    "import pytest\nfrom a import b\nX = 1\n\n@pytest.fixture\ndef db():\n    return X\n\n"
    "def test_a(db, tmp_path):\n    assert db == X and b(tmp_path)\n"
)
RENAMED = (
    "import pytest\nfrom a import b as c\nY = 1\nX = 2\n\n@pytest.fixture\ndef db2():\n"
    '    """Doc."""\n    return Y\n\n'
    "def test_a(db2, tmp_path):\n    assert db2 == Y and c(tmp_path)\n"
)
assert Canon(ORIGINAL).test("test_a") == Canon(RENAMED).test("test_a")
assert Canon(ORIGINAL).test("test_a") != Canon(ORIGINAL.replace("X = 1", "X = 3")).test("test_a")
assert Canon(ORIGINAL).test("test_a") != Canon(ORIGINAL.replace("tmp_path)\n", "1)\n")).test(
    "test_a"
)
assert Canon(ORIGINAL).context() == []
assert (
    len(Canon("import pytest\n@pytest.fixture(autouse=True)\ndef f():\n    pass\n").context()) == 1
)

ROOT = Path.cwd()


def old_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{BASE}:tests/{path}"], capture_output=True, text=True, check=True
    ).stdout


def new_source(path: str) -> str:
    return (ROOT / "tests" / path).read_text(encoding="utf-8")


def sections_of(path: str) -> str:
    table = tomllib.loads((ROOT / "tests" / "sections.toml").read_text(encoding="utf-8"))
    for entry in table["section"]:
        if any(fnmatch.fnmatch(path, pattern) for pattern in entry["patterns"]):
            return entry["name"]
    return ""


def moved_twins() -> bool:
    compared = 0
    same = True
    for old, new in MOVES.items():
        before, after = Canon(old_source(old)), Canon(new_source(new))
        same &= sections_of(old) == sections_of(new)
        for name in before.tests():
            compared += 1
            same &= name in after.defs and before.test(name) == after.test(name)
    return same and compared == MOVED_TESTS


def same_context() -> bool:
    compared = 0
    same = True
    for old, new in MOVES.items():
        before, after = Canon(old_source(old)), Canon(new_source(new))
        for name in before.tests():
            compared += 1
            same &= name in after.defs
        same &= before.context() == after.context()
    return same and compared == MOVED_TESTS


def collected(root: Path) -> set[str]:
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov"]
    command += ["-p", "no:cacheprovider", "tests"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if "::" in line}


def moved_id(node: str) -> str:
    path, rest = node.split("::", 1)
    relative = path.removeprefix("tests/")
    return f"tests/{MOVES.get(relative, relative)}::{rest}"


def same_ids() -> bool:
    archive = subprocess.run(
        ["git", "archive", BASE, "tests", "pyproject.toml"], capture_output=True, check=True
    ).stdout
    with tempfile.TemporaryDirectory() as folder:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(folder, filter="data")
        before = collected(Path(folder))
    after = {node for node in collected(ROOT) if not node.startswith(GIVEN + "::")}
    return len(before) >= 1500 and {moved_id(node) for node in before} == after


section(
    f"the {MOVED_TESTS} tests of the 5 CLI families have identical twins at their new paths",
    moved_twins,
)
section("every moved test runs under the same autouse fixtures and module marks", same_context)
section("the suite collects the same node ids, with only the moved files' paths changed", same_ids)

print(f"FAILURES {failures}")
