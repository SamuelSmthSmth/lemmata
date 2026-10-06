"""FastAPI backend exposing the proof-checking engine (``aether``) to the web UI.

The engine is used strictly as a library -- nothing here reaches into
``aether.core`` / ``aether.parser`` / ``aether.engine`` internals, it only
consumes the public API documented in AGENTS.md.

Endpoints
---------
GET  /               -> the single-page frontend
GET  /api/examples   -> bundled sample proofs
GET  /api/library    -> the bundled pack catalogue (examples + courses/*.json), format 1
POST /api/packs/validate -> check a .pack.json before the browser installs it
GET  /api/capabilities -> the capability matrix (pins), for the Guide
POST /api/check      -> verify a proof source string
GET  /api/site       -> the product name, tagline and version (ui/site.json)
GET  /api/health     -> liveness probe

Every engine call (checking and the LaTeX/PDF report, which re-checks) runs in
a worker process from ``checking.pool()`` under a hard wall-clock budget, so a
stalled solver query can cost a request its answer but never a server thread.
"""

from __future__ import annotations

import re
import time
from html import escape
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aether.packs import PACK_FORMAT, load_packs, validate_pack

from .checking import CheckTimeout, WorkerCrashed, pool
from .examples import EXAMPLE_FILE_VERDICTS, EXAMPLES
from .site import NAME, SITE, TAGLINE, VERSION

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
    # The result a `by …` citation used, and what to do about a failure.
    citation: Optional[dict[str, str]] = None
    hints: list[dict[str, Any]] = Field(default_factory=list)
    # With `audit`: what the line was proved from ({"kind", "line", "label",
    # "fact"}), whether that list is the whole story, and the backend calls
    # made checking it ({"backend", "call", "query", "result", "ms", "depth"}).
    premises: list[dict[str, Any]] = Field(default_factory=list)
    premises_complete: bool = False
    trace: list[dict[str, Any]] = Field(default_factory=list)
    # A block's own lines, each {"line", "statement", "status", "trace", "inner"}.
    inner: list[dict[str, Any]] = Field(default_factory=list)


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
    # Show your working: a step that skips the working a question asks to see
    # is a warning naming the rule (ProofChecker(show_working=True)).
    show_working: bool = False
    # What each line used and the trace of its backend calls (the proof graph
    # and the Trace tab): ProofChecker(dependencies=True, trace=True).
    audit: bool = False
    # The proof kernel's level (aether.kernel): how big a step one line may
    # take, and premise selection for cited lines; None checks without it.
    kernel: Optional[Literal["exam", "course", "scratch"]] = None
    # The browser workspace: other files `import` can resolve against, keyed by
    # workspace path, and the checked file's own path for relative imports.
    files: Optional[dict[str, str]] = None
    path: Optional[str] = None
    # The names a step may cite, each with the files that prove it (see
    # aether.engine.citations): {"Theorem 1.1": [["MTH2008 Theorem 1.1 · …", "@core/mth2008/….aether"]]}.
    citations: Optional[dict[str, Any]] = None


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
    title=NAME,
    description="Controlled-natural-language proof intern for undergraduate mathematics.",
    version=VERSION,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    # The <title> carries the name from site.json, so it is right before any
    # script runs (and for whatever reads the page without running them).
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(NAME)} · {escape(TAGLINE)}</title>", html, count=1)
    return HTMLResponse(html)


@app.get("/api/site")
def site() -> dict[str, Any]:
    return {**SITE, "version": VERSION}


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
    # The checking level this entry's verdict holds at, when not the pack's.
    level: Optional[Literal["off", "exam", "course", "scratch"]] = None
    source: str


class LibraryChapterModel(BaseModel):
    id: str
    title: str


class LibraryPackModel(BaseModel):
    """A pack in format 1 (see ``aether.packs``)."""

    format: int
    name: str
    version: str
    title: str
    courses: list[str]
    summary: str
    authors: list[str]
    license: str
    engine: str
    depends: dict[str, str]
    # The checking level its verdicts hold at (aether.packs.entry_level); absent is off.
    level: Optional[Literal["off", "exam", "course", "scratch"]] = None
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
                "id": "file-" + re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-"),
                "chapter": "files",
                "ref": path.name,
                "title": path.stem.replace("_", " ").capitalize(),
                "kind": "proof",
                "expected": EXAMPLE_FILE_VERDICTS.get(path.name, "VALID"),
                "source": path.read_text(encoding="utf-8"),
            }
        )
    pack, errors = validate_pack(
        {
            "format": PACK_FORMAT,
            "name": "core/examples",
            "version": VERSION,
            "title": "Worked examples",
            "summary": "Short proofs that show each part of the language, including deliberate failures.",
            "license": "Apache-2.0",
            "chapters": [
                {"id": "bundled", "title": "The language, by example"},
                {"id": "files", "title": "Standalone proofs"},
            ],
            "entries": entries,
        }
    )
    assert pack is not None, errors
    return pack


@app.get("/api/library", response_model=list[LibraryPackModel], response_model_exclude_none=True)
def library() -> list[dict[str, Any]]:
    """The bundled catalogue: the examples, then every pack in courses/.

    Read fresh on each request, so a new pack file shows up without a restart.
    The browser installs these into its own pack store; this list is what
    "Browse" and "Updates" compare against.
    """
    return [_examples_pack(), *load_packs(COURSES_DIR)]


class PackValidateRequest(BaseModel):
    pack: Any = Field(description="The parsed contents of a .pack.json file.")


class PackValidateResponse(BaseModel):
    pack: Optional[LibraryPackModel] = None
    errors: list[str] = Field(default_factory=list)


@app.post("/api/packs/validate", response_model=PackValidateResponse, response_model_exclude_none=True)
def validate_pack_file(request: PackValidateRequest) -> PackValidateResponse:
    """Check a pack someone wants to install, naming every problem by where it is."""
    pack, errors = validate_pack(request.pack)
    return PackValidateResponse(pack=pack, errors=errors)


@app.get("/api/capabilities")
def capabilities() -> list[dict[str, str]]:
    """The capability matrix the Guide publishes: the pins in verify_capabilities.

    Served as metadata only -- nothing is checked on request.  The pins are
    re-verified by `ui/verify_capabilities.py`, so what the Guide shows is
    exactly what that gate holds the engine to.
    """
    from .verify_capabilities import PROBES

    return [
        {
            "area": probe.area,
            "name": probe.name,
            "source": probe.source,
            "expect": probe.expect,
            "note": probe.gap or probe.guard or probe.why,
            "kind": "gap" if probe.gap else "guard" if probe.guard else "why" if probe.why else "",
        }
        for probe in PROBES
    ]


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
                "show_working": request.show_working,
                "audit": request.audit,
                "kernel": request.kernel,
                "files": request.files,
                "citations": request.citations,
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


class LeanExportRequest(BaseModel):
    source: str = ""
    # As for /api/check: the workspace, so imports and citations resolve.
    files: Optional[dict[str, str]] = None
    path: Optional[str] = None
    citations: Optional[dict[str, Any]] = None


class LeanRowModel(BaseModel):
    # The source line these Lean lines came from; None for Lean's own scaffolding.
    line: Optional[int] = None
    source: str = ""
    lean_from: int
    lean_to: int
    # The source line's verdict (VALID, WARNING, INVALID), when it has one.
    status: Optional[str] = None


class LeanUntranslatedModel(BaseModel):
    line: Optional[int] = None
    what: str


class LeanExportResponse(BaseModel):
    lean: str = ""
    rows: list[LeanRowModel] = []
    untranslated: list[LeanUntranslatedModel] = []
    error: Optional[str] = None


@app.post("/api/export/lean", response_model=LeanExportResponse)
def export_lean(request: LeanExportRequest) -> LeanExportResponse:
    """The proof as a Lean 4 + Mathlib skeleton, lined up with its source lines."""
    try:
        result = pool().run(
            "lean",
            {"source": request.source, "files": request.files, "path": request.path, "citations": request.citations},
        )
        return LeanExportResponse(**result)
    except CheckTimeout as exc:
        return LeanExportResponse(error=f"checking the proof for the export stopped after {exc.budget:g} s")
    except Exception as exc:
        return LeanExportResponse(error=str(exc))


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

