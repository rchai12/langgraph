from pathlib import Path
from typing import Annotated

import typer

from conductor import domains
from conductor.cli import common
from conductor.evals import run as evals_run
from conductor.evals.cases import CaseFileError, load_cases
from conductor.evals.report import (
    ReportError,
    build_report,
    compare_lines,
    latest_report,
    save_report,
)
from conductor.events import EventLog
from conductor.registry import Registry

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _case_files(given: str) -> list[Path]:
    path = Path(given)
    names = [path] if path.is_file() else sorted(path.glob("*.toml"))
    return [item for item in names if item.suffix == ".toml"]


@app.command("run")
def eval_run(
    cases: Annotated[str, typer.Option("--cases")] = "evals/cases",
    runs: Annotated[int, typer.Option("--runs")] = 5,
) -> None:
    if not 1 <= runs <= evals_run.MAX_RUNS:
        common.bail("--runs must be 1 to 100")
    files = _case_files(cases)
    if not files:
        common.bail(f"no case files at {cases}")
    settings = common.load_settings()
    registry = Registry(domains.registered(settings))
    seen: set[str] = set()
    loaded = []
    for path in files:
        try:
            loaded.extend(load_cases(path, registry, seen=seen))
        except CaseFileError as error:
            common.bail(str(error))
    reports = settings.data_dir / "evals" / "reports"
    try:
        previous = latest_report(reports)
    except ReportError as error:
        common.bail(str(error))
    model = evals_run.model_for(settings)
    log = EventLog(settings.data_dir / "evals" / "runs")
    results = []
    for case in loaded:
        result = evals_run.run_case(
            case,
            registry,
            model=model,
            model_name=settings.model,
            log=log,
            runs=runs,
        )
        typer.echo(evals_run.case_line(result))
        results.append(result)
    typer.echo(evals_run.overall_line(tuple(results)))
    current = build_report(results, files=files, model_name=settings.model, runs=runs, log=log)
    typer.echo(f"report {save_report(current, reports).name}")
    if previous is not None:
        typer.echo(f"previous {previous[0]}")
        for line in compare_lines(previous[1], current):
            typer.echo(line)
