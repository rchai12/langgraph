import socket

import pytest

from conductor.llm.tags import OllamaUnreachable, fetch_model_names


def test_a_silent_server_times_out() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        with pytest.raises(OllamaUnreachable) as raised:
            fetch_model_names(f"http://127.0.0.1:{port}", timeout=0.3)
        assert str(raised.value) == "not reachable"
    finally:
        listener.close()
