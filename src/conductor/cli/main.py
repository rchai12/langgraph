import json
from typing import Annotated, NoReturn

import typer

from conductor.config import Settings, SettingsError, get_settings
from conductor.diagnostics import run_checks, summary_line
from conductor.events import EventLog, EventLogCorrupt, RunNotFound

app = typer.Typer(no_args_is_help=True, add_completion=False)
runs_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(runs_app, name="runs")

_STORED_AT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _bail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _settings() -> Settings:
    try:
        return get_settings()
    except SettingsError as error:
        _bail(str(error))


@app.command()
def doctor() -> None:
    settings = _settings()
    checks = run_checks(settings)
    for check in checks:
        typer.echo(check.line)
    typer.echo(summary_line(checks))
    if any(check.status == "FAIL" for check in checks):
        raise typer.Exit(1)


@runs_app.command("list")
def list_runs() -> None:
    settings = _settings()
    try:
        found = EventLog(settings.runs_dir).runs()
    except (ValueError, RunNotFound, EventLogCorrupt) as error:
        _bail(str(error))
    if not found:
        typer.echo("No runs yet.")
        return
    for summary in found:
        when = summary.started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        word = "event" if summary.events == 1 else "events"
        typer.echo(f"{summary.run_id}  {when}  {summary.events} {word}")


@runs_app.command("show")
def show(run_id: str, payload: Annotated[bool, typer.Option("--payload")] = False) -> None:
    settings = _settings()
    try:
        events = EventLog(settings.runs_dir).read(run_id)
    except (ValueError, RunNotFound, EventLogCorrupt) as error:
        _bail(str(error))
    for event in events:
        line = f"{event.seq:4d}  {event.at.strftime(_STORED_AT)}  {event.kind.value}"
        if event.node is not None:
            line = f"{line}  {event.node}"
        typer.echo(line)
        if payload and event.payload:
            rendered = json.dumps(event.payload, ensure_ascii=False, sort_keys=True, indent=2)
            for part in rendered.split("\n"):
                typer.echo(f"      {part}")
