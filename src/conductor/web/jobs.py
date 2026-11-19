import threading

from conductor import runtime
from conductor.config import Settings
from conductor.graph.supervisor import RunError
from conductor.mcp_client.check import ToolCheckFailed

MAX_FAILURES = 100
SHUTDOWN_SECONDS = 10.0
STOPPING_MESSAGE = "the server is stopping"
UNFINISHED_MESSAGE = "the resume did not finish before shutdown"


class Resumer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._held: dict[str, threading.Thread] = {}
        self._failures: dict[str, str] = {}
        self._stopping = False

    def start(self, run_id: str) -> None:
        with self._lock:
            if self._stopping:
                self._keep(run_id, STOPPING_MESSAGE)
                return
            if run_id in self._held:
                return
            self._failures.pop(run_id, None)
            thread = threading.Thread(target=self._run, args=(run_id,), daemon=True)
            self._held[run_id] = thread
            thread.start()

    def running(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._held

    def error(self, run_id: str) -> str | None:
        with self._lock:
            return self._failures.get(run_id)

    def join(self, run_id: str, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._held.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def retained(self) -> tuple[int, int]:
        with self._lock:
            return (len(self._held), len(self._failures))

    def close(self, timeout: float = SHUTDOWN_SECONDS) -> tuple[str, ...]:
        with self._idle:
            self._stopping = True
            self._idle.wait_for(lambda: not self._held, timeout)
            return tuple(sorted(self._held))

    def _keep(self, run_id: str, message: str) -> None:
        self._failures.pop(run_id, None)
        self._failures[run_id] = message
        while len(self._failures) > MAX_FAILURES:
            del self._failures[next(iter(self._failures))]

    def _run(self, run_id: str) -> None:
        message: str | None = None
        try:
            with runtime.open_runtime(self._settings) as opened:
                runtime.resume(opened, run_id)
        except (RunError, ToolCheckFailed) as error:
            message = str(error)
        except Exception:
            message = "the resume failed"
        with self._idle:
            self._held.pop(run_id, None)
            if message is None:
                self._failures.pop(run_id, None)
            else:
                self._keep(run_id, message)
            self._idle.notify_all()
