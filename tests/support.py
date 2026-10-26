"""Helpers shared by tests: running a command, fixed times, and a fake Ollama on 127.0.0.1.

New tests import these instead of copying them.
"""

import json
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from typer.testing import CliRunner

from conductor import clock
from conductor.cli.main import app

runner = CliRunner(env={"COLUMNS": "200"})


def run(*args: object):
    """Run `conductor` with these arguments, each turned into text."""
    return runner.invoke(app, [str(arg) for arg in args])


def fixed_times(monkeypatch: pytest.MonkeyPatch, *moments: str) -> None:
    """Make `clock.now()` return these ISO moments, one per call, in order."""
    times = iter([datetime.fromisoformat(moment) for moment in moments])
    monkeypatch.setattr(clock, "now", lambda: next(times))


class FakeOllama:
    """What the fake answers to every GET: `status` and `body`. `paths` lists what was asked."""

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"models": []}'
        self.paths: list[str] = []

    def models(self, *names: str) -> None:
        listed = [{"name": name, "model": name, "size": 1} for name in names]
        self.body = json.dumps({"models": listed}).encode()


class _LocalServer(HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer looks up the machine's name here, which costs seconds on macOS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


@contextmanager
def fake_ollama() -> Iterator[tuple[FakeOllama, str]]:
    """Start a fake Ollama on 127.0.0.1; yield it and its host, such as http://127.0.0.1:50123."""
    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.paths.append(self.path)
            self.send_response(fake.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(fake.body)))
            self.end_headers()
            self.wfile.write(fake.body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _LocalServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
