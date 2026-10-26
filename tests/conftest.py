import os
import socket
from pathlib import Path

import pytest

# Where a test's Ollama host points unless it starts its own server: a closed local port, so a
# test that forgets to replace the model fails at once instead of reaching a real Ollama.
CLOSED_OLLAMA = "http://127.0.0.1:9"

_LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost")
_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_TERMINAL_KEYS = ("FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE", "TTY_INTERACTIVE")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every connection and name lookup that leaves the machine."""
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: object) -> object:
        if self.family == socket.AF_UNIX:
            return real_connect(self, address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOCAL_HOSTS:
            raise AssertionError("a test tried to use the network")
        return real_connect(self, address)

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        if host not in _LOCAL_HOSTS:
            raise AssertionError("a test tried to use the network")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No CONDUCTOR_ variable from the shell; data under tmp_path; Ollama on a closed port."""
    for key in list(os.environ):
        if key.startswith("CONDUCTOR_"):
            monkeypatch.delenv(key)
    for key in _PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    for key in _TERMINAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONDUCTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONDUCTOR_OLLAMA_HOST", CLOSED_OLLAMA)
