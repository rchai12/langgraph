import hmac
import re
import secrets

from fastapi import Request
from fastapi.responses import PlainTextResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from conductor.config import Settings
from conductor.contracts.base import is_id

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
NOT_FOUND = "Not found"

_HEADER_BYTES = [(name.encode(), value.encode()) for name, value in SECURITY_HEADERS.items()]
_TOKEN = re.compile(r"^[0-9a-f]{64}$")


class HostGuard:
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


def form_token(request: Request) -> tuple[str, bool]:
    current = request.cookies.get(FORM_COOKIE, "")
    if _TOKEN.fullmatch(current) is None:
        return secrets.token_hex(32), True
    return current, False


def set_form_cookie(response: Response, token: str) -> None:
    response.set_cookie(FORM_COOKIE, token, httponly=True, samesite="strict", path="/")


def _origins(settings: Settings) -> set[str]:
    port = settings.web_port_number
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def check_post(request: Request, item_id: str, sent: str, settings: Settings) -> Response | None:
    if not is_id(item_id):
        return PlainTextResponse(NOT_FOUND, status_code=404)
    origin = request.headers.get("origin")
    if origin is not None and origin not in _origins(settings):
        return PlainTextResponse("Bad origin", status_code=403)
    cookie = request.cookies.get(FORM_COOKIE, "")
    if _TOKEN.fullmatch(cookie) is None or not hmac.compare_digest(cookie, sent):
        return PlainTextResponse("Bad form token", status_code=403)
    return None
