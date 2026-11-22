import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import Response
from starlette.types import ASGIApp

from conductor import domains, runtime, times
from conductor.config import Settings
from conductor.contracts.base import is_id
from conductor.decisions import answer_escalation, decide_approval, parse_json_object
from conductor.events import EventKind, EventLog, EventLogCorrupt, RunNotFound
from conductor.graph.status import RunState, RunStateUnavailable
from conductor.graph.supervisor import RunError, can_resume
from conductor.policy import DecisionRefused
from conductor.registry import NotRegistered, Registry
from conductor.store import AlreadyDecided, NotFound, Store, StoreError
from conductor.views import escalation_lines, request_lines

from . import security
from .jobs import Resumer
from .security import FORM_COOKIE, NOT_FOUND, SECURITY_HEADERS

__all__ = ["FORM_COOKIE", "SECURITY_HEADERS", "create_app"]

_TEMPLATES = Path(__file__).parent / "templates"
_STORE = "The store is not available"
_ARGUMENTS = "The arguments must be a JSON object."
_RUN_STATE = "The run state is not available"
_BUTTONS = {
    "approve": "Approve",
    "reject": "Reject",
    "edit": "Edit and approve",
    "retry": "Retry",
    "cancel": "Cancel",
}
_FIXED_FAILURE = "the resume failed"


@dataclass(frozen=True)
class Context:
    settings: Settings
    templates: Jinja2Templates
    resumer: Resumer


def _with_store(ctx: Context, read: Callable[[Store], Response]) -> Response:
    try:
        return read(Store(ctx.settings.db_path))
    except NotFound:
        return PlainTextResponse(NOT_FOUND, status_code=404)
    except StoreError:
        return PlainTextResponse(_STORE, status_code=503)


def _page(
    ctx: Context,
    request: Request,
    name: str,
    context: dict[str, object],
    status_code: int = 200,
) -> Response:
    token, fresh = security.form_token(request)
    response = ctx.templates.TemplateResponse(
        request,
        name,
        {**context, "token": token},
        status_code=status_code,
    )
    if fresh:
        security.set_form_cookie(response, token)
    return response


def _home(ctx: Context, store: Store, request: Request) -> Response:
    approvals = [
        {
            "approval_id": item.approval_id,
            "when": times.display(item.requested_at),
            "stage": item.stage,
            "actions": ", ".join(step.action for step in item.steps),
        }
        for item in store.pending()
    ]
    escalations = [
        {
            "escalation_id": item.escalation_id,
            "when": times.display(item.raised_at),
            "kind": item.escalation.kind,
            "run_id": item.escalation.run_id,
        }
        for item in store.open_escalations()
    ]
    return _page(
        ctx,
        request,
        "home.html",
        {"approvals": approvals, "escalations": escalations},
    )


def _form(action: str, args: str | None = None) -> dict[str, str | None]:
    verb = action.rsplit("/", 1)[-1]
    return {"action": action, "args": args, "verb": verb, "button": _BUTTONS[verb]}


def _detail(
    ctx: Context,
    lines: tuple[str, ...],
    forms: list[dict[str, str | None]],
    request: Request,
) -> Response:
    return _page(ctx, request, "detail.html", {"lines": lines, "forms": forms})


def _problem(
    ctx: Context,
    request: Request,
    status_code: int,
    message: str,
    problems: tuple[object, ...],
    back: str,
) -> Response:
    return _page(
        ctx,
        request,
        "problem.html",
        {"message": message, "problems": problems, "back": back},
        status_code,
    )


async def _fields(request: Request) -> tuple[str, str, str]:
    form = await request.form()
    return (
        str(form.get("token") or ""),
        str(form.get("note") or ""),
        str(form.get("args") or ""),
    )


def _failed(ctx: Context, request: Request, error: Exception, back: str) -> Response:
    if isinstance(error, NotFound):
        return PlainTextResponse(NOT_FOUND, status_code=404)
    if isinstance(error, AlreadyDecided):
        return _problem(ctx, request, 409, str(error), (), back)
    if isinstance(error, DecisionRefused):
        return _problem(ctx, request, 400, str(error), error.problems, back)
    if isinstance(error, (ValueError, NotRegistered)):
        return _problem(ctx, request, 400, str(error), (), back)
    return PlainTextResponse(_STORE, status_code=503)


def _run_state(ctx: Context, run_id: str) -> RunState | Response:
    try:
        return runtime.read_state(ctx.settings, run_id)
    except RunStateUnavailable:
        return PlainTextResponse(_RUN_STATE, status_code=503)
    except RunError:
        return PlainTextResponse(NOT_FOUND, status_code=404)


def _resumable(ctx: Context, found: RunState, busy: bool) -> bool:
    if busy:
        return False
    try:
        return can_resume(found, Store(ctx.settings.db_path))
    except StoreError:
        return False


def _shown_failure(ctx: Context, run_id: str, kept: str | None, busy: bool) -> str | None:
    if kept not in (None, _FIXED_FAILURE):
        return kept
    if not busy:
        recorded = _recorded_type(ctx, run_id)
        if recorded is not None:
            return f"{_FIXED_FAILURE} ({recorded})"
    return kept


def _recorded_type(ctx: Context, run_id: str) -> str | None:
    try:
        events = EventLog(ctx.settings.runs_dir).read(run_id)
    except (RunNotFound, EventLogCorrupt, OSError):
        return None
    if not events:
        return None
    last = events[-1]
    if last.kind is not EventKind.ERROR or last.node is not None:
        return None
    if last.payload.get("error") != runtime.RESUME_FAILED:
        return None
    name = last.payload.get("type")
    if not isinstance(name, str):
        return None
    return name


def home(ctx: Context, request: Request) -> Response:
    return _with_store(ctx, lambda store: _home(ctx, store, request))


def approval_page(ctx: Context, approval_id: str, request: Request) -> Response:
    if not is_id(approval_id):
        return PlainTextResponse(NOT_FOUND, status_code=404)

    def read(store: Store) -> Response:
        stored = store.approval(approval_id)
        forms: list[dict[str, str | None]] = []
        if stored.decision is None:
            base = f"/approvals/{approval_id}"
            forms.append(_form(f"{base}/approve"))
            forms.append(_form(f"{base}/reject"))
            if stored.request.stage == "step":
                rendered = json.dumps(
                    stored.request.steps[0].args, ensure_ascii=False, sort_keys=True
                )
                forms.append(_form(f"{base}/edit", rendered))
        return _detail(ctx, request_lines(stored), forms, request)

    return _with_store(ctx, read)


def escalation_page(ctx: Context, escalation_id: str, request: Request) -> Response:
    if not is_id(escalation_id):
        return PlainTextResponse(NOT_FOUND, status_code=404)

    def read(store: Store) -> Response:
        stored = store.escalation(escalation_id)
        forms: list[dict[str, str | None]] = []
        if stored.answer is None:
            base = f"/escalations/{escalation_id}"
            forms.append(_form(f"{base}/retry"))
            forms.append(_form(f"{base}/cancel"))
        return _detail(ctx, escalation_lines(stored), forms, request)

    return _with_store(ctx, read)


def run_page(ctx: Context, run_id: str, request: Request) -> Response:
    if not is_id(run_id):
        return PlainTextResponse(NOT_FOUND, status_code=404)
    found = _run_state(ctx, run_id)
    if isinstance(found, Response):
        return found
    busy = ctx.resumer.running(run_id)
    return _page(
        ctx,
        request,
        "run.html",
        {
            "run_id": run_id,
            "busy": busy,
            "resumable": _resumable(ctx, found, busy),
            "status": found.status,
            "approval_id": found.approval_id,
            "escalation_id": found.escalation_id,
            "reply": found.reply,
            "note": found.note,
            "stopped_at": found.stopped_at,
            "error": _shown_failure(ctx, run_id, ctx.resumer.error(run_id), busy),
        },
    )


async def post_resume(ctx: Context, run_id: str, request: Request) -> Response:
    sent, _note, _args = await _fields(request)
    refused = security.check_post(request, run_id, sent, ctx.settings)
    if refused is not None:
        return refused
    found = _run_state(ctx, run_id)
    if isinstance(found, Response):
        return found
    if ctx.resumer.running(run_id):
        return RedirectResponse(f"/runs/{run_id}", status_code=303)
    try:
        allowed = can_resume(found, Store(ctx.settings.db_path))
    except StoreError:
        return PlainTextResponse(_STORE, status_code=503)
    if allowed:
        ctx.resumer.start(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


def record_and_resume(
    ctx: Context, request: Request, back: str, record: Callable[[Store], str]
) -> Response:
    try:
        run_id = record(Store(ctx.settings.db_path))
    except (
        NotFound,
        AlreadyDecided,
        DecisionRefused,
        ValueError,
        NotRegistered,
        StoreError,
    ) as error:
        return _failed(ctx, request, error, back)
    ctx.resumer.start(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


async def post_approval(ctx: Context, approval_id: str, request: Request, verdict: str) -> Response:
    sent, note, args_text = await _fields(request)
    refused = security.check_post(request, approval_id, sent, ctx.settings)
    if refused is not None:
        return refused
    back = f"/approvals/{approval_id}"
    edited = None
    if verdict == "edit":
        edited = parse_json_object(args_text)
        if edited is None:
            return _problem(ctx, request, 400, _ARGUMENTS, (), back)

    def record(store: Store) -> str:
        stored = store.approval(approval_id)
        decide_approval(
            store,
            Registry(domains.registered(ctx.settings)),
            approval_id,
            verdict,  # type: ignore[arg-type]
            channel="web",
            decided_by=ctx.settings.decided_by,
            note=note,
            edited_args=edited,
        )
        return stored.request.run_id

    return record_and_resume(ctx, request, back, record)


async def post_escalation(
    ctx: Context, escalation_id: str, request: Request, answer: str
) -> Response:
    sent, note, _args_text = await _fields(request)
    refused = security.check_post(request, escalation_id, sent, ctx.settings)
    if refused is not None:
        return refused

    def record(store: Store) -> str:
        stored = store.escalation(escalation_id)
        answer_escalation(
            store,
            escalation_id,
            answer,  # type: ignore[arg-type]
            channel="web",
            decided_by=ctx.settings.decided_by,
            note=note,
        )
        return stored.escalation.run_id

    return record_and_resume(ctx, request, f"/escalations/{escalation_id}", record)


def _context(settings: Settings, resumer: Resumer | None) -> Context:
    return Context(
        settings=settings,
        templates=Jinja2Templates(
            env=Environment(
                loader=FileSystemLoader(_TEMPLATES),
                autoescape=select_autoescape(["html"]),
            )
        ),
        resumer=Resumer(settings) if resumer is None else resumer,
    )


def _add_pages(api: FastAPI, ctx: Context) -> None:
    @api.get("/")
    def get_home(request: Request) -> Response:
        return home(ctx, request)

    @api.get("/approvals/{approval_id}")
    def get_approval(approval_id: str, request: Request) -> Response:
        return approval_page(ctx, approval_id, request)

    @api.get("/escalations/{escalation_id}")
    def get_escalation(escalation_id: str, request: Request) -> Response:
        return escalation_page(ctx, escalation_id, request)

    @api.get("/runs/{run_id}")
    def get_run(run_id: str, request: Request) -> Response:
        return run_page(ctx, run_id, request)


def _add_forms(api: FastAPI, ctx: Context) -> None:
    @api.post("/runs/{run_id}/resume")
    async def resume(run_id: str, request: Request) -> Response:
        return await post_resume(ctx, run_id, request)

    @api.post("/approvals/{approval_id}/approve")
    async def approve(approval_id: str, request: Request) -> Response:
        return await post_approval(ctx, approval_id, request, "approve")

    @api.post("/approvals/{approval_id}/reject")
    async def reject(approval_id: str, request: Request) -> Response:
        return await post_approval(ctx, approval_id, request, "reject")

    @api.post("/approvals/{approval_id}/edit")
    async def edit(approval_id: str, request: Request) -> Response:
        return await post_approval(ctx, approval_id, request, "edit")

    @api.post("/escalations/{escalation_id}/retry")
    async def retry(escalation_id: str, request: Request) -> Response:
        return await post_escalation(ctx, escalation_id, request, "retry")

    @api.post("/escalations/{escalation_id}/cancel")
    async def cancel(escalation_id: str, request: Request) -> Response:
        return await post_escalation(ctx, escalation_id, request, "cancel")


def create_app(settings: Settings, *, resumer: Resumer | None = None) -> ASGIApp:
    ctx = _context(settings, resumer)
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    _add_pages(api, ctx)
    _add_forms(api, ctx)
    return security.HostGuard(api, settings.web_port_number)
