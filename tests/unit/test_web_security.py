import asyncio
import re

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from conductor.config import get_settings
from conductor.web import security

PORT = 8766
TOKEN = "ab" * 32
OTHER = "cd" * 32
ITEM = "0" * 31 + "7"
GOOD_ORIGIN = f"http://127.0.0.1:{PORT}"
BASE = {"item_id": ITEM, "cookie": TOKEN, "sent": TOKEN, "origin": None}
NOT_FOUND = (404, "Not found")
BAD_ORIGIN = (403, "Bad origin")
BAD_TOKEN = (403, "Bad form token")
POSTS = {
    "accepted": ({}, None),
    "same origin": ({"origin": GOOD_ORIGIN}, None),
    "localhost origin": ({"origin": f"http://localhost:{PORT}"}, None),
    "not an id": ({"item_id": "nope"}, NOT_FOUND),
    "upper-case id": ({"item_id": ITEM.upper().replace("0", "A")}, NOT_FOUND),
    "other port": ({"origin": "http://127.0.0.1:9999"}, BAD_ORIGIN),
    "null origin": ({"origin": "null"}, BAD_ORIGIN),
    "https origin": ({"origin": f"https://127.0.0.1:{PORT}"}, BAD_ORIGIN),
    "no cookie": ({"cookie": None}, BAD_TOKEN),
    "short cookie": ({"cookie": TOKEN[:-1], "sent": TOKEN[:-1]}, BAD_TOKEN),
    "other token sent": ({"sent": OTHER}, BAD_TOKEN),
    "empty token sent": ({"sent": ""}, BAD_TOKEN),
    "id before origin": ({"item_id": "nope", "origin": "null"}, NOT_FOUND),
    "origin before token": ({"origin": "null", "sent": OTHER}, BAD_ORIGIN),
}
HOSTS = {
    "this server": ([(b"host", f"127.0.0.1:{PORT}".encode())], 200),
    "localhost": ([(b"host", f"localhost:{PORT}".encode())], 200),
    "upper-case header name": ([(b"HOST", f"127.0.0.1:{PORT}".encode())], 200),
    "other port": ([(b"host", b"127.0.0.1:9999")], 400),
    "other name": ([(b"host", f"example.test:{PORT}".encode())], 400),
    "no host": ([], 400),
    "two hosts": ([(b"host", f"127.0.0.1:{PORT}".encode())] * 2, 400),
}


def request(*headers: tuple[str, str]) -> Request:
    raw = [(name.encode(), value.encode()) for name, value in headers]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def shown(found: Response | None) -> tuple[int, str] | None:
    return None if found is None else (found.status_code, bytes(found.body).decode())


def served(scope: dict) -> tuple[list[dict], list[str]]:
    """What the guard sends for this scope, and which scope types reached the inner app."""
    sent: list[dict] = []
    reached: list[str] = []
    inner = PlainTextResponse("hi", headers={"x-frame-options": "SAMEORIGIN"})

    async def app(scope: dict, receive, send) -> None:
        reached.append(scope["type"])
        if scope["type"] == "http":
            await inner(scope, receive, send)

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(security.HostGuard(app, PORT)(scope, receive, send))
    return sent, reached


@pytest.mark.parametrize("case", list(POSTS))
def test_a_post_is_checked_for_its_id_origin_and_form_token(case: str) -> None:
    change, expected = POSTS[case]
    given = {**BASE, **change}
    headers = []
    if given["cookie"] is not None:
        headers.append(("cookie", f"{security.FORM_COOKIE}={given['cookie']}"))
    if given["origin"] is not None:
        headers.append(("origin", given["origin"]))
    found = security.check_post(request(*headers), given["item_id"], given["sent"], get_settings())
    assert shown(found) == expected


@pytest.mark.parametrize(
    "cookie", [None, TOKEN.upper(), TOKEN + "0", "g" * 64], ids=["none", "upper", "long", "not-hex"]
)
def test_a_missing_or_malformed_cookie_gets_a_fresh_token(cookie: str | None) -> None:
    headers = [] if cookie is None else [("cookie", f"{security.FORM_COOKIE}={cookie}")]
    token, fresh = security.form_token(request(*headers))
    assert (re.fullmatch(r"[0-9a-f]{64}", token) is not None, fresh) == (True, True)
    assert token != cookie


def test_a_valid_cookie_keeps_its_token() -> None:
    found = security.form_token(request(("cookie", f"{security.FORM_COOKIE}={TOKEN}")))
    assert found == (TOKEN, False)


def test_the_form_cookie_is_http_only_strict_and_site_wide() -> None:
    response = Response()
    security.set_form_cookie(response, TOKEN)
    assert response.headers["set-cookie"] == (
        f"conductor_form={TOKEN}; HttpOnly; Path=/; SameSite=strict"
    )


@pytest.mark.parametrize("case", list(HOSTS))
def test_the_guard_serves_only_this_host_and_always_adds_the_headers(case: str) -> None:
    headers, status = HOSTS[case]
    sent, reached = served({"type": "http", "method": "GET", "path": "/", "headers": headers})
    start, body = sent
    names = [name.decode() for name, _ in start["headers"]]
    added = {name.decode(): value.decode() for name, value in start["headers"]}
    assert (start["status"], reached) == (status, ["http"] if status == 200 else [])
    assert body["body"] == (b"hi" if status == 200 else b"Bad host")
    assert {name: names.count(name) for name in security.SECURITY_HEADERS} == dict.fromkeys(
        security.SECURITY_HEADERS, 1
    )
    assert {name: added[name] for name in security.SECURITY_HEADERS} == security.SECURITY_HEADERS


def test_the_guard_passes_other_scopes_through() -> None:
    sent, reached = served({"type": "lifespan"})
    assert (sent, reached) == ([], ["lifespan"])
