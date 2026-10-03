"""Run the engine in worker processes, each job under a hard wall-clock budget.

Z3's ``timeout`` is advisory: a query stalled in model-based quantifier
instantiation ignores it, and an in-process check that stalls holds a server
thread for as long as it likes (minutes, in the worst case the capability sweep
has seen).  So the engine never runs in the server process.  A few warm workers
each hold a ready ``ProofChecker`` -- building the parser costs about a second,
which is why a process is not spawned per request -- and a job that overruns
its budget is answered with a timeout while its worker is killed and replaced.

Workers are started with ``spawn`` rather than ``fork``: the server is
multi-threaded, and forking a threaded process can copy a lock some other
thread was holding.
"""

from __future__ import annotations

import multiprocessing
import os
import queue
import threading
from typing import Any, Optional

from .engine_jobs import check_payload  # noqa: F401 - re-exported for callers and tests

DEFAULT_BUDGET_S = float(os.environ.get("AETHER_CHECK_BUDGET", "20"))
DEFAULT_WORKERS = max(1, int(os.environ.get("AETHER_CHECK_WORKERS", "2")))


class CheckTimeout(Exception):
    """The job ran past its budget; its worker has been replaced."""

    def __init__(self, budget: float) -> None:
        super().__init__(f"stopped after {budget:g} s")
        self.budget = budget


class WorkerCrashed(Exception):
    """The worker died mid-job (e.g. out of memory); it has been replaced."""


# ---------------------------------------------------------------------------
# What a worker does: the jobs themselves live in engine_jobs.py
# ---------------------------------------------------------------------------

def _worker_main(conn) -> None:
    """Serve jobs over *conn* until it closes."""
    from .engine_jobs import Engine, error_text

    engine = Engine()
    conn.send(("ready", None))
    while True:
        try:
            kind, payload = conn.recv()
        except (EOFError, OSError):
            return
        try:
            conn.send(("ok", engine.run(kind, payload)))
        except Exception as exc:  # noqa: BLE001 - reported to the caller as the job's failure
            conn.send(("error", error_text(exc)))


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------


class _Worker:
    def __init__(self, ctx) -> None:
        parent, child = ctx.Pipe()
        self.conn = parent
        self.proc = ctx.Process(target=_worker_main, args=(child,), daemon=True)
        self.proc.start()
        child.close()

    def wait_ready(self, timeout: float) -> bool:
        if not self.conn.poll(timeout):
            return False
        try:
            tag, _ = self.conn.recv()
        except (EOFError, OSError):
            return False
        return tag == "ready"

    def kill(self) -> None:
        try:
            self.proc.kill()
        finally:
            self.proc.join(timeout=5)
            self.conn.close()


class CheckPool:
    """A fixed set of warm workers; jobs queue for the next idle one."""

    def __init__(self, workers: int = DEFAULT_WORKERS, budget: float = DEFAULT_BUDGET_S) -> None:
        self.size = workers
        self.budget = budget
        self._ctx = multiprocessing.get_context("spawn")
        self._idle: "queue.Queue[_Worker]" = queue.Queue()
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        for _ in range(self.size):
            self._spawn_async()

    def _spawn_async(self) -> None:
        def spawn() -> None:
            worker = _Worker(self._ctx)
            if worker.wait_ready(timeout=120):
                self._idle.put(worker)
            else:  # a worker that cannot even start is replaced, not queued
                worker.kill()
                self._spawn_async()

        threading.Thread(target=spawn, name="aether-check-spawn", daemon=True).start()

    def run(self, kind: str, payload: dict[str, Any], budget: Optional[float] = None) -> Any:
        """Run one job; raises ``CheckTimeout`` past the budget."""
        self.start()
        budget = self.budget if budget is None else budget
        worker = self._idle.get()
        try:
            worker.conn.send((kind, payload))
            if not worker.conn.poll(budget):
                raise CheckTimeout(budget)
            tag, result = worker.conn.recv()
        except CheckTimeout:
            worker.kill()
            self._spawn_async()
            raise
        except (EOFError, OSError) as exc:
            worker.kill()
            self._spawn_async()
            raise WorkerCrashed(str(exc)) from exc
        self._idle.put(worker)
        if tag == "error":
            raise RuntimeError(result)
        return result

    def close(self) -> None:
        while True:
            try:
                self._idle.get_nowait().kill()
            except queue.Empty:
                return


_pool: Optional[CheckPool] = None
_pool_lock = threading.Lock()


def pool() -> CheckPool:
    """The process-wide pool, created on first use."""
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = CheckPool()
        return _pool
