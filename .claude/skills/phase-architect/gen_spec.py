"""Build a phase spec or verification guide from a Markdown template, and check what it embeds.

Run from the repository root with the project's interpreter:

    .venv/bin/python .claude/skills/phase-architect/gen_spec.py \
        --root <scratch clone> --template <spec template .md> --out docs/phases/<slug>.md \
        [--var NAME=VALUE ...]

Placeholders in the template (plain Markdown, so no Python string escaping):

- ``{{file:PATH}}``: the file at ROOT/PATH (or an absolute PATH) as a fenced code block, its
  language taken from the suffix. Use it for every given test, migration, template, and probe.
- ``{{raw:PATH}}``: the file's text inline, without a fence.
- ``{{var:NAME}}``: a value given with ``--var NAME=VALUE`` (N, the given test count, commands).

The output is refused when a placeholder is left or a variable is missing. After writing, each
``{{file:...}}`` block is read back from the output and compared with its source.
"""

import argparse
import re
import sys
from pathlib import Path

FENCE = "```"
LANGUAGES = {
    ".py": "python",
    ".html": "html",
    ".css": "css",
    ".sh": "sh",
    ".toml": "toml",
    ".md": "markdown",
    ".json": "json",
    ".txt": "text",
}
PLACEHOLDER = re.compile(r"\{\{(file|raw|var):([^}]+)\}\}")


def source(root: Path, path: str) -> Path:
    given = Path(path.strip())
    return given if given.is_absolute() else root / given


def fenced(file: Path) -> str:
    language = LANGUAGES.get(file.suffix, "sh" if file.suffix == "" else "text")
    return f"{FENCE}{language}\n{file.read_text(encoding='utf-8').rstrip(chr(10))}\n{FENCE}"


def render(template: str, root: Path, values: dict[str, str]) -> tuple[str, list[Path]]:
    embedded: list[Path] = []

    def replace(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2).strip()
        if kind == "var":
            if name not in values:
                raise SystemExit(f"error: no --var given for {name}")
            return values[name]
        file = source(root, name)
        if not file.is_file():
            raise SystemExit(f"error: {file} not found")
        if kind == "raw":
            return file.read_text(encoding="utf-8").rstrip("\n")
        embedded.append(file)
        return fenced(file)

    return PLACEHOLDER.sub(replace, template), embedded


def check_copies(text: str, embedded: list[Path]) -> list[str]:
    """Each embedded file must appear in the output exactly as its source."""
    return [str(file) for file in embedded if fenced(file) not in text]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a spec or guide from a template.")
    parser.add_argument("--root", required=True, type=Path, help="the scratch clone")
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--var", action="append", default=[], help="NAME=VALUE")
    args = parser.parse_args(argv)
    values = dict(item.split("=", 1) for item in args.var)
    text, embedded = render(args.template.read_text(encoding="utf-8"), args.root, values)
    left = PLACEHOLDER.findall(text)
    if left:
        print(f"error: placeholders left: {left}", file=sys.stderr)
        return 1
    args.out.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    wrong = check_copies(args.out.read_text(encoding="utf-8"), embedded)
    if wrong:
        print(f"error: embedded copies differ: {wrong}", file=sys.stderr)
        return 1
    print(f"{args.out}: {len(text.splitlines())} lines, {len(embedded)} files embedded and checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
