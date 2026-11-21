import json
from typing import Annotated, Any

import typer

from conductor import runtime, times
from conductor.cli import common
from conductor.config import Settings
from conductor.decisions import decide_approval, parse_json_object
from conductor.store import Store, StoredApproval
from conductor.views import request_lines

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _args(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_object(text: str) -> dict[str, Any]:
    parsed = parse_json_object(text)
    if parsed is None:
        common.bail("--args must be a JSON object")
    return parsed


def _approval_json(stored: StoredApproval) -> dict[str, object]:
    decision = stored.decision
    dumped = None if decision is None else decision.model_dump(mode="json")
    return {"request": stored.request.model_dump(mode="json"), "decision": dumped}


@app.command("list")
def list_approvals(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, store: Store) -> None:
        pending = store.pending()
        if json_output:
            common.dump([request.model_dump(mode="json") for request in pending])
            return
        if not pending:
            typer.echo("No pending approvals.")
            return
        for request in pending:
            actions = ", ".join(step.action for step in request.steps)
            when = times.display(request.requested_at)
            typer.echo(f"{request.approval_id}  {when}  {request.stage}  {actions}")

    common.with_store(work)


@app.command("show")
def show_approval(
    approval_id: str, json_output: Annotated[bool, typer.Option("--json")] = False
) -> None:
    def work(settings: Settings, store: Store) -> None:
        stored = store.approval(approval_id)
        if json_output:
            common.dump(_approval_json(stored))
            return
        typer.echo("\n".join(request_lines(stored)))

    common.with_store(work)


@app.command("approve")
def approve(
    approval_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.approval(approval_id)

        def record() -> None:
            decide_approval(
                opened.store,
                opened.registry,
                approval_id,
                "approve",
                channel="terminal",
                decided_by=settings.decided_by,
                note=note,
            )

        common.decide_then_resume(
            opened,
            stored.request.run_id,
            record,
            f"Approved {approval_id}.",
            no_resume=no_resume,
            confirm=("Approve?", "\n".join(request_lines(stored))),
            yes=yes,
        )

    common.with_runtime(work)


@app.command("reject")
def reject(
    approval_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.approval(approval_id)

        def record() -> None:
            decide_approval(
                opened.store,
                opened.registry,
                approval_id,
                "reject",
                channel="terminal",
                decided_by=settings.decided_by,
                note=note,
            )

        common.decide_then_resume(
            opened,
            stored.request.run_id,
            record,
            f"Rejected {approval_id}.",
            no_resume=no_resume,
        )

    common.with_runtime(work)


@app.command("edit")
def edit(
    approval_id: str,
    args_text: Annotated[str, typer.Option("--args")],
    note: Annotated[str, typer.Option("--note")] = "",
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    edited = _json_object(args_text)

    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.approval(approval_id)
        preview = "\n".join(request_lines(stored)) + f"\nedited args: {_args(edited)}"

        def record() -> None:
            decide_approval(
                opened.store,
                opened.registry,
                approval_id,
                "edit",
                channel="terminal",
                decided_by=settings.decided_by,
                note=note,
                edited_args=edited,
            )

        common.decide_then_resume(
            opened,
            stored.request.run_id,
            record,
            f"Approved {approval_id} with edited arguments.",
            no_resume=no_resume,
            confirm=("Approve with these arguments?", preview),
            yes=yes,
        )

    common.with_runtime(work)
