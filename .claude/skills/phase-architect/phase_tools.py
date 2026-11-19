"""Small jobs the phase-architect checklist repeats, each printing only what the next step needs.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py clone 10a --scratch DIR
        Make (or remake) DIR/fail10a from the repository's HEAD, link the venv (excluded through
        the clone's .git/info/exclude), and say whether `conductor` imports from the clone.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py failcheck CLONE TEST...
        Run only these tests in the clone (PYTHONPATH=<clone>/src) and print each distinct
        failure reason with its count, then pytest's last line.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py stubcheck CLONE TEST...
        In a throwaway copy (<clone>-names), append names-only stubs for every name the tests
        import from `conductor.<module>` that the module does not define, then print each test
        file's function and collected test counts, the failure reasons, and every test that
        passes on the stub (a guard, or a weak test). The copy is deleted afterwards.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py searches SPEC [--cwd DIR] \
            [--plant FILE|auto]
        Run each line of the spec's `### Searches` block in DIR (default: the repository) and
        print how many lines it matched. With --plant, append each `path<TAB>line` of FILE (or,
        with `auto`, each catalog search's own plant line) first, and restore every file after.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py catalog [NAME...] \
            [--modules PATH...]
        Print the standing searches (SEARCHES), expanded for the phase's modules, ready to paste.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py lint SPEC GUIDE --clone CLONE
        Check the spec and guide against each other and against what pytest collects in a
        names-only copy of CLONE: per-file and total given counts, the at-least count, given
        files present and protected, spot-check test ids, the searches and what accept.py
        extracts, placeholders and banned wording. Prints `Lint OK.` or each problem.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py promote CLONE FILE... \
            [--ignore TEST...]
        Copy given files from the clone into the repository, compare each byte for byte, then run
        the suite without the --ignore files and print its last line (it must be N passed).

Only `clone`, `promote` and `--plant` write files: the clone, the given files, and planted lines
that are restored before it returns. Nothing here starts a model, a tool server or the web page.
"""

import argparse
import ast
import filecmp
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

BANNED = ("as appropriate", "or similar", "if needed", "etc.")
PLACEHOLDER = re.compile(r"TODO|\{\{[a-z]+:|<(?:path|name|sections|modules|pattern)[^>]*>")

# Standing searches: name -> (rule, command, plant line). `{modules}` is the phase's own source
# modules. The plant line goes into the first .py file the command names, or into
# src/conductor/_planted.py when it names only folders, and must make that search match.
SEARCHES: dict[str, tuple[str, str, str]] = {
    "network": (
        "network code only in llm/ (Ollama) and the CLI's web server",
        "git grep --untracked -n -E 'import (socket|ssl|http|requests|httpx|aiohttp|websockets)"
        "([^A-Za-z_]|$)|from (socket|ssl|http|requests|httpx|aiohttp|websockets)([^A-Za-z_]|$)"
        "|urllib\\.request' -- src ':!src/conductor/llm' ':!src/conductor/cli/main.py'",
        "import httpx",
    ),
    "hosted-model": (
        "no hosted model provider or LangChain model wrapper",
        "git grep --untracked -n -E 'anthropic|openai|langchain_[a-z]|ChatOllama|init_chat_model"
        "|BaseChatModel|bedrock|vertexai' -- src pyproject.toml",
        "import anthropic",
    ),
    "ollama": (
        "only llm/ talks to Ollama",
        "git grep --untracked -n -E 'import ollama|from ollama|/api/(chat|generate|tags)' -- src"
        " ':!src/conductor/llm'",
        'URL = "/api/chat"',
    ),
    "telemetry": (
        "no telemetry, tracing exporter or crash reporting",
        "git grep --untracked -n -E 'opentelemetry|sentry_sdk|posthog|langsmith\\.Client'"
        " -- src pyproject.toml",
        "import sentry_sdk",
    ),
    "clock": (
        "time and ids only through conductor.clock and conductor.ids, through the module",
        "git grep --untracked -n -E 'datetime\\.now|datetime\\.utcnow|date\\.today|time\\.time\\("
        "|uuid\\.uuid[0-9]|from conductor\\.(clock|ids) import' -- src"
        " ':!src/conductor/clock.py' ':!src/conductor/ids.py'",
        "x = datetime.now()",
    ),
    "output": (
        "no print outside the CLI",
        "git grep --untracked -n -E 'print\\(' -- src ':!src/conductor/cli'",
        "print(1)",
    ),
    "environment": (
        "configuration only through get_settings() in this phase's modules",
        "git grep --untracked -n -E 'os\\.environ|getenv\\(' -- {modules}",
        'host = os.environ["OLLAMA_HOST"]',
    ),
    "exclusions": (
        "no coverage or lint exclusions in this phase's modules",
        "git grep --untracked -n -E 'pragma: no cover|noqa' -- {modules}",
        "x = 1  # noqa",
    ),
}
DEFAULT_SEARCHES = "network,hosted-model,ollama,telemetry,clock,output,exclusions"


def file_id(phase: str) -> str:
    found = re.fullmatch(r"([1-9][0-9]*)([a-z]?)", phase)
    if found is None:
        raise SystemExit("phase id must look like 9 or 10a")
    return f"{int(found.group(1)):02d}{found.group(2)}"


def clone_env(clone: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(clone.resolve() / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _python(clone: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / ".venv/bin/python"), *args],
        cwd=clone,
        env=clone_env(clone),
        capture_output=True,
        text=True,
        check=False,
    )


def make_clone(phase: str, scratch: Path) -> int:
    dest = scratch.resolve() / f"fail{file_id(phase)}"
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "-q", str(ROOT), str(dest)], check=True)
    (dest / ".venv").symlink_to(ROOT / ".venv")
    with (dest / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
        handle.write(".venv\n")
    found = _python(dest, ["-c", "import conductor; print(conductor.__file__)"]).stdout.strip()
    inside = bool(found) and Path(found).resolve().is_relative_to(dest)
    print(f"{dest}\nconductor imports from the clone: {'yes' if inside else 'NO: ' + found}")
    return 0 if inside else 1


def fail_check(clone: Path, tests: list[str]) -> int:
    done = _python(
        clone,
        ["-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider", "-rfE", "--tb=line", *tests],
    )
    lines = done.stdout.splitlines()
    reasons: Counter[str] = Counter()
    for line in lines:
        found = re.fullmatch(r"\S+:[0-9]+: (.*)", line)
        if found is not None:
            reasons[found.group(1)[:110]] += 1
    for reason, count in reasons.most_common():
        print(f"{count:4}  {reason}")
    print(lines[-1] if lines else "no output")
    return 0


def defined_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.ImportFrom | ast.Import):
            names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
    return names


def module_file(root: Path, module: str) -> str:
    """`conductor.graph.status` as its file: the module, or the package's __init__.py."""
    base = "src/" + module.replace(".", "/")
    if (root / base).is_dir():
        return base + "/__init__.py"
    return base + ".py"


def missing_imports(root: Path, tests: list[str]) -> dict[str, list[str]]:
    """Names the tests import from `conductor.<module>` that the module doesn't define yet."""
    missing: dict[str, list[str]] = {}
    for test in tests:
        for node in ast.walk(ast.parse((root / test).read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if not node.module.startswith("conductor."):
                continue
            source = module_file(root, node.module)
            have = defined_names(root / source)
            for alias in node.names:
                if alias.name not in have and alias.name not in missing.get(source, []):
                    missing.setdefault(source, []).append(alias.name)
    return missing


def stub_text(names: list[str]) -> str:
    """Names only: constants a placeholder, classes an exception, functions NotImplementedError."""
    lines = []
    for name in names:
        if name.isupper():
            lines.append(f'{name} = "stub"')
        elif name[:1].isupper():
            lines.append(f"class {name}(Exception):\n    pass")
        else:
            lines.append(f"def {name}(*args, **kwargs):\n    raise NotImplementedError")
    return "\n\n\n".join(lines) + "\n"


def _names_copy(clone: Path, suffix: str, tests: list[str], *, show: bool) -> Path:
    copy = clone.resolve().with_name(clone.resolve().name + suffix)
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(clone, copy, symlinks=True)
    for path, names in missing_imports(copy, tests).items():
        if show:
            print(f"auto stub {path}: {', '.join(names)}")
        (copy / path).parent.mkdir(parents=True, exist_ok=True)
        with (copy / path).open("a", encoding="utf-8") as handle:
            handle.write("\n\n" + stub_text(names))
    return copy


def functions_in(path: Path) -> int:
    return len(re.findall(r"^(?:async )?def test_", path.read_text(encoding="utf-8"), re.M))


def stub_check(clone: Path, tests: list[str]) -> int:
    copy = _names_copy(clone, "-names", tests, show=True)
    try:
        for test in tests:
            done = _python(
                copy, ["-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", test]
            )
            last = done.stdout.splitlines()[-1] if done.stdout else "no output"
            print(f"{test}: {functions_in(copy / test)} functions, {last}")
        fail_check(copy, tests)
        passed = _python(
            copy, ["-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider", "-rA", *tests]
        ).stdout.splitlines()
        for line in passed:
            if line.startswith("PASSED "):
                print(f"  passes on the stub: {line.removeprefix('PASSED ')}")
    finally:
        shutil.rmtree(copy)
    return 0


def collected_ids(clone: Path, tests: list[str]) -> dict[str, list[str]]:
    """Every collected test id per file, in a throwaway copy with names-only stubs."""
    ids: dict[str, list[str]] = {test: [] for test in tests}
    if not tests:
        return ids
    copy = _names_copy(clone, "-lint", tests, show=False)
    try:
        done = _python(
            copy, ["-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *tests]
        )
    finally:
        shutil.rmtree(copy)
    for line in done.stdout.splitlines():
        path, _, _ = line.partition("::")
        if path in ids:
            ids[path].append(line)
    return ids


def search_commands(markdown: str) -> list[str]:
    """The lines of the first fenced block after a `Searches` heading (`###` or `## n.`)."""
    lines = markdown.splitlines()
    heading = re.compile(r"^#{2,3} (?:[0-9]+\. )?Searches$")
    start = next((index for index, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return []
    commands: list[str] = []
    inside = False
    for line in lines[start + 1 :]:
        if line.startswith("```"):
            if inside:
                break
            inside = True
            continue
        if inside and line.strip():
            commands.append(line)
    return commands


def run_searches(spec_path: Path, cwd: Path) -> int:
    commands = search_commands(spec_path.read_text(encoding="utf-8"))
    if not commands:
        print("no Searches block")
        return 1
    for command in commands:
        done = subprocess.run(["/bin/zsh", "-c", command], cwd=cwd, capture_output=True, text=True)
        count = len([line for line in done.stdout.splitlines() if line.strip()])
        note = f"  (exit {done.returncode})" if done.returncode not in (0, 1) else ""
        print(f"{count:3}  {command[:90]}{note}")
    return 0


def expand_search(name: str, modules: list[str]) -> str:
    if name not in SEARCHES:
        raise SystemExit(f"unknown search {name!r}; known: {', '.join(SEARCHES)}")
    return SEARCHES[name][1].replace("{modules}", " ".join(modules) or "src")


def catalog_entry(command: str) -> tuple[str, str] | None:
    """The catalog's (rule, plant line) for an expanded command, or None for a phase's own."""
    for rule, template, plant in SEARCHES.values():
        before, marker, after = template.partition("{modules}")
        if command == template:
            return rule, plant
        if marker and command.startswith(before) and command.endswith(after):
            return rule, plant
    return None


def plant_path(command: str) -> str:
    _, _, paths = command.partition(" -- ")
    for token in paths.split():
        token = token.strip("'")
        if token.endswith(".py") and not token.startswith(":!"):
            return token
    return "src/conductor/_planted.py"


def plant_and_search(spec_path: Path, cwd: Path, plant: Path) -> int:
    if str(plant) == "auto":
        lines: list[tuple[str, str]] = []
        for command in search_commands(spec_path.read_text(encoding="utf-8")):
            entry = catalog_entry(command)
            if entry is None:
                print(f"no catalog plant (give --plant FILE): {command[:70]}")
                continue
            lines.append((plant_path(command), entry[1]))
    else:
        text = plant.read_text(encoding="utf-8")
        lines = [(a, b) for a, _, b in (line.partition("\t") for line in text.splitlines()) if b]
    planted: dict[Path, list[str]] = {}
    for path, text in lines:
        planted.setdefault(cwd / path, []).append(text)
    saved = {path: path.read_bytes() if path.exists() else None for path in planted}
    try:
        for path, texts in planted.items():
            before = (saved[path] or b"").decode()
            if before and not before.endswith("\n"):
                before += "\n"
            path.write_text(before + "\n".join(texts) + "\n", encoding="utf-8")
        return run_searches(spec_path, cwd)
    finally:
        for path, content in saved.items():
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
        print("planted lines removed")


def section(text: str, heading: str) -> str:
    """The text under a heading line, up to the next `## ` heading (subsections included)."""
    found = re.search(rf"^{re.escape(heading)}[ \t]*$", text, flags=re.MULTILINE)
    if found is None:
        return ""
    start = found.end()
    following = re.search(r"^## ", text[start:], flags=re.MULTILINE)
    return text[start : start + following.start()] if following else text[start:]


def guide_section(text: str, name: str) -> str:
    found = re.search(rf"^## (?:[0-9]+\. )?{re.escape(name)}[ \t]*$", text, flags=re.MULTILINE)
    return section(text, found.group(0).rstrip()) if found else ""


def table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))])
    return rows[1:]


def paths_in(cell: str) -> list[str]:
    return [name for name in re.findall(r"`([^`]+)`", cell) if "/" in name and " " not in name]


def tracked(root: Path, paths: list[str]) -> set[str]:
    done = subprocess.run(
        ["git", "ls-files", "--", *paths], cwd=root, capture_output=True, text=True, check=False
    )
    return set(done.stdout.split())


def _first_span(cell: str) -> str:
    found = re.search(r"`([^`]+)`", cell)
    return found.group(1).replace("\\|", "|") if found else ""


def lint(spec_path: Path, guide_path: Path, clone: Path) -> int:
    from conductor.acceptance import read_rows

    spec = spec_path.read_text(encoding="utf-8")
    guide = guide_path.read_text(encoding="utf-8")
    problems: list[str] = []
    for name, text in (("spec", spec), ("guide", guide)):
        for number, line in enumerate(text.splitlines(), start=1):
            if PLACEHOLDER.search(line):
                problems.append(f"{name}:{number}: a placeholder is left")
            for word in BANNED:
                if word in line.lower():
                    problems.append(f"{name}:{number}: banned wording {word!r}")
    head = re.match(r"# Phase ([1-9][0-9]*[a-z]?): ", spec)
    if head is None:
        problems.append("spec:1: must start with '# Phase <id>: <title>'")
    acceptance = section(spec, "## Acceptance")
    accept_rows = table_rows(acceptance)
    given_rows = table_rows(section(spec, "## Given files"))
    given = [path for row in given_rows for path in paths_in(row[0])]
    if not given_rows:
        problems.append("spec: no `## Given files` table")
    for path in given:
        if not (clone / path).exists():
            problems.append(f"spec: given file {path} does not exist in the clone")
    protected = " ".join(row[0] for row in accept_rows if "git diff HEAD --stat" in row[0])
    for path in given:
        if path not in protected:
            problems.append(
                f"spec: given file {path} is missing from the `git diff HEAD --stat` row"
            )
    if head is not None:
        probe = f"docs/verification/probe-{file_id(head.group(1))}.py"
        if probe not in given:
            problems.append(f"spec: the probe {probe} is not a given file")
        if not any(f".venv/bin/python {probe}" in row[0] for row in accept_rows):
            problems.append(f"spec: acceptance does not run {probe}")
    tests = [path for path in given if Path(path).name.startswith("test_")]
    new_tests = tests  # given files are tracked once the spec is committed; count them all
    spot_ids = re.findall(r"`(tests/[^`:]+\.py::[^`]+)`", guide)
    spot_files = sorted({test_id.partition("::")[0] for test_id in spot_ids} - set(new_tests))
    ids = collected_ids(clone, new_tests + [path for path in spot_files if (clone / path).exists()])
    total = sum(len(ids[path]) for path in new_tests)
    for row in given_rows:
        stated = re.search(r"([0-9]+) tests? from ([0-9]+) functions?", row[1])
        files = [path for path in paths_in(row[0]) if path in new_tests]
        if len(files) != 1:
            continue
        found = (len(ids[files[0]]), functions_in(clone / files[0]))
        if stated is None or found != (int(stated.group(1)), int(stated.group(2))):
            problems.append(f"spec: {files[0]} has {found[0]} tests from {found[1]} functions")
    count = re.search(r"Given test count: \*\*([0-9]+)\*\*", spec)
    if count is None or int(count.group(1)) != total:
        problems.append(f"spec: `Given test count: **{total}**` is missing or wrong")
    base = re.search(r"N is `?([0-9]+)`?", spec)
    if base is None:
        problems.append("spec: no `N is <count>` in the starting state")
    else:
        least = re.search(r"at least ([0-9]+) passed", acceptance)
        if least is None or int(least.group(1)) != int(base.group(1)) + total:
            problems.append(
                f"spec: acceptance should say at least {int(base.group(1)) + total} passed"
            )
    if f"`{total} passed`" not in acceptance:
        problems.append(f"spec: acceptance should name `{total} passed` for the given tests")
    wanted = [_first_span(row[0]) for row in accept_rows]
    gates = [_first_span(row[1]) for row in table_rows(guide_section(guide, "Gates"))]
    if gates[: len(wanted)] != wanted:
        problems.append("guide: its first gates differ from the spec's acceptance commands")
    known = {line for found in ids.values() for line in found}
    for test_id in spot_ids:
        if test_id not in known:
            problems.append(f"guide: {test_id} is not a collected test id")
    searches = search_commands(spec)
    if search_commands(guide) != searches:
        problems.append("guide: its searches differ from the spec's")
    if [row.command for row in read_rows(spec, "Acceptance") if row.label.startswith("Q")] != (
        searches
    ):
        problems.append("spec: accept.py extracts different search commands")
    if [row.command for row in read_rows(guide, "Searches")] != searches:
        problems.append("guide: accept.py extracts different search commands")
    for problem in problems:
        print(problem)
    print("Lint OK." if not problems else f"{len(problems)} problems.")
    return 1 if problems else 0


def promote(clone: Path, files: list[str], ignore: list[str]) -> int:
    differ = []
    for name in files:
        (ROOT / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(clone / name, ROOT / name)
        if not filecmp.cmp(clone / name, ROOT / name, shallow=False):
            differ.append(name)
    print(f"copied {len(files)}; differ: {', '.join(differ) or 'none'}")
    done = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider"]
        + [f"--ignore={name}" for name in ignore],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    print("Start:", lines[-1] if lines else "no output")
    return 1 if differ else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    clone = commands.add_parser("clone")
    clone.add_argument("id")
    clone.add_argument("--scratch", type=Path, required=True)
    failcheck = commands.add_parser("failcheck")
    failcheck.add_argument("clone", type=Path)
    failcheck.add_argument("tests", nargs="+")
    stubcheck = commands.add_parser("stubcheck")
    stubcheck.add_argument("clone", type=Path)
    stubcheck.add_argument("tests", nargs="+")
    searches = commands.add_parser("searches")
    searches.add_argument("spec", type=Path)
    searches.add_argument("--cwd", type=Path, default=ROOT)
    searches.add_argument("--plant", type=Path)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("names", nargs="*")
    catalog.add_argument("--modules", nargs="+", default=[])
    linter = commands.add_parser("lint")
    linter.add_argument("spec", type=Path)
    linter.add_argument("guide", type=Path)
    linter.add_argument("--clone", type=Path, required=True)
    given = commands.add_parser("promote")
    given.add_argument("clone", type=Path)
    given.add_argument("files", nargs="+")
    given.add_argument("--ignore", nargs="+", action="extend", default=[])
    args = parser.parse_args()
    if args.command == "clone":
        return make_clone(args.id, args.scratch)
    if args.command == "failcheck":
        return fail_check(args.clone, args.tests)
    if args.command == "stubcheck":
        return stub_check(args.clone, args.tests)
    if args.command == "searches":
        if args.plant is not None:
            return plant_and_search(args.spec, args.cwd, args.plant)
        return run_searches(args.spec, args.cwd)
    if args.command == "catalog":
        for name in args.names or DEFAULT_SEARCHES.split(","):
            print(expand_search(name, args.modules))
        return 0
    if args.command == "lint":
        return lint(args.spec, args.guide, args.clone)
    return promote(args.clone, args.files, args.ignore)


if __name__ == "__main__":
    sys.exit(main())
