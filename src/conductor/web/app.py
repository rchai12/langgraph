import hmac
import json
import re
import secrets
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from conductor import domains, runtime
from conductor.config import Settings
from conductor.decisions import answer_escalation, decide_approval, parse_json_object
from conductor.graph.supervisor import RunError
from conductor.policy import DecisionRefused
from conductor.registry import NotRegistered, Registry
from conductor.store import AlreadyDecided, NotFound, Store, StoreError
from conductor.views import escalation_lines, request_lines

from .jobs import Resumer

SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "cache-control": "no-store",
}
FORM_COOKIE = "conductor_form"

_TEMPLATES = Path(__file__).parent / "templates"
_HEADER_BYTES = [(name.encode(), value.encode()) for name, value in SECURITY_HEADERS.items()]
_ID = re.compile(r"^[0-9a-f]{32}$")
_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_NOT_FOUND = "Not found"
_STORE = "The store is not available"
_ARGUMENTS = "The arguments must be a JSON object."
_WHEN = "%Y-%m-%dT%H:%M:%SZ"


class _HostGuard:
    """Refuse a request whose Host is not this server, and add the security headers."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        self._app = app
        self._hosts = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [
                    (name, value)
                    for name, value in message["headers"]
                    if name.lower().decode("latin-1") not in SECURITY_HEADERS
                ]
                message = {**message, "headers": [*kept, *_HEADER_BYTES]}
            await send(message)

        hosts = [value for name, value in scope["headers"] if name.lower() == b"host"]
        if len(hosts) != 1 or hosts[0] not in self._hosts:
            refused = PlainTextResponse("Bad host", status_code=400)
            await refused(scope, receive, send_with_headers)
            return
        await self._app(scope, receive, send_with_headers)


def _with_store(settings: Settings, read: Callable[[Store], Response]) -> Response:
    try:
        return read(Store(settings.db_path))
    except NotFound:
        return PlainTextResponse(_NOT_FOUND, status_code=404)
    except StoreError:
        return PlainTextResponse(_STORE, status_code=503)


def _prepare(request: Request) -> tuple[str, bool]:
    current = request.cookies.get(FORM_COOKIE, "")
    if _TOKEN.fullmatch(current) is None:
        return secrets.token_hex(32), True
    return current, False


def _page(
    templates: Jinja2Templates,
    request: Request,
    name: str,
    context: dict[str, object],
    status_code: int = 200,
) -> Response:
    token, fresh = _prepare(request)
    response = templates.TemplateResponse(
        request,
        name,
        {**context, "token": token},
        status_code=status_code,
    )
    if fresh:
        response.set_cookie(FORM_COOKIE, token, httponly=True, samesite="strict", path="/")
    return response


def _home(store: Store, request: Request, templates: Jinja2Templates) -> Response:
    approvals = [
        {
            "approval_id": item.approval_id,
            "when": item.requested_at.strftime(_WHEN),
            "stage": item.stage,
            "actions": ", ".join(step.action for step in item.steps),
        }
        for item in store.pending()
    ]
    escalations = [
        {
            "escalation_id": item.escalation_id,
            "when": item.raised_at.strftime(_WHEN),
            "kind": item.escalation.kind,
            "run_id": item.escalation.run_id,
        }
        for item in store.open_escalations()
    ]
    return _page(
        templates,
        request,
        "home.html",
        {"approvals": approvals, "escalations": escalations},
    )


_BUTTONS = {
    "approve": "Approve",
    "reject": "Reject",
    "edit": "Edit and approve",
    "retry": "Retry",
    "cancel": "Cancel",
}


def _form(action: str, args: str | None = None) -> dict[str, str | None]:
    verb = action.rsplit("/", 1)[-1]
    return {"action": action, "args": args, "verb": verb, "button": _BUTTONS[verb]}


def _detail(
    lines: tuple[str, ...],
    forms: list[dict[str, str | None]],
    request: Request,
    templates: Jinja2Templates,
) -> Response:
    return _page(templates, request, "detail.html", {"lines": lines, "forms": forms})


def _problem(
    templates: Jinja2Templates,
    request: Request,
    status_code: int,
    message: str,
    problems: tuple[object, ...],
    back: str,
) -> Response:
    return _page(
        templates,
        request,
        "problem.html",
        {"message": message, "problems": problems, "back": back},
        status_code,
    )


def _origins(settings: Settings) -> set[str]:
    port = settings.web_port_number
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def _refused(request: Request, item_id: str, sent: str, settings: Settings) -> Response | None:
    if _ID.fullmatch(item_id) is None:
        return PlainTextResponse(_NOT_FOUND, status_code=404)
    origin = request.headers.get("origin")
    if origin is not None and origin not in _origins(settings):
        return PlainTextResponse("Bad origin", status_code=403)
    cookie = request.cookies.get(FORM_COOKIE, "")
    if _TOKEN.fullmatch(cookie) is None or not hmac.compare_digest(cookie, sent):
        return PlainTextResponse("Bad form token", status_code=403)
    return None


def create_app(settings: Settings, *, resumer: Resumer | None = None) -> ASGIApp:
    chosen = Resumer(settings) if resumer is None else resumer
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(
        env=Environment(
            loader=FileSystemLoader(_TEMPLATES),
            autoescape=select_autoescape(["html"]),
        )
    )

    async def _fields(request: Request) -> tuple[str, str, str]:
        form = await request.form()
        return (
            str(form.get("token") or ""),
            str(form.get("note") or ""),
            str(form.get("args") or ""),
        )

    def _failed(request: Request, error: Exception, back: str) -> Response:
        if isinstance(error, NotFound):
            return PlainTextResponse(_NOT_FOUND, status_code=404)
        if isinstance(error, AlreadyDecided):
            return _problem(templates, request, 409, str(error), (), back)
        if isinstance(error, DecisionRefused):
            return _problem(templates, request, 400, str(error), error.problems, back)
        if isinstance(error, (ValueError, NotRegistered)):
            return _problem(templates, request, 400, str(error), (), back)
        return PlainTextResponse(_STORE, status_code=503)

    def _record_approval(
        request: Request, approval_id: str, verdict: str, note: str, edited: dict | None
    ) -> Response:
        back = f"/approvals/{approval_id}"
        try:
            store = Store(settings.db_path)
            stored = store.approval(approval_id)
            decide_approval(
                store,
                Registry(domains.registered(settings)),
                approval_id,
                verdict,  # type: ignore[arg-type]
                channel="web",
                decided_by=settings.decided_by,
                note=note,
                edited_args=edited,
            )
        except (
            NotFound,
            AlreadyDecided,
            DecisionRefused,
            ValueError,
            NotRegistered,
            StoreError,
        ) as error:
            return _failed(request, error, back)
        chosen.start(stored.request.run_id)
        return RedirectResponse(f"/runs/{stored.request.run_id}", status_code=303)

    def _record_escalation(
        request: Request, escalation_id: str, answer: str, note: str
    ) -> Response:
        back = f"/escalations/{escalation_id}"
        try:
            store = Store(settings.db_path)
            stored = store.escalation(escalation_id)
            answer_escalation(
                store,
                escalation_id,
                answer,  # type: ignore[arg-type]
                channel="web",
                decided_by=settings.decided_by,
                note=note,
            )
        except (
            NotFound,
            AlreadyDecided,
            DecisionRefused,
            ValueError,
            NotRegistered,
            StoreError,
        ) as error:
            return _failed(request, error, back)
        chosen.start(stored.escalation.run_id)
        return RedirectResponse(f"/runs/{stored.escalation.run_id}", status_code=303)

    @api.get("/")
    def home(request: Request) -> Response:
        return _with_store(settings, lambda store: _home(store, request, templates))

    @api.get("/approvals/{approval_id}")
    def approval(approval_id: str, request: Request) -> Response:
        if _ID.fullmatch(approval_id) is None:
            return PlainTextResponse(_NOT_FOUND, status_code=404)

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
            return _detail(request_lines(stored), forms, request, templates)

        return _with_store(settings, read)

    @api.get("/escalations/{escalation_id}")
    def escalation(escalation_id: str, request: Request) -> Response:
        if _ID.fullmatch(escalation_id) is None:
            return PlainTextResponse(_NOT_FOUND, status_code=404)

        def read(store: Store) -> Response:
            stored = store.escalation(escalation_id)
            forms: list[dict[str, str | None]] = []
            if stored.answer is None:
                base = f"/escalations/{escalation_id}"
                forms.append(_form(f"{base}/retry"))
                forms.append(_form(f"{base}/cancel"))
            return _detail(escalation_lines(stored), forms, request, templates)

        return _with_store(settings, read)

    @api.get("/runs/{run_id}")
    def run(run_id: str, request: Request) -> Response:
        if _ID.fullmatch(run_id) is None:
            return PlainTextResponse(_NOT_FOUND, status_code=404)
        try:
            with runtime.open_runtime(settings) as opened:
                found = runtime.state(opened, run_id)
        except RunError:
            return PlainTextResponse(_NOT_FOUND, status_code=404)
        return _page(
            templates,
            request,
            "run.html",
            {
                "busy": chosen.running(run_id),
                "status": found.status,
                "approval_id": found.approval_id,
                "escalation_id": found.escalation_id,
                "reply": found.reply,
                "note": found.note,
                "stopped_at": found.stopped_at,
                "error": chosen.error(run_id),
            },
        )

    async def _post_approval(approval_id: str, request: Request, verdict: str) -> Response:
        sent, note, args_text = await _fields(request)
        refused = _refused(request, approval_id, sent, settings)
        if refused is not None:
            return refused
        edited = None
        if verdict == "edit":
            edited = parse_json_object(args_text)
            if edited is None:
                return _problem(
                    templates,
                    request,
                    400,
                    _ARGUMENTS,
                    (),
                    f"/approvals/{approval_id}",
                )
        return _record_approval(request, approval_id, verdict, note, edited)

    @api.post("/approvals/{approval_id}/approve")
    async def approve(approval_id: str, request: Request) -> Response:
        return await _post_approval(approval_id, request, "approve")

    @api.post("/approvals/{approval_id}/reject")
    async def reject(approval_id: str, request: Request) -> Response:
        return await _post_approval(approval_id, request, "reject")

    @api.post("/approvals/{approval_id}/edit")
    async def edit(approval_id: str, request: Request) -> Response:
        return await _post_approval(approval_id, request, "edit")

    async def _post_escalation(escalation_id: str, request: Request, answer: str) -> Response:
        sent, note, _args_text = await _fields(request)
        refused = _refused(request, escalation_id, sent, settings)
        if refused is not None:
            return refused
        return _record_escalation(request, escalation_id, answer, note)

    @api.post("/escalations/{escalation_id}/retry")
    async def retry(escalation_id: str, request: Request) -> Response:
        return await _post_escalation(escalation_id, request, "retry")

    @api.post("/escalations/{escalation_id}/cancel")
    async def cancel(escalation_id: str, request: Request) -> Response:
        return await _post_escalation(escalation_id, request, "cancel")

    return _HostGuard(api, settings.web_port_number)
