"""The engine's jobs, as plain functions: what a check returns, and how.

The same code answers a check wherever the engine runs:

* in the server, inside the worker processes of ``ui/checking.py``;
* in the browser, inside the Pyodide Web Worker of the static build
  (``ui/static/js/engine-worker.js``).

So this module must stay importable without the server's machinery: no
``multiprocessing``, no FastAPI, nothing that needs threads or a real OS.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional


# ---------------------------------------------------------------------------
# Checking a proof and shaping the result
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
    path: Optional[str] = None,
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
            # The workspace: imports resolve against these files, relative to `path`.
            reports = checker.check_source(source, file_path=path, sources=dict(files))
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


# ---------------------------------------------------------------------------
# A warm engine that answers jobs by kind
# ---------------------------------------------------------------------------


class Engine:
    """One ready checker per strictness mode; building the parser is the expensive part."""

    def __init__(self) -> None:
        from aether import ProofChecker

        self.checkers = {False: ProofChecker(strict_domains=False), True: ProofChecker(strict_domains=True)}

    def run(self, kind: str, payload: dict[str, Any]) -> Any:
        if kind == "check":
            strict = bool(payload["strict_domains"])
            try:
                return check_payload(
                    payload["source"],
                    strict,
                    payload.get("files"),
                    checker=self.checkers[strict],
                    path=payload.get("path"),
                )
            finally:
                self.checkers[strict].clear_cache()
        if kind == "latex":
            from .latex_report import export_report_latex

            options = dict(payload)
            return export_report_latex(options.pop("source"), **options)
        if kind == "validate_pack":
            from aether.packs import validate_pack

            pack, errors = validate_pack(payload.get("pack"))
            return {"pack": pack, "errors": errors} if pack is not None else {"errors": errors}
        raise ValueError(f"unknown job kind {kind!r}")


def error_text(exc: BaseException) -> str:
    """How a failed job is reported: a parse error by its own message, anything else by type."""
    message = getattr(exc, "message", None) if type(exc).__name__ == "ParseError" else None
    return str(message) if message else f"{type(exc).__name__}: {exc}"
