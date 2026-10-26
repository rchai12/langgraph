"""Print where the project stands after the last phase, in one screen.

Run from the repository root with the project's interpreter:

    .venv/bin/python .claude/skills/phase-architect/phase_status.py

It shows: whether the working tree is clean, the last commits, the specs that have no review
yet, the latest entry of docs/progress.md (each line cut to 200 characters), the summary block of
the newest review in docs/reviews/, and the public names the last commit that touched src/ added.
Use it instead of re-running the test suite or reading whole files to learn what the last phase
did.
"""

import ast
import subprocess
import sys
from pathlib import Path

WIDTH = 200


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return done.stdout


def public_names(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    if not target.id.startswith("_"):
                        names.add(target.id)
    return names


def latest_progress() -> list[str]:
    lines = Path("docs/progress.md").read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if not starts:
        return []
    return [line[:WIDTH] for line in lines[starts[-1] :] if line.strip()]


def latest_review() -> list[str]:
    folder = Path("docs/reviews")
    # Spec names sort in build order (phase-01, phase-02a, ...), so the last name is the newest.
    reviews = sorted(folder.glob("*.md")) if folder.is_dir() else []
    if not reviews:
        return ["(no review yet)"]
    lines = reviews[-1].read_text(encoding="utf-8").splitlines()
    block = [line[:WIDTH] for line in lines[:12] if line.startswith(("# ", "- "))]
    return [str(reviews[-1]), *block]


def added_names() -> list[str]:
    commit = git("log", "-1", "--format=%H", "--", "src").strip()
    if not commit:
        return []
    found = []
    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).split()
    for path in changed:
        if not (path.startswith("src/") and path.endswith(".py")) or "migrations" in path:
            continue
        now = git("show", f"{commit}:{path}")
        before = git("show", f"{commit}~1:{path}")
        new = sorted(public_names(now) - public_names(before))
        if new:
            module = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
            found.append(f"{module}: {', '.join(new)}")
    return found


def main() -> int:
    status = git("status", "--short").splitlines()
    print("Working tree:", "clean" if not status else f"{len(status)} changed paths")
    for line in status[:15]:
        print("   ", line)
    print("\nLast commits:")
    for line in git("log", "--oneline", "-5").splitlines():
        print("   ", line[:WIDTH])
    reviewed = {path.name for path in Path("docs/reviews").glob("*.md")}
    waiting = [
        path.name for path in sorted(Path("docs/phases").glob("*.md")) if path.name not in reviewed
    ]
    print("\nSpecs with no review yet:", ", ".join(waiting) if waiting else "(none)")
    print("\nLatest progress entry:")
    for line in latest_progress():
        print("   ", line)
    print("\nNewest review:")
    for line in latest_review():
        print("   ", line)
    print("\nPublic names added by the last commit that touched src/:")
    for line in added_names() or ["(none)"]:
        print("   ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
