"""Paste LaTeX: a proof written in LaTeX as a Lemmata draft.

Most students already have their proofs in LaTeX (notes, Overleaf).  This
turns one into Lemmata lines by fixed rules, so the same input always gives
the same draft, offline and in the browser:

- ``\\begin{theorem}[Name] … \\end{theorem}`` (or lemma, proposition, claim)
  becomes ``Theorem: "Name"``, its formula a ``Claim:`` when it is one;
  ``\\begin{proof} … \\end{proof}`` becomes ``Proof:`` … ``QED``.
- Each sentence of the proof is read by its opening words: *Let/Fix/Take/
  Choose/Set* keep their word (Lemmata reads them), *Suppose/Assume* become
  ``Assume``, *Since A, B* stays, and *Then/So/Thus/Hence/We have/It follows
  that/Therefore* become ``Then``/``Therefore``.  A displayed equation
  (``\\[…\\]``, ``align*`` and friends) becomes a chain of ``Step:`` lines, one
  per row, ``&= …`` rows continuing the chain.
- The maths is normalised to what the parser reads: ``\\frac{a}{b}`` is
  ``((a)/(b))``, ``x^{2}`` is ``x^(2)``, ``\\sqrt{x}`` is ``sqrt(x)``, ``2k`` is
  ``2*k``, ``\\mathbb{R}`` is ``ℝ``; spacing, ``\\left``/``\\right`` and
  ``\\text{…}`` go.  ``\\sum``, ``\\int`` and ``\\lim`` keep the forms the grammar
  already reads.

Anything it cannot place becomes a ``#`` comment saying so, and every line
the parser then refuses is commented out the same way, so the draft always
parses: it is a draft for the student to finish, never a guess presented as
their proof.  ``latex_to_lemmata(text)`` returns a :class:`LatexImport`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

INDENT = "    "

_THEOREM_ENVS = ("theorem", "lemma", "proposition", "claim", "corollary")
_DISPLAY_ENVS = ("align", "align*", "aligned", "equation", "equation*", "gather", "gather*", "eqnarray", "eqnarray*", "multline", "multline*")


@dataclass
class LatexImport:
    """The draft, and the lines kept as comments for the student to rewrite."""

    source: str
    #: ``{"line": n, "text": …, "why": …}`` for each line left as a comment.
    comments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "comments": self.comments}


# ---------------------------------------------------------------------------
# Braces and maths
# ---------------------------------------------------------------------------


def _group(text: str, i: int) -> tuple[str, int]:
    """The brace group starting at text[i] == "{": its inside, and the index after it.
    A single token stands for a group, as in TeX (``\\frac12``, ``x^2``)."""
    while i < len(text) and text[i] == " ":
        i += 1
    if i >= len(text):
        return "", i
    if text[i] != "{":
        if text[i] == "\\":
            m = re.match(r"\\[a-zA-Z]+", text[i:])
            if m:
                return m.group(0), i + len(m.group(0))
        return text[i], i + 1
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j], j + 1
        j += 1
    return text[i + 1 :], len(text)


_BLACKBOARD = {"R": "ℝ", "Z": "ℤ", "N": "ℕ", "Q": "ℚ", "C": "ℂ"}
_DROP = (r"\\left", r"\\right", r"\\displaystyle", r"\\textstyle", r"\\limits", r"\\nolimits", r"\\nonumber", r"\\notag", r"\\bigl?", r"\\bigr?", r"\\Bigl?", r"\\Bigr?")
_SPACES = (r"\\,", r"\\;", r"\\:", r"\\!", r"\\quad", r"\\qquad", r"\\ ", "~")
_SAME = {r"\leqslant": r"\le", r"\geqslant": r"\ge", r"\ne": r"\neq", r"\lt": "<", r"\gt": ">", r"\lvert": "|", r"\rvert": "|", r"\vert": "|", r"\times": "*", r"\cdot": "*", r"\colon": ":"}
#: Commands whose bounds the grammar reads as written (`\sum_{k=1}^{n}`).
_BOUNDED = ("\\sum", "\\int", "\\lim", "\\prod")


def math(tex: str) -> str:
    """LaTeX maths as Lemmata reads it."""
    s = tex
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:text|mbox|textrm|textit|intertext)\{[^}]*\}", " ", s)
    s = re.sub(r"\\(?:mathrm|operatorname|mathit)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathbb\{?([RZNQC])\}?", lambda m: _BLACKBOARD[m.group(1)], s)
    for pattern in _DROP:
        s = re.sub(pattern + r"(?![a-zA-Z])", "", s)
    for pattern in _SPACES:
        s = re.sub(pattern + (r"(?![a-zA-Z])" if pattern[-1].isalpha() else ""), " ", s)
    for old, new in _SAME.items():
        s = re.sub(re.escape(old) + r"(?![a-zA-Z])", lambda _m, new=new: f" {new} " if new in ("*", "<", ">") else new, s)
    s = _commands(s)
    s = _implicit_products(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip(".,;").strip()


def _commands(s: str) -> str:
    """\\frac, \\sqrt, ^{…} and _{…}, rewritten from the inside out."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s.startswith(_BOUNDED, i):
            # Keep `\sum_{k=1}^{n}` as written: the grammar reads it.
            m = re.match(r"\\[a-zA-Z]+", s[i:])
            j = i + len(m.group(0))
            while j < len(s) and s[j] in "_^":
                inner, k = _group(s, j + 1)
                out.append(s[i:j] + s[j] + "{" + _commands(inner) + "}")
                i = j = k
            if i < j:
                out.append(s[i:j])
                i = j
            continue
        m = re.match(r"\\[dt]?frac(?![a-zA-Z])", s[i:])
        if m:
            num, j = _group(s, i + len(m.group(0)))
            den, k = _group(s, j)
            out.append(f"(({_commands(num)})/({_commands(den)}))")
            i = k
            continue
        m = re.match(r"\\sqrt(?![a-zA-Z])", s[i:])
        if m:
            j = i + len(m.group(0))
            root = None
            if j < len(s) and s[j] == "[":
                end = s.index("]", j)
                root, j = s[j + 1 : end], end + 1
            arg, k = _group(s, j)
            out.append(f"sqrt({_commands(arg)})" if root is None else f"(({_commands(arg)})^(1/({root})))")
            i = k
            continue
        if s[i] == "^":
            arg, k = _group(s, i + 1)
            out.append(f"^({_commands(arg)})")
            i = k
            continue
        if s[i] == "_" and out and re.search(r"[A-Za-z]$", out[-1]):
            arg, k = _group(s, i + 1)
            if re.fullmatch(r"\d+", arg):
                out.append(f"_{arg}")  # x_1: a name
            else:
                out.append(f"({_commands(arg)})")  # a_n, a_{n+1}: a sequence's value
            i = k
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _bars(s: str) -> str:
    """3|x - 2| as 3*|x - 2|: an opening bar right after a value multiplies."""
    out, opening = [], True
    for i, ch in enumerate(s):
        if ch == "|":
            before = "".join(out).rstrip()
            if opening and before and re.search(r"[\w)]$", before):
                out.append("*")
            opening = not opening
        out.append(ch)
    return "".join(out)


def _implicit_products(s: str) -> str:
    """2k, 2(x + 1), 2\\pi, (a)(b) and 3|x| written as products."""
    s = _bars(s)
    s = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?=[A-Za-z(\\])(?!\\(?:le|ge|neq|in|to|cdot|times|leq|geq|lt|gt|mid|implies|iff|land|lor|cup|cap|subset)\b)", r"\1*", s)
    s = re.sub(r"\)\s*(?=[(A-Za-z0-9])(?!(?:and|or|in|implies|iff)\b)", ")*", s)
    return s


# ---------------------------------------------------------------------------
# Text: math runs, sentences
# ---------------------------------------------------------------------------

_MATH_RUN = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$(.+?)\$|\\\((.+?)\\\)", re.S)


def _display_blocks(text: str) -> str:
    """Display environments as \\[ … \\] blocks, rows separated by \\\\."""
    for env in _DISPLAY_ENVS:
        pattern = re.compile(r"\\begin\{" + re.escape(env) + r"\}(.*?)\\end\{" + re.escape(env) + r"\}", re.S)
        text = pattern.sub(lambda m: "\\[" + m.group(1) + "\\]", text)
    return text


def _segments(body: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """The proof as (sentence text, its inline maths, its displayed rows)."""
    body = _display_blocks(body)
    out: list[tuple[str, list[str], list[list[str]]]] = []
    words: list[str] = []
    inline: list[str] = []
    displays: list[list[str]] = []
    pos = 0

    def flush() -> None:
        nonlocal words, inline, displays
        text = " ".join(" ".join(words).split())
        if text or inline or displays:
            out.append((text, inline, displays))
        words, inline, displays = [], [], []

    def prose(chunk: str) -> None:
        for piece in re.split(r"(?<=[.!?])\s+", chunk):
            ends = bool(re.search(r"[.!?]\s*$", piece))
            if piece.strip():
                words.append(piece.strip())
            if ends:
                flush()

    for m in _MATH_RUN.finditer(body):
        prose(body[pos : m.start()])
        display = m.group(1) or m.group(2)
        if display is not None:
            rows = [r for r in re.split(r"\\\\", display) if r.strip()]
            displays.append(rows)
            words.append("⟨display⟩")
            pos = m.end()
            flush()  # what follows a display is a sentence of its own
            continue
        else:
            inline.append(m.group(3) or m.group(4))
            words.append("⟨math⟩")
        pos = m.end()
    prose(body[pos:])
    flush()
    return out


# ---------------------------------------------------------------------------
# Sentences as lines
# ---------------------------------------------------------------------------

_LEADS: tuple[tuple[str, str], ...] = (
    (r"(?:let|fix)\b", "Let"),
    (r"(?:take|choose|pick|put|set)\b", "Take"),
    (r"(?:suppose|assume)(?: that)?\b", "Assume"),
    (r"(?:therefore|consequently)\b", "Therefore"),
    (r"(?:then|so|thus|hence|we have|we get|we see that|it follows that|this gives|note that|clearly|now)\b", "Then"),
)


def _lead(text: str) -> Optional[str]:
    low = text.lower().lstrip("(").strip()
    for pattern, word in _LEADS:
        if re.match(pattern, low):
            return word
    return None


def _rows(rows: list[str]) -> list[str]:
    """A displayed equation or aligned rows as a chain of Step: lines."""
    lines: list[str] = []
    for row in rows:
        row = row.replace("&", " ")
        expr = math(row)
        if not expr:
            continue
        if re.match(r"(=|<|>|\\le|\\ge|\\neq|≤|≥|<=|>=)", expr) and lines:
            lines.append(f"Step: {expr}")
        else:
            lines.append(f"Step: {expr}")
    return lines


_CLAUSE = re.compile(r"(?:,\s*|\s+)(?:and\s+)?(?=(?:suppose|assume|let|then|so|hence|thus|therefore)\b)", re.I)
_RELATION = re.compile(r"=|<|>|\\le|\\ge|\\neq|\\in\b|∈|≤|≥|\\subset")
_KIND = {"integer": "ℤ", "integers": "ℤ", "real": "ℝ", "natural": "ℕ", "rational": "ℚ"}


def _sentence(text: str, inline: list[str], displays: list[list[str]]) -> list[tuple[str, Optional[str]]]:
    """(line, why-it-is-a-comment or None) for one sentence, clause by clause."""
    parts = [p for p in _CLAUSE.split(text) if p.strip()]
    if len(parts) <= 1:
        return _clause(text, inline, displays)
    out: list[tuple[str, Optional[str]]] = []
    k = 0
    for i, part in enumerate(parts):
        n = part.count("⟨math⟩")
        out.extend(_clause(part, inline[k : k + n], displays if i == len(parts) - 1 else []))
        k += n
    return out


def _clause(text: str, inline: list[str], displays: list[list[str]]) -> list[tuple[str, Optional[str]]]:
    lead = _lead(text)
    out: list[tuple[str, Optional[str]]] = []
    # "for some integer $k$": the witness is declared.
    for m in re.finditer(r"for some (integer|integers|real|natural|rational)?\s*(?:number\s*)?⟨math⟩", text, re.I):
        idx = text[: m.end()].count("⟨math⟩") - 1  # this placeholder's place among the maths
        var = math(inline[idx]) if 0 <= idx < len(inline) else ""
        if re.fullmatch(r"\\?[A-Za-z]+", var):
            out.append((f"Let {var} ∈ {_KIND.get((m.group(1) or 'real').lower(), 'ℝ')}", None))
    every = [math(m) for m in inline if math(m)]
    maths = [m for m in every if _RELATION.search(m)]
    low = text.lower()
    if low.startswith("since") and len(maths) >= 2:
        out.append((f"Since {maths[0]}, {' and '.join(maths[1:])}", None))
    elif lead == "Let" and maths and not out:
        tail = " be given" if "given" in low or "arbitrary" in low else ""
        out.extend((f"Let {m}{tail}", None) for m in maths)
    elif lead == "Take" and maths:
        out.extend((f"Take {m}", None) for m in maths)
    elif lead == "Assume" and maths:
        out.append((f"Assume {' and '.join(maths)}", None))
    elif lead in ("Then", "Therefore") and maths:
        out.append((f"{lead} {' and '.join(maths)}", None))
    elif out:
        pass
    elif text and not displays:
        why = "no formula to check" if not maths else "the sentence's role is not clear: write it as a line"
        out.append((f"# {_plain(text, inline)}", why))
    elif text and _lead(text) is None and text.replace("⟨display⟩", "").strip(" .,:"):
        out.append((f"# {_plain(text, inline)}", None))
    for rows in displays:
        out.extend((line, None) for line in _rows(rows))
    return out


def _plain(text: str, inline: list[str]) -> str:
    for m in inline:
        text = text.replace("⟨math⟩", f"${m}$", 1)
    return text.replace("⟨display⟩", "(displayed below)").strip()


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def _strip(text: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", text)  # comments
    m = re.search(r"\\begin\{document\}(.*?)(\\end\{document\}|$)", text, re.S)
    if m:
        text = m.group(1)
    text = re.sub(r"\\(?:qed|qedhere|blacksquare|square)(?![a-zA-Z])", "", text)
    text = re.sub(r"\\(?:emph|textbf|textit)\{([^}]*)\}", r"\1", text)
    return text


def latex_to_lemmata(text: str) -> LatexImport:
    """*text*, a proof in LaTeX, as a Lemmata draft that parses."""
    text = _strip(text)
    lines: list[tuple[str, Optional[str]]] = []
    theorem = re.search(r"\\begin\{(" + "|".join(_THEOREM_ENVS) + r")\*?\}(?:\[([^\]]*)\])?(.*?)\\end\{\1\*?\}", text, re.S)
    proof = re.search(r"\\begin\{proof\}(?:\[[^\]]*\])?(.*?)\\end\{proof\}", text, re.S)
    body = proof.group(1) if proof else (text if theorem is None else text[theorem.end() :])
    indent = ""
    if theorem or proof:
        name = (theorem.group(2) if theorem and theorem.group(2) else (theorem.group(1).title() if theorem else "Pasted proof")).strip()
        lines.append((f'Theorem: "{name}"', None))
        if theorem:
            statement = theorem.group(3)
            runs = [m for m in _MATH_RUN.finditer(statement)]
            prose = _MATH_RUN.sub("", statement).strip(" .\n")
            if len(runs) == 1 and len(prose.split()) <= 3:
                claim = math(next(g for g in runs[0].groups() if g))
                lines.append((f"Claim: {claim}", None))
            elif statement.strip():
                lines.append((f"# Statement: {' '.join(statement.split())}", "the statement is prose: write it as a Claim"))
        lines.append(("Proof:", None))
        indent = INDENT
    for sentence, inline, displays in _segments(body):
        for line, why in _sentence(sentence, inline, displays):
            lines.append((indent + line, why))
    if indent:
        lines.append(("QED", None))
    return _parseable(lines)


def _parseable(lines: list[tuple[str, Optional[str]]]) -> LatexImport:
    """Comment out each line the parser refuses, until the draft parses."""
    from aether.parser.parser import AetherParser, ParseError

    parser = AetherParser()
    current = [line for line, _ in lines]
    whys = {i: why for i, (_, why) in enumerate(lines) if why}
    for _ in range(len(current) + 1):
        source = "\n".join(current) + "\n"
        try:
            parser.parse(source)
            break
        except ParseError as exc:
            n = (exc.line or 1) - 1
            while n < len(current) and current[n].lstrip().startswith("#"):
                n += 1  # reported at the end of a comment: the next line is at fault
            if n >= len(current):
                break
            body = current[n].lstrip()
            pad = current[n][: len(current[n]) - len(body)]
            current[n] = f"{pad}# {body}"
            whys[n] = "Lemmata could not read this line: rewrite it"
    comments = [
        {"line": i + 1, "text": current[i].strip(), "why": whys[i]}
        for i in sorted(whys)
        if current[i].lstrip().startswith("#")
    ]
    return LatexImport(source="\n".join(current) + "\n", comments=comments)
