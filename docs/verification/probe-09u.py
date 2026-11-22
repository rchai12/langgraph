"""Probe for Phase 9u: the first half of the unit test families moved without changing a test.

The oracle is the test tree at d42c3d8, the commit before the spec. Each test function is reduced
to a canonical form: its code, with every module-level name it uses replaced by the canonical form
of that name's definition (a helper, constant or fixture, whatever it is now called) and every
imported name by what it imports. A name imported from another test module resolves to that
module's definition on the same side (old or new), so a test that imports a fixture or constant
equals one where the same definition sits in its own file. A moved test must have the same
canonical form, run under the same autouse fixtures and module marks, and the whole suite must
collect the same node ids with only the moved files' paths changed.
Run from the repository root with .venv/bin/python docs/verification/probe-09u.py. The last line is
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
BASE = "d42c3d8"
GIVEN = "tests/unit/test_suite_layout.py"
MOVES = {
    "unit/test_answer.py": "unit/test_answer.py",
    "unit/test_answer_more.py": "unit/test_answer.py",
    "unit/test_decisions.py": "unit/test_decisions.py",
    "unit/test_decisions_more.py": "unit/test_decisions.py",
    "unit/test_diagnostics.py": "unit/test_diagnostics.py",
    "unit/test_diagnostics_more.py": "unit/test_diagnostics.py",
    "unit/test_finance_catalog.py": "unit/test_finance_catalog.py",
    "unit/test_finance_catalog_more.py": "unit/test_finance_catalog.py",
    "unit/test_finance_proposals.py": "unit/test_finance_proposals.py",
    "unit/test_finance_proposals_more.py": "unit/test_finance_proposals.py",
    "unit/test_mcp_declarations.py": "unit/test_mcp_declarations.py",
    "unit/test_mcp_declarations_more.py": "unit/test_mcp_declarations.py",
    "unit/test_mcp_runner.py": "unit/test_mcp_runner.py",
    "unit/test_mcp_runner_more.py": "unit/test_mcp_runner.py",
    "unit/test_contracts_more.py": "unit/test_contracts_edge_cases.py",
    "unit/test_decide_more.py": "unit/test_decide_failures.py",
    "unit/test_dollars_more.py": "unit/test_dollars_and_days.py",
    "unit/test_eval_more.py": "unit/test_eval_case_runs.py",
    "unit/test_eval_more_reports.py": "unit/test_eval_report_history.py",
    "unit/test_finance_more.py": "unit/test_finance_arguments.py",
    "unit/test_graph_split_more.py": "unit/test_graph_step_failures.py",
    "unit/test_groundwork_more.py": "unit/test_groundwork_limits.py",
}
MOVED_TESTS = 108  # counted by the oracle over the old files: sum(len(Canon(old).tests()))


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

    def __init__(self, source: str, load: Callable[[str], "Canon | None"] = lambda _: None) -> None:
        self.load = load
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

    def owner(self, name: str) -> "tuple[Canon, str] | None":
        """The module and name that define this name, following imports between test modules."""
        if name in self.defs:
            return self, name
        target = self.imports.get(name, "")
        module, _, attr = target.rpartition(".")
        other = self.load(module) if module.startswith("tests.") else None
        return other.owner(attr) if other is not None else None

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
        fixtures = set()
        for arg in ast.walk(node):
            if isinstance(arg, ast.arg) and (found := self.owner(arg.arg)) is not None:
                if is_fixture(found[0].defs[found[1]]):
                    fixtures.add(arg.arg)
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
            elif inner is not node and isinstance(inner, ast.FunctionDef | ast.ClassDef):
                local.add(inner.name)  # a class or function defined inside, not the module's
        for inner in ast.walk(node):
            if isinstance(inner, ast.arg) and inner.arg in fixtures:
                module, name = self.owner(inner.arg)
                inner.arg = module.ref(name)
            elif isinstance(inner, ast.Name) and inner.id not in local:
                if (found := self.owner(inner.id)) is not None:
                    inner.id = found[0].ref(found[1])
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
# A name imported from another test module is the same as that definition placed here.
SHARED = {"tests.m": Canon("X = 1\nY = 2\n")}
IMPORTED = "from tests.m import X\n\ndef test_a():\n    assert X\n"
assert Canon(IMPORTED, SHARED.get).test("test_a") == Canon(
    "X = 1\n\ndef test_a():\n    assert X\n"
).test("test_a")
assert Canon(IMPORTED, SHARED.get).test("test_a") != Canon(
    "from tests.m import Y as X\n\ndef test_a():\n    assert X\n", SHARED.get
).test("test_a")
assert (
    len(Canon("import pytest\n@pytest.fixture(autouse=True)\ndef f():\n    pass\n").context()) == 1
)
# A class defined inside a function is that function's own, whatever the module defines.
INNER = "def test_a():\n    class Q:\n        pass\n    assert Q\n"
assert Canon(INNER).test("test_a") == Canon("class Q:\n    x = 1\n\n" + INNER).test("test_a")

ROOT = Path.cwd()


def old_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{BASE}:tests/{path}"], capture_output=True, text=True, check=True
    ).stdout


def new_source(path: str) -> str:
    return (ROOT / "tests" / path).read_text(encoding="utf-8")


def loader(read: Callable[[str], str | None]) -> Callable[[str], Canon | None]:
    """Load test modules by dotted name from one side, each parsed once."""
    cache: dict[str, Canon | None] = {}

    def load(module: str) -> Canon | None:
        if module not in cache:
            cache[module] = None
            source = read(module.removeprefix("tests.").replace(".", "/") + ".py")
            cache[module] = Canon(source, load) if source is not None else None
        return cache[module]

    return load


def old_or_none(path: str) -> str | None:
    result = subprocess.run(["git", "show", f"{BASE}:tests/{path}"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def new_or_none(path: str) -> str | None:
    file = ROOT / "tests" / path
    return file.read_text(encoding="utf-8") if file.exists() else None


OLD, NEW = loader(old_or_none), loader(new_or_none)


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
        before, after = Canon(old_source(old), OLD), Canon(new_source(new), NEW)
        same &= sections_of(old) == sections_of(new)
        for name in before.tests():
            compared += 1
            twin = name in after.defs and before.test(name) == after.test(name)
            if not twin:
                print(f"     {old}::{name} has no identical twin in {new}")
            same &= twin
    if compared != MOVED_TESTS:
        print(f"     compared {compared} tests, expected {MOVED_TESTS}")
    return same and compared == MOVED_TESTS


def same_context() -> bool:
    compared = 0
    same = True
    for old, new in MOVES.items():
        before, after = Canon(old_source(old), OLD), Canon(new_source(new), NEW)
        for name in before.tests():
            compared += 1
            same &= name in after.defs
        if before.context() != after.context():
            print(f"     {new} runs under different autouse fixtures or marks than {old}")
            same = False
    if compared != MOVED_TESTS:
        print(f"     compared {compared} tests, expected {MOVED_TESTS}")
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
        before = {node for node in collected(Path(folder)) if not node.startswith(GIVEN + "::")}
    after = {node for node in collected(ROOT) if not node.startswith(GIVEN + "::")}
    moved = {moved_id(node) for node in before}
    for node in sorted(moved ^ after)[:10]:
        print(f"     {node} is collected on {'today' if node in after else BASE} only")
    return len(before) >= 1500 and moved == after


section(
    f"the {MOVED_TESTS} tests of the 15 families have identical twins at their new paths",
    moved_twins,
)
section("every moved test runs under the same autouse fixtures and module marks", same_context)
section("the suite collects the same node ids, with only the moved files' paths changed", same_ids)

print(f"FAILURES {failures}")
