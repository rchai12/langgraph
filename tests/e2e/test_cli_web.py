import socket

import pytest
import uvicorn

from conductor.config import SettingsError, get_settings
from tests.support import run


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake_run(app, **options) -> None:
        calls.append({"app": app, **options})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return calls


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_the_default_port() -> None:
    assert (get_settings().web_port, get_settings().web_port_number) == ("8766", 8766)


def test_the_web_command_serves_on_this_machine_only(
    served: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(port))
    result = run("web")
    assert (result.exit_code, result.stdout) == (0, f"Serving on http://127.0.0.1:{port}/\n")
    [call] = served
    assert {key: call[key] for key in ("host", "port", "server_header", "proxy_headers")} == {
        "host": "127.0.0.1",
        "port": port,
        "server_header": False,
        "proxy_headers": False,
    }


def test_a_port_in_use_is_refused(served: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    port = taken.getsockname()[1]
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", str(port))
    try:
        result = run("web")
    finally:
        taken.close()
    assert (result.exit_code, result.stdout, result.stderr) == (
        1,
        "",
        f"Error: port {port} is taken\n",
    )
    assert served == []


@pytest.mark.parametrize("value", ["80", "65536", "87a5"])
def test_a_bad_port_setting(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CONDUCTOR_WEB_PORT", value)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert str(raised.value) == "CONDUCTOR_WEB_PORT: must be a port from 1024 to 65535"
