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
import time
from typing import Any, Mapping, Optional

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
# What a worker does (importable on its own, so tests can run it in-process)
# ---------------------------------------------------------------------------


def _source_line(lines: list[str], line: Optional[int]) -> Optional[str]:
    if line is None or not (1 <= line <= len(lines)):
        return None
    return lines[line - 1]


def _report_verdict(report) -> str:
    if not report.is_valid:
        return "INVALID"
    if report.has_warnings:
        return "VALID (with domain warnings)"
    return "VALID"


def _step(result, lines: list[str]) -> dict[str, Any]:
    return {
        "line": result.line,
        "col": getattr(result, "col", None),
        "statement": str(result.statement),
        "source_line": _source_line(lines, result.line),
        "status": result.status.value,
        "message": result.message,
        "backend": result.backend,
        "scope_depth": result.scope_depth,
        "active_variables": dict(result.active_variables),
        "active_hypotheses": list(result.active_hypotheses),
        "domain_warnings": list(result.domain_warnings),
        "counterexample": result.counterexample,
        "counterexample_dict": getattr(result, "counterexample_dict", None),
        "diagnostic_range": getattr(result, "diagnostic_range", None),
        "subproof_metadata": getattr(result, "subproof_metadata", None),
    }


def _empty_summary(invalid: int = 0) -> dict[str, int]:
    return {"total": 0, "valid": 0, "warnings": 0, "invalid": invalid}


def check_payload(
    source: str,
    strict_domains: bool,
    files: Optional[Mapping[str, str]] = None,
    checker=None,
) -> dict[str, Any]:
    """Check *source* and shape the result as the ``/api/check`` response body."""
    from aether import ParseError, ProofChecker

    started = time.perf_counter()
    lines = source.splitlines()
    if checker is None:
        checker = ProofChecker(strict_domains=strict_domains)

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000.0

    try:
        if files:
            reports = checker.check_source(source, sources=dict(files))
        else:
            reports = checker.check_source(source)
    except ParseError as err:
        headline = str(err.message).splitlines()[0] if err.message else str(err)
        return {
            "verdict": "PARSE ERROR",
            "reports": [],
            "parse_error": {"message": str(err.message), "headline": headline, "line": err.line, "col": err.col},
            "summary": _empty_summary(),
            "strict_domains": strict_domains,
            "duration_ms": elapsed(),
        }
    except Exception as exc:  # noqa: BLE001 - an engine bug must not take the API down
        return {
            "verdict": "INVALID",
            "reports": [],
            "parse_error": {
                "message": str(exc),
                "headline": f"Engine error: {type(exc).__name__}",
                "line": None,
                "col": None,
            },
            "summary": _empty_summary(invalid=1),
            "strict_domains": strict_domains,
            "duration_ms": elapsed(),
        }

    report_models = []
    counts = {"VALID": 0, "WARNING": 0, "INVALID": 0}
    for report in reports:
        steps = [_step(result, lines) for result in report.results]
        for step in steps:
            counts[step["status"]] += 1
        report_models.append(
            {
                "theorem_name": report.theorem_name,
                "is_valid": report.is_valid,
                "has_warnings": report.has_warnings,
                "verdict": _report_verdict(report),
                "results": steps,
            }
        )

    if any(not r.is_valid for r in reports):
        verdict = "INVALID"
    elif any(r.has_warnings for r in reports):
        verdict = "VALID (with domain warnings)"
    else:
        verdict = "VALID"
    return {
        "verdict": verdict,
        "reports": report_models,
        "parse_error": None,
        "summary": {
            "total": sum(counts.values()),
            "valid": counts["VALID"],
            "warnings": counts["WARNING"],
            "invalid": counts["INVALID"],
        },
        "strict_domains": strict_domains,
        "duration_ms": elapsed(),
    }


def _worker_main(conn) -> None:
    """Serve jobs over *conn* until it closes."""
    from aether import ProofChecker

    from .latex_report import export_report_latex

    # One warm checker per mode; building the parser is the expensive part.
    checkers = {False: ProofChecker(strict_domains=False), True: ProofChecker(strict_domains=True)}
    conn.send(("ready", None))
    while True:
        try:
            kind, payload = conn.recv()
        except (EOFError, OSError):
            return
        try:
            if kind == "check":
                strict = bool(payload["strict_domains"])
                result = check_payload(
                    payload["source"], strict, payload.get("files"), checker=checkers[strict]
                )
                checkers[strict].clear_cache()
            elif kind == "latex":
                result = export_report_latex(payload.pop("source"), **payload)
            else:
                raise ValueError(f"unknown job kind {kind!r}")
            conn.send(("ok", result))
        except Exception as exc:  # noqa: BLE001 - reported to the caller as the job's failure
            # A parse error's own message is what the UI shows; anything else
            # keeps its type so an engine bug is recognisable as one.
            message = getattr(exc, "message", None) if type(exc).__name__ == "ParseError" else None
            conn.send(("error", str(message) if message else f"{type(exc).__name__}: {exc}"))


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
