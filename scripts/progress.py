"""Append, or replace, one phase's progress entry in the form check_reports.py enforces.

Run it as: .venv/bin/python scripts/progress.py --phase ID --title TEXT --date YYYY-MM-DD \
    --tests-before N --tests-after N --given N --names TEXT --changed N \
    [--deviation TEXT ...] [--follow-up TEXT ...]

A stop's `Stopped: ...` line is the first --follow-up.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from conductor.reports import ProgressEntry, put_entry

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append or replace a progress entry.")
    parser.add_argument("--file", type=Path, default=ROOT / "docs" / "progress.md")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--date", required=True, help="ISO date, YYYY-MM-DD.")
    parser.add_argument("--tests-before", required=True, type=int)
    parser.add_argument("--tests-after", required=True, type=int)
    parser.add_argument("--given", required=True, type=int)
    parser.add_argument("--names", required=True, help="New public names, or None.")
    parser.add_argument("--changed", required=True, type=int)
    parser.add_argument("--deviation", action="append")
    parser.add_argument("--follow-up", action="append")
    options = parser.parse_args(argv)
    try:
        when = date.fromisoformat(options.date)
    except ValueError:
        print("Error: the date is not a real date", file=sys.stderr)
        return 2
    entry = ProgressEntry(
        phase=options.phase,
        title=options.title,
        date=when,
        tests_before=options.tests_before,
        tests_after=options.tests_after,
        given=options.given,
        new_names=options.names,
        changed_files=options.changed,
        deviations=tuple(options.deviation or ()),
        follow_ups=tuple(options.follow_up or ()),
        line=0,
    )
    original = options.file.read_text(encoding="utf-8")
    try:
        updated = put_entry(original, entry)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    options.file.write_text(updated, encoding="utf-8")
    print(f"Progress entry for Phase {options.phase} written.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
