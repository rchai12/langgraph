import threading

from conductor import runtime
from conductor.config import Settings
from conductor.graph.supervisor import RunError
from conductor.mcp_client.check import ToolCheckFailed


class Resumer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._errors: dict[str, str | None] = {}

    def start(self, run_id: str) -> None:
        with self._lock:
            current = self._threads.get(run_id)
            if current is not None and current.is_alive():
                return
            self._errors[run_id] = None
            thread = threading.Thread(target=self._run, args=(run_id,))
            self._threads[run_id] = thread
            thread.start()

    def running(self, run_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(run_id)
            return thread is not None and thread.is_alive()

    def error(self, run_id: str) -> str | None:
        with self._lock:
            return self._errors.get(run_id)

    def join(self, run_id: str, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def _run(self, run_id: str) -> None:
        message: str | None = None
        try:
            with runtime.open_runtime(self._settings) as opened:
                runtime.resume(opened, run_id)
        except (RunError, ToolCheckFailed) as error:
            message = str(error)
        except Exception:
            message = "the resume failed"
        with self._lock:
            self._errors[run_id] = message
