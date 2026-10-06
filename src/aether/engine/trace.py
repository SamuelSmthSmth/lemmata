"""What the engine computed for a line, as it computed it: the trace.

``ProofChecker(trace=True)`` records one event per backend call made while
checking a statement -- an entailment Z3 was asked, an identity SymPy
simplified, a domain side condition, an unsat core -- with what was asked, the
answer and how long it took, and attaches them to the statement's result
(``StepResult.trace``).  Calls made inside another call are nested under it
(``depth``), so a fallback reads as part of the check that needed it.

Off by default, and then a backend call costs one context-variable lookup.
"""

from __future__ import annotations

import functools
import time
from contextvars import ContextVar
from typing import Any, Callable, Optional, TypeVar

#: Longest text an event keeps of what was asked; a hypothesis list can be long.
QUERY_LIMIT = 240

F = TypeVar("F", bound=Callable[..., Any])


class Recorder:
    """The events of one statement, in the order their calls started."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.depth = 0


_recorder: ContextVar[Optional[Recorder]] = ContextVar("aether_trace", default=None)


def active() -> Optional[Recorder]:
    return _recorder.get()


class recording:
    """``with recording() as rec:`` collects the events of the calls made inside."""

    def __init__(self, enabled: bool = True) -> None:
        self.recorder = Recorder() if enabled else None
        self._token = None

    def __enter__(self) -> Optional[Recorder]:
        self._token = _recorder.set(self.recorder)
        return self.recorder

    def __exit__(self, *exc: object) -> None:
        _recorder.reset(self._token)  # type: ignore[arg-type]


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= QUERY_LIMIT else text[: QUERY_LIMIT - 1] + "…"


def _outcome(value: Any, none: str) -> str:
    """A call's answer in a word or two."""
    if value is None:
        return none
    valid = getattr(value, "valid", None)
    if isinstance(valid, bool):
        return "holds" if valid else "fails"
    if isinstance(value, list):
        return f"{len(value)} used"
    return str(value)


def traced(
    backend: str, call: str, describe: Callable[..., str], quiet: bool = False, none: str = "does not apply"
) -> Callable[[F], F]:
    """Record a call to the decorated backend function while a trace is on.

    *describe* takes the call's arguments and says what was asked, in the
    proof's own notation (``x^2 > 4``).  A *quiet* call that answers None
    without asking anything else is left out: it did not apply."""

    def wrap(fn: F) -> F:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            rec = _recorder.get()
            if rec is None:
                return fn(*args, **kwargs)
            try:
                query = _clip(describe(*args, **kwargs))
            except Exception:  # noqa: BLE001 - describing a call must never break it
                query = ""
            depth = rec.depth
            slot = len(rec.events)
            rec.events.append({})
            rec.depth += 1
            start = time.perf_counter()
            try:
                value = fn(*args, **kwargs)
            except BaseException:
                rec.events[slot] = _event(backend, call, query, "error", start, depth, None)
                raise
            finally:
                rec.depth = depth
            if value is None and quiet and slot == len(rec.events) - 1:
                # It did not apply (no induction to check) and asked nothing.
                rec.events.pop()
            else:
                rec.events[slot] = _event(backend, call, query, _outcome(value, none), start, depth, value)
            return value

        return inner  # type: ignore[return-value]

    return wrap


def solver_event(result: str, assertions: int, start: float) -> None:
    """Record one Z3 ``check()``: its answer and the size of the problem."""
    rec = _recorder.get()
    if rec is None:
        return
    rec.events.append(
        _event("Z3", "check", f"{assertions} assertions", result, start, rec.depth, None)
    )


def _event(
    backend: str, call: str, query: str, result: str, start: float, depth: int, value: Any
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "backend": backend,
        "call": call,
        "query": query,
        "result": result,
        "ms": round((time.perf_counter() - start) * 1000, 2),
        "depth": depth,
    }
    detail = getattr(value, "backend", None)
    if isinstance(detail, str) and detail != backend:
        event["settled_by"] = detail
    return event
