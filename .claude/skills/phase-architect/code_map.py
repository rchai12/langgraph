"""Print the project's public names and which tests import them, to read before designing a phase.

Run from the repository root with the project's interpreter:

    .venv/bin/python .claude/skills/phase-architect/code_map.py               every module
    .venv/bin/python .claude/skills/phase-architect/code_map.py conductor.policy
    .venv/bin/python .claude/skills/phase-architect/code_map.py --who needs_approval

For each module: public functions with their signatures, public classes with their bases (and a
dataclass's fields), and upper-case constants, each with the number of test files that import it.
``--who NAME`` lists the test files that import NAME and the modules they import it from.
"""

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

SOURCE = Path("src")
TESTS = Path("tests")


def module_name(path: Path) -> str:
    parts = path.relative_to(SOURCE).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def test_imports() -> dict[tuple[str, str], set[str]]:
    """(module, name) -> the test files that import name from module."""
    found: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(TESTS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("conductor"):
                for alias in node.names:
                    found[(node.module, alias.name)].add(str(path))
    return found


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {node.name}({ast.unparse(node.args)}){returns}"


def describe(node: ast.stmt) -> str | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_"):
        return signature(node)
    if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        fields = [
            ast.unparse(item.target)
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        ]
        shown = f" fields: {', '.join(fields)}" if fields else ""
        return f"class {node.name}({bases}){shown}"
    if isinstance(node, ast.Assign | ast.AnnAssign):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [
            t.id
            for t in targets
            if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_")
        ]
        if names and node.value is not None:
            value = ast.unparse(node.value)
            return f"{', '.join(names)} = {value if len(value) <= 60 else value[:57] + '...'}"
    return None


def public_name(line: str) -> str:
    text = line.removeprefix("def ").removeprefix("class ")
    return text.split("(")[0].split(" ")[0].split(",")[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show public names and their test imports.")
    parser.add_argument("prefix", nargs="*", help="dotted module prefixes, e.g. conductor.policy")
    parser.add_argument("--who", help="list the test files that import this name")
    args = parser.parse_args(argv)
    imports = test_imports()
    if args.who:
        for (module, name), files in sorted(imports.items()):
            if name == args.who:
                print(f"{module}.{name}: {', '.join(sorted(files))}")
        return 0
    for path in sorted(SOURCE.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        module = module_name(path)
        if args.prefix and not any(module.startswith(prefix) for prefix in args.prefix):
            continue
        lines = [
            line for line in map(describe, ast.parse(path.read_text(encoding="utf-8")).body) if line
        ]
        if not lines:
            continue
        print(module)
        for line in lines:
            count = len(imports.get((module, public_name(line)), ()))
            print(f"    {line}" + (f"   [tests: {count}]" if count else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
