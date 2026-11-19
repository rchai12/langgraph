"""Read a spec's acceptance table or a guide's gates, run each command, and print a digest.

Phase tooling for `scripts/accept.py`; it never runs as part of the agent.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HEADING_MESSAGE = "no such heading"
MAX_DETAIL = 20
_SPAN = re.compile(r"`([^`]*)`")


@dataclass(frozen=True)
class Row:
    label: str
    command: str


def read_rows(markdown: str, heading: str) -> list[Row]:
    """Rows under `## <heading>` or `## <n>. <heading>`, up to the next `## ` heading.

    A table row's command is its first backtick span; a fenced block's lines are searches.
    """
    lines = markdown.splitlines()
    marker = re.compile(rf"^## (?:[0-9]+\. )?{re.escape(heading)}$")
    start = next((index + 1 for index, line in enumerate(lines) if marker.match(line)), None)
    if start is None:
        raise ValueError(f"{HEADING_MESSAGE}: {heading}")
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        section.append(line)
    return _rows(section)


def digest(row: Row, output: str, code: int) -> list[str]:
    lines = _kept(output)
    if "scripts/check.py" in row.command:
        head = _last(lines)
        details = _sections(lines)
    elif row.command.startswith(("git status", "git diff", "git grep")):
        head = _count(len(lines))
        details = lines
    else:
        head = _last(lines)
        details = []
    shown = details[:MAX_DETAIL]
    result = [f"{row.label}: {head}{_suffix(row.command, code)}"]
    result.extend(f"  {line}" for line in shown)
    hidden = len(details) - len(shown)
    if hidden:
        result.append(f"  ... {hidden} more lines in the log")
    return result


def accept(
    rows: list[Row],
    run: Callable[[str], tuple[int, str]],
    log_dir: Path,
) -> list[str]:
    log_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        code, output = run(row.command)
        (log_dir / f"{row.label}.log").write_text(f"$ {row.command}\n{output}", encoding="utf-8")
        lines.extend(digest(row, output, code))
    lines.append(f"Logs: {log_dir}")
    return lines


def _rows(lines: list[str]) -> list[Row]:
    rows: list[Row] = []
    in_code = False
    table_index = 0
    a_number = 0
    q_number = 0
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            table_index = 0
            continue
        if in_code:
            if line.strip():
                q_number += 1
                rows.append(Row(f"Q{q_number}", line))
            continue
        if not line.startswith("|"):
            table_index = 0
            continue
        table_index += 1
        if table_index <= 2:
            continue
        command = _command(line)
        if command is None:
            continue
        first = [part.strip() for part in line.split("|")[1:-1]][0]
        if "`" in first:
            a_number += 1
            label = f"A{a_number}"
        else:
            label = first
        rows.append(Row(label, command))
    return rows


def _command(line: str) -> str | None:
    found = _SPAN.search(line)
    if found is None:
        return None
    return found.group(1).replace("\\|", "|")


def _kept(output: str) -> list[str]:
    return [line.rstrip() for line in output.splitlines() if line.strip()]


def _last(lines: list[str]) -> str:
    if lines:
        return lines[-1]
    return "empty"


def _count(count: int) -> str:
    if count == 0:
        return "empty"
    if count == 1:
        return "1 line"
    return f"{count} lines"


def _sections(lines: list[str]) -> list[str]:
    details: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index] != "Sections:":
            index += 1
            continue
        details.append(lines[index])
        index += 1
        while index < len(lines) and lines[index].startswith("  "):
            details.append(lines[index])
            index += 1
    return details


def _suffix(command: str, code: int) -> str:
    if code == 0 or (code == 1 and command.startswith("git grep")):
        return ""
    return f" (exit {code})"
