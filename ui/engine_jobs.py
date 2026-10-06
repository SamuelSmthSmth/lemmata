"""The engine's jobs, as plain functions: what a check returns, and how.

The same code answers a check wherever the engine runs:

* in the server, inside the worker processes of ``ui/checking.py``;
* in the browser, inside the Pyodide Web Worker of the static build
  (``ui/static/js/engine-worker.js``).

So this module must stay importable without the server's machinery: no
``multiprocessing``, no FastAPI, nothing that needs threads or a real OS.
"""

from __future__ import annotations

import re
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
        "citation": getattr(result, "citation", None),
        "hints": list(getattr(result, "hints", []) or []),
        # What the line was proved from, and the backend calls that checked it
        # (ProofChecker(dependencies=True, trace=True)); empty unless asked for.
        "premises": [dict(p) for p in getattr(result, "premises", []) or []],
        "premises_complete": bool(getattr(result, "premises_complete", False)),
        "trace": [dict(e) for e in getattr(result, "trace", []) or []],
        # A block's own lines, with their traces, for the Trace tab (the auditor
        # shows a block as one row); only when the check was traced.
        "inner": _inner(result),
    }


def _inner(result) -> list[dict[str, Any]]:
    subs = getattr(result, "sub_results", None) or []
    if not subs or not any(_traced(s) for s in subs):
        return []
    return [
        {
            "line": s.line,
            "statement": str(s.statement),
            "status": s.status.value,
            "trace": [dict(e) for e in getattr(s, "trace", []) or []],
            "inner": _inner(s),
        }
        for s in subs
    ]


def _traced(result) -> bool:
    return bool(getattr(result, "trace", None)) or any(_traced(s) for s in getattr(result, "sub_results", None) or [])


def _empty_summary(invalid: int = 0) -> dict[str, int]:
    return {"total": 0, "valid": 0, "warnings": 0, "invalid": invalid}


def check_payload(
    source: str,
    strict_domains: bool,
    files: Optional[Mapping[str, str]] = None,
    checker=None,
    path: Optional[str] = None,
    citations: Optional[Mapping[str, Any]] = None,
    show_working: bool = False,
    audit: bool = False,
) -> dict[str, Any]:
    """Check *source* and shape the result as the ``/api/check`` response body.

    *audit* asks for what each line used and the trace of its backend calls,
    which the app draws as the proof graph and the Trace tab."""
    from aether import ParseError, ProofChecker

    started = time.perf_counter()
    lines = source.splitlines()
    if checker is None:
        checker = ProofChecker(
            strict_domains=strict_domains, show_working=show_working, dependencies=audit, trace=audit
        )

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000.0

    try:
        if files:
            # The workspace: imports resolve against these files, relative to `path`;
            # `citations` names the results a step may cite (`by Theorem 1.1`).
            reports = checker.check_source(source, file_path=path, sources=dict(files), citations=citations or None)
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
    """One ready checker per mode (strict domains, show working, audit); building the parser is the expensive part."""

    def __init__(self) -> None:
        self.checkers: dict[tuple[bool, bool, bool], Any] = {}
        self.checker(False, False, True)

    def checker(self, strict: bool, working: bool, audit: bool):
        key = (strict, working, audit)
        if key not in self.checkers:
            from aether import ProofChecker

            self.checkers[key] = ProofChecker(
                strict_domains=strict, show_working=working, dependencies=audit, trace=audit
            )
        return self.checkers[key]

    def run(self, kind: str, payload: dict[str, Any]) -> Any:
        if kind == "check":
            strict = bool(payload["strict_domains"])
            working = bool(payload.get("show_working", False))
            audit = bool(payload.get("audit", False))
            checker = self.checker(strict, working, audit)
            try:
                return check_payload(
                    payload["source"],
                    strict,
                    payload.get("files"),
                    checker=checker,
                    path=payload.get("path"),
                    citations=payload.get("citations"),
                    show_working=working,
                    audit=audit,
                )
            finally:
                checker.clear_cache()
        if kind == "latex":
            from .latex_report import export_report_latex

            options = dict(payload)
            return export_report_latex(options.pop("source"), **options)
        if kind == "lean":
            from aether.core.lean_export import export_to_lean

            from .site import NAME

            # The skeleton's namespace is the product's name, as a Lean identifier.
            namespace = re.sub(r"[^A-Za-z0-9_]", "", NAME.title().replace(" ", "")) or "Proof"
            return export_to_lean(
                payload["source"],
                sources=payload.get("files"),
                file_path=payload.get("path"),
                citations=payload.get("citations"),
                namespace=namespace if namespace[0].isalpha() else f"P{namespace}",
            ).to_dict()
        if kind == "validate_pack":
            from aether.packs import validate_pack

            pack, errors = validate_pack(payload.get("pack"))
            return {"pack": pack, "errors": errors} if pack is not None else {"errors": errors}
        raise ValueError(f"unknown job kind {kind!r}")


def error_text(exc: BaseException) -> str:
    """How a failed job is reported: a parse error by its own message, anything else by type."""
    message = getattr(exc, "message", None) if type(exc).__name__ == "ParseError" else None
    return str(message) if message else f"{type(exc).__name__}: {exc}"
