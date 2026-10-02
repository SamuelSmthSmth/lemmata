"""FastAPI backend exposing the Aether engine to the web UI.

The engine is used strictly as a library -- nothing here reaches into
``aether.core`` / ``aether.parser`` / ``aether.engine`` internals, it only
consumes the public API documented in AGENTS.md.

Endpoints
---------
GET  /               -> the single-page frontend
GET  /api/examples   -> bundled sample proofs
GET  /api/library    -> course packs (courses/*.json) plus the examples, for the Library
POST /api/check      -> verify a proof source string
GET  /api/health     -> liveness probe

Every engine call (checking and the LaTeX/PDF report, which re-checks) runs in
a worker process from ``checking.pool()`` under a hard wall-clock budget, so a
stalled solver query can cost a request its answer but never a server thread.
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .checking import CheckTimeout, WorkerCrashed, pool
from .examples import EXAMPLES

STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_DIR = Path(__file__).resolve().parent.parent
COURSES_DIR = PROJECT_DIR / "courses"
EXAMPLE_FILES_DIR = PROJECT_DIR / "examples"

StepStatusName = Literal["VALID", "WARNING", "INVALID"]
Verdict = Literal["VALID", "VALID (with domain warnings)", "INVALID", "PARSE ERROR", "TIMEOUT"]


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
    # The browser workspace: other files `import` can resolve against, keyed by
    # workspace path, and the checked file's own path for relative imports.
    files: Optional[dict[str, str]] = None
    path: Optional[str] = None


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
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm the workers while the server comes up, so the first check does not
    # pay for starting them.
    pool().start()
    yield
    pool().close()


app = FastAPI(
    title="Aether Proof Checker",
    description="Controlled-natural-language proof intern for undergraduate mathematics.",
    version="0.1.0",
    lifespan=lifespan,
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


class LibraryEntryModel(BaseModel):
    id: str
    chapter: str
    ref: str
    title: str
    kind: Literal["proof", "trap"]
    expected: str
    explanation: Optional[str] = None
    blurb: Optional[str] = None
    source: str


class LibraryChapterModel(BaseModel):
    id: str
    title: str


class LibraryPackModel(BaseModel):
    id: str
    code: str
    title: str
    note: str
    chapters: list[LibraryChapterModel]
    entries: list[LibraryEntryModel]


def _examples_pack() -> dict[str, Any]:
    """The bundled examples, and the standalone proofs in examples/, as one pack."""
    entries: list[dict[str, Any]] = []
    for example in EXAMPLES:
        # The blurbs lead with the verdict word ("WARNING (INVALID when strict ...)").
        first = example["expected"].split(" ")[0].upper()
        expected = {"WARNING": "WARN", "PARSE": "PARSE ERROR"}.get(first, first)
        entries.append(
            {
                "id": example["id"],
                "chapter": "bundled",
                "ref": "Example",
                "title": example["name"],
                "kind": "proof",
                "expected": expected,
                "blurb": example["blurb"],
                "source": example["source"],
            }
        )
    for path in sorted(EXAMPLE_FILES_DIR.glob("*.aether")):
        entries.append(
            {
                "id": f"file-{path.stem}",
                "chapter": "files",
                "ref": path.name,
                "title": path.stem.replace("_", " ").capitalize(),
                "kind": "proof",
                "expected": "VALID",
                "source": path.read_text(encoding="utf-8"),
            }
        )
    return {
        "id": "examples",
        "code": "EXAMPLES",
        "title": "Worked examples",
        "note": "Short proofs that show each part of the language, including deliberate failures.",
        "chapters": [
            {"id": "bundled", "title": "The language, by example"},
            {"id": "files", "title": "Standalone proofs"},
        ],
        "entries": entries,
    }


@app.get("/api/library", response_model=list[LibraryPackModel])
def library() -> list[dict[str, Any]]:
    """Every course pack, read fresh so a new pack file shows up without a restart."""
    packs = [_examples_pack()]
    for pack_file in sorted(COURSES_DIR.glob("*.json")):
        packs.append(json.loads(pack_file.read_text(encoding="utf-8")))
    return packs


@app.post("/api/check", response_model=CheckResponse)
def check_proof(request: CheckRequest) -> CheckResponse:
    """Verify a proof document.

    Declared with ``def`` (not ``async def``) so FastAPI runs it on a worker
    thread: SymPy and Z3 are blocking and CPU-bound, and would otherwise stall
    the event loop.
    """
    started = time.perf_counter()
    try:
        payload = pool().run(
            "check",
            {
                "source": request.source,
                "strict_domains": request.strict_domains,
                "files": request.files,
                "path": request.path,
            },
        )
    except (CheckTimeout, WorkerCrashed) as exc:
        if isinstance(exc, CheckTimeout):
            headline = f"Checking stopped after {exc.budget:g} s"
            message = (
                "One of the steps asks the solver something it cannot settle quickly, so the check "
                "was stopped rather than left running. Split the step into smaller ones, or add the "
                "hypothesis it depends on."
            )
        else:
            headline = "The checker stopped unexpectedly"
            message = "The worker checking this proof exited mid-check (it may have run out of memory)."
        return CheckResponse(
            verdict="TIMEOUT",
            reports=[],
            parse_error=ParseErrorModel(message=message, headline=headline, line=None, col=None),
            summary=SummaryModel(total=0, valid=0, warnings=0, invalid=0),
            strict_domains=request.strict_domains,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    return CheckResponse(**payload)


def _latex_job(source: str, **options: Any) -> str:
    """Render the report in a worker; the export re-checks, so it is budgeted too."""
    try:
        return pool().run("latex", {"source": source, **options})
    except CheckTimeout as exc:
        raise RuntimeError(f"checking the proof for the report stopped after {exc.budget:g} s") from exc


@app.post("/api/export/latex", response_model=LatexExportResponse)
def export_latex(request: LatexExportRequest) -> LatexExportResponse:
    """Export proof source text to clean LaTeX markup.

    This is the ``.tex`` a user takes away to edit, so it stays the plain
    article presentation; the designed one is only used when Aether compiles
    the document itself (see ``export_pdf``).
    """
    try:
        latex_code = _latex_job(
            request.source,
            strict_domains=request.strict_domains,
            standalone=request.standalone,
            breakdown=request.breakdown,
            session=request.session,
            style="plain",
        )
        return LatexExportResponse(latex=latex_code)
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
        # The PDF is a finished document, so it gets the designed presentation:
        # a site-matched layout with journal proof and auditor step list.
        tex_code = _latex_job(
            request.source,
            strict_domains=request.strict_domains,
            standalone=True,
            breakdown=request.breakdown,
            session=request.session,
            style="fancy",
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

