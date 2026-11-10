import hashlib
import os
import re
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, ValidationError

from conductor import clock
from conductor.contracts import Contract
from conductor.events import EventKind, EventLog, RunNotFound

from .run import CaseResult

_REPORT_NAME = re.compile(r"\d{8}T\d{12}Z\.json")
_LABELS = (
    ("consistent", "consistent"),
    ("route_ok", "route"),
    ("plan_ok", "plan"),
    ("args_ok", "args"),
    ("valid", "valid"),
    ("escalated", "escalated"),
)


class CaseNumbers(Contract):
    id: str
    runs: int
    consistent: int
    route_ok: int
    plan_ok: int
    args_ok: int | None
    valid: int
    escalated: int
    unavailable: int
    seconds: list[float]
    run_ids: list[str]


class Report(Contract):
    version: Literal[1]
    created: AwareDatetime
    model: str
    digests: list[str]
    templates: dict[str, list[str]]
    case_files: dict[str, str]
    runs: int
    cases: list[CaseNumbers]


class ReportError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} is not a report")


def build_report(
    results: Sequence[CaseResult],
    *,
    files: Sequence[Path],
    model_name: str,
    runs: int,
    log: EventLog,
) -> Report:
    digests: set[str] = set()
    templates: dict[str, set[str]] = {}
    for result in results:
        for run_id in result.run_ids:
            try:
                events = log.read(run_id)
            except RunNotFound:
                continue
            for event in events:
                if event.kind is not EventKind.MODEL_REQUEST:
                    continue
                digests.add(str(event.payload["digest"]))
                point = str(event.payload["point"])
                templates.setdefault(point, set()).add(str(event.payload["template_sha256"]))
    return Report(
        version=1,
        created=clock.now(),
        model=model_name,
        digests=sorted(digests),
        templates={point: sorted(found) for point, found in templates.items()},
        case_files={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        runs=runs,
        cases=[_numbers(result) for result in results],
    )


def save_report(report: Report, folder: Path) -> Path:
    if not folder.exists():
        folder.mkdir(parents=True, mode=0o700)
        folder.chmod(0o700)
    name = report.created.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    path = folder / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, (report.model_dump_json(indent=2) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def latest_report(folder: Path) -> tuple[str, Report] | None:
    if not folder.is_dir():
        return None
    names = [path.name for path in folder.iterdir() if _REPORT_NAME.fullmatch(path.name)]
    if not names:
        return None
    name = max(names)
    try:
        return name, Report.from_json((folder / name).read_bytes())
    except (ValidationError, ValueError, UnicodeDecodeError):
        raise ReportError(name) from None


def compare_lines(previous: Report, current: Report) -> list[str]:
    lines: list[str] = []
    if previous.model != current.model:
        lines.append("changed: model")
    if previous.digests != current.digests:
        lines.append("changed: digest")
    for point in sorted(set(previous.templates) | set(current.templates)):
        if previous.templates.get(point, []) != current.templates.get(point, []):
            lines.append(f"changed: template {point}")
    for name in sorted(set(previous.case_files) | set(current.case_files)):
        if previous.case_files.get(name) != current.case_files.get(name):
            lines.append(f"changed: case file {name}")
    earlier = {case.id: case for case in previous.cases}
    for case in current.cases:
        old = earlier.get(case.id)
        if old is None:
            continue
        moved = _moved(old, case)
        if moved:
            lines.append(f"{case.id}  {'  '.join(moved)}")
    current_ids = {case.id for case in current.cases}
    for case in current.cases:
        if case.id not in earlier:
            lines.append(f"added: case {case.id}")
    for case in previous.cases:
        if case.id not in current_ids:
            lines.append(f"removed: case {case.id}")
    return lines or ["no change"]


def _numbers(result: CaseResult) -> CaseNumbers:
    return CaseNumbers(
        id=result.case_id,
        runs=result.runs,
        consistent=result.consistent,
        route_ok=result.route_ok,
        plan_ok=result.plan_ok,
        args_ok=result.args_ok,
        valid=result.valid,
        escalated=result.escalated,
        unavailable=result.unavailable,
        seconds=list(result.seconds),
        run_ids=list(result.run_ids),
    )


def _moved(previous: CaseNumbers, current: CaseNumbers) -> list[str]:
    lines: list[str] = []
    for field_name, label in _LABELS:
        before = getattr(previous, field_name)
        after = getattr(current, field_name)
        if _differs(before, previous.runs, after, current.runs):
            shown = f"{_shown(before, previous.runs)} -> {_shown(after, current.runs)}"
            lines.append(f"{label} {shown}")
    return lines


def _differs(before: int | None, before_runs: int, after: int | None, after_runs: int) -> bool:
    if (before is None) != (after is None):
        return True
    if before is None:
        return False
    return before * after_runs != after * before_runs


def _shown(count: int | None, runs: int) -> str:
    if count is None:
        return "-"
    return f"{count}/{runs}"
