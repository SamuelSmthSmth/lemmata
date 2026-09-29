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
(``booktabs``, ``longtable``, ``array``, ``xcolor``, ``fancyvrb``); all of them
ship with TeX Live and MiKTeX.
"""

from __future__ import annotations

import datetime as _datetime
import re
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
# Entry point
# ---------------------------------------------------------------------------


def _overall_verdict(reports: Iterable[Any]) -> str:
    reports = list(reports)
    if any(not report.is_valid for report in reports):
        return "INVALID"
    if any(report.has_warnings for report in reports):
        return "VALID (with domain warnings)"
    return "VALID"


def export_report_latex(
    source: str,
    *,
    strict_domains: bool = False,
    standalone: bool = True,
    breakdown: bool = True,
    session: Optional[Mapping[str, Any]] = None,
) -> str:
    """Render a proof to LaTeX, optionally followed by its verification report.

    Raises ``aether.ParseError`` if the source cannot be parsed, the same way
    the engine's exporter does.
    """
    if not breakdown:
        # Exactly the engine's own output; the report is purely additive.
        return export_to_latex(source, standalone=standalone)

    checker = ProofChecker(strict_domains=strict_domains)
    reports = checker.check_source(source)
    body = export_to_latex(source, standalone=False)

    results: list[Any] = [result for report in reports for result in report.results]
    verdict = _overall_verdict(reports)

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

    if not standalone:
        return body

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
