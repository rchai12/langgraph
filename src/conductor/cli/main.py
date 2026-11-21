from typing import Annotated

import typer

from conductor import runtime
from conductor.cli import approvals, common, escalations, evals, runs, web
from conductor.config import Settings
from conductor.diagnostics import run_checks, summary_line

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def doctor() -> None:
    settings = common.load_settings()
    checks = run_checks(settings)
    for check in checks:
        typer.echo(check.line)
    typer.echo(summary_line(checks))
    if any(check.status == "FAIL" for check in checks):
        raise typer.Exit(1)


@app.command()
def ask(request: str, json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        common.emit(opened, runtime.ask(opened, request), json_output)

    common.with_runtime(work)


@app.command()
def resume(run_id: str, json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        common.emit(opened, runtime.resume(opened, run_id), json_output)

    common.with_runtime(work)


app.add_typer(runs.app, name="runs")
app.add_typer(evals.app, name="eval")
app.add_typer(approvals.app, name="approvals")
app.add_typer(escalations.app, name="escalations")
app.command("web")(web.serve)
