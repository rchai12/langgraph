"""An HTTP server on 127.0.0.1 that answers every request with exactly the bytes it is given.

It reads the whole request first (headers and any Content-Length body), so the client never
sees a reset, then sends the answer and closes the connection.
"""

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager


def answer(body: bytes, *headers: str) -> bytes:
    """A 200 answer with these header lines and this body, closed after the body."""
    head = "HTTP/1.1 200 OK\r\n" + "".join(f"{line}\r\n" for line in headers)
    return (head + "Connection: close\r\n\r\n").encode() + body


def _read_request(connection: socket.socket) -> None:
    received = b""
    while b"\r\n\r\n" not in received:
        part = connection.recv(65536)
        if not part:
            return
        received += part
    head, _, rest = received.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value.strip())
    while len(rest) < length:
        part = connection.recv(65536)
        if not part:
            return
        rest += part


@contextmanager
def raw_server(sent: bytes) -> Iterator[str]:
    """Serve `sent` to every connection; yield the host, such as http://127.0.0.1:50123."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    listener.settimeout(0.1)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                try:
                    _read_request(connection)
                    connection.sendall(sent)
                except OSError:
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        stop.set()
        thread.join(5)
        listener.close()
