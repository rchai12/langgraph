import json
from typing import Annotated

import typer

from conductor import times
from conductor.cli import common
from conductor.events import EventLog, EventLogCorrupt, RunNotFound

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("list")
def list_runs() -> None:
    settings = common.load_settings()
    try:
        found = EventLog(settings.runs_dir).runs()
    except (ValueError, RunNotFound, EventLogCorrupt) as error:
        common.bail(str(error))
    if not found:
        typer.echo("No runs yet.")
        return
    for summary in found:
        when = times.display(summary.started_at)
        word = "event" if summary.events == 1 else "events"
        typer.echo(f"{summary.run_id}  {when}  {summary.events} {word}")


@app.command("show")
def show(run_id: str, payload: Annotated[bool, typer.Option("--payload")] = False) -> None:
    settings = common.load_settings()
    try:
        events = EventLog(settings.runs_dir).read(run_id)
    except (ValueError, RunNotFound, EventLogCorrupt) as error:
        common.bail(str(error))
    for event in events:
        line = f"{event.seq:4d}  {times.stored(event.at)}  {event.kind.value}"
        if event.node is not None:
            line = f"{line}  {event.node}"
        typer.echo(line)
        if payload and event.payload:
            rendered = json.dumps(event.payload, ensure_ascii=False, sort_keys=True, indent=2)
            for part in rendered.split("\n"):
                typer.echo(f"      {part}")
