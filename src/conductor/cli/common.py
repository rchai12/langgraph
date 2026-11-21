import dataclasses
import json
from collections.abc import Callable
from typing import NoReturn

import typer

from conductor import runtime
from conductor.config import Settings, SettingsError, get_settings
from conductor.graph.supervisor import RunError, RunState
from conductor.mcp_client.check import ToolCheckFailed
from conductor.policy import DecisionRefused
from conductor.registry import NotRegistered
from conductor.store import AlreadyDecided, NotFound, Store, StoreError
from conductor.views import escalation_lines, request_lines

CAUGHT = (StoreError, NotFound, AlreadyDecided, NotRegistered, ValueError, DecisionRefused)


def bail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def load_settings() -> Settings:
    try:
        return get_settings()
    except SettingsError as error:
        bail(str(error))


def report(error: BaseException) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    if isinstance(error, DecisionRefused):
        for problem in error.problems:
            typer.echo(f"  {problem.loc}: {problem.code}", err=True)
    if isinstance(error, ToolCheckFailed):
        for problem in error.problems:
            typer.echo(f"  {problem.text}", err=True)
    raise typer.Exit(1)


def with_store(work: Callable[[Settings, Store], None]) -> None:
    settings = load_settings()
    try:
        work(settings, Store(settings.db_path))
    except CAUGHT as error:
        report(error)


def with_runtime(work: Callable[[Settings, runtime.Runtime], None]) -> None:
    settings = load_settings()
    try:
        with runtime.open_runtime(settings) as opened:
            work(settings, opened)
    except (*CAUGHT, RunError, ToolCheckFailed) as error:
        report(error)


def dump(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def state_text(opened: runtime.Runtime, found: RunState) -> str:
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


def emit(opened: runtime.Runtime, found: RunState, json_output: bool) -> None:
    if json_output:
        dump(dataclasses.asdict(found))
        return
    typer.echo(state_text(opened, found))


def decide_then_resume(
    opened: runtime.Runtime,
    run_id: str,
    record: Callable[[], object],
    line: str,
    *,
    no_resume: bool,
    confirm: tuple[str, str] | None = None,
    yes: bool = False,
) -> None:
    if confirm is not None and not yes:
        prompt, preview = confirm
        typer.echo(preview)
        if not typer.confirm(prompt, default=False):
            typer.echo("Nothing recorded.")
            return
    record()
    typer.echo(line)
    if not no_resume:
        emit(opened, runtime.resume(opened, run_id), False)
