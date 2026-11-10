import dataclasses
import json
import socket
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, NoReturn

import typer
import uvicorn

from conductor import runtime
from conductor.config import Settings, SettingsError, get_settings
from conductor.decisions import answer_escalation, decide_approval, parse_json_object
from conductor.diagnostics import run_checks, summary_line
from conductor.events import EventLog, EventLogCorrupt, RunNotFound
from conductor.graph.supervisor import RunError, RunState
from conductor.mcp_client.check import ToolCheckFailed
from conductor.policy import DecisionRefused
from conductor.registry import NotRegistered
from conductor.store import (
    AlreadyDecided,
    NotFound,
    Store,
    StoredApproval,
    StoredEscalation,
    StoreError,
)
from conductor.views import escalation_lines, request_lines
from conductor.web.app import create_app

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


approvals_app = typer.Typer(no_args_is_help=True, add_completion=False)
escalations_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(approvals_app, name="approvals")
app.add_typer(escalations_app, name="escalations")

_WHEN = "%Y-%m-%dT%H:%M:%SZ"
_CAUGHT = (StoreError, NotFound, AlreadyDecided, NotRegistered, ValueError, DecisionRefused)


def _report(error: BaseException) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    if isinstance(error, DecisionRefused):
        for problem in error.problems:
            typer.echo(f"  {problem.loc}: {problem.code}", err=True)
    if isinstance(error, ToolCheckFailed):
        for problem in error.problems:
            typer.echo(f"  {problem.text}", err=True)
    raise typer.Exit(1)


def _run(work: Callable[[Settings, Store], None]) -> None:
    settings = _settings()
    try:
        work(settings, Store(settings.db_path))
    except _CAUGHT as error:
        _report(error)


def _session(work: Callable[[Settings, runtime.Runtime], None]) -> None:
    settings = _settings()
    try:
        with runtime.open_runtime(settings) as opened:
            work(settings, opened)
    except (*_CAUGHT, RunError, ToolCheckFailed) as error:
        _report(error)


def _when(moment: datetime) -> str:
    return moment.strftime(_WHEN)


def _args(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _dump(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def _json_object(text: str) -> dict[str, Any]:
    parsed = parse_json_object(text)
    if parsed is None:
        _bail("--args must be a JSON object")
    return parsed


def _allow(yes: bool, prompt: str, preview: str) -> bool:
    if yes:
        return True
    typer.echo(preview)
    return typer.confirm(prompt, default=False)


def _approval_json(stored: StoredApproval) -> dict[str, object]:
    decision = stored.decision
    dumped = None if decision is None else decision.model_dump(mode="json")
    return {"request": stored.request.model_dump(mode="json"), "decision": dumped}


def _escalation_json(stored: StoredEscalation) -> dict[str, object]:
    answer = stored.answer
    dumped = None if answer is None else answer.model_dump(mode="json")
    return {
        "escalation_id": stored.escalation_id,
        "raised_at": _when(stored.raised_at),
        "escalation": stored.escalation.model_dump(mode="json"),
        "answer": dumped,
    }


def _state_text(opened: runtime.Runtime, found: RunState) -> str:
    if found.status == "waiting" and found.approval_id is not None:
        block = "\n".join(request_lines(opened.store.approval(found.approval_id)))
        return (
            f"{block}\nNext: conductor approvals approve {found.approval_id}"
            " (or reject, or edit --args)"
        )
    if found.status == "waiting" and found.escalation_id is not None:
        block = "\n".join(escalation_lines(opened.store.escalation(found.escalation_id)))
        return f"{block}\nNext: conductor escalations retry {found.escalation_id} (or cancel)"
    if found.status == "done":
        return f"run {found.run_id}  done\n{found.reply}"
    if found.status == "rejected":
        line = f"run {found.run_id}  rejected"
        if found.note:
            return f"{line}\nnote: {found.note}"
        return line
    if found.status == "cancelled":
        return f"run {found.run_id}  cancelled"
    return f"run {found.run_id}  stopped at {found.stopped_at}"


def _emit(opened: runtime.Runtime, found: RunState, json_output: bool) -> None:
    if json_output:
        _dump(dataclasses.asdict(found))
        return
    typer.echo(_state_text(opened, found))


def _recorded(opened: runtime.Runtime, run_id: str, line: str, no_resume: bool) -> None:
    typer.echo(line)
    if no_resume:
        return
    _emit(opened, runtime.resume(opened, run_id), False)


def _stopped(yes: bool, prompt: str, preview: str) -> bool:
    if _allow(yes, prompt, preview):
        return False
    typer.echo("Nothing recorded.")
    return True


@approvals_app.command("list")
def list_approvals(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, store: Store) -> None:
        pending = store.pending()
        if json_output:
            _dump([request.model_dump(mode="json") for request in pending])
            return
        if not pending:
            typer.echo("No pending approvals.")
            return
        for request in pending:
            actions = ", ".join(step.action for step in request.steps)
            when = _when(request.requested_at)
            typer.echo(f"{request.approval_id}  {when}  {request.stage}  {actions}")

    _run(work)


@approvals_app.command("show")
def show_approval(
    approval_id: str, json_output: Annotated[bool, typer.Option("--json")] = False
) -> None:
    def work(settings: Settings, store: Store) -> None:
        stored = store.approval(approval_id)
        if json_output:
            _dump(_approval_json(stored))
            return
        typer.echo("\n".join(request_lines(stored)))

    _run(work)


@app.command()
def ask(request: str, json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        _emit(opened, runtime.ask(opened, request), json_output)

    _session(work)


@app.command()
def resume(run_id: str, json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        _emit(opened, runtime.resume(opened, run_id), json_output)

    _session(work)


@approvals_app.command("approve")
def approve(
    approval_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.approval(approval_id)
        if _stopped(yes, "Approve?", "\n".join(request_lines(stored))):
            return
        decide_approval(
            opened.store,
            opened.registry,
            approval_id,
            "approve",
            channel="terminal",
            decided_by=settings.decided_by,
            note=note,
        )
        _recorded(opened, stored.request.run_id, f"Approved {approval_id}.", no_resume)

    _session(work)


@approvals_app.command("reject")
def reject(
    approval_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.approval(approval_id)
        decide_approval(
            opened.store,
            opened.registry,
            approval_id,
            "reject",
            channel="terminal",
            decided_by=settings.decided_by,
            note=note,
        )
        _recorded(opened, stored.request.run_id, f"Rejected {approval_id}.", no_resume)

    _session(work)


@approvals_app.command("edit")
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
        if _stopped(yes, "Approve with these arguments?", preview):
            return
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
        _recorded(
            opened,
            stored.request.run_id,
            f"Approved {approval_id} with edited arguments.",
            no_resume,
        )

    _session(work)


@escalations_app.command("list")
def list_escalations(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    def work(settings: Settings, store: Store) -> None:
        opened = store.open_escalations()
        if json_output:
            _dump([_escalation_json(stored) for stored in opened])
            return
        if not opened:
            typer.echo("No open escalations.")
            return
        for stored in opened:
            typer.echo(
                f"{stored.escalation_id}  {_when(stored.raised_at)}  {stored.escalation.kind}"
                f"  run {stored.escalation.run_id}"
            )

    _run(work)


@escalations_app.command("show")
def show_escalation(
    escalation_id: str, json_output: Annotated[bool, typer.Option("--json")] = False
) -> None:
    def work(settings: Settings, store: Store) -> None:
        stored = store.escalation(escalation_id)
        if json_output:
            _dump(_escalation_json(stored))
            return
        typer.echo("\n".join(escalation_lines(stored)))

    _run(work)


@escalations_app.command("retry")
def retry(
    escalation_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.escalation(escalation_id)
        if _stopped(yes, "Retry?", "\n".join(escalation_lines(stored))):
            return
        answer_escalation(
            opened.store,
            escalation_id,
            "retry",
            channel="terminal",
            decided_by=settings.decided_by,
            note=note,
        )
        _recorded(
            opened, stored.escalation.run_id, f"Retry recorded for {escalation_id}.", no_resume
        )

    _session(work)


@escalations_app.command("cancel")
def cancel(
    escalation_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
) -> None:
    def work(settings: Settings, opened: runtime.Runtime) -> None:
        stored = opened.store.escalation(escalation_id)
        answer_escalation(
            opened.store,
            escalation_id,
            "cancel",
            channel="terminal",
            decided_by=settings.decided_by,
            note=note,
        )
        _recorded(opened, stored.escalation.run_id, f"Cancelled {escalation_id}.", no_resume)

    _session(work)


@app.command()
def web() -> None:
    settings = _settings()
    port = settings.web_port_number
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        _bail(f"port {port} is taken")
    finally:
        probe.close()
    typer.echo(f"Serving on http://127.0.0.1:{port}/")
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=port,
        server_header=False,
        proxy_headers=False,
        log_level="warning",
    )
