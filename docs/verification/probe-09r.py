"""Phase 9r probe: unused-argument repairs change no behaviour.

Run from the repository root with .venv/bin/python docs/verification/probe-09r.py.
The last line is FAILURES <n>.

The oracle reads every Python file under src, tests, scripts and .claude twice, at BASE
and in the working tree, and compares each pair after one normalisation written from the
spec's repair rules (never from the code under test):

- a parameter of an ordinary function, method or lambda may gain one leading underscore;
- a test function or fixture requests the same fixtures, counting the names in
  @pytest.mark.usefixtures, except that an unused tmp_path or monkeypatch may go;
- wait_escalation in src/conductor/graph/nodes.py may lose its config parameter;
- an imported name that nothing reads any more may go (an annotation's Path, say).

Anything else that differs is a change of behaviour. Comments are not in the syntax tree,
so a noqa comment never counts; tests/unit/test_lint_rules.py judges where one stands.
"""

import ast
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

BASE = "6b26679"
TREES = ("src", "tests", "scripts", ".claude")
GIVEN = {"tests/unit/test_lint_rules.py"}
BUILTINS = {"tmp_path", "monkeypatch"}
DROPPED = {("src/conductor/graph/nodes.py", "wait_escalation", "config")}
ROOT = Path.cwd()

failures = 0


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


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def is_usefixtures(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and ast.unparse(node.func) == "pytest.mark.usefixtures"


def is_pytest_function(node: ast.AST, parent: ast.AST) -> bool:
    if not isinstance(node, FUNCTIONS):
        return False
    if any(ast.unparse(item).startswith("pytest.fixture") for item in node.decorator_list):
        return True
    in_class = isinstance(parent, ast.ClassDef) and parent.name.startswith("Test")
    return node.name.startswith("test_") and (isinstance(parent, ast.Module) or in_class)


def requested(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    names = {arg.arg for arg in [*node.args.posonlyargs, *node.args.args]}
    for item in node.decorator_list:
        if is_usefixtures(item):
            names |= {arg.value for arg in item.args if isinstance(arg, ast.Constant)}
    kept = sorted(names - BUILTINS)
    return [ast.arg(arg=name) for name in kept]


def plain(name: str) -> str:
    return name[1:] if name.startswith("_") and len(name) > 1 else name


class Normal(ast.NodeTransformer):
    def __init__(self, path: str) -> None:
        self.path = path
        self.parents: list[ast.AST] = [ast.Module(body=[], type_ignores=[])]

    def visit(self, node: ast.AST) -> ast.AST:
        parent = self.parents[-1]
        self.parents.append(node)
        try:
            if isinstance(node, FUNCTIONS):
                self.normalise_function(node, parent)
            elif isinstance(node, ast.Lambda):
                self.underscores(node.args)
            return self.generic_visit(node)
        finally:
            self.parents.pop()

    def normalise_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, parent) -> None:
        arguments = node.args
        for key in DROPPED:
            if key[:2] == (self.path, node.name):
                arguments.args = [arg for arg in arguments.args if arg.arg != key[2]]
        if is_pytest_function(node, parent):
            arguments.posonlyargs = []
            arguments.args = requested(node)
            node.decorator_list = [item for item in node.decorator_list if not is_usefixtures(item)]
        else:
            self.underscores(arguments)

    @staticmethod
    def underscores(arguments: ast.arguments) -> None:
        every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
        for arg in every:
            arg.arg = plain(arg.arg)


def without_unused_imports(tree: ast.Module) -> ast.Module:
    """Drop imported names nothing reads, so an import a dropped annotation used may go."""
    read = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        kept = []
        for item in body:
            if isinstance(item, (ast.Import, ast.ImportFrom)):
                item.names = [
                    alias
                    for alias in item.names
                    if (alias.asname or alias.name.split(".")[0]) in read
                ]
                if not item.names:
                    continue
            kept.append(item)
        node.body = kept
    return tree


def normal(source: str, path: str = "x.py") -> str:
    tree = without_unused_imports(Normal(path).visit(ast.parse(source)))
    return ast.dump(tree, include_attributes=False)


def same(old: str, new: str, path: str = "x.py") -> bool:
    return normal(old, path) == normal(new, path)


# The oracle on known cases.
FAKE = "def fake(a, run_id):\n    return a\n"
assert same(FAKE, FAKE.replace("run_id", "_run_id"))
assert same("f = lambda settings: 1\n", "f = lambda _settings: 1\n")
assert not same("f = lambda settings: 1\n", "f = lambda _: 1\n")
assert not same(FAKE, "def fake(a):\n    return a\n")
assert not same(FAKE, "def fake(a, run_id):\n    return 2\n")
assert same("def f(*args, **kwargs):\n    pass\n", "def f(*_args, **_kwargs):\n    pass\n")
TEST = "def test_a(db: Store, value: int) -> None:\n    assert value\n"
MOVED = '@pytest.mark.usefixtures("db")\ndef test_a(value: int) -> None:\n    assert value\n'
assert same(TEST, MOVED)
assert not same(TEST, "def test_a(value: int) -> None:\n    assert value\n")
assert not same(TEST, TEST.replace("db: Store", "_db: Store"))
EMPTY = "def test_b(tmp_path: Path, monkeypatch) -> None:\n    assert 1\n"
assert same(EMPTY, "def test_b() -> None:\n    assert 1\n")
assert not same(EMPTY, "def test_b() -> None:\n    assert 2\n")
FIXTURE = "@pytest.fixture\ndef db(tmp_path, time):\n    return 1\n"
assert same(FIXTURE, "@pytest.fixture\ndef db(time):\n    return 1\n")
assert not same(FIXTURE, "@pytest.fixture\ndef db(tmp_path, _time):\n    return 1\n")
NODE = "def build():\n    def wait_escalation(state, config):\n        return state\n"
NODES = "src/conductor/graph/nodes.py"
assert same(NODE, NODE.replace(", config", ""), NODES)
assert not same(NODE, NODE.replace(", config", ""))
METHOD = "class Fake:\n    def test_like(self, run_id):\n        return 1\n"
assert same(METHOD, METHOD.replace("run_id", "_run_id"))
ANNOTATED = "from pathlib import Path\n\ndef test_b(tmp_path: Path) -> None:\n    assert 1\n"
assert same(ANNOTATED, "def test_b() -> None:\n    assert 1\n")
assert not same("import os\n\ndef f():\n    return os.sep\n", "def f():\n    return os.sep\n")


def base_tree() -> Path:
    folder = Path(tempfile.mkdtemp())
    archive = folder / "base.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "archive", BASE, *TREES], check=True, stdout=out)
    with tarfile.open(archive) as tar:
        tar.extractall(folder / "base", filter="data")
    return folder / "base"


def python_files(root: Path) -> set[str]:
    found = {path for tree in TREES for path in (root / tree).rglob("*.py")}
    names = {str(path.relative_to(root)) for path in found if "__pycache__" not in path.parts}
    return names - GIVEN


OLD = base_tree()


def same_files() -> bool:
    old, new = python_files(OLD), python_files(ROOT)
    for path in sorted(old ^ new):
        print(f"     {'gone' if path in old else 'new '}: {path}")
    return old == new


def same_behaviour() -> bool:
    paths = sorted(python_files(OLD) & python_files(ROOT))
    changed = 0
    differ = []
    for path in paths:
        old = (OLD / path).read_text(encoding="utf-8")
        new = (ROOT / path).read_text(encoding="utf-8")
        if old == new:
            continue
        changed += 1
        if not same(old, new, path):
            differ.append(path)
    for path in differ:
        print(f"     differs beyond the repair rules: {path}")
    print(f"     {changed} files changed of {len(paths)}")
    return differ == []


def no_unused_arguments() -> bool:
    command = [".venv/bin/python", "-m", "ruff", "check", "--no-cache", "--select", "ARG"]
    result = subprocess.run(
        [*command, "--output-format", "concise", "."], capture_output=True, text=True
    )
    findings = [line for line in result.stdout.splitlines() if ": ARG" in line]
    print(f"     {len(findings)} unused-argument findings")
    return result.returncode == 0 and findings == []


section("the same Python files exist as at BASE, besides the given test", same_files)
section("every changed file differs from BASE only by the repair rules", same_behaviour)
section("ruff finds no unused argument anywhere", no_unused_arguments)

print(f"FAILURES {failures}")
