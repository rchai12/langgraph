import socket

import typer
import uvicorn

from conductor.cli import common
from conductor.web.app import create_app
from conductor.web.jobs import UNFINISHED_MESSAGE, Resumer


def serve() -> None:
    settings = common.load_settings()
    port = settings.web_port_number
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        common.bail(f"port {port} is taken")
    finally:
        probe.close()
    typer.echo(f"Serving on http://127.0.0.1:{port}/")
    resumer = Resumer(settings)
    try:
        uvicorn.run(
            create_app(settings, resumer=resumer),
            host="127.0.0.1",
            port=port,
            server_header=False,
            proxy_headers=False,
            log_level="warning",
        )
    finally:
        for run_id in resumer.close():
            typer.echo(f"{UNFINISHED_MESSAGE}: run {run_id}", err=True)
