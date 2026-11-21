import ast
import dataclasses
from collections import Counter
from pathlib import Path

from starlette.requests import Request

from conductor.config import get_settings
from conductor.store import NotFound, StoreError
from conductor.web import app, security

WEB = Path(app.__file__).parent
HANDLERS = {
    "create_app",
    "home",
    "approval_page",
    "escalation_page",
    "run_page",
    "post_resume",
    "post_approval",
    "post_escalation",
    "record_and_resume",
}
SECURITY_IMPORTS = {"conductor.config", "conductor.contracts.base"}


def tree(name: str) -> ast.Module:
    return ast.parse((WEB / f"{name}.py").read_text(encoding="utf-8"))


def top_functions(name: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    return {node.name: node for node in tree(name).body if isinstance(node, kinds)}


def called(name: str) -> Counter[str]:
    names: Counter[str] = Counter()
    for node in ast.walk(tree(name)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names[node.func.id] += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names[f".{node.func.attr}"] += 1
    return names


class FakeResumer:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, run_id: str) -> None:
        self.started.append(run_id)


def context(resumer: FakeResumer) -> "app.Context":
    return app.Context(settings=get_settings(), templates=None, resumer=resumer)


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def test_the_web_package_has_a_security_module() -> None:
    assert sorted(path.name for path in WEB.glob("*.py")) == [
        "__init__.py",
        "app.py",
        "jobs.py",
        "security.py",
    ]


def test_security_imports_nothing_from_the_web_package() -> None:
    found = set()
    for node in ast.walk(tree("security")):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
            found.add(node.module or "")
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    assert {name for name in found if name.startswith("conductor")} <= SECURITY_IMPORTS


def test_the_page_still_exports_the_cookie_and_headers() -> None:
    assert (app.FORM_COOKIE is security.FORM_COOKIE, app.FORM_COOKIE) == (True, "conductor_form")
    assert app.SECURITY_HEADERS is security.SECURITY_HEADERS
    assert sorted(app.__all__) == ["FORM_COOKIE", "SECURITY_HEADERS", "create_app"]


def test_the_handlers_are_named_functions_that_take_the_context() -> None:
    found = top_functions("app")
    assert {name for name in found if not name.startswith("_")} == HANDLERS
    firsts = {
        name: ast.unparse(found[name].args.args[0].annotation) for name in HANDLERS - {"create_app"}
    }
    assert firsts == dict.fromkeys(HANDLERS - {"create_app"}, "Context")


def test_the_context_is_frozen_and_holds_three_things() -> None:
    assert [field.name for field in dataclasses.fields(app.Context)] == [
        "settings",
        "templates",
        "resumer",
    ]
    assert app.Context.__dataclass_params__.frozen is True


def test_create_app_only_registers_one_line_routes() -> None:
    body = top_functions("app")["create_app"].body
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    routes = [node for node in body if isinstance(node, kinds)]
    assert len(routes) == 10
    assert [len(route.body) for route in routes] == [1] * 10
    assert {type(route.body[0]).__name__ for route in routes} == {"Return"}
    assert [
        node for node in ast.walk(top_functions("app")["create_app"]) if isinstance(node, ast.Try)
    ] == []


def test_each_decision_state_read_and_resume_start_is_written_once() -> None:
    counts = called("app")
    once = ("decide_approval", "answer_escalation", ".read_state", ".start")
    assert {name: counts[name] for name in once} == {
        "decide_approval": 1,
        "answer_escalation": 1,
        ".read_state": 1,
        ".start": 2,
    }


def test_a_recorded_decision_starts_its_run_and_redirects() -> None:
    resumer = FakeResumer()
    opened: list[str] = []

    def record(store: object) -> str:
        opened.append(type(store).__name__)
        return "r1"

    found = app.record_and_resume(context(resumer), request(), "/approvals/x", record)
    assert (found.status_code, found.headers["location"]) == (303, "/runs/r1")
    assert (resumer.started, opened) == (["r1"], ["Store"])


def test_a_missing_item_is_not_found_and_starts_nothing() -> None:
    resumer = FakeResumer()

    def record(store: object) -> str:
        raise NotFound("no approval")

    found = app.record_and_resume(context(resumer), request(), "/approvals/x", record)
    assert (found.status_code, bytes(found.body), resumer.started) == (404, b"Not found", [])


def test_a_store_failure_is_unavailable_and_starts_nothing() -> None:
    resumer = FakeResumer()

    def record(store: object) -> str:
        raise StoreError("database is locked")

    found = app.record_and_resume(context(resumer), request(), "/approvals/x", record)
    assert (found.status_code, bytes(found.body), resumer.started) == (
        503,
        b"The store is not available",
        [],
    )
