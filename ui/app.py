"""FastAPI backend exposing the Aether engine to the web UI.

The engine is used strictly as a library -- nothing here reaches into
``aether.core`` / ``aether.parser`` / ``aether.engine`` internals, it only
consumes the public API documented in AGENTS.md.

Endpoints
---------
GET  /               -> the single-page frontend
GET  /api/examples   -> bundled sample proofs
POST /api/check      -> verify a proof source string
GET  /api/health     -> liveness probe
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aether import ParseError, ProofChecker, ProofReport

from .examples import EXAMPLES
from .latex_report import export_report_latex

STATIC_DIR = Path(__file__).resolve().parent / "static"

StepStatusName = Literal["VALID", "WARNING", "INVALID"]
Verdict = Literal["VALID", "VALID (with domain warnings)", "INVALID", "PARSE ERROR"]


# ---------------------------------------------------------------------------
# Response models - these are the UI's contract, so they are explicit rather
# than reflecting arbitrary engine objects.
# ---------------------------------------------------------------------------


class ParseErrorModel(BaseModel):
    """A syntax/indentation error, with the location the UI highlights."""

    message: str = Field(description="Full parser message.")
    headline: str = Field(description="First line of the parser message.")
    line: Optional[int] = None
    col: Optional[int] = None


class StepModel(BaseModel):
    """One audited statement."""

    line: Optional[int] = None
    col: Optional[int] = None
    statement: str
    source_line: Optional[str] = Field(
        default=None, description="The verbatim source line, for exact display."
    )
    status: StepStatusName
    message: str
    backend: str
    scope_depth: int
    active_variables: dict[str, str]
    active_hypotheses: list[str]
    domain_warnings: list[str]
    counterexample: Optional[str] = None
    counterexample_dict: Optional[dict[str, str]] = None
    diagnostic_range: Optional[dict[str, int]] = None
    subproof_metadata: Optional[dict[str, Any]] = None


class ReportModel(BaseModel):
    """Audit for a single theorem (or the top-level scratchpad)."""

    theorem_name: Optional[str] = None
    is_valid: bool
    has_warnings: bool
    verdict: str
    results: list[StepModel]


class SummaryModel(BaseModel):
    total: int
    valid: int
    warnings: int
    invalid: int


class CheckResponse(BaseModel):
    verdict: Verdict
    reports: list[ReportModel]
    parse_error: Optional[ParseErrorModel] = None
    summary: SummaryModel
    strict_domains: bool
    duration_ms: float


class CheckRequest(BaseModel):
    source: str = ""
    strict_domains: bool = False


class ExampleModel(BaseModel):
    id: str
    name: str
    blurb: str
    expected: str
    source: str


class LatexExportRequest(BaseModel):
    source: str = ""
    standalone: bool = True
    strict_domains: bool = False
    # Appending the verification report is what turns the export from a
    # typeset proof into an audit of one; it can be turned off to get exactly
    # the engine's own output.
    breakdown: bool = True
    # The workspace panel's timeline and snapshots live in the browser's local
    # storage, so the client sends them if it wants them in the document.
    session: Optional[dict[str, Any]] = None


class LatexExportResponse(BaseModel):
    latex: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Verdict helpers
# ---------------------------------------------------------------------------


def _report_verdict(report: ProofReport) -> str:
    """Mirror ``ProofReport.format_report``'s verdict wording."""
    if not report.is_valid:
        return "INVALID"
    if report.has_warnings:
        return "VALID (with domain warnings)"
    return "VALID"


def _overall_verdict(reports: list[ProofReport]) -> Verdict:
    if any(not r.is_valid for r in reports):
        return "INVALID"
    if any(r.has_warnings for r in reports):
        return "VALID (with domain warnings)"
    return "VALID"


def _source_line(lines: list[str], line: Optional[int]) -> Optional[str]:
    if line is None or not (1 <= line <= len(lines)):
        return None
    return lines[line - 1]


def _to_step(result, lines: list[str]) -> StepModel:
    return StepModel(
        line=result.line,
        col=getattr(result, "col", None),
        statement=str(result.statement),
        source_line=_source_line(lines, result.line),
        status=result.status.value,
        message=result.message,
        backend=result.backend,
        scope_depth=result.scope_depth,
        active_variables=dict(result.active_variables),
        active_hypotheses=list(result.active_hypotheses),
        domain_warnings=list(result.domain_warnings),
        counterexample=result.counterexample,
        counterexample_dict=getattr(result, "counterexample_dict", None),
        diagnostic_range=getattr(result, "diagnostic_range", None),
        subproof_metadata=getattr(result, "subproof_metadata", None),
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aether Proof Checker",
    description="Controlled-natural-language proof intern for undergraduate mathematics.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/examples", response_model=list[ExampleModel])
def list_examples() -> list[ExampleModel]:
    return [ExampleModel(**example) for example in EXAMPLES]


@app.post("/api/check", response_model=CheckResponse)
def check_proof(request: CheckRequest) -> CheckResponse:
    """Verify a proof document.

    Declared with ``def`` (not ``async def``) so FastAPI runs it on a worker
    thread: SymPy and Z3 are blocking and CPU-bound, and would otherwise stall
    the event loop.
    """
    started = time.perf_counter()
    lines = request.source.splitlines()
    checker = ProofChecker(strict_domains=request.strict_domains)

    try:
        reports = checker.check_source(request.source)
    except ParseError as err:
        headline = str(err.message).splitlines()[0] if err.message else str(err)
        return CheckResponse(
            verdict="PARSE ERROR",
            reports=[],
            parse_error=ParseErrorModel(
                message=str(err.message),
                headline=headline,
                line=err.line,
                col=err.col,
            ),
            summary=SummaryModel(total=0, valid=0, warnings=0, invalid=0),
            strict_domains=request.strict_domains,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as exc:
        headline = f"Engine error: {type(exc).__name__}"
        return CheckResponse(
            verdict="INVALID",
            reports=[],
            parse_error=ParseErrorModel(
                message=str(exc),
                headline=headline,
                line=None,
                col=None,
            ),
            summary=SummaryModel(total=0, valid=0, warnings=0, invalid=1),
            strict_domains=request.strict_domains,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    report_models: list[ReportModel] = []
    counts = {"VALID": 0, "WARNING": 0, "INVALID": 0}
    total = 0

    for report in reports:
        steps = [_to_step(result, lines) for result in report.results]
        total += len(steps)
        for step in steps:
            counts[step.status] += 1
        report_models.append(
            ReportModel(
                theorem_name=report.theorem_name,
                is_valid=report.is_valid,
                has_warnings=report.has_warnings,
                verdict=_report_verdict(report),
                results=steps,
            )
        )

    return CheckResponse(
        verdict=_overall_verdict(reports),
        reports=report_models,
        parse_error=None,
        summary=SummaryModel(
            total=total,
            valid=counts["VALID"],
            warnings=counts["WARNING"],
            invalid=counts["INVALID"],
        ),
        strict_domains=request.strict_domains,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


@app.post("/api/export/latex", response_model=LatexExportResponse)
async def export_latex(request: LatexExportRequest) -> LatexExportResponse:
    """Export proof source text to clean LaTeX markup."""
    try:
        latex_code = export_report_latex(
            request.source,
            strict_domains=request.strict_domains,
            standalone=request.standalone,
            breakdown=request.breakdown,
            session=request.session,
        )
        return LatexExportResponse(latex=latex_code)
    except ParseError as err:
        return LatexExportResponse(latex="", error=str(err.message))
    except Exception as exc:
        return LatexExportResponse(latex="", error=str(exc))


class PdfExportRequest(BaseModel):
    source: str = ""
    strict_domains: bool = False
    breakdown: bool = True
    session: Optional[dict[str, Any]] = None


@app.post("/api/export/pdf")
def export_pdf(request: PdfExportRequest) -> Response:
    """Compile proof LaTeX into a publication-ready PDF using pdflatex."""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("pdflatex"):
        return JSONResponse(
            status_code=501,
            content={"error": "pdflatex is not installed on the server host."},
        )

    try:
        tex_code = export_report_latex(
            request.source,
            strict_domains=request.strict_domains,
            standalone=True,
            breakdown=request.breakdown,
            session=request.session,
        )
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": f"LaTeX generation failed: {exc}"})

    with tempfile.TemporaryDirectory() as td:
        tex_file = Path(td) / "proof.tex"
        tex_file.write_text(tex_code, encoding="utf-8")
        # Two passes: longtable measures its columns on the first and lays them
        # out on the second, so a single pass leaves the report's tables ragged.
        res = None
        for _ in range(2):
            try:
                res = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "proof.tex"],
                    cwd=td,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                return JSONResponse(status_code=504, content={"error": "PDF compilation timed out."})

        pdf_file = Path(td) / "proof.pdf"
        if not pdf_file.exists():
            log_tail = "\n".join(res.stdout.splitlines()[-15:])
            return JSONResponse(
                status_code=422,
                content={"error": f"pdflatex compilation failed:\n{log_tail}"},
            )

        pdf_bytes = pdf_file.read_bytes()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="proof.pdf"'},
        )

