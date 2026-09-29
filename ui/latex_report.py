"""LaTeX export for the UI: the proof, plus the audit behind it.

The engine's own exporter (``aether.export_to_latex``) typesets a proof and
nothing else -- it is handed source text and never sees a verification result.
Everything the Auditor and Context & State panes show therefore has to be added
here, in the UI layer, instead of by reaching into ``aether.core``.  That keeps
the engine's public API and its tests untouched, and it puts the audit where it
belongs: the engine proves, the UI reports.

The generated document is:

    1. the proof                    -- from ``aether.export_to_latex``, unchanged
    2. Verification Report          -- the verdict, then the per-statement audit
    3. Proof State                  -- what was in scope at each statement
    4. Session                      -- workspace timeline and snapshots
    5. Original Proof Source        -- the Aether source, verbatim

Sections 2-5 are skipped when ``breakdown=False``, which reproduces exactly
what the engine's exporter produced before this module existed.

Every value that comes from the source or from a checker message is escaped,
because a proof is arbitrary text and LaTeX treats ``^``, ``_``, ``&`` and
friends as syntax: an unescaped ``n^2`` in a table cell is a compile error, not
a typo.  The one place escaping is deliberately *not* used is the source
listing, which is verbatim by definition.

The document needs a TeX installation with the usual LaTeX packages
(``booktabs``, ``longtable``, ``array``, ``xcolor``, ``tcolorbox``,
``titlesec``, ``fancyhdr``); all of them ship with TeX Live and MiKTeX.
"""

from __future__ import annotations

import datetime as _datetime
import re
import time
from typing import Any, Iterable, Mapping, Optional, Sequence

from aether import ProofChecker, export_to_latex

# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

# One pass, via a regex, rather than a chain of str.replace calls: replacing
# "\\" first and "{" second would go on to escape the braces in the
# replacement text of the backslash itself.
_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
}

_ESCAPE_RE = re.compile(r"[\\&%$#_{}~^<>|]")

# Tabular cells cannot contain a newline, and checker messages do sometimes
# carry one.
_WHITESPACE_RE = re.compile(r"\s+")


def _escape(text: Any) -> str:
    """Escape LaTeX's special characters in arbitrary text."""
    flat = _WHITESPACE_RE.sub(" ", str(text if text is not None else "")).strip()
    return _ESCAPE_RE.sub(lambda match: _LATEX_ESCAPES[match.group()], flat)


def _status(value: Any) -> str:
    """``StepStatus.VALID`` and ``"VALID"`` both become ``"VALID"``."""
    return str(getattr(value, "value", value))


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------

_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage{amsmath,amssymb,amsthm}
\usepackage[margin=1in]{geometry}
\usepackage{microtype}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage{xcolor}

% The document is near-monochrome on purpose, like the interface: ink for the
% maths, muted grey for provenance, and colour only where something went wrong.
\definecolor{aeInk}{HTML}{1A1D21}
\definecolor{aeMuted}{HTML}{6B7280}
\definecolor{aeRule}{HTML}{D5DAE0}
\definecolor{aeAccent}{HTML}{0A5FBF}
\definecolor{aeWarning}{HTML}{8A5A00}
\definecolor{aeInvalid}{HTML}{B3261E}

\color{aeInk}

\newcolumntype{S}{>{\ttfamily\small}p{0.46\textwidth}}
\newcolumntype{V}{>{\small}p{0.30\textwidth}}
\newcolumntype{H}{>{\small}p{0.46\textwidth}}

% Each report section opens on a new page under a hairline, which is the same
% device the auditor uses to separate statements from their explanations.
\newcommand{\aesection}[1]{%
  \clearpage
  \section*{\normalfont\large\bfseries #1}%
  \vspace{-0.9em}\noindent\textcolor{aeRule}{\rule{\textwidth}{0.6pt}}%
  \par\vspace{0.9em}%
}

\newcommand{\aelabel}[1]{\textcolor{aeMuted}{\textsf{\footnotesize #1}}}

\theoremstyle{definition}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}
\newtheorem{definition}{Definition}
"""


# ---------------------------------------------------------------------------
# The fancy style
# ---------------------------------------------------------------------------
#
# A second presentation of the same material, used for the PDF.  The plain
# style is what the .tex export and the CLI have always produced; this one is
# a printed twin of the Proof Intern UI: journal maths, gallery air, auditor
# density.  Palette and status language match ``ui/static/styles.css`` (light).

_FANCY_PREAMBLE = r"""% NOTE ON FONTS: only the base Computer Modern / EC set is assumed here.
% The site uses JetBrains Mono; under pdflatex we approximate that voice with
% CM Typewriter for every structural mark (brand, verdict, statements, source)
% and CM Roman for mathematics and prose.  EC has no bold-extended sans below
% 8pt, so bold labels stay at 8pt or larger.
\documentclass[10pt]{article}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
% Asymmetric margins: gallery air on the left, denser reading on the right.
\usepackage[left=1.35in,right=0.85in,top=0.85in,bottom=0.95in,headsep=12pt]{geometry}
\usepackage[protrusion=true,expansion=false]{microtype}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage{needspace}
\usepackage[table]{xcolor}
\usepackage{tcolorbox}
\tcbuselibrary{skins,breakable}
\usepackage{fancyhdr}
\usepackage{setspace}

% Site light-theme tokens (styles.css).
\definecolor{aeInk}{HTML}{16181D}
\definecolor{aeMuted}{HTML}{646B78}
\definecolor{aeMutedDim}{HTML}{9AA1AC}
\definecolor{aeRule}{HTML}{DDE1E6}
\definecolor{aeHair}{HTML}{E8EBEE}
\definecolor{aePanel}{HTML}{F7F8F9}
\definecolor{aePanel2}{HTML}{EFF1F4}
\definecolor{aeAccent}{HTML}{0A5FBF}
\definecolor{aeWash}{HTML}{E8F1FA}
\definecolor{aeGreen}{HTML}{157333}
\definecolor{aeAmber}{HTML}{7D4E00}
\definecolor{aeRed}{HTML}{BE1824}
\definecolor{aeGreenBg}{HTML}{E8F3EB}
\definecolor{aeAmberBg}{HTML}{F5EFE3}
\definecolor{aeRedBg}{HTML}{F8E9EA}

\color{aeInk}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.35em}
\setstretch{1.12}

% Section openers are mono labels over a hairline -- like pane heads, not
% chapter titles.  No forced page break: density from flowing content, air
% from the asymmetric margin and the gaps we choose.
\newcommand{\aesection}[1]{%
  \needspace{6\baselineskip}%
  \vspace{1.6em}%
  \markboth{#1}{}%
  \noindent{\ttfamily\fontsize{8}{10}\selectfont\bfseries\color{aeInk}\MakeUppercase{#1}}\\[-0.15em]%
  {\color{aeRule}\rule{\textwidth}{0.4pt}}\par\vspace{0.7em}%
}
\newcommand{\aepage}{\clearpage}

\newcommand{\aekey}[1]{\ttfamily\fontsize{8}{10}\selectfont\color{aeAccent}#1}
\newcommand{\aevalue}[1]{\ttfamily\fontsize{8}{10}\selectfont\color{aeInk}#1}
\newcommand{\aehead}[1]{\ttfamily\fontsize{8}{9.5}\selectfont\bfseries\color{aeMuted}#1}

% Running head: brand left, section right -- the site topbar, quiet.
\newcommand{\aerunningtitle}{Aether}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.35pt}
\renewcommand{\footrulewidth}{0pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{aeHair}\leaders\hrule height \headrulewidth\hfill}}
\fancyhead[L]{\ttfamily\fontsize{8}{9.5}\selectfont\bfseries\color{aeInk}\aerunningtitle%
  \hspace{0.55em}{\fontsize{7.5}{9}\selectfont\mdseries\color{aeMutedDim}Proof intern}}
\fancyhead[R]{\ttfamily\fontsize{7.5}{9}\selectfont\color{aeMuted}\nouppercase{\leftmark}}
\fancyfoot[L]{\ttfamily\fontsize{7.5}{9}\selectfont\color{aeMutedDim}Generated by Aether}
\fancyfoot[R]{\ttfamily\fontsize{7.5}{9}\selectfont\color{aeAccent}\thepage}

% Verdict: a rail and a word -- .verdict in styles.css.
\newcommand{\aeverdict}[2]{%
  {\color{#1}\rule{1.5pt}{2.6ex}\hspace{2.2mm}%
   \ttfamily\fontsize{9}{11}\selectfont\bfseries\color{#1}\MakeUppercase{#2}}%
}

% Auditor step: continuous left rail, hairline underside -- .step in styles.css.
\newtcolorbox{aestep}[1]{%
  enhanced, breakable, sharp corners,
  boxrule=0pt, bottomrule=0.35pt,
  colframe=aeRule, colback=white,
  borderline west={1.5pt}{0pt}{#1},
  left=3.2mm, right=2mm, top=2.1mm, bottom=2.1mm,
  before skip=0pt, after skip=0pt}

\newtcolorbox{aenote}[1]{%
  enhanced, breakable, sharp corners, boxrule=0pt,
  colback=#1, colframe=#1,
  left=2.4mm, right=2.4mm, top=1.6mm, bottom=1.6mm,
  before skip=1.4mm, after skip=0pt}

\newtcolorbox{aecode}{%
  enhanced, breakable, sharp corners, boxrule=0pt, leftrule=1.5pt,
  colframe=aeAccent, colback=aePanel,
  left=3mm, right=2.5mm, top=2.2mm, bottom=2.2mm, before skip=0.6em}

% Theorems: journal, ink, no chrome.
\newtheoremstyle{aether}%
  {1.1em}{0.4em}%
  {}%
  {}%
  {\ttfamily\bfseries\color{aeInk}}%
  {.}%
  {0.5em}%
  {}
\theoremstyle{aether}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}
\newtheorem{definition}{Definition}

\renewcommand{\qedsymbol}{\textcolor{aeAccent}{\rule{1.8mm}{1.8mm}}}
\renewcommand{\proofname}{\ttfamily\bfseries\color{aeInk}Proof}
"""


def _fancy_verbatim(source: str) -> str:
    """Source listing on a pale panel with an accent rail -- the editor twin."""
    if "\\end{verbatim}" not in source:
        body = "\\begin{verbatim}\n" + source.rstrip("\n") + "\n\\end{verbatim}"
    else:
        body = _verbatim(source)
    return (
        r"\begin{aecode}\ttfamily\footnotesize\color{aeInk}" + "\n"
        + body
        + "\n\\end{aecode}"
    )



def _verbatim(source: str) -> str:
    """The source listing.

    ``verbatim`` is the right environment -- it preserves the indentation the
    grammar depends on and needs no escaping -- but it ends at the first
    ``\\end{verbatim}`` wherever that appears.  Aether source will never contain
    one, so rather than mangle the content to guard against it, the listing
    falls back to an escaped fixed-width block in that case.
    """
    if "\\end{verbatim}" not in source:
        return "\\begin{verbatim}\n" + source.rstrip("\n") + "\n\\end{verbatim}"

    lines = "\\\\\n".join(
        "\\mbox{\\ttfamily\\small " + (_escape(line) or "\\mbox{}") + "}" for line in source.splitlines()
    )
    return "{\\parindent0pt\\linespread{1.0}\\selectfont\n" + lines + "\n\\par}"


def _verdict_text(verdict: str) -> str:
    colour = {
        "INVALID": "aeInvalid",
        "VALID (with domain warnings)": "aeWarning",
    }.get(verdict)
    return f"\\textcolor{{{colour}}}{{{_escape(verdict)}}}" if colour else f"\\textbf{{{_escape(verdict)}}}"


def _status_text(status: str) -> str:
    colour = {"INVALID": "aeInvalid", "WARNING": "aeWarning"}.get(status)
    return f"\\textcolor{{{colour}}}{{\\textsf{{{_escape(status)}}}}}" if colour else f"\\textsf{{{_escape(status)}}}"


def _summary_table(verdict: str, results: Sequence[Any], strict_domains: bool, duration_ms: Optional[float]) -> str:
    valid = sum(1 for r in results if _status(r.status) == "VALID")
    warnings = sum(1 for r in results if _status(r.status) == "WARNING")
    invalid = sum(1 for r in results if _status(r.status) == "INVALID")

    rows = [
        ("Verdict", _verdict_text(verdict)),
        (
            "Statements",
            f"{len(results)} total --- {valid} valid, {warnings} warning"
            f"{'' if warnings == 1 else 's'}, {invalid} invalid",
        ),
        ("Domain checking", "strict" if strict_domains else "lenient"),
    ]
    if duration_ms is not None:
        rows.append(("Verified in", f"{duration_ms:.0f}\\,ms"))

    body = " \\\\\n".join(
        f"\\aelabel{{{_escape(label)}}} & {value}" for label, value in rows
    )
    return "\\noindent\n\\begin{tabular}{@{}l@{\\hspace{2em}}l@{}}\n\\toprule\n" + body + " \\\\\n\\bottomrule\n\\end{tabular}"


def _audit_table(reports: Sequence[Sequence[Any]]) -> str:
    header = (
        "\\textbf{Line} & \\textbf{Status} & \\textbf{Backend} & \\textbf{Statement} \\\\"
    )
    rows: list[str] = []
    for results in reports:
        for result in results:
            line = result.line if result.line is not None else "--"
            rows.append(
                f"{_escape(line)} & {_status_text(_status(result.status))} & "
                f"\\aelabel{{{_escape(result.backend)}}} & {_escape(result.statement)} \\\\"
            )

    if not rows:
        return "\\emph{Nothing was audited.}"

    return (
        "\\begin{longtable}{@{}r l l S@{}}\n"
        "\\toprule\n" + header + "\n\\midrule\n\\endfirsthead\n"
        "\\toprule\n" + header + "\n\\midrule\n\\endhead\n"
        "\\midrule\n\\multicolumn{4}{r}{\\aelabel{continued on the next page}} \\\\\n\\endfoot\n"
        "\\bottomrule\n\\endlastfoot\n"
        + "\n".join(rows)
        + "\n\\end{longtable}"
    )


def _notes_list(results: Sequence[Any]) -> str:
    """Only the statements that had something to say.

    A clean proof produces no entries at all: eight rows of "verified" would
    bury the one that actually failed.
    """
    items: list[str] = []
    for result in results:
        body: list[str] = []
        if result.message:
            body.append(_escape(result.message))
        if result.counterexample:
            body.append(f"\\textcolor{{aeInvalid}}{{{_escape(result.counterexample)}}}")
        for warning in result.domain_warnings:
            body.append(f"\\textcolor{{aeWarning}}{{{_escape(warning)}}}")

        # A failing obligation is reported as both the message and a warning,
        # and they are the same sentence; print it once.
        seen: list[str] = []
        for entry in body:
            if entry not in seen:
                seen.append(entry)
        if not seen:
            continue

        location = f"L{result.line}" if result.line is not None else "unplaced"
        items.append(
            f"\\item[{_escape(location)}] " + " \\par ".join(seen)
        )

    if not items:
        return "\\emph{Every statement verified without comment.}"

    return (
        "\\begin{description}[leftmargin=3.4em,style=nextline,itemsep=0.5em]\n"
        + "\n".join(items)
        + "\n\\end{description}"
    )


def _state_table(results: Sequence[Any]) -> str:
    header = (
        "\\textbf{Line} & \\textbf{Depth} & \\textbf{In scope} & "
        "\\textbf{Assumptions and derived facts} \\\\"
    )
    rows: list[str] = []
    for result in results:
        line = result.line if result.line is not None else "--"

        variables = getattr(result, "active_variables", None) or {}
        in_scope = ", ".join(
            f"{_escape(name)} : {_escape(type_name)}" for name, type_name in variables.items()
        ) or "\\aelabel{none}"

        hypotheses = getattr(result, "active_hypotheses", None) or []
        facts = " \\par ".join(_escape(item) for item in hypotheses) or "\\aelabel{none}"

        rows.append(
            f"{_escape(line)} & {_escape(getattr(result, 'scope_depth', 0))} & "
            f"\\ttfamily\\small {in_scope} & {facts} \\\\"
        )

    if not rows:
        return "\\emph{No statements to describe.}"

    return (
        "\\begin{longtable}{@{}r r V H@{}}\n"
        "\\toprule\n" + header + "\n\\midrule\n\\endfirsthead\n"
        "\\toprule\n" + header + "\n\\midrule\n\\endhead\n"
        "\\midrule\n\\multicolumn{4}{r}{\\aelabel{continued on the next page}} \\\\\n\\endfoot\n"
        "\\bottomrule\n\\endlastfoot\n"
        + "\n".join(rows)
        + "\n\\end{longtable}"
    )


def _clean_verdict(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _clock(timestamp_ms: Any) -> str:
    try:
        stamp = _datetime.datetime.fromtimestamp(float(timestamp_ms) / 1000.0)
    except (TypeError, ValueError, OSError, OverflowError):
        return "--"
    return stamp.strftime("%H:%M:%S")


def _session_section(session: Optional[Mapping[str, Any]]) -> str:
    """The workspace panel's contents: this session's verdicts and snapshots.

    These live in the browser's local storage, so the client has to send them.
    They are treated as untrusted text throughout -- everything is escaped, and
    nothing but a count, a verdict word and a clock is ever read out of them.
    """
    if not session:
        return ""

    timeline = session.get("timeline") or []
    snapshots = session.get("snapshots") or []

    parts: list[str] = []
    if timeline:
        rows = []
        for entry in timeline:
            if not isinstance(entry, Mapping):
                continue
            count = entry.get("n") or 1
            rows.append(
                f"{_escape(_clean_verdict(entry.get('verdict')) or 'unknown')} & "
                f"{_escape(count)} & {_escape(_clock(entry.get('ts')))} \\\\"
            )
        if rows:
            parts.append(
                "\\noindent\\textbf{Checks this session}\n\n"
                "\\begin{longtable}{@{}l r l@{}}\n"
                "\\toprule\n\\textbf{Verdict} & \\textbf{Runs} & \\textbf{Last at} \\\\\n\\midrule\n"
                "\\endfirsthead\n"
                "\\toprule\n\\textbf{Verdict} & \\textbf{Runs} & \\textbf{Last at} \\\\\n\\midrule\n\\endhead\n"
                "\\bottomrule\n\\endlastfoot\n"
                + "\n".join(rows)
                + "\n\\end{longtable}"
            )

    if snapshots:
        rows = []
        for snapshot in snapshots:
            if not isinstance(snapshot, Mapping):
                continue
            flavour = "automatic" if snapshot.get("auto") else "manual"
            if snapshot.get("strict"):
                flavour += ", strict"
            rows.append(
                f"{_escape(snapshot.get('name') or 'snapshot')} & "
                f"{_escape(_clock(snapshot.get('ts')))} & \\aelabel{{{flavour}}} \\\\"
            )
        if rows:
            parts.append(
                "\\noindent\\textbf{Saved snapshots}\n\n"
                "\\begin{longtable}{@{}l l l@{}}\n"
                "\\toprule\n\\textbf{Name} & \\textbf{Taken at} & \\textbf{Kind} \\\\\n\\midrule\n"
                "\\endfirsthead\n"
                "\\toprule\n\\textbf{Name} & \\textbf{Taken at} & \\textbf{Kind} \\\\\n\\midrule\n\\endhead\n"
                "\\bottomrule\n\\endlastfoot\n"
                + "\n".join(rows)
                + "\n\\end{longtable}"
            )

    if not parts:
        return ""
    return "\\aesection{Session}\n\n" + "\n\n\\medskip\n\n".join(parts)


# ---------------------------------------------------------------------------
# Fancy builders
# ---------------------------------------------------------------------------

# Site status language: valid is quiet (muted); warning/invalid carry colour.
# Rails match .step::before -- transparent/hairline for valid, coloured for breaks.
_RAIL = {"VALID": "aeRule", "WARNING": "aeAmber", "INVALID": "aeRed"}
_STATUS_TONE = {"VALID": "aeMutedDim", "WARNING": "aeAmber", "INVALID": "aeRed"}
_VERDICT_TONE = {
    "VALID": "aeGreen",
    "INVALID": "aeRed",
    "VALID (with domain warnings)": "aeAmber",
}
_NOTE_BG = {"WARNING": "aeAmberBg", "INVALID": "aeRedBg"}


def _fancy_counts(results: Sequence[Any]) -> tuple[int, int, int]:
    valid = sum(1 for r in results if _status(r.status) == "VALID")
    warnings = sum(1 for r in results if _status(r.status) == "WARNING")
    invalid = sum(1 for r in results if _status(r.status) == "INVALID")
    return valid, warnings, invalid


def _fancy_opening(
    *,
    title: Optional[str],
    verdict: str,
    results: Sequence[Any],
    strict_domains: bool,
    duration_ms: float,
    source: str,
) -> str:
    """Topbar + title plate: brand, rail-verdict, theorem hero, tight meta.

    Flows straight into the proof on the same page -- dense and airy, like the
    UI where the topbar never claims a whole viewport.
    """
    valid, warnings, invalid = _fancy_counts(results)
    tone = _VERDICT_TONE.get(verdict, "aeGreen")
    total = len(results)
    display_title = _escape(title) if title else "Top-level scratchpad"

    meta = " \\textperiodcentered{} ".join(
        [
            "strict" if strict_domains else "lenient",
            f"{total} statement{'' if total == 1 else 's'}",
            f"{valid} valid",
            f"{warnings} warning{'' if warnings == 1 else 's'}",
            f"{invalid} invalid",
            f"{duration_ms:.0f}\\,ms",
            f"{len(source.splitlines())} lines",
            _datetime.datetime.now().strftime("%d %b %Y"),
        ]
    )

    return (
        "\\thispagestyle{empty}\n"
        "\\vspace*{2mm}\n"
        # Topbar row: brand left, verdict right.
        "\\noindent\\begin{minipage}[b]{0.52\\textwidth}\n"
        "{\\ttfamily\\fontsize{9}{11}\\selectfont\\bfseries\\color{aeInk}AETHER}"
        "\\hspace{0.6em}"
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}Proof intern}\n"
        "\\end{minipage}\\hfill"
        "\\begin{minipage}[b]{0.46\\textwidth}\\raggedleft\n"
        "\\aeverdict{%s}{%s}\\par\\vspace{0.6mm}\n"
        "{\\ttfamily\\fontsize{7.5}{9}\\selectfont\\color{aeMutedDim}%s}\n"
        "\\end{minipage}\\par\n"
        "\\vspace{3.2mm}\n"
        "{\\color{aeRule}\\rule{\\textwidth}{0.4pt}}\\par\n"
        "\\vspace{7mm}\n"
        # Theorem as the hero -- gallery label over journal title.
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeAccent}THEOREM}\\par\\vspace{1.5mm}\n"
        "{\\fontsize{22}{26}\\selectfont\\bfseries\\color{aeInk}%s}\\par\n"
        "\\vspace{5mm}\n"
        "{\\color{aeAccent}\\rule{12mm}{1.3pt}}\\par\n"
        "\\vspace{4mm}\n"
        "{\\ttfamily\\fontsize{7.5}{9.5}\\selectfont\\color{aeMuted}%s}\\par\n"
        "\\vspace{6mm}\n"
        "{\\color{aeHair}\\rule{\\textwidth}{0.35pt}}\\par\n"
        % (
            tone,
            _escape(verdict),
            f"{total} statements \\textperiodcentered{{}} {duration_ms:.0f}\\,ms",
            display_title,
            meta,
        )
    )


def _dedup(items: Iterable[str]) -> list[str]:
    """Drop exact repeats, keeping order.

    A failing obligation arrives as the message *and* as a warning, and they
    are the same sentence; so does an algebraic failure, whose message ends
    with the same counterexample the note shows.
    """
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _fancy_step(result: Any) -> str:
    """One auditor row: rail, line, statement, status/backend, optional notes."""
    status = _status(result.status)
    rail = _RAIL.get(status, "aeRule")
    tone = _STATUS_TONE.get(status, "aeMutedDim")
    line = result.line if result.line is not None else "--"
    weight = "\\bfseries" if status in ("WARNING", "INVALID") else "\\mdseries"

    head = (
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}%s}"
        "\\hfill"
        "{\\ttfamily\\fontsize{7.5}{9}\\selectfont%s\\color{%s}%s}"
        "{\\ttfamily\\fontsize{7.5}{9}\\selectfont\\color{aeMutedDim}"
        "\\hspace{0.4em}\\textperiodcentered{}\\hspace{0.4em}%s}\\par\\vspace{0.9mm}\n"
        "{\\ttfamily\\fontsize{9}{11.5}\\selectfont\\color{aeInk}%s}\\par"
        % (
            _escape(line),
            weight,
            tone,
            _escape(status),
            _escape(result.backend),
            _escape(result.statement),
        )
    )

    notes: list[str] = []
    if result.message:
        notes.append(_escape(result.message))
    if result.counterexample:
        notes.append(
            "{\\color{aeRed}%s}" % _escape(result.counterexample)
        )
    for warning in result.domain_warnings:
        notes.append("{\\color{aeAmber}%s}" % _escape(warning))
    notes = _dedup(notes)

    body = head
    if notes:
        if status in ("WARNING", "INVALID") or result.counterexample or result.domain_warnings:
            bg = _NOTE_BG.get(status, "aeAmberBg")
            if result.counterexample or status == "INVALID":
                bg = "aeRedBg"
            body += (
                "\n\\begin{aenote}{%s}\n"
                "{\\fontsize{8.5}{11}\\selectfont\\color{aeMuted}%s}\n"
                "\\end{aenote}"
                % (bg, " \\par ".join(notes))
            )
        else:
            body += (
                "\n\\vspace{1mm}\n"
                "{\\fontsize{8.5}{11}\\selectfont\\color{aeMuted}%s}"
                % (" \\par ".join(notes))
            )

    return "\\begin{aestep}{%s}\n%s\n\\end{aestep}" % (rail, body)


def _fancy_auditor(results: Sequence[Any]) -> str:
    """Vertical step list -- the site auditor, not a spreadsheet."""
    if not results:
        return "{\\ttfamily\\fontsize{8.5}{11}\\selectfont\\color{aeMuted}Nothing was audited.}"
    return "\n".join(_fancy_step(result) for result in results)


def _fancy_state(results: Sequence[Any]) -> str:
    """Compact per-line scope cards under hairlines."""
    if not results:
        return "{\\ttfamily\\fontsize{8.5}{11}\\selectfont\\color{aeMuted}No statements to describe.}"

    blocks: list[str] = []
    for result in results:
        line = result.line if result.line is not None else "--"
        depth = getattr(result, "scope_depth", 0)
        variables = getattr(result, "active_variables", None) or {}
        in_scope = ", ".join(
            f"{_escape(name)}:{_escape(type_name)}" for name, type_name in variables.items()
        ) or "{\\color{aeMutedDim}none}"
        hypotheses = getattr(result, "active_hypotheses", None) or []
        facts = " \\textperiodcentered{} ".join(_escape(item) for item in hypotheses) or (
            "{\\color{aeMutedDim}none}"
        )
        blocks.append(
            "\\noindent{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeAccent}L%s}"
            "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}"
            "\\hspace{0.7em}depth\\,%s}\\par\\vspace{0.6mm}\n"
            "{\\ttfamily\\fontsize{8}{10.5}\\selectfont\\color{aeInk}%s}\\par\\vspace{0.4mm}\n"
            "{\\fontsize{8}{10.5}\\selectfont\\color{aeMuted}%s}\\par\n"
            "\\vspace{1.2mm}{\\color{aeHair}\\rule{\\textwidth}{0.3pt}}\\par\\vspace{1.2mm}"
            % (_escape(line), _escape(depth), in_scope, facts)
        )
    return "\n".join(blocks)


def _fancy_session(session: Optional[Mapping[str, Any]]) -> str:
    """Session timeline and snapshots as compact mono ledgers."""
    if not session:
        return ""

    parts: list[str] = []
    timeline = session.get("timeline") or []
    if timeline:
        rows = []
        for entry in timeline:
            if not isinstance(entry, Mapping):
                continue
            rows.append(
                "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeAccent}%s}"
                "\\hspace{1em}%s\\hspace{1em}%s \\\\"
                % (
                    _escape(_clock(entry.get("ts"))),
                    _escape(entry.get("n") or 1),
                    _escape(_clean_verdict(entry.get("verdict")) or "unknown"),
                )
            )
        if rows:
            parts.append(
                "{\\ttfamily\\fontsize{8}{10}\\selectfont\\bfseries\\color{aeMuted}CHECKS}\\par\\vspace{1mm}\n"
                + "\n".join(rows)
            )

    snapshots = session.get("snapshots") or []
    if snapshots:
        rows = []
        for snapshot in snapshots:
            if not isinstance(snapshot, Mapping):
                continue
            flavour = "automatic" if snapshot.get("auto") else "manual"
            if snapshot.get("strict"):
                flavour += ", strict"
            rows.append(
                "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeInk}%s}"
                "\\hspace{1em}{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeAccent}%s}"
                "\\hspace{1em}{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}%s} \\\\"
                % (
                    _escape(snapshot.get("name") or "snapshot"),
                    _escape(_clock(snapshot.get("ts"))),
                    _escape(flavour),
                )
            )
        if rows:
            parts.append(
                "{\\ttfamily\\fontsize{8}{10}\\selectfont\\bfseries\\color{aeMuted}SNAPSHOTS}\\par\\vspace{1mm}\n"
                + "\n".join(rows)
            )

    if not parts:
        return ""
    return "\\aesection{Session}\n\n" + "\n\n\\vspace{2mm}\n\n".join(parts)


def _fancy_about() -> str:
    """Short closing legend -- back matter, not a second deck."""
    rows = [
        ("Audit", "One row per statement, in the same language as the on-screen auditor."),
        ("Rails", "A coloured margin marks a break: amber for an unresolved obligation, red for a step that does not hold. Valid steps stay quiet."),
        ("Backends", "SymPy rewrites; Z3 inequalities, quantifiers and witnesses; Context declarations; ChainGuard and ScopeGuard catch monotonicity, capture and generalisation errors before any solver runs."),
        ("Domains", "Division needs a non-zero denominator; square roots a non-negative radicand. Lenient mode warns; strict mode errors."),
    ]
    body = "\n\n".join(
        "\\noindent{\\ttfamily\\fontsize{8}{10}\\selectfont\\bfseries\\color{aeAccent}%s}\\par\\vspace{0.4mm}\n"
        "{\\fontsize{8.5}{11}\\selectfont\\color{aeMuted}%s}"
        % (_escape(label), text)
        for label, text in rows
    )
    return "\\aesection{About}\n\n" + body


def _overall_verdict(reports: Iterable[Any]) -> str:
    reports = list(reports)
    if any(not report.is_valid for report in reports):
        return "INVALID"
    if any(report.has_warnings for report in reports):
        return "VALID (with domain warnings)"
    return "VALID"


def _fancy_document(
    *,
    body: str,
    source: str,
    reports: Sequence[Any],
    results: Sequence[Any],
    verdict: str,
    strict_domains: bool,
    duration_ms: float,
    session: Optional[Mapping[str, Any]],
) -> str:
    """Assemble the site-matched PDF: opening into proof, then auditor back matter."""
    title = next((report.theorem_name for report in reports if report.theorem_name), None)
    session_section = _fancy_session(session)

    opening = _fancy_opening(
        title=title,
        verdict=verdict,
        results=results,
        strict_domains=strict_domains,
        duration_ms=duration_ms,
        source=source,
    )

    # Proof continues on the opening page; auditor and back matter get air.
    proof = (
        "\\aesection{The Proof}\n\n"
        + body
    )

    auditor = (
        "\\aepage\n"
        "\\aesection{Auditor}\n\n"
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}"
        "Each statement as the intern saw it --- rail, line, verdict, backend.}\\par\\vspace{2mm}\n\n"
        + _fancy_auditor(results)
    )

    state = (
        "\\aesection{Proof State}\n\n"
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}"
        "What was in scope at each line.}\\par\\vspace{2mm}\n\n"
        + _fancy_state(results)
    )

    pieces = [opening, proof, auditor, state]
    if session_section:
        pieces.append(session_section)
    pieces.append(
        "\\aesection{Source}\n\n"
        "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}"
        "As written, before parsing.}\\par\\vspace{1.5mm}\n\n"
        + _fancy_verbatim(source)
    )
    pieces.append(_fancy_about())

    return (
        _FANCY_PREAMBLE
        + "\n\\begin{document}\n"
        + "\n\n".join(pieces)
        + "\n\n\\end{document}\n"
    )



def export_report_latex(
    source: str,
    *,
    strict_domains: bool = False,
    standalone: bool = True,
    breakdown: bool = True,
    session: Optional[Mapping[str, Any]] = None,
    style: str = "plain",
) -> str:
    """Render a proof to LaTeX, optionally followed by its verification report.

    ``style`` selects the presentation.  ``"plain"`` is the sober article the
    engine's own exporter has always produced -- what the .tex download and the
    CLI give you.  ``"fancy"`` is the designed PDF: a printed twin of the
    Proof Intern UI (journal proof, auditor step list, site palette).  Both
    contain exactly the same facts.

    Raises ``aether.ParseError`` if the source cannot be parsed, the same way
    the engine's exporter does.
    """
    if not breakdown:
        # Exactly the engine's own output; the report is purely additive.
        return export_to_latex(source, standalone=standalone)

    started = time.perf_counter()
    checker = ProofChecker(strict_domains=strict_domains)
    reports = checker.check_source(source)
    duration_ms = (time.perf_counter() - started) * 1000.0
    body = export_to_latex(source, standalone=False)

    results: list[Any] = [result for report in reports for result in report.results]
    verdict = _overall_verdict(reports)

    if not standalone:
        return body

    if style == "fancy":
        return _fancy_document(
            body=body,
            source=source,
            reports=reports,
            results=results,
            verdict=verdict,
            strict_domains=strict_domains,
            duration_ms=duration_ms,
            session=session,
        )

    sections = [
        "\\aesection{Verification Report}\n\n"
        + _summary_table(verdict, results, strict_domains, None)
        + "\n\n\\subsection*{Statement audit}\n\n"
        + _audit_table([report.results for report in reports])
        + "\n\n\\subsection*{Verification notes}\n\n"
        + _notes_list(results),
        "\\aesection{Proof State}\n\n"
        "\\noindent\\aelabel{What the intern knew at each statement --- declared "
        "variables, active hypotheses and derived facts, and the enclosing scope."
        "}\n\n\\medskip\n\n"
        + _state_table(results),
    ]

    session_section = _session_section(session)
    if session_section:
        sections.append(session_section)

    sections.append(
        "\\aesection{Original Proof Source}\n\n"
        "\\noindent\\aelabel{The document as it was written, before parsing.}\n\n\\medskip\n\n"
        + _verbatim(source)
    )

    title = next(
        (report.theorem_name for report in reports if report.theorem_name),
        None,
    )
    subtitle = (
        f"\\large {_escape(title)}\\\\[0.3em]\n" if title else ""
    )

    return (
        _PREAMBLE
        + "\n\\title{\\textbf{Aether Verified Proof Document}\\vspace{0.35em}\\\\"
        + subtitle
        + "\\normalsize\\textcolor{aeMuted}{Generated by Aether Proof Intern --- "
        + _datetime.datetime.now().strftime("%d %B %Y")
        + "}}\n"
        "\\author{}\n"
        "\\date{}\n\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        + body
        + "\n\n"
        + "\n\n".join(sections)
        + "\n\n\\end{document}\n"
    )
