import re
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from conductor.config import Settings
from conductor.store import NotFound, Store, StoreError
from conductor.views import escalation_lines, request_lines

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

_TEMPLATES = Path(__file__).parent / "templates"
_HEADER_BYTES = [(name.encode(), value.encode()) for name, value in SECURITY_HEADERS.items()]
_ID = re.compile(r"^[0-9a-f]{32}$")
_NOT_FOUND = "Not found"
_STORE = "The store is not available"
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
    return templates.TemplateResponse(
        request,
        "home.html",
        {"approvals": approvals, "escalations": escalations},
    )


def _detail(lines: tuple[str, ...], request: Request, templates: Jinja2Templates) -> Response:
    return templates.TemplateResponse(request, "detail.html", {"lines": lines})


def create_app(settings: Settings) -> ASGIApp:
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(
        env=Environment(
            loader=FileSystemLoader(_TEMPLATES),
            autoescape=select_autoescape(["html"]),
        )
    )

    @api.get("/")
    def home(request: Request) -> Response:
        return _with_store(settings, lambda store: _home(store, request, templates))

    @api.get("/approvals/{approval_id}")
    def approval(approval_id: str, request: Request) -> Response:
        if _ID.fullmatch(approval_id) is None:
            return PlainTextResponse(_NOT_FOUND, status_code=404)

        def read(store: Store) -> Response:
            return _detail(request_lines(store.approval(approval_id)), request, templates)

        return _with_store(settings, read)

    @api.get("/escalations/{escalation_id}")
    def escalation(escalation_id: str, request: Request) -> Response:
        if _ID.fullmatch(escalation_id) is None:
            return PlainTextResponse(_NOT_FOUND, status_code=404)

        def read(store: Store) -> Response:
            stored = store.escalation(escalation_id)
            return _detail(escalation_lines(stored), request, templates)

        return _with_store(settings, read)

    return _HostGuard(api, settings.web_port_number)
