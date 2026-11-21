from typing import Annotated

import typer

from conductor import runtime, times
from conductor.cli import common
from conductor.config import Settings
from conductor.decisions import answer_escalation
from conductor.store import Store, StoredEscalation
from conductor.views import escalation_lines

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _escalation_json(stored: StoredEscalation) -> dict[str, object]:
    answer = stored.answer
    dumped = None if answer is None else answer.model_dump(mode="json")
    return {
        "escalation_id": stored.escalation_id,
        "raised_at": times.display(stored.raised_at),
        "escalation": stored.escalation.model_dump(mode="json"),
        "answer": dumped,
    }


@app.command("list")
def list_escalations(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, store: Store) -> None:
        opened = store.open_escalations()
        if json_output:
            common.dump([_escalation_json(stored) for stored in opened])
            return
        if not opened:
            typer.echo("No open escalations.")
            return
        for stored in opened:
            when = times.display(stored.raised_at)
            typer.echo(
                f"{stored.escalation_id}  {when}  {stored.escalation.kind}"
                f"  run {stored.escalation.run_id}"
            )

    common.with_store(work)


@app.command("show")
def show_escalation(
    escalation_id: str, json_output: Annotated[bool, typer.Option("--json")] = False
) -> None:
    def work(settings: Settings, store: Store) -> None:
        stored = store.escalation(escalation_id)
        if json_output:
            common.dump(_escalation_json(stored))
            return
        typer.echo("\n".join(escalation_lines(stored)))

    common.with_store(work)


@app.command("retry")
def retry(
    escalation_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.escalation(escalation_id)

        def record() -> None:
            answer_escalation(
                opened.store,
                escalation_id,
                "retry",
                channel="terminal",
                decided_by=settings.decided_by,
                note=note,
            )

        common.decide_then_resume(
            opened,
            stored.escalation.run_id,
            record,
            f"Retry recorded for {escalation_id}.",
            no_resume=no_resume,
            confirm=("Retry?", "\n".join(escalation_lines(stored))),
            yes=yes,
        )

    common.with_runtime(work)


@app.command("cancel")
def cancel(
    escalation_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.escalation(escalation_id)

        def record() -> None:
            answer_escalation(
                opened.store,
                escalation_id,
                "cancel",
                channel="terminal",
                decided_by=settings.decided_by,
                note=note,
            )

        common.decide_then_resume(
            opened,
            stored.escalation.run_id,
            record,
            f"Cancelled {escalation_id}.",
            no_resume=no_resume,
        )

    common.with_runtime(work)
