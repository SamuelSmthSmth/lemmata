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
    5. Original Proof Source        -- the proof source, verbatim

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

from .site import NAME as _SITE_NAME, TAGLINE as _SITE_TAGLINE

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
# the designed document: a full-bleed cover, a verdict at a glance, tinted
# findings, and then the proof and its audit trail.
#
# Palette and status language match ``ui/static/styles.css`` (light theme),
# with a light variant of each status colour for the navy cover, where the
# dark ones have no contrast at all.

_FANCY_PREAMBLE = r"""% NOTE ON FONTS: only the base Computer Modern / EC set is assumed here.
% The site uses JetBrains Mono; under pdflatex we approximate that voice with
% CM Typewriter for every structural mark (brand, verdict, statements, source)
% and CM Roman for mathematics and prose.  EC has no bold-extended sans below
% 8pt, so no bold label is set smaller than that.
\documentclass[10pt]{article}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
% Asymmetric margins: gallery air on the left, denser reading on the right.
\usepackage[left=1.3in,right=0.85in,top=0.9in,bottom=1.0in,headsep=14pt]{geometry}
\usepackage[protrusion=true,expansion=false]{microtype}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage{needspace}
\usepackage[table]{xcolor}
\usepackage{tcolorbox}
\tcbuselibrary{skins,breakable}
% Source listing: `verbatim` never breaks a line, so a long statement ran
% 180pt into the margin.  fvextra's Verbatim wraps instead, and marks the
% continuation with a hook.
\usepackage{fvextra}
\usepackage{fancyhdr}
\usepackage{setspace}
\usepackage{calc}
\usepackage{eso-pic}

% ---------------------------------------------------------------------------
% Palette.  Site light-theme tokens, plus a light variant of each status
% colour for the cover.
% ---------------------------------------------------------------------------
\definecolor{aeInk}{HTML}{16181D}
\definecolor{aeMuted}{HTML}{646B78}
\definecolor{aeMutedDim}{HTML}{9AA1AC}
\definecolor{aeRule}{HTML}{DDE1E6}
\definecolor{aeHair}{HTML}{E8EBEE}
\definecolor{aePanel}{HTML}{F7F8F9}
\definecolor{aePanel2}{HTML}{EFF1F4}
\definecolor{aeAccent}{HTML}{0A5FBF}
\definecolor{aeAccentLight}{HTML}{7CB7FF}
\definecolor{aeWash}{HTML}{E8F1FA}
\definecolor{aeGreen}{HTML}{157333}
\definecolor{aeAmber}{HTML}{7D4E00}
\definecolor{aeRed}{HTML}{BE1824}
\definecolor{aeGreenBg}{HTML}{E8F3EB}
\definecolor{aeAmberBg}{HTML}{F7F0E1}
\definecolor{aeRedBg}{HTML}{FAEBEC}
% Saturated versions, for rails, chips and callout edges.
\definecolor{aeGreenBar}{HTML}{2E9E5B}
\definecolor{aeAmberBar}{HTML}{C6862B}
\definecolor{aeRedBar}{HTML}{D2453C}
% The same three lifted for a dark ground.
\definecolor{aeGreenLight}{HTML}{86E0A0}
\definecolor{aeAmberLight}{HTML}{F2C169}
\definecolor{aeRedLight}{HTML}{FF9A90}
% The cover ground.
\definecolor{aeNavy}{HTML}{0C1A30}
\definecolor{aeNavyDeep}{HTML}{0A1526}
\definecolor{aeNavyLift}{HTML}{35558A}

\color{aeInk}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.35em}
\setstretch{1.12}

% ---------------------------------------------------------------------------
% Section openers: a numbered chip, the title, and a rule.  No forced page
% break -- density comes from flowing content, air from the asymmetric margin
% and the gaps chosen at each joint.
% ---------------------------------------------------------------------------
\newcommand{\aesection}[2]{%
  \needspace{7\baselineskip}%
  \par\vspace{2em}%
  \markboth{#2}{}%
  \noindent
  {\setlength{\fboxsep}{1.6mm}\colorbox{aeAccent}{%
    \ttfamily\fontsize{8}{10}\selectfont\bfseries\color{white}#1}}%
  \hspace{2.8mm}%
  {\ttfamily\fontsize{9.5}{12}\selectfont\bfseries\color{aeInk}\MakeUppercase{#2}}%
  \par\vspace{1.7mm}%
  {\color{aeRule}\rule{\textwidth}{0.5pt}}\par\vspace{1.2em}%
}
\newcommand{\aepage}{\clearpage}

% A line of explanatory prose under a section opener.
\newcommand{\aelede}[1]{{\fontsize{9}{12.5}\selectfont\color{aeMuted}#1}\par\vspace{2.4mm}}

% A stat card: one big figure over a caption, on a tinted panel.  Four of
% these sit side by side under the proof heading -- the "at a glance" strip.
\newcommand{\aecard}[4]{%
  {\setlength{\fboxsep}{2.7mm}%
   \colorbox{#1}{\parbox[t]{\dimexpr0.235\textwidth-5.4mm\relax}{%
     {\ttfamily\fontsize{19}{22}\selectfont\bfseries\color{#2}#3}\par
     \vspace{0.9mm}%
     {\ttfamily\fontsize{8}{10}\selectfont\color{aeMuted}\MakeUppercase{#4}}\par
     \vspace{0.4mm}}}}%
}

% Running head: brand left, section right -- the site topbar, quiet.
\newcommand{\aerunningtitle}{@@SITE_NAME@@}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.35pt}
\renewcommand{\footrulewidth}{0pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{aeHair}\leaders\hrule height \headrulewidth\hfill}}
\fancyhead[L]{\ttfamily\fontsize{8}{9.5}\selectfont\bfseries\color{aeInk}\aerunningtitle%
  \hspace{0.55em}{\fontsize{7.5}{9}\selectfont\mdseries\color{aeMutedDim}@@SITE_TAGLINE@@}}
\fancyhead[R]{\ttfamily\fontsize{7.5}{9}\selectfont\color{aeMuted}\nouppercase{\leftmark}}
\fancyfoot[L]{\ttfamily\fontsize{7.5}{9}\selectfont\color{aeMutedDim}Generated by @@SITE_NAME@@}
\fancyfoot[R]{\ttfamily\fontsize{8}{10}\selectfont\bfseries\color{aeAccent}\thepage}

% The cover: a full-bleed plate.  width/height are the paper itself, which is
% why the cover is emitted inside \newgeometry{margin=0pt}.
\tcbset{aecover/.style={%
  enhanced, sharp corners, boxrule=0pt, frame hidden,
  width=\paperwidth, height=\paperheight,
  left=26mm, right=26mm, top=0pt, bottom=0pt,
  interior style={left color=aeNavyDeep, right color=aeNavyLift, shading angle=28},
  colframe=aeNavy, colback=aeNavy, valign=center}}

% Verdict: a rail and a word -- .verdict in styles.css.
\newcommand{\aeverdict}[2]{%
  {\color{#1}\rule{1.5pt}{2.6ex}\hspace{2.2mm}%
   \ttfamily\fontsize{9}{11}\selectfont\bfseries\color{#1}\MakeUppercase{#2}}%
}

% Auditor step: continuous left rail, hairline underside -- .step in styles.css.
% The second argument is the row's wash, so a failure reads as a block rather
% than as one coloured word in a grey column.
\newtcolorbox{aestep}[2]{%
  enhanced, breakable, sharp corners,
  boxrule=0pt, bottomrule=0.35pt,
  colframe=aeRule, colback=#2,
  borderline west={2pt}{0pt}{#1},
  left=3.4mm, right=2.4mm, top=2.4mm, bottom=2.4mm,
  before skip=0pt, after skip=0pt}

% The status chip on an audit row.  Quiet for a valid step, saturated for the
% two that matter.
\newcommand{\aechip}[2]{%
  {\setlength{\fboxsep}{1.2mm}\colorbox{#1}{%
    \ttfamily\fontsize{8}{10}\selectfont\bfseries\color{white}#2}}%
}

\newtcolorbox{aenote}[1]{%
  enhanced, breakable, sharp corners, boxrule=0pt,
  colback=#1, colframe=#1,
  left=2.4mm, right=2.4mm, top=1.6mm, bottom=1.6mm,
  before skip=1.4mm, after skip=0pt}

% A finding: one statement that did not clear, with its evidence.
\newtcolorbox{aefinding}[1]{%
  enhanced, breakable, sharp corners, boxrule=0pt,
  colframe=#1, colback=white,
  borderline west={3pt}{0pt}{#1},
  left=4.4mm, right=3mm, top=3mm, bottom=3mm,
  before skip=3mm, after skip=0pt}

% The source panel, with an editor window's title bar.
\newtcolorbox{aecode}{%
  enhanced, breakable, sharp corners, boxrule=0pt, leftrule=1.5pt,
  colframe=aeAccent, colback=aePanel,
  left=3mm, right=2.5mm, top=2.4mm, bottom=2.4mm, before skip=0.6em}
\newcommand{\aecodebar}[1]{%
  {\fontsize{10}{10}\selectfont%
   \textcolor{aeRedBar}{\textbullet}\hspace{1.2mm}%
   \textcolor{aeAmberBar}{\textbullet}\hspace{1.2mm}%
   \textcolor{aeGreenBar}{\textbullet}}%
  \hspace{3.2mm}%
  {\ttfamily\fontsize{8}{10}\selectfont\color{aeMuted}#1}\par
  \vspace{1.4mm}%
  {\color{aeHair}\rule{\linewidth}{0.4pt}}\par\vspace{1.4mm}}

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


def _fancy_verbatim(source: str, name: str = "proof.aether") -> str:
    """Source listing as an editor window: title bar, then the buffer.

    The title bar goes *inside* the panel so the whole thing reads as one
    object -- the twin of the textarea on the site.  The buffer is a
    ``Verbatim`` (fvextra) rather than a plain ``verbatim``: a statement can be
    wider than the panel, and wrapping it with a continuation hook beats
    printing it across the margin.  tcolorbox scans the box body for verbatim
    environments and hands them through untouched.
    """
    if "\\end{Verbatim}" not in source:
        body = (
            "\\begin{Verbatim}[breaklines=true,breakanywhere=true,"
            "breaksymbolleft={\\tiny\\ensuremath{\\hookrightarrow}},breaksymbolsepleft=2pt,"
            "breakindent=6pt]\n"
            + source.rstrip("\n")
            + "\n\\end{Verbatim}"
        )
    else:
        body = _verbatim(source)
    return (
        "\\begin{aecode}\\ttfamily\\footnotesize\\color{aeInk}\n"
        "\\aecodebar{" + _escape(name) + "}"
        + "\n"
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
# Rails match .step::before -- hairline for valid, saturated for a break.
_RAIL = {"VALID": "aeRule", "WARNING": "aeAmberBar", "INVALID": "aeRedBar"}
_STATUS_TONE = {"VALID": "aeMutedDim", "WARNING": "aeAmber", "INVALID": "aeRed"}
_NOTE_BG = {"WARNING": "aeAmberBg", "INVALID": "aeRedBg"}


def _fancy_counts(results: Sequence[Any]) -> tuple[int, int, int]:
    valid = sum(1 for r in results if _status(r.status) == "VALID")
    warnings = sum(1 for r in results if _status(r.status) == "WARNING")
    invalid = sum(1 for r in results if _status(r.status) == "INVALID")
    return valid, warnings, invalid


# Status colours lifted for the navy cover, where the light-theme status inks
# have no contrast at all.
_COVER_TONE = {
    "VALID": "aeGreenLight",
    "INVALID": "aeRedLight",
    "VALID (with domain warnings)": "aeAmberLight",
}

# The wash behind an audit row, and the chip that labels it.  A valid step
# stays on white: it is the unremarkable case, and spending colour on it would
# leave nothing for the two rows that are actually telling you something.
_STEP_WASH = {"VALID": "white", "WARNING": "aeAmberBg", "INVALID": "aeRedBg"}
_FINDING_TONE = {"WARNING": "aeAmberBar", "INVALID": "aeRedBar"}


def _fancy_cover(
    *,
    title: Optional[str],
    verdict: str,
    results: Sequence[Any],
    strict_domains: bool,
    duration_ms: float,
    source: str,
) -> str:
    """The cover plate: full bleed, navy, one centred composition.

    Everything a reader needs before the proof is on this one page -- what was
    proved, how it came out, and how long it took.  The plate is the paper
    itself, which is why it is emitted inside ``\\newgeometry{margin=0pt}``
    with the margins restored straight afterwards.  The amber bar across the
    foot is drawn in the shipout foreground, over the plate; the star form of
    ``\\AddToShipoutPictureFG`` applies it to this page alone.
    """
    valid, warnings, invalid = _fancy_counts(results)
    tone = _COVER_TONE.get(verdict, "aeGreenLight")
    total = len(results)
    display_title = _escape(title) if title else "Top-level scratchpad"

    facts = " \\textperiodcentered{} ".join(
        [
            f"{total} statement{'' if total == 1 else 's'}",
            f"{valid} valid",
            f"{warnings} warning{'' if warnings == 1 else 's'}",
            f"{invalid} invalid",
        ]
    )
    stamp = " \\textperiodcentered{} ".join(
        [
            _datetime.datetime.now().strftime("%d %B %Y"),
            f"verified in {duration_ms:.0f}\\,ms",
            "strict domains" if strict_domains else "lenient domains",
            f"{len(source.splitlines())} lines of source",
        ]
    )

    return (
        "\\newgeometry{margin=0pt}\n"
        "\\thispagestyle{empty}\n"
        "\\noindent\n"
        "\\begin{tcolorbox}[aecover]\n"
        "\\centering\n"
        # Brand.
        "{\\ttfamily\\fontsize{9}{12}\\selectfont\\bfseries\\color{white}AETHER}"
        "\\hspace{1.8mm}"
        "{\\ttfamily\\fontsize{8}{11}\\selectfont\\color{aeAccentLight}PROOF INTERN}\\par\n"
        "\\vspace{15mm}\n"
        # Kicker: a rule, then the label it belongs to.
        "{\\color{aeAmberLight}\\rule{18mm}{1.4pt}}\\par\n"
        "\\vspace{6mm}\n"
        "{\\ttfamily\\fontsize{8.5}{11}\\selectfont\\color{aeAmberLight}VERIFICATION DOSSIER}\\par\n"
        "\\vspace{7mm}\n"
        # The theorem, as the title of the whole document.
        "{\\fontsize{31}{37}\\selectfont\\bfseries\\color{white}%s}\\par\n"
        "\\vspace{10mm}\n"
        # The verdict, big enough to read from the back of the room.
        "{\\ttfamily\\fontsize{17}{20}\\selectfont\\bfseries\\color{%s}%s}\\par\n"
        "\\vspace{5mm}\n"
        "{\\ttfamily\\fontsize{9.5}{13}\\selectfont\\color{aeAccentLight}%s}\\par\n"
        "\\vspace{20mm}\n"
        "{\\color{white}\\rule{0.7\\paperwidth}{0.4pt}}\\par\n"
        "\\vspace{5mm}\n"
        "{\\ttfamily\\fontsize{8}{11}\\selectfont\\color{aeMutedDim}%s}\\par\n"
        "\\end{tcolorbox}\n"
        "\\AddToShipoutPictureFG*{\\AtPageLowerLeft{\\color{aeAmberLight}"
        "\\rule{\\paperwidth}{3.6mm}}}\n"
        "\\clearpage\n"
        "\\restoregeometry\n"
        % (display_title, tone, _escape(verdict), facts, stamp)
    )


def _fancy_summary(
    results: Sequence[Any],
    *,
    strict_domains: bool,
    duration_ms: float,
) -> str:
    """The at-a-glance strip: four stat cards over a thin meta line."""
    valid, warnings, invalid = _fancy_counts(results)
    total = len(results)
    cards = [
        ("aePanel2", "aeInk", total, "statements"),
        ("aeGreenBg", "aeGreen", valid, "valid"),
        ("aeAmberBg", "aeAmber", warnings, "warnings"),
        ("aeRedBg", "aeRed", invalid, "invalid"),
    ]
    strip = "\\hfill".join("\\aecard{%s}{%s}{%s}{%s}" % card for card in cards)
    meta = " \\textperiodcentered{} ".join(
        [
            f"verified in {duration_ms:.0f}\\,ms",
            "strict domains" if strict_domains else "lenient domains",
            "every statement cleared" if not (warnings or invalid) else "see Findings",
        ]
    )
    # `meta` is already LaTeX -- it carries \\textperiodcentered{} separators --
    # so it is deliberately *not* escaped here.
    return (
        "\\noindent" + strip + "\\par\n"
        "\\vspace{3.2mm}\n"
        "{\\ttfamily\\fontsize{8}{10.5}\\selectfont\\color{aeMuted}%s}\\par" % meta
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

    # The wash is the second argument: a failed row is a block of colour, not
    # one coloured word at the end of a grey line.
    return "\\begin{aestep}{%s}{%s}\n%s\n\\end{aestep}" % (
        rail,
        _STEP_WASH.get(status, "white"),
        body,
    )


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
    # No section header here: _fancy_document numbers and titles every section
    # so the sequence stays contiguous when one of them is skipped.
    return "\n\n\\vspace{2mm}\n\n".join(parts)


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
    return body


def _overall_verdict(reports: Iterable[Any]) -> str:
    reports = list(reports)
    if any(not report.is_valid for report in reports):
        return "INVALID"
    if any(report.has_warnings for report in reports):
        return "VALID (with domain warnings)"
    return "VALID"


def _fancy_findings(results: Sequence[Any]) -> str:
    """The statements that had something to say, as evidence callouts.

    A clean proof produces none of these and the section is left out entirely:
    a wall of boxes saying "verified" would bury the one that did not.
    """
    blocks: list[str] = []
    for result in results:
        status = _status(result.status)
        counterexample = result.counterexample
        warnings = list(result.domain_warnings or [])
        # A valid step's message says only that it verified, which is not a
        # finding.  Only a break, or an obligation nobody discharged, gets a
        # box -- and a step can clear while still carrying one.
        if status == "VALID" and not counterexample and not warnings:
            continue

        notes: list[str] = []
        if result.message and status != "VALID":
            notes.append(_escape(result.message))
        for warning in warnings:
            notes.append("{\\color{aeAmber}%s}" % _escape(warning))
        # A failing obligation arrives as the message *and* as a warning, and
        # they are the same sentence.
        notes = _dedup(notes)

        tone = _FINDING_TONE.get(status, "aeRedBar" if counterexample else "aeAmberBar")
        label = "WARNING" if status == "VALID" and warnings else status
        line = result.line if result.line is not None else "--"
        body = [
            "{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMutedDim}L%s}"
            "\\hspace{2.2mm}\\aechip{%s}{%s}"
            "\\hspace{2.2mm}{\\ttfamily\\fontsize{8}{10}\\selectfont\\color{aeMuted}%s}"
            % (_escape(line), tone, _escape(label), _escape(result.backend)),
            "\\par\\vspace{2.2mm}",
            "{\\ttfamily\\fontsize{9.5}{12.5}\\selectfont\\color{aeInk}%s}"
            % _escape(result.statement),
        ]
        if notes:
            body += [
                "\\par\\vspace{1.8mm}",
                "{\\fontsize{8.5}{11.5}\\selectfont\\color{aeMuted}%s}"
                % " \\par ".join(notes),
            ]
        if counterexample:
            body += [
                "\\par\\vspace{1.8mm}",
                "{\\ttfamily\\fontsize{8.5}{11}\\selectfont\\bfseries\\color{aeRed}%s}"
                % _escape(counterexample),
            ]
        blocks.append("\\begin{aefinding}{%s}\n%s\n\\end{aefinding}" % (tone, "\n".join(body)))

    if not blocks:
        return ""
    return (
        "\\aelede{Statements the checker would not let pass, with the evidence "
        "it produced.}"
        + "\n".join(blocks)
    )


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
    """Assemble the designed document.

    The cover, then the proof with its at-a-glance strip, then whatever evidence
    there is: findings, the auditor, the state at each line, the session, the
    source and a legend.  Sections are collected as pairs and numbered in one
    pass at the end, so leaving one out -- Findings on a clean proof, Session
    with no recorded history -- does not leave a hole in the sequence.
    """
    title = next((report.theorem_name for report in reports if report.theorem_name), None)

    sections: list[tuple[str, str]] = [
        (
            "The Proof",
            _fancy_summary(results, strict_domains=strict_domains, duration_ms=duration_ms)
            + "\n\\vspace{5mm}\n"
            + body,
        )
    ]

    findings = _fancy_findings(results)
    if findings:
        sections.append(("Findings", findings))

    sections.append(
        (
            "Auditor",
            "\\aelede{Each statement as the intern saw it: line, verdict, "
            "backend, and what it was checked against.}" + _fancy_auditor(results),
        )
    )
    sections.append(
        (
            "Proof State",
            "\\aelede{What was in scope at each line.}" + _fancy_state(results),
        )
    )

    session_body = _fancy_session(session)
    if session_body:
        sections.append(
            (
                "Session",
                "\\aelede{What this proof did while you worked on it.}" + session_body,
            )
        )

    sections.append(
        (
            "Source",
            "\\aelede{As written, before parsing.}" + _fancy_verbatim(source),
        )
    )
    sections.append(("About", "\\aelede{How to read this document.}" + _fancy_about()))

    chunks = [
        _fancy_cover(
            title=title,
            verdict=verdict,
            results=results,
            strict_domains=strict_domains,
            duration_ms=duration_ms,
            source=source,
        )
    ]
    # The auditor and the source listing each want a fresh page: the first is a
    # long column of rows, the second a wall of monospace that reads badly
    # starting halfway down a page.
    for index, (heading, content) in enumerate(sections, start=1):
        prefix = "\\aepage\n" if heading in ("Auditor", "Source") else ""
        chunks.append("%s\\aesection{%02d}{%s}\n\n%s" % (prefix, index, heading, content))

    preamble = _FANCY_PREAMBLE.replace("@@SITE_NAME@@", _escape(_SITE_NAME)).replace("@@SITE_TAGLINE@@", _escape(_SITE_TAGLINE))
    return (
        preamble
        + "\n\\begin{document}\n"
        + "\n\n".join(chunks)
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
        + "\n\\title{\\textbf{" + _escape(_SITE_NAME) + " Verified Proof Document}\\vspace{0.35em}\\\\"
        + subtitle
        + "\\normalsize\\textcolor{aeMuted}{Generated by " + _escape(_SITE_NAME) + " --- "
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
