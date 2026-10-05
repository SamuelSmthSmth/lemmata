"""What to do about a step that did not check: a hint, and a fix when one is sure.

The checker's messages say *why* a step failed in the solvers' terms.  A hint
says it in the student's: their own symbols (δ, not ``\\delta``), their own
line, and the edit that would mend it when there is exactly one.  Hints never
change a verdict; they are read from the result, the statement, the proof
state after it and the proof's source lines.

A hint is ``{"message": str, "fix": {...}?}``.  A fix is one of

    {"line": n, "insert_before": "Assume x - 1 != 0", "label": "Add Assume x - 1 != 0"}
    {"line": n, "col_start": a, "col_end": b, "text": "≤", "label": "Use ≤"}

with 1-based lines and columns, ``col_end`` exclusive.  A replacement is only
offered when the text it replaces occurs once on that line, so applying it can
never edit the wrong thing.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Callable, Optional

from aether.core.ast import (
    DeduceNode,
    ExprNode,
    FunctionCallNode,
    RelationNode,
    StepNode,
)

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
}
_GREEK_RE = re.compile(r"\\?\b(" + "|".join(sorted(GREEK, key=len, reverse=True)) + r")\b")

# What a student may call, as the Guide spells it.
KNOWN_CALLS = (
    "Even", "Odd", "Positive", "NonNegative", "MultipleOf", "Divides", "Congruent", "Prime",
    "Coprime", "Rational", "Irrational",
    "Group", "AbelianGroup", "Subgroup", "NormalSubgroup", "Ring", "Field",
    "sqrt", "abs", "exp", "ln", "log", "sin", "cos", "tan", "min", "max", "factorial",
    "gcd", "lcm", "lim", "sum", "diff", "integrate", "det", "inv",
)


def typeset(text: str) -> str:
    """The engine's spelling in the notes' symbols: ``\\delta`` -> δ, ``!=`` -> ≠, ``<=`` -> ≤."""
    text = _GREEK_RE.sub(lambda m: GREEK[m.group(1)], text)
    return text.replace("!=", "≠").replace("<=", "≤").replace(">=", "≥")


def _bare(expr: Any) -> str:
    """An expression as a student would write it: no outermost parentheses."""
    text = str(expr)
    while text.startswith("(") and text.endswith(")") and _balanced(text[1:-1]):
        text = text[1:-1]
    return text


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if depth < 0:
            return False
    return depth == 0


def _relation_text(rel: RelationNode) -> str:
    return f"{_bare(rel.left)} {rel.op} {_bare(rel.right)}"


def _unique_span(line_text: str, needle: str) -> Optional[tuple[int, int]]:
    """The 1-based [start, end) columns of *needle* in the line, if it occurs exactly once."""
    starts = [m.start() for m in re.finditer(re.escape(needle), line_text)]
    if len(starts) != 1:
        return None
    return starts[0] + 1, starts[0] + 1 + len(needle)


# ---------------------------------------------------------------------------
# The hints
# ---------------------------------------------------------------------------


def domain_hints(result, ctx, line: Optional[int]) -> list[dict[str, Any]]:
    """An unresolved obligation: say what the step needs, and offer to assume it."""
    out = []
    seen: set[str] = set()
    for ob in getattr(ctx, "obligations", []):
        if ob.discharged or ob.line != line or not isinstance(ob.condition, RelationNode):
            continue
        need = _relation_text(ob.condition)
        if need in seen:
            continue
        seen.add(need)
        found = next((re.search(r"\(violated at ([^)]*)\)", w) for w in result.domain_warnings if "violated at" in w), None)
        at = result.counterexample or (found.group(1) if found else "")
        where = f" (it fails at {typeset(at)})" if at else ""
        out.append(
            {
                "message": f"This step needs {typeset(need)}, which nothing before it guarantees{where}. Assume it, or show it holds.",
                "fix": {"line": line, "insert_before": f"Assume {need}", "label": f"Add Assume {typeset(need)}"},
            }
        )
    return out


_DIFF_RE = re.compile(r"simplifies to (.+?) != 0\.")


def algebra_hints(result) -> list[dict[str, Any]]:
    match = _DIFF_RE.search(result.message or "")
    if not match:
        return []
    return [{"message": f"The two sides differ by {typeset(match.group(1))}."}]


_STRICT = {"<": "<=", ">": ">=", "\\lt": "<=", "\\gt": ">="}
_STRICT_GLYPHS = {"<": ("<", "≤"), ">": (">", "≥")}


def _claim(stmt) -> Optional[ExprNode]:
    """What a statement asserts, when it asserts a whole relation (not a chained `< …`)."""
    if isinstance(stmt, DeduceNode):
        claim = stmt.claim
        if isinstance(claim, RelationNode) and getattr(claim.left, "name", None) == "<prev>":
            return None
        return claim
    if isinstance(stmt, StepNode) and stmt.lhs is not None:
        return RelationNode(op=stmt.relation, left=stmt.lhs, right=stmt.rhs)
    return None


def strictness_hints(stmt, line_text: str, holds: Callable[[RelationNode], bool]) -> list[dict[str, Any]]:
    """`<` fails but `≤` holds: say so, and offer the swap when the operator is unambiguous."""
    claim = _claim(stmt)
    if not isinstance(claim, RelationNode) or claim.op not in _STRICT:
        return []
    weaker = RelationNode(op=_STRICT[claim.op], left=claim.left, right=claim.right)
    if not holds(weaker):
        return []
    glyph = _STRICT_GLYPHS["<" if claim.op in ("<", "\\lt") else ">"]
    hint: dict[str, Any] = {"message": f"This holds with {glyph[1]}, not {glyph[0]}: the two sides can be equal."}
    if line_text.count(glyph[0]) == 1:
        span = _unique_span(line_text, glyph[0])
        hint["fix"] = {"col_start": span[0], "col_end": span[1], "text": glyph[1], "label": f"Use {glyph[1]}"}
    return [hint]


def label_hints(result, lines: list[str], line: Optional[int], active_labels: list[str]) -> list[dict[str, Any]]:
    """An unknown label: say where it was assumed if a block has closed over it, or suggest one."""
    match = re.search(r"Unknown or out-of-scope justification: '([^']+)'", result.message or "")
    if not match:
        return []
    name = match.group(1)
    introduced = re.compile(rf"^\s*(assume|suppose|hypothesize|obtain|choose|pick)\b.*?\b{re.escape(name)}\s*:", re.IGNORECASE)
    for n, text in enumerate(lines[: (line or 1) - 1], start=1):
        if introduced.match(text) and name not in active_labels:
            return [{"message": f"{name} was introduced on line {n}, inside a block that has ended, so it isn't available here."}]
    close = difflib.get_close_matches(name, active_labels, n=1, cutoff=0.5)
    if close and line is not None:
        span = _unique_span(lines[line - 1], name) if line - 1 < len(lines) else None
        hint: dict[str, Any] = {"message": f"There is no {name} here. Did you mean {close[0]}?"}
        if span:
            hint["fix"] = {"col_start": span[0], "col_end": span[1], "text": close[0], "label": f"Use {close[0]}"}
        return [hint]
    return []


def _calls(expr: Any, out: list[str]) -> list[str]:
    if isinstance(expr, FunctionCallNode):
        out.append(expr.func)
        for arg in expr.args:
            _calls(arg, out)
    elif isinstance(expr, ExprNode):
        for value in vars(expr).values():
            if isinstance(value, ExprNode):
                _calls(value, out)
            elif isinstance(value, list):
                for item in value:
                    _calls(item, out)
    return out


def name_hints(stmt, line_text: str, defined: set[str]) -> list[dict[str, Any]]:
    """A call to a name that is not known: the nearest known name, and the swap."""
    claim = getattr(stmt, "claim", None) if isinstance(stmt, DeduceNode) else _claim(stmt)
    if claim is None:
        return []
    known = {k.lower() for k in KNOWN_CALLS} | {d.lower() for d in defined}
    out = []
    for name in dict.fromkeys(_calls(claim, [])):
        if name.lower() in known:
            continue
        pool = list(KNOWN_CALLS) + sorted(defined)
        close = difflib.get_close_matches(name, pool, n=1, cutoff=0.6) or [
            k for k in pool if k.lower() == name.lower()
        ]
        if not close:
            continue
        hint: dict[str, Any] = {"message": f"{name} is not a known predicate or function, so it proves nothing. Did you mean {close[0]}?"}
        span = _unique_span(line_text, name)
        if span:
            hint["fix"] = {"col_start": span[0], "col_end": span[1], "text": close[0], "label": f"Use {close[0]}"}
        out.append(hint)
    return out


def citation_hints(result, line_text: str) -> list[dict[str, Any]]:
    match = re.search(r"No result called '([^']+)'.*?Did you mean '([^']+)'", result.message or "")
    if not match:
        return []
    cited, better = match.groups()
    hint: dict[str, Any] = {"message": f"Did you mean {better}?"}
    span = _unique_span(line_text, cited)
    if span:
        hint["fix"] = {"col_start": span[0], "col_end": span[1], "text": better, "label": f"Cite {better}"}
    return [hint]


def chain_hints(result) -> list[dict[str, Any]]:
    if result.backend != "ChainGuard" or "direction" not in (result.message or "").lower():
        return []
    return [{"message": "A chain can only run one way (all ≤ or all ≥). Start a new chain with a full Step: a … b here."}]


def hints_for(result, stmt, ctx, lines: list[str], holds: Callable[[RelationNode], bool]) -> list[dict[str, Any]]:
    """Every hint for a step that did not simply check."""
    if result.status.value == "VALID":
        return []
    line = result.line
    line_text = lines[line - 1] if line and 0 < line <= len(lines) else ""
    labels = [h.label for h in ctx.all_hypotheses() if h.label]
    defined = set(ctx.all_functions())
    hints: list[dict[str, Any]] = []
    hints += domain_hints(result, ctx, line)
    if result.status.value == "INVALID":
        hints += citation_hints(result, line_text)
        hints += label_hints(result, lines, line, labels)
        hints += chain_hints(result)
        hints += algebra_hints(result)
        hints += name_hints(stmt, line_text, defined)
        if result.backend in ("Z3", "SymPy+Logic", "Z3 (Witness)"):
            hints += strictness_hints(stmt, line_text, holds)
    for hint in hints:
        fix = hint.get("fix")
        if fix is None:
            continue
        fix.setdefault("line", line)
        # What a replacement expects to find there, so an editor whose line has
        # changed since the check can refuse to apply it rather than edit blindly.
        if "col_start" in fix:
            fix["was"] = line_text[fix["col_start"] - 1 : fix["col_end"] - 1]
    return hints
