"""A Lemmata proof as a Lean 4 + Mathlib skeleton: "Show me in Lean".

Each statement becomes the Lean that says the same thing -- ``Given`` an
``intro``, a ``Step:`` chain a ``calc``, ``Therefore`` a ``have`` -- and every
proof obligation is a ``sorry`` for Lean's tactics to discharge, with a comment
saying which of Lemmata's backends checked it and the tactic most likely to do
the same in Lean.  Nothing is proved here that Lemmata did not check, and no
proof is invented: the skeleton is the proof's *statement* in Lean.

Every skeleton must compile against Mathlib (``lean/generate.py`` and the
``lean`` CI job hold it to that), so anything without a faithful translation --
an integral, a matrix, an unknown structure -- becomes a typed ``sorry`` and is
listed in ``untranslated`` with its line, rather than guessed at.

``rows`` lines the two up, in Lean's order: each run of Lean lines (1-based,
inclusive) with the source line it came from (None for Lean's own scaffolding)
and that line's verdict, for the side-by-side view.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from aether.core.ast import (
    BinaryOpNode,
    DeduceNode,
    DocumentNode,
    EmptySetNode,
    ExprNode,
    FuncDefNode,
    FunctionCallNode,
    GreekSymbolNode,
    ImportNode,
    IntegralNode,
    LimitNode,
    MatrixNode,
    NumberNode,
    ObtainNode,
    QuantifierNode,
    RawMathNode,
    RelationNode,
    StatementNode,
    StepNode,
    StringLiteralNode,
    SubProofNode,
    SymbolNode,
    TheoremNode,
    UnaryOpNode,
    VarDeclNode,
    VectorNode,
    AssumeNode,
)
from aether.core.types import MathType, normalize_type_name, split_function_type

# ---------------------------------------------------------------------------
# Names and types
# ---------------------------------------------------------------------------

LEAN_NUMBER_TYPES: dict[MathType, str] = {
    MathType.Nat: "ℕ",
    MathType.Int: "ℤ",
    MathType.Rat: "ℚ",
    MathType.Real: "ℝ",
    MathType.Complex: "ℂ",
    MathType.Bool: "Prop",
    MathType.Set: "Set ℝ",
}

_GREEK: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "«λ»", "mu": "μ",
    "nu": "ν", "xi": "ξ", "omicron": "ο", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "«Π»", "Sigma": "«Σ»", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω", "pi": "π",
}

#: Words Lean reads as syntax, which a variable may still be called: «at».
_LEAN_RESERVED = frozenset(
    """at by do else end fun from have if in let match open show then with where calc set obtain
    suffices exact intro theorem lemma def example instance structure class namespace section
    variable universe import axiom mutual deriving this Type Sort Prop sorry rfl forall exists
    local private protected noncomputable partial unsafe macro syntax notation infix prefix
    postfix attribute abbrev opaque inductive for unless return try catch finally mut break
    continue nomatch nofun using only generalizing induction cases rcases rintro refine trivial""".split()
)

#: Constants Lemmata knows by name when nothing else is called that.
_CONSTANTS = {"pi": "Real.pi", "e": "Real.exp 1"}

#: Calls with a Mathlib spelling: name -> (Lean head, arity) for plain application.
_FUNCTIONS: dict[str, str] = {
    "sqrt": "Real.sqrt", "exp": "Real.exp", "ln": "Real.log", "log": "Real.log",
    "sin": "Real.sin", "cos": "Real.cos", "tan": "Real.tan", "arctan": "Real.arctan",
    "sinh": "Real.sinh", "cosh": "Real.cosh", "max": "max", "min": "min",
    "gcd": "gcd", "lcm": "lcm", "factorial": "Nat.factorial",
}

#: Predicates on integers: their arguments are read in ℤ.
_INTEGER_CALLS = frozenset({"even", "odd", "multipleof", "divides", "congruent", "cong", "prime", "gcd", "lcm", "factorial", "floor", "ceil"})

#: Lemmata's structure assumptions, and the Mathlib class each is.
_STRUCTURES: dict[str, str] = {
    "group": "Group", "abeliangroup": "CommGroup", "ring": "Ring", "field": "Field",
}

#: Relations, by Lemmata's canonical spelling.
_RELATIONS: dict[str, str] = {
    "=": "=", "!=": "≠", "/=": "≠", "\\neq": "≠", "<": "<", ">": ">", "<=": "≤", "\\le": "≤",
    "\\leq": "≤", ">=": "≥", "\\ge": "≥", "\\geq": "≥", "in": "∈", "\\in": "∈", "notin": "∉",
    "\\notin": "∉", "not in": "∉", "subset": "⊂", "\\subset": "⊂", "subseteq": "⊆",
    "\\subseteq": "⊆", "\\equiv": "=",
}

_IMPLIES = frozenset({"=>", "->", "implies", "\\implies"})
_IFF = frozenset({"<=>", "<->", "iff", "\\iff"})
_AND = frozenset({"and", "\\land", "/\\"})
_OR = frozenset({"or", "\\lor", "\\/"})

# Lean's precedences (Prelude / Mathlib notation), for minimal parentheses.
_P_BINDER, _P_IFF, _P_IMP, _P_OR, _P_AND, _P_NOT, _P_REL = 0, 20, 25, 30, 35, 40, 50
_P_ADD, _P_MUL, _P_NEG, _P_POW, _P_APP, _P_ATOM = 65, 70, 64, 75, 1024, 2000
#: `x⁻¹` is postfix at max: `f x⁻¹` is `f (x⁻¹)`, so its operand needs an atom.
_P_INV = 1500


def lean_name(name: str) -> str:
    """A Lemmata identifier as a Lean one: ``epsilon`` → ``ε``, ``at`` → ``«at»``."""
    if name in _GREEK:
        return _GREEK[name]
    if name in _LEAN_RESERVED or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_']*", name):
        return f"«{name}»"
    return name


def lean_type(raw: Optional[str]) -> Optional[str]:
    """A declared type as Lean writes it, or None if it is not a number type."""
    if raw is None:
        return "ℝ"
    parts = split_function_type(raw)
    if parts is not None:
        types = [lean_type(p) for p in parts]
        return None if any(t is None or t == "Prop" for t in types[:-1]) or types[-1] is None else " → ".join(types)  # type: ignore[arg-type]
    try:
        mt = normalize_type_name(raw)
    except ValueError:
        return None
    if mt == MathType.Function:
        return "ℝ → ℝ"
    return LEAN_NUMBER_TYPES.get(mt)


def slug(name: Optional[str]) -> Optional[str]:
    """A theorem's name as a Lean declaration name: "Even square theorem" → ``even_square_theorem``."""
    if not name:
        return None
    words = re.findall(r"[A-Za-z0-9]+", name.lower())
    if not words:
        return None
    text = "_".join(words)
    if text[0].isdigit():
        text = "t_" + text
    return lean_name(text)


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


@dataclass
class LeanExport:
    """The skeleton, how it lines up with the source, and what it left out."""

    lean: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    untranslated: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"lean": self.lean, "rows": self.rows, "untranslated": self.untranslated}


class _Untranslatable(Exception):
    """Raised inside a proposition that has no faithful Lean; the caller makes it ``sorry``."""


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


@dataclass
class _Scope:
    """What the translation knows at a point: variable types, definitions, structures."""

    types: dict[str, str] = field(default_factory=dict)
    #: Group/ring operation names → how Lean writes them.
    ops: dict[str, str] = field(default_factory=dict)
    carriers: dict[str, str] = field(default_factory=dict)
    defs: dict[str, FuncDefNode] = field(default_factory=dict)
    #: `Let u = x^2 - y^2`: what a named value stands for, for derivatives of it.
    lets: dict[str, ExprNode] = field(default_factory=dict)
    #: Which structure each operation name belongs to (`star` → `H`).
    op_carrier: dict[str, str] = field(default_factory=dict)

    def child(self) -> "_Scope":
        return _Scope(
            dict(self.types), dict(self.ops), dict(self.carriers), dict(self.defs), dict(self.lets), dict(self.op_carrier)
        )


class _Expr:
    """Expression printer: Lemmata AST → Lean term, with minimal parentheses."""

    def __init__(self, scope: _Scope, untranslated: list[dict[str, Any]], line: Optional[int]):
        self._tail = False
        self.scope = scope
        self.untranslated = untranslated
        self.line = line

    # -- entry points -------------------------------------------------------

    def prop(self, node: ExprNode) -> str:
        """A proposition; ``(sorry : Prop)`` if it has no faithful Lean."""
        try:
            return self.show(node, 0, tail=True)
        except _Untranslatable as exc:
            self._note(str(exc))
            return "(sorry : Prop)"

    def term(self, node: ExprNode, prec: int = 0) -> str:
        try:
            return self.show(node, prec)
        except _Untranslatable as exc:
            self._note(str(exc))
            return "(sorry : ℝ)"

    def _note(self, what: str) -> None:
        item = {"line": self.line, "what": what}
        if item not in self.untranslated:
            self.untranslated.append(item)

    # -- kinds --------------------------------------------------------------

    def kind(self, node: ExprNode) -> Optional[str]:
        """``"real"`` if *node* lives in ℝ (a real variable, a decimal, sqrt, …),
        ``"int"`` if only in ℤ/ℕ, None for bare literals."""
        found: set[str] = set()

        def walk(n: Any) -> None:
            if isinstance(n, (SymbolNode, GreekSymbolNode)):
                t = self.scope.types.get(n.name)
                if t in ("ℤ", "ℕ"):
                    found.add("int")
                elif t is not None and "→" not in t:
                    found.add("real")
                elif n.name in _CONSTANTS:
                    found.add("real")
            elif isinstance(n, NumberNode):
                if "." in n.value:
                    found.add("real")
            elif isinstance(n, (IntegralNode, LimitNode, MatrixNode, VectorNode)):
                found.add("real")
            elif isinstance(n, FunctionCallNode):
                fn = n.func.lower()
                if fn in ("sqrt", "exp", "ln", "log", "sin", "cos", "tan", "arctan", "sinh", "cosh", "diff", "derivative", "det", "tr", "dot"):
                    found.add("real")
                    return
                if fn in _INTEGER_CALLS:
                    found.add("int")
                    return
                t = self.scope.types.get(n.func, "")
                if "→" in t:
                    found.add("int" if t.endswith(("ℤ", "ℕ")) else "real")
                for a in n.args:
                    walk(a)
            elif isinstance(n, (BinaryOpNode, RelationNode)):
                walk(n.left)
                walk(n.right)
            elif isinstance(n, UnaryOpNode):
                walk(n.operand)

        walk(node)
        if "real" in found:
            return "real"
        return "int" if "int" in found else None

    @staticmethod
    def _has_division(node: Any) -> bool:
        if isinstance(node, BinaryOpNode):
            return node.op == "/" or _Expr._has_division(node.left) or _Expr._has_division(node.right)
        if isinstance(node, UnaryOpNode):
            return _Expr._has_division(node.operand)
        if isinstance(node, FunctionCallNode):
            return node.func.lower() not in _INTEGER_CALLS and any(_Expr._has_division(a) for a in node.args)
        return isinstance(node, NumberNode) and "." in node.value

    # -- printing -----------------------------------------------------------

    def show(self, node: ExprNode, prec: int = 0, tail: bool = False) -> str:
        """*node* at precedence *prec*.  A binder (∀, ∃, ∑) reaches as far right
        as it can, so it goes unparenthesised only at the *tail* of a formula:
        `A → ∀ x, P` reads as meant, `(∀ x, P) ∧ A` needs its parentheses."""
        if tail and prec <= _P_NOT and isinstance(node, (QuantifierNode, BinaryOpNode, UnaryOpNode)):
            self._tail = True
        else:
            self._tail = False
        text, own = self._show(node)
        if own == _P_BINDER and tail and prec <= _P_NOT:
            return text
        return f"({text})" if own < prec else text

    def _show(self, node: ExprNode) -> tuple[str, int]:
        if isinstance(node, NumberNode):
            if "." in node.value:
                return f"({node.value} : ℝ)", _P_ATOM
            return node.value, _P_ATOM
        if isinstance(node, (SymbolNode, GreekSymbolNode)):
            return self._symbol(node.name), _P_ATOM
        if isinstance(node, UnaryOpNode):
            if node.op in ("not", "\\neg", "~"):
                return f"¬{self.show(node.operand, _P_NOT, tail=self._tail)}", _P_NOT
            if node.op == "+":
                return self._show(node.operand)
            return f"-{self.show(node.operand, _P_ATOM)}", _P_NEG
        if isinstance(node, RelationNode):
            return self._relation(node)
        if isinstance(node, BinaryOpNode):
            return self._binary(node)
        if isinstance(node, QuantifierNode):
            return self._quantifier(node), _P_BINDER
        if isinstance(node, FunctionCallNode):
            return self._call(node)
        if isinstance(node, EmptySetNode):
            return "∅", _P_ATOM
        if isinstance(node, LimitNode):
            raise _Untranslatable(f"the limit {node}")
        if isinstance(node, IntegralNode):
            if node.lower is None or node.upper is None:
                raise _Untranslatable(f"the indefinite integral {node}")
            return self._integral(node), _P_APP
        if isinstance(node, MatrixNode):
            cols = {len(r) for r in node.rows}
            if len(cols) != 1:
                raise _Untranslatable(f"the ragged matrix {node}")
            body = "; ".join(", ".join(self.show(e) for e in row) for row in node.rows)
            return f"(!![{body}] : {_matrix_type(len(node.rows), cols.pop())})", _P_ATOM
        if isinstance(node, VectorNode):
            body = ", ".join(self.show(e) for e in node.elements)
            return f"(![{body}] : Fin {len(node.elements)} → ℝ)", _P_ATOM
        if isinstance(node, (RawMathNode, StringLiteralNode)):
            raise _Untranslatable(f"{node}")
        raise _Untranslatable(f"{node}")

    def _symbol(self, name: str) -> str:
        if name in self.scope.ops:
            return self.scope.ops[name]
        if name not in self.scope.types and name in _CONSTANTS:
            return _CONSTANTS[name] if name != "e" else "(Real.exp 1)"
        if name == "oo" and name not in self.scope.types:
            raise _Untranslatable("∞, which is not a real number")
        if name in ("Real", "Int", "Nat", "Rat", "Complex"):
            raise _Untranslatable(f"the set {name} used as a value")
        if name.lower() in ("true", "false") and name not in self.scope.types:
            return "True" if name.lower() == "true" else "False"
        if name.lower() == "contradiction" and name not in self.scope.types:
            return "False"
        return lean_name(name)

    def _relation(self, node: RelationNode) -> tuple[str, int]:
        op = _RELATIONS.get(node.op)
        if op is None:
            raise _Untranslatable(f"the relation {node.op}")
        # `lim(f, x, a) = L` is Mathlib's `Tendsto f (𝓝[≠] a) (𝓝 L)`.
        if op == "=" and isinstance(node.left, LimitNode) != isinstance(node.right, LimitNode):
            limit, value = (node.left, node.right) if isinstance(node.left, LimitNode) else (node.right, node.left)
            return self._tendsto(limit, value), _P_APP
        left, right = node.left, node.right
        if op in ("∈", "∉") and isinstance(right, SymbolNode) and right.name in ("Real", "Int", "Nat", "Rat", "Complex"):
            raise _Untranslatable(f"membership of the type {right.name}")
        return f"{self.show(left, _P_REL + 1)} {op} {self.show(right, _P_REL + 1)}", _P_REL

    @staticmethod
    def _has_integer_call(node: Any) -> bool:
        if isinstance(node, FunctionCallNode):
            return node.func.lower() in _INTEGER_CALLS or any(_Expr._has_integer_call(a) for a in node.args)
        if isinstance(node, (BinaryOpNode, RelationNode)):
            return _Expr._has_integer_call(node.left) or _Expr._has_integer_call(node.right)
        if isinstance(node, UnaryOpNode):
            return _Expr._has_integer_call(node.operand)
        return False

    def _tendsto(self, limit: LimitNode, value: ExprNode) -> str:
        var = lean_name(limit.var)
        inner = self.scope.child()
        inner.types[limit.var] = "ℝ"
        saved, self.scope = self.scope, inner
        try:
            body = self.show(limit.body)
        finally:
            self.scope = saved
        infinite = _infinity(limit.target)
        if infinite is not None:
            within = "Filter.atTop" if infinite > 0 else "Filter.atBot"
        else:
            target = self.show(limit.target, _P_APP + 1)
            within = {"+": f"(nhdsWithin {target} (Set.Ioi {target}))", "-": f"(nhdsWithin {target} (Set.Iio {target}))"}.get(
                limit.direction, f"(nhdsWithin {target} {{{self.show(limit.target)}}}ᶜ)"
            )
        tends = _infinity(value)
        if tends is not None:
            to = "Filter.atTop" if tends > 0 else "Filter.atBot"
        else:
            to = f"(nhds ({self.show(value)} : ℝ))"
        return f"Filter.Tendsto (fun {var} : ℝ => {body}) {within} {to}"

    def _binary(self, node: BinaryOpNode) -> tuple[str, int]:
        op = node.op
        tail = self._tail
        if op in _IMPLIES:
            return f"{self.show(node.left, _P_IMP + 1)} → {self.show(node.right, _P_IMP, tail=tail)}", _P_IMP
        if op in _IFF:
            return f"{self.show(node.left, _P_IFF + 1)} ↔ {self.show(node.right, _P_IFF + 1, tail=tail)}", _P_IFF
        if op in _AND:
            return f"{self.show(node.left, _P_AND + 1)} ∧ {self.show(node.right, _P_AND, tail=tail)}", _P_AND
        if op in _OR:
            return f"{self.show(node.left, _P_OR + 1)} ∨ {self.show(node.right, _P_OR, tail=tail)}", _P_OR
        if op in ("+", "-"):
            return f"{self.show(node.left, _P_ADD)} {op} {self.show(node.right, _P_ADD + 1)}", _P_ADD
        if op in ("*", "\\cdot", "/"):
            group_op = self._group_product(node)
            if group_op is not None:
                return group_op
            if op == "/" and self.kind(node) != "real" and not _is_matrix(self.scope, node.left):
                # Lemmata's `/` is exact; on ℕ and ℤ Lean's rounds down.
                return f"({self.show(node.left)} : ℝ) / {self.show(node.right, _P_MUL + 1)}", _P_MUL
            sym = "/" if op == "/" else "*"
            return f"{self.show(node.left, _P_MUL)} {sym} {self.show(node.right, _P_MUL + 1)}", _P_MUL
        if op in ("^", "**"):
            return self._power(node)
        if op in ("\\cup", "union"):
            return f"{self.show(node.left, _P_ADD)} ∪ {self.show(node.right, _P_ADD + 1)}", _P_ADD
        if op in ("\\cap", "intersect"):
            return f"{self.show(node.left, _P_MUL)} ∩ {self.show(node.right, _P_MUL + 1)}", _P_MUL
        if op in ("\\setminus", "setminus"):
            return f"{self.show(node.left, _P_ADD)} \\ {self.show(node.right, _P_ADD + 1)}", _P_ADD
        raise _Untranslatable(f"the operation {op}")

    def _group_product(self, node: BinaryOpNode) -> Optional[tuple[str, int]]:
        return None

    def _power(self, node: BinaryOpNode) -> tuple[str, int]:
        if _is_matrix(self.scope, node.left):
            if isinstance(node.right, (SymbolNode,)) and node.right.name == "T":
                return f"Matrix.transpose {self.show(node.left, _P_APP + 1)}", _P_APP
        exp = node.right
        if isinstance(exp, UnaryOpNode) and exp.op == "-" and isinstance(exp.operand, NumberNode) and exp.operand.value == "1":
            return f"{self.show(node.left, _P_APP + 1)}⁻¹", _P_INV
        base = self.show(node.left, _P_POW + 1)
        if isinstance(exp, UnaryOpNode) and exp.op == "-" and isinstance(exp.operand, NumberNode):
            return f"{base} ^ (-{exp.operand.value} : ℤ)", _P_POW
        if self._has_division(exp):
            return f"{base} ^ ({self.show(exp)} : ℝ)", _P_POW
        if any(self.scope.types.get(n) == "ℤ" for n in _names(exp)) and self.kind(node.left) != "real":
            # An integer exponent needs a base with inverses: zpow on ℝ.
            base = f"({self.show(node.left)} : ℝ)"
        return f"{base} ^ {self.show(exp, _P_POW)}", _P_POW

    def _quantifier(self, node: QuantifierNode) -> str:
        sym = "∀" if node.quantifier == "forall" else "∃"
        name = lean_name(node.var)
        inner = self.scope.child()
        saved = self.scope
        binder: str
        vt = node.var_type
        if vt is not None and vt in saved.types and saved.types[vt] == "Set ℝ":
            binder = f"{name} ∈ {lean_name(vt)}"
            inner.types[node.var] = "ℝ"
        elif vt is not None and vt in saved.carriers:
            binder = f"{name} : {saved.carriers[vt]}"
            inner.types[node.var] = saved.carriers[vt]
        else:
            t = lean_type(vt)
            if t is None:
                raise _Untranslatable(f"a quantifier over {vt}")
            binder = f"{name} : {t}"
            inner.types[node.var] = t
        self.scope = inner
        try:
            body = self.show(node.formula, _P_BINDER, tail=True)
        finally:
            self.scope = saved
        return f"{sym} {binder}, {body}"

    def _call(self, node: FunctionCallNode) -> tuple[str, int]:
        fn = node.func
        low = fn.lower()
        args = node.args
        n = len(args)

        if fn in self.scope.ops:
            return self._structure_call(self.scope.ops[fn], args)
        if fn in self.scope.defs or fn in self.scope.types:
            return self._apply(lean_name(fn), args), _P_APP

        if low == "abs" and n == 1:
            inner = self.show(args[0])
            return (f"|{inner}|" if "|" not in inner else f"abs ({inner})"), _P_ATOM
        if low == "even" and n == 1:
            return self._apply("Even", args), _P_APP
        if low == "odd" and n == 1:
            return self._apply("Odd", args), _P_APP
        if low == "multipleof" and n == 2:
            return f"({self.show(args[1])} : ℤ) ∣ {self.show(args[0], _P_REL + 1)}", _P_REL
        if low == "divides" and n == 2:
            return f"({self.show(args[0])} : ℤ) ∣ {self.show(args[1], _P_REL + 1)}", _P_REL
        if low in ("congruent", "cong") and n == 3:
            a, b, m = (self.show(x, _P_REL + 1) for x in args)
            return f"({self.show(args[0])} : ℤ) ≡ {b} [ZMOD {m}]", _P_REL
        if low == "prime" and n == 1:
            return f"Prime ({self.show(args[0])} : ℤ)", _P_APP
        if low == "positive" and n == 1:
            return f"0 < {self.show(args[0], _P_REL + 1)}", _P_REL
        if low == "nonnegative" and n == 1:
            return f"0 ≤ {self.show(args[0], _P_REL + 1)}", _P_REL
        if low == "negative" and n == 1:
            return f"{self.show(args[0], _P_REL + 1)} < 0", _P_REL
        if low == "nonzero" and n == 1:
            return f"{self.show(args[0], _P_REL + 1)} ≠ 0", _P_REL
        if low == "floor" and n == 1:
            return f"⌊({self.show(args[0])} : ℝ)⌋", _P_ATOM
        if low == "ceil" and n == 1:
            return f"⌈({self.show(args[0])} : ℝ)⌉", _P_ATOM
        if low == "sum" and n == 4 and isinstance(args[0], (SymbolNode, GreekSymbolNode)):
            return self._sum(args), _P_BINDER
        if low in ("gcd", "lcm") and n == 2:
            return f"{low} ({self.show(args[0])} : ℤ) {self.show(args[1], _P_APP + 1)}", _P_APP
        if low == "factorial" and n == 1:
            return self._apply("Nat.factorial", args), _P_APP
        if low in _FUNCTIONS and (n == 1 or low in ("max", "min")):
            return self._apply(_FUNCTIONS[low], args), _P_APP
        if low in ("diff", "derivative") and n in (2, 3) and isinstance(args[1], (SymbolNode, GreekSymbolNode)):
            return self._derivative(args), _P_APP
        if low == "det" and n == 1:
            return self._apply("Matrix.det", args), _P_APP
        if low == "tr" and n == 1:
            return self._apply("Matrix.trace", args), _P_APP
        if low == "transpose" and n == 1:
            return self._apply("Matrix.transpose", args), _P_APP
        if low in ("inv", "inverse") and n == 1:
            return f"{self.show(args[0], _P_APP + 1)}⁻¹", _P_INV
        if low == "orthogonal" and n == 2:
            return f"{self.show(args[0], _P_MUL + 1)} ⬝ᵥ {self.show(args[1], _P_MUL + 1)} = 0", _P_REL
        if low == "dot" and n == 2:
            return f"{self.show(args[0], _P_MUL + 1)} ⬝ᵥ {self.show(args[1], _P_MUL + 1)}", _P_MUL
        if low in _STRUCTURES or low in ("subgroup", "normalsubgroup"):
            raise _Untranslatable(f"the structure {fn}(…) here")
        if low in _KNOWN_CALLS or low in _FUNCTIONS:
            raise _Untranslatable(f"{fn} with {n} argument(s)")
        # Anything else is an abstract function or predicate the statement binds.
        return self._apply(lean_name(fn), args), _P_APP

    def _derivative(self, args: list[ExprNode]) -> str:
        from aether.engine.context import substitute_mapping

        body, var = args[0], args[1].name  # type: ignore[attr-defined]
        # `Let u = x^2 - y^2` then `diff(u, x)`: the derivative of what u stands for.
        for _ in range(8):
            names = _names(body) & set(self.scope.lets)
            if not names:
                break
            body = substitute_mapping(body, {k: self.scope.lets[k] for k in names})
        inner = self.scope.child()
        inner.types[var] = "ℝ"
        saved, self.scope = self.scope, inner
        try:
            fn = f"(fun {lean_name(var)} : ℝ => {self.show(body)})"
        finally:
            self.scope = saved
        point = lean_name(var)
        if len(args) == 3:
            return f"iteratedDeriv {self.show(args[2], _P_APP + 1)} {fn} {point}"
        return f"deriv {fn} {point}"

    def _integral(self, node: IntegralNode) -> str:
        inner = self.scope.child()
        inner.types[node.var] = "ℝ"
        saved, self.scope = self.scope, inner
        try:
            body = self.show(node.body)
        finally:
            self.scope = saved
        low = self.show(node.lower, _P_APP + 1)  # type: ignore[arg-type]
        high = self.show(node.upper, _P_APP + 1)  # type: ignore[arg-type]
        return f"intervalIntegral (fun {lean_name(node.var)} : ℝ => {body}) {low} {high} MeasureTheory.volume"

    def _apply(self, head: str, args: list[ExprNode]) -> str:
        if not args:
            return head
        return head + " " + " ".join(self.show(a, _P_APP + 1) for a in args)

    def _structure_call(self, op: str, args: list[ExprNode]) -> tuple[str, int]:
        if op == "*" and len(args) == 2:
            return f"{self.show(args[0], _P_MUL)} * {self.show(args[1], _P_MUL + 1)}", _P_MUL
        if op == "+" and len(args) == 2:
            return f"{self.show(args[0], _P_ADD)} + {self.show(args[1], _P_ADD + 1)}", _P_ADD
        if op == "⁻¹" and len(args) == 1:
            return f"{self.show(args[0], _P_APP + 1)}⁻¹", _P_INV
        if op == "-" and len(args) == 1:
            return f"-{self.show(args[0], _P_ATOM)}", _P_NEG
        raise _Untranslatable(f"the structure operation {op} with {len(args)} argument(s)")

    def _sum(self, args: list[ExprNode]) -> str:
        var_node, low, high, body = args
        var = var_node.name  # type: ignore[attr-defined]
        # ℕ unless a bound can be negative: an integer variable, or a minus sign.
        negative = any(isinstance(b, UnaryOpNode) and b.op == "-" for b in (low, high))
        integer = any(self.scope.types.get(n) == "ℤ" for n in _names(low) | _names(high))
        index_type = "ℤ" if negative or integer else "ℕ"
        inner = self.scope.child()
        inner.types[var] = index_type
        saved, self.scope = self.scope, inner
        try:
            body_text = self.show(body, _P_ADD)
        finally:
            self.scope = saved
        return f"∑ {lean_name(var)} ∈ Finset.Icc ({self.show(low)} : {index_type}) {self.show(high, _P_APP + 1)}, {body_text}"


def _infinity(node: Any) -> Optional[int]:
    """+1 for ∞, -1 for -∞, else None."""
    if isinstance(node, SymbolNode) and node.name == "oo":
        return 1
    if isinstance(node, UnaryOpNode) and node.op == "-" and _infinity(node.operand) == 1:
        return -1
    return None


def _matrix_type(rows: int, cols: int) -> str:
    return f"Matrix (Fin {rows}) (Fin {cols}) ℝ"


def _is_matrix(scope: "_Scope", node: Any) -> bool:
    if isinstance(node, MatrixNode):
        return True
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        return scope.types.get(node.name, "").startswith("Matrix")
    return False


def _names(node: Any) -> set[str]:
    """Every symbol name in *node*, bound or not."""
    out: set[str] = set()
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        out.add(node.name)
    elif isinstance(node, list):
        for item in node:
            out |= _names(item)
    elif isinstance(node, (ExprNode, StatementNode)):
        for value in vars(node).values():
            if isinstance(value, (ExprNode, StatementNode, list)):
                out |= _names(value)
    return out


# ---------------------------------------------------------------------------
# Free names: what a statement must bind for its proof to elaborate
# ---------------------------------------------------------------------------


def _free_in_expr(node: Any, bound: set[str], out: dict[str, Any], sites: Optional[dict[str, list[list[ExprNode]]]] = None) -> None:
    """Free variables (name → None) and called functions (name → arity) in *node*;
    *sites* collects each called function's argument lists."""
    if sites is None:
        sites = {}
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        if node.name not in bound and node.name != "<prev>":
            out.setdefault(node.name, None)
    elif isinstance(node, QuantifierNode):
        if node.var_type and not lean_type(node.var_type):
            out.setdefault(node.var_type, None)
        _free_in_expr(node.formula, bound | {node.var}, out, sites)
    elif isinstance(node, LimitNode):
        _free_in_expr(node.body, bound | {node.var}, out, sites)
        _free_in_expr(node.target, bound, out, sites)
    elif isinstance(node, IntegralNode):
        _free_in_expr(node.body, bound | {node.var}, out, sites)
        for part in (node.lower, node.upper):
            if part is not None:
                _free_in_expr(part, bound, out, sites)
    elif isinstance(node, FunctionCallNode):
        args = node.args
        if node.func.lower() == "sum" and len(args) == 4 and isinstance(args[0], (SymbolNode, GreekSymbolNode)):
            _free_in_expr(args[1], bound, out, sites)
            _free_in_expr(args[2], bound, out, sites)
            _free_in_expr(args[3], bound | {args[0].name}, out, sites)
            return
        if node.func not in bound:
            out[f"{node.func}()"] = len(args)
            sites.setdefault(node.func, []).append(args)
        for a in args:
            _free_in_expr(a, bound, out, sites)
    elif isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode):
                _free_in_expr(value, bound, out, sites)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ExprNode):
                        _free_in_expr(item, bound, out, sites)
                    elif isinstance(item, list):
                        for x in item:
                            _free_in_expr(x, bound, out, sites)


def _declared_types(exprs: list[ExprNode], stmts: list[StatementNode], scope: "_Scope") -> dict[str, str]:
    """Every name's declared Lean type anywhere in a block, bound or not (a guide, not a scope)."""
    out: dict[str, str] = {}

    def lean_of(raw: Optional[str]) -> Optional[str]:
        if raw is None:
            return None
        return scope.carriers.get(raw) or lean_type(raw)

    def walk(node: Any) -> None:
        if isinstance(node, QuantifierNode):
            t = lean_of(node.var_type)
            if t:
                out.setdefault(node.var, t)
        if isinstance(node, ExprNode):
            for value in vars(node).values():
                if isinstance(value, ExprNode):
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

    def stmts_walk(items: list[StatementNode]) -> None:
        for st in items:
            if isinstance(st, VarDeclNode):
                t = lean_of(st.type_name)
                for v in st.variables:
                    if t:
                        out.setdefault(v, t)
            elif isinstance(st, ObtainNode):
                t = lean_of(st.type_name)
                if t:
                    out.setdefault(st.variable, t)
            elif isinstance(st, SubProofNode):
                stmts_walk(st.statements)

    for e in exprs:
        walk(e)
    stmts_walk(stmts)
    return out


def _result_carrier(fn: str, exprs: list[ExprNode], scope: "_Scope") -> Optional[str]:
    """The structure *fn*'s values live in: what operation they are fed to, or
    which identity they are compared with (`f(e) = eH`, `star(f(x), f(y))`)."""
    found: list[str] = []

    def is_call(n: Any) -> bool:
        return isinstance(n, FunctionCallNode) and n.func == fn

    def walk(n: Any) -> None:
        if isinstance(n, FunctionCallNode) and n.func in scope.op_carrier and any(is_call(a) for a in n.args):
            found.append(scope.op_carrier[n.func])
        if isinstance(n, RelationNode):
            for a, b in ((n.left, n.right), (n.right, n.left)):
                if is_call(a) and isinstance(b, (SymbolNode, FunctionCallNode)):
                    name = b.name if isinstance(b, SymbolNode) else b.func
                    if name in scope.op_carrier:
                        found.append(scope.op_carrier[name])
        if isinstance(n, ExprNode):
            for value in vars(n).values():
                if isinstance(value, ExprNode):
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

    for e in exprs:
        walk(e)
    return found[0] if found else None


def _guess_type(arg: ExprNode, hints: dict[str, str], scope: "_Scope") -> str:
    """The Lean type an argument most likely has, for typing an abstract function."""
    if isinstance(arg, (SymbolNode, GreekSymbolNode)):
        return hints.get(arg.name, "ℝ") if "→" not in hints.get(arg.name, "") else "ℝ"
    carriers = list(scope.carriers.values())
    if isinstance(arg, (FunctionCallNode, SymbolNode)):
        name = arg.func if isinstance(arg, FunctionCallNode) else arg.name
        if name in scope.op_carrier:
            return scope.op_carrier[name]
    if isinstance(arg, BinaryOpNode) and arg.op in ("*", "\\cdot"):
        for side in (arg.left, arg.right):
            t = _guess_type(side, hints, scope)
            if t in carriers:
                return t
    if isinstance(arg, BinaryOpNode) and arg.op in ("^",):
        return _guess_type(arg.left, hints, scope)
    if isinstance(arg, NumberNode) and "." not in arg.value:
        return "ℝ"
    return "ℝ"


def _statement_exprs(stmt: StatementNode) -> list[ExprNode]:
    if isinstance(stmt, VarDeclNode):
        return [stmt.condition] if stmt.condition is not None else []
    if isinstance(stmt, AssumeNode):
        return [stmt.proposition]
    if isinstance(stmt, ObtainNode):
        return [stmt.condition]
    if isinstance(stmt, StepNode):
        return [e for e in (stmt.lhs, stmt.rhs) if e is not None]
    if isinstance(stmt, DeduceNode):
        return [e for e in (stmt.premise, stmt.claim, stmt.witness) if e is not None]
    if isinstance(stmt, SubProofNode):
        return [stmt.case_condition] if stmt.case_condition is not None else []
    return []


def _declared(stmts: list[StatementNode]) -> set[str]:
    """Names a block introduces itself (Given, Let, Obtain, definitions), at any depth."""
    out: set[str] = set()
    for s in stmts:
        if isinstance(s, VarDeclNode):
            out.update(s.variables)
        elif isinstance(s, ObtainNode):
            out.add(s.variable)
        elif isinstance(s, FuncDefNode):
            out.add(s.name)
        elif isinstance(s, SubProofNode):
            out |= _declared(s.statements)
            if s.label in ("Base case", "Inductive step") and isinstance(s.case_condition, RelationNode):
                if isinstance(s.case_condition.left, (SymbolNode, GreekSymbolNode)):
                    out.add(s.case_condition.left.name)
    return out


def _all_exprs(stmts: list[StatementNode]) -> list[ExprNode]:
    out: list[ExprNode] = []
    for s in stmts:
        out.extend(_statement_exprs(s))
        if isinstance(s, FuncDefNode):
            pass  # a definition's parameters are its own
        if isinstance(s, SubProofNode):
            out.extend(_all_exprs(s.statements))
    return out


# ---------------------------------------------------------------------------
# Goals: a statement's binders, peeled one intro at a time
# ---------------------------------------------------------------------------


@dataclass
class _Binder:
    kind: str  # "var" | "hyp"
    name: str = ""
    type: Optional[str] = None
    prop: Optional[ExprNode] = None
    quant: Optional[QuantifierNode] = None
    #: A `Let δ = e` the statement binds as `∀ δ, δ = e → …`.
    from_let: bool = False


def _peel(claim: ExprNode, defs: dict[str, FuncDefNode]) -> tuple[list[_Binder], ExprNode]:
    """∀s and ⇒s in front of *claim*, unfolding a defined head (`Continuous(g, 2)`)."""
    from aether.engine.context import substitute_mapping  # the engine's capture-avoiding substitution

    binders: list[_Binder] = []
    target = claim
    for _ in range(64):
        if isinstance(target, QuantifierNode) and target.quantifier == "forall":
            binders.append(_Binder("var", target.var, target.var_type, quant=target))
            target = target.formula
        elif isinstance(target, BinaryOpNode) and target.op in _IMPLIES:
            binders.append(_Binder("hyp", prop=target.left))
            target = target.right
        elif (
            isinstance(target, FunctionCallNode)
            and target.func in defs
            and len(defs[target.func].params) == len(target.args)
            and _peelable(defs[target.func].body)
        ):
            fn = defs[target.func]
            target = substitute_mapping(fn.body, dict(zip(fn.params, target.args)))
        else:
            break
    return binders, target


def _peelable(body: ExprNode) -> bool:
    return (isinstance(body, QuantifierNode) and body.quantifier == "forall") or (
        isinstance(body, BinaryOpNode) and body.op in _IMPLIES
    )


def _wrap(binders: list[_Binder], target: ExprNode) -> ExprNode:
    out = target
    for b in reversed(binders):
        if b.kind == "var":
            out = QuantifierNode(quantifier="forall", var=b.name, var_type=b.type, formula=out)
        else:
            out = BinaryOpNode(op="=>", left=b.prop, right=out)  # type: ignore[arg-type]
    return out


# ---------------------------------------------------------------------------
# The exporter
# ---------------------------------------------------------------------------


_COMBINE = {
    ("=", "="): "=", ("=", "<"): "<", ("<", "="): "<", ("<", "<"): "<", ("=", "≤"): "≤", ("≤", "="): "≤",
    ("≤", "≤"): "≤", ("≤", "<"): "<", ("<", "≤"): "<", ("=", ">"): ">", (">", "="): ">", (">", ">"): ">",
    ("=", "≥"): "≥", ("≥", "="): "≥", ("≥", "≥"): "≥", ("≥", ">"): ">", (">", "≥"): ">",
}


@dataclass
class _Fact:
    """A `have` the block made: its name and its statement's Lean text."""

    name: str
    text: str
    kind: str = ""


class LeanExporter:
    def __init__(
        self,
        source: str,
        results: Optional[dict[int, Any]] = None,
        namespace: str = "Lemmata",
    ):
        self.source_lines = source.splitlines()
        self.results = results or {}
        self.namespace = namespace
        self.out: list[str] = []
        #: The source line each Lean line came from (None for Lean's own scaffolding).
        self.owner: list[Optional[int]] = []
        self.untranslated: list[dict[str, Any]] = []
        self.used_names: set[str] = set()
        #: The algebra the current theorem works in ("group", "ring"), for hints.
        self.algebra: Optional[str] = None
        #: The last inferred statement's conclusion before its `Let`s were unfolded.
        self.as_written: Optional[ExprNode] = None

    # -- output ---------------------------------------------------------------

    def emit(self, text: str, line: Optional[int] = None) -> None:
        self.out.append(text)
        self.owner.append(line)

    # -- the document -----------------------------------------------------------

    def export(self, doc: DocumentNode) -> LeanExport:
        self.emit("import Mathlib")
        self.emit("")
        self.emit("/-! Each step tries the Lean tactic for the rule Lemmata's kernel checked it")
        self.emit("    by (`first | ring | sorry`); where that tactic cannot finish it, the step")
        self.emit("    falls back to `sorry`.  The comment beside it names the rule. -/")
        self.emit("")
        self.emit(f"namespace {self.namespace}")
        self.emit("")

        scope = _Scope()
        top = sorted(doc.statements, key=lambda s: s.line or 0)
        defs = [s for s in top if isinstance(s, FuncDefNode)]
        for imp in [s for s in top if isinstance(s, ImportNode)]:
            self.emit(f'-- import "{imp.path}": its results are not restated here', imp.line)
        for d in defs:
            self._definition(d, scope)
        if defs:
            self.emit("")

        theorem_lines = self._header_lines(r"(theorem|lemma|proposition)\b")
        qed_lines = self._header_lines(r"qed\b")
        claim_lines = self._header_lines(r"claim\s*:")
        # Statements at the top level that are not definitions: a scratchpad.
        loose = [s for s in top if not isinstance(s, (FuncDefNode, ImportNode))]
        if loose:
            self._block_decl(None, None, loose, scope, header_line=None, qed_line=None, claim_line=None)
        for i, thm in enumerate(doc.theorems):
            t_line = theorem_lines[i] if i < len(theorem_lines) else None
            stmts = thm.proof.statements if thm.proof else []
            after = [ln for ln in qed_lines if t_line is None or ln > t_line]
            nxt = theorem_lines[i + 1] if i + 1 < len(theorem_lines) else None
            q_line = after[0] if after and (nxt is None or after[0] < nxt) else None
            c_after = [ln for ln in claim_lines if t_line is not None and ln > t_line and (nxt is None or ln < nxt)]
            self._block_decl(thm, thm.claim, stmts, scope, t_line, q_line, c_after[0] if c_after else None)

        self.emit(f"end {self.namespace}")
        # Rows in Lean's order: each run of Lean lines from one source line.
        rows: list[dict[str, Any]] = []
        for n, ln in enumerate(self.owner, start=1):
            if rows and rows[-1]["line"] == ln and rows[-1]["lean_to"] == n - 1:
                rows[-1]["lean_to"] = n
                continue
            text = self.source_lines[ln - 1].rstrip() if ln is not None and 0 < ln <= len(self.source_lines) else ""
            result = self.results.get(ln) if ln is not None else None
            status = getattr(result.status, "value", None) if result is not None else None
            rows.append({"line": ln, "source": text, "lean_from": n, "lean_to": n, "status": status})
        placed = {u["what"] for u in self.untranslated if u["line"] is not None}
        untranslated = [u for u in self.untranslated if u["line"] is not None or u["what"] not in placed]
        return LeanExport(lean="\n".join(self.out) + "\n", rows=rows, untranslated=untranslated)

    def _header_lines(self, pattern: str) -> list[int]:
        rx = re.compile(r"\s*" + pattern, re.IGNORECASE)
        return [i + 1 for i, text in enumerate(self.source_lines) if rx.match(text)]

    # -- definitions --------------------------------------------------------

    def _definition(self, d: FuncDefNode, scope: _Scope, indent: str = "", local: bool = False) -> None:
        params = []
        inner = scope.child()
        for p in d.params:
            t = self._param_type(p, d.body)
            params.append((p, t))
            inner.types[p] = t
        is_prop = _is_proposition(d.body)
        expr = _Expr(inner, self.untranslated, d.line)
        body = expr.prop(d.body) if is_prop else expr.term(d.body)
        result = "Prop" if is_prop else self._value_type(d.body, inner)
        name = lean_name(d.name)
        if local:
            binders = " ".join(f"({lean_name(p)} : {t})" for p, t in params)
            self.emit(f"{indent}let {name} : {' → '.join([t for _, t in params] + [result])} := fun {binders} => {body}", d.line)
        else:
            binders = " ".join(f"({lean_name(p)} : {t})" for p, t in params)
            kw = "def" if is_prop else "noncomputable def"
            self.emit(f"{indent}{kw} {name} {binders} : {result} :=", d.line)
            self.emit(f"{indent}  {body}", d.line)
        scope.defs[d.name] = d
        scope.types.pop(d.name, None)

    def _sequence_params(self, stmts: list[StatementNode], claim: Optional[ExprNode], scope: _Scope) -> list[str]:
        """A sequence the question defines, bound by the statement with its definitions.

        ``Given u : Nat -> Int`` with ``Assume u1: u(1) = 2`` and a recurrence,
        and a claim about u: the checker reads the assumptions as u's
        definition, and the theorem proved is "for u so defined, the claim".
        In Lean that is ``theorem t (u : ℕ → ℤ) (u1 : u 1 = 2) (rec : …) : claim``.
        The claim mentions u, so u cannot wait to be introduced by the proof.
        """
        if claim is None:
            return []
        claim_free: dict[str, Any] = {}
        _free_in_expr(claim, set(), claim_free)
        called = {k[:-2] for k in claim_free if k.endswith("()")}
        params: list[str] = []
        functions: set[str] = set()
        for s in stmts:
            if not (isinstance(s, VarDeclNode) and s.condition is None and s.type_name):
                continue
            if not split_function_type(s.type_name) or not set(s.variables) & called:
                continue
            t = lean_type(s.type_name)
            if t is None:
                continue
            for v in s.variables:
                scope.types[v] = t
                params.append(f"({lean_name(v)} : {t})")
                functions.add(v)
            s._lean_structure = True  # type: ignore[attr-defined]
        for s in stmts:
            if not isinstance(s, AssumeNode) or not functions:
                continue
            prop_free: dict[str, Any] = {}
            _free_in_expr(s.proposition, set(), prop_free)
            plain = {k[:-2] if k.endswith("()") else k for k in prop_free}
            if not plain & functions or plain - functions - set(_CONSTANTS):
                continue
            text = _Expr(scope, self.untranslated, s.line).prop(s.proposition)
            params.append(f"({self._hyp_name(s.label, s.line)} : {text})")
            s._lean_structure = True  # type: ignore[attr-defined]
        return params

    def _param_type(self, param: str, body: ExprNode) -> str:
        arity = _called_arity(body, param)
        if arity is not None:
            return " → ".join(["ℝ"] * (arity + 1))
        if _used_in_integer_call(body, param):
            return "ℤ"
        return "ℝ"

    def _value_type(self, body: ExprNode, scope: _Scope) -> str:
        return "ℤ" if _Expr(scope, [], None).kind(body) == "int" else "ℝ"

    # -- a theorem, or the top-level scratchpad --------------------------------

    def _block_decl(
        self,
        thm: Optional[TheoremNode],
        claim: Optional[ExprNode],
        stmts: list[StatementNode],
        outer: _Scope,
        header_line: Optional[int],
        qed_line: Optional[int],
        claim_line: Optional[int],
    ) -> None:
        scope = outer.child()
        name = self._fresh(slug(thm.name) if thm and thm.name else None)
        params, structure_rows = self._structure_params(stmts, scope)
        params += self._sequence_params(stmts, claim, scope)
        self.algebra = next((p.split("[")[1].split()[0] for p in params if "[" in p and "Subgroup" not in p and ".Normal" not in p), None)
        # Everything the statement and proof use but never introduce is bound
        # by the statement: an abstract `f`, a predicate `P`, an undeclared `x`.
        declared = _declared(stmts)
        free: dict[str, Any] = {}
        sites: dict[str, list[list[ExprNode]]] = {}
        exprs = ([claim] if claim is not None else []) + _all_exprs(stmts)
        for e in exprs:
            _free_in_expr(e, set(), free, sites)
        hints = _declared_types(exprs, stmts, scope)
        local_defs = {s.name for s in stmts if isinstance(s, FuncDefNode)} | _nested_defs(stmts)
        for key, arity in free.items():
            plain = key[:-2] if key.endswith("()") else key
            if plain in declared or plain in scope.defs or plain in scope.ops or plain in scope.carriers or plain in local_defs:
                continue
            if key.endswith("()"):
                if plain.lower() in _KNOWN_CALLS or plain in scope.types:
                    continue
                # An abstract function's type, from what it is applied to: a
                # homomorphism of G takes (and here returns) elements of G.
                arg_types = ["ℝ"] * arity
                for call in sites.get(plain, [])[:1]:
                    arg_types = [_guess_type(a, hints, scope) for a in call]
                carrier = _result_carrier(plain, exprs, scope) or next(
                    (t for t in arg_types if t in scope.carriers.values()), None
                )
                result = "Prop" if plain[:1].isupper() else (carrier or "ℝ")
                t = " → ".join(arg_types + [result]) if arity else result
                params.append(f"({lean_name(plain)} : {t})")
                scope.types[plain] = t
            else:
                if plain in _CONSTANTS or plain == "oo" or plain.lower() in ("true", "false", "contradiction"):
                    continue
                if plain in ("Real", "Int", "Nat", "Rat", "Complex"):
                    continue
                if plain not in scope.types:
                    params.append(f"({lean_name(plain)} : ℝ)")
                    scope.types[plain] = "ℝ"

        if claim is not None:
            goal = claim
        else:
            goal = self._infer_statement(stmts, scope, toplevel=True)
        expr = _Expr(scope, self.untranslated, claim_line or header_line)
        goal_text = expr.prop(goal) if goal is not None else "True"
        as_written = self.as_written if claim is None else None
        if claim is None and "sorry" in goal_text:
            # What a claim-less proof shows has no Lean statement: say nothing false.
            goal, goal_text, as_written = None, "True", None
        kw = f"theorem {name}" if name else "example"
        binders = (" " + " ".join(params)) if params else ""
        line_for_header = header_line if header_line is not None else (stmts[0].line if stmts and not claim else None)
        if thm is not None and thm.name:
            self.emit(f"/-- {thm.name} -/", header_line)
        self.emit(f"{kw}{binders} :", line_for_header)
        self.emit(f"    {goal_text} := by", claim_line if claim_line is not None else line_for_header)
        for line, text in structure_rows:
            self.emit(f"  {text}", line)

        binders_list, target = _peel(goal, scope.defs) if goal is not None else ([], None)
        state = _GoalState(goal, binders_list, target)
        state.as_written = as_written
        facts = self._block(stmts, scope, "  ", state)
        self._close(state, facts, scope, "  ", qed_line)
        self.emit("")

    def _fresh(self, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        candidate, i = name, 2
        while candidate in self.used_names:
            candidate, i = f"{name}_{i}", i + 1
        self.used_names.add(candidate)
        return candidate

    def _structure_params(self, stmts: list[StatementNode], scope: _Scope) -> tuple[list[str], list[tuple[int, str]]]:
        """`Assume Group(G, op, e, inv)` → `{G : Type*} [Group G]`, and op/e/inv as `*`/`1`/`⁻¹`."""
        params: list[str] = []
        rows: list[tuple[int, str]] = []
        for s in stmts:
            if not isinstance(s, AssumeNode) or not isinstance(s.proposition, FunctionCallNode):
                continue
            call = s.proposition
            low = call.func.lower()
            names = [a.name if isinstance(a, (SymbolNode, GreekSymbolNode)) else None for a in call.args]
            if low in _STRUCTURES and names and names[0]:
                carrier = names[0]
                params.append(f"{{{lean_name(carrier)} : Type*}} [{_STRUCTURES[low]} {lean_name(carrier)}]")
                scope.carriers[carrier] = lean_name(carrier)
                if low in ("group", "abeliangroup"):
                    roles = dict(zip(("op", "e", "inv"), names[1:4] + [None] * 3))
                    spell = {"op": "*", "e": "1", "inv": "⁻¹"}
                    for role, nm in roles.items():
                        if nm:
                            scope.ops[nm] = spell[role]
                            scope.op_carrier[nm] = lean_name(carrier)
                    words = ", ".join(f"{nm} is {spell[r]}" for r, nm in roles.items() if nm)
                else:
                    roles = dict(zip(("add", "mul", "zero", "one", "neg", "inv"), names[1:7] + [None] * 6))
                    spell = {"add": "+", "mul": "*", "zero": "0", "one": "1", "neg": "-", "inv": "⁻¹"}
                    for role, nm in roles.items():
                        if nm:
                            scope.ops[nm] = spell[role]
                            scope.op_carrier[nm] = lean_name(carrier)
                    words = ", ".join(f"{nm} is {spell[r]}" for r, nm in roles.items() if nm)
                text = f"-- {carrier} is a {_STRUCTURES[low]}" + (f": {words}" if words else "")
                rows.append((s.line, text))  # type: ignore[arg-type]
                s._lean_structure = True  # type: ignore[attr-defined]
            elif low in ("subgroup", "normalsubgroup") and len(names) >= 2 and names[0] and names[1] in scope.carriers:
                params.append(f"({lean_name(names[0])} : Subgroup {lean_name(names[1])})")
                if low == "normalsubgroup":
                    params.append(f"[{lean_name(names[0])}.Normal]")
                scope.types[names[0]] = f"Subgroup {lean_name(names[1])}"
                scope.carriers[names[0]] = f"↥{lean_name(names[0])}"
                rows.append((s.line, f"-- {names[0]} is a {'normal ' if low == 'normalsubgroup' else ''}subgroup of {names[1]}"))  # type: ignore[arg-type]
                s._lean_structure = True  # type: ignore[attr-defined]
        return params, rows

    # -- inferring what a block proves -----------------------------------------

    def _infer_statement(self, stmts: list[StatementNode], scope: _Scope, toplevel: bool = False) -> Optional[ExprNode]:
        """What a claim-less block proves: ∀ its Givens, its Assumptions ⇒ its last conclusion."""
        from aether.engine.context import substitute_mapping

        self.as_written = None
        binders: list[_Binder] = []
        lets: dict[str, ExprNode] = {}
        bound: set[str] = set()
        for s in stmts:
            if getattr(s, "_lean_structure", False):
                continue
            if isinstance(s, VarDeclNode):
                cond = s.condition
                if len(s.variables) == 1 and isinstance(cond, RelationNode) and cond.op == "=" and _is_var(cond.left, s.variables[0]):
                    v = s.variables[0]
                    if isinstance(cond.right, (MatrixNode, VectorNode)):
                        # A named matrix keeps its value in the statement (it carries its type).
                        lets[v] = substitute_mapping(cond.right, lets)
                        continue
                    t = "Int" if _Expr(scope, [], None).kind(cond.right) == "int" else "Real"
                    binders.append(_Binder("var", v, t, from_let=True))
                    binders.append(_Binder("hyp", prop=substitute_mapping(cond, lets), from_let=True))
                    bound.add(v)
                    continue
                for v in s.variables:
                    binders.append(_Binder("var", v, None if s.type_name == "Real" and cond is not None and not _is_typed(s) else s.type_name))
                    bound.add(v)
                if cond is not None:
                    binders.append(_Binder("hyp", prop=substitute_mapping(cond, lets)))
            elif isinstance(s, AssumeNode):
                binders.append(_Binder("hyp", prop=substitute_mapping(s.proposition, lets)))
        from aether.engine.context import collect_free_symbols

        conclusion = self._last_conclusion(stmts)
        self.as_written = None
        if conclusion is None:
            return _wrap(binders, SymbolNode(name="True")) if binders else None
        written = conclusion
        conclusion = substitute_mapping(conclusion, lets)
        inner = _declared(stmts) - bound - set(lets)
        if collect_free_symbols(conclusion) & inner:
            return _wrap(binders, SymbolNode(name="True"))
        hyps_ok = all(not (collect_free_symbols(b.prop) & inner) for b in binders if b.kind == "hyp")  # type: ignore[arg-type]
        if not hyps_ok:
            return _wrap([b for b in binders if b.kind == "var"], SymbolNode(name="True"))
        # The proof names its matrices with `set`, which Lean unfolds, so the
        # conclusion as written closes the goal too.
        self.as_written = written if lets else None
        return _wrap(binders, conclusion)

    def _last_conclusion(self, stmts: list[StatementNode]) -> Optional[ExprNode]:
        chain_head: Optional[ExprNode] = None
        chain_rel: Optional[str] = None
        last: Optional[ExprNode] = None
        for s in stmts:
            if isinstance(s, StepNode) and s.relation:
                rel = _RELATIONS.get(s.relation, s.relation)
                if s.lhs is not None:
                    chain_head, chain_rel = s.lhs, s.relation
                    last = RelationNode(op=s.relation, left=s.lhs, right=s.rhs)
                elif chain_head is not None:
                    combined = _COMBINE.get((_RELATIONS.get(chain_rel or "", ""), rel))
                    if combined is None:
                        last = None
                        chain_head = None
                        continue
                    chain_rel = {v: k for k, v in _RELATIONS.items() if k in ("=", "<", ">", "<=", ">=")}.get(combined, combined)
                    last = RelationNode(op=chain_rel, left=chain_head, right=s.rhs)
            elif isinstance(s, StepNode):
                last, chain_head = s.rhs, None
            elif isinstance(s, DeduceNode):
                if isinstance(s.claim, RelationNode) and isinstance(s.claim.left, SymbolNode) and s.claim.left.name == "<prev>":
                    if chain_head is not None:
                        combined = _COMBINE.get((_RELATIONS.get(chain_rel or "", ""), _RELATIONS.get(s.claim.op, "")))
                        if combined is not None:
                            chain_rel = {"=": "=", "<": "<", ">": ">", "≤": "<=", "≥": ">="}[combined]
                            last = RelationNode(op=chain_rel, left=chain_head, right=s.claim.right)
                    continue
                last, chain_head = s.claim, None
            elif isinstance(s, SubProofNode):
                if s.label == "Case":
                    last = self._last_conclusion(s.statements)
                else:
                    last = self._infer_statement(s.statements, _Scope())
                chain_head = None
        return last

    # -- statements -------------------------------------------------------------

    def _block(self, stmts: list[StatementNode], scope: _Scope, indent: str, state: "_GoalState") -> list[_Fact]:
        facts: list[_Fact] = []
        chain: Optional[_Chain] = None
        i = 0
        while i < len(stmts):
            s = stmts[i]
            # A run of Case blocks is one case split.
            if isinstance(s, SubProofNode) and s.label == "Case":
                j = i
                while j < len(stmts) and isinstance(stmts[j], SubProofNode) and stmts[j].label == "Case":  # type: ignore[union-attr]
                    j += 1
                facts.append(self._cases(stmts[i:j], scope, indent))  # type: ignore[arg-type]
                chain = None
                i = j
                continue
            if _is_chain_link(s):
                run = [s]
                j = i + 1
                while j < len(stmts) and _is_chain_link(stmts[j]) and _chained(stmts[j]):
                    run.append(stmts[j])
                    j += 1
                fact, chain = self._chain(run, scope, indent, chain)
                if fact is not None:
                    facts.append(fact)
                i = j
                continue
            fact = self._statement(s, scope, indent, state)
            if fact is not None:
                facts.append(fact)
            if not isinstance(s, (VarDeclNode, AssumeNode, FuncDefNode)):
                chain = None
            i += 1
        return facts

    def _statement(self, s: StatementNode, scope: _Scope, indent: str, state: "_GoalState") -> Optional[_Fact]:
        line = s.line
        expr = _Expr(scope, self.untranslated, line)
        if getattr(s, "_lean_structure", False):
            return None
        if isinstance(s, FuncDefNode):
            self._definition(s, scope, indent, local=True)
            return None
        if isinstance(s, ImportNode):
            self.emit(f'{indent}-- import "{s.path}": its results are not restated here', line)
            return None
        if isinstance(s, VarDeclNode):
            return self._var_decl(s, scope, indent, state)
        if isinstance(s, AssumeNode):
            name = self._hyp_name(s.label, line)
            prop = expr.prop(s.proposition)
            if state.next_is("hyp"):
                state.take()
                self.emit(f"{indent}intro {name}", line)
            elif state.case_hyp is not None and state.case_hyp[0] == prop:
                self.emit(f"{indent}have {name} : {prop} := {state.case_hyp[1]}", line)
            else:
                self.emit(f"{indent}have {name} : {expr.prop(s.proposition)} := by", line)
                self.emit(f"{indent}  sorry  -- assumed here, but the statement does not say so", line)
            return None
        if isinstance(s, ObtainNode):
            t = lean_type(s.type_name) if s.type_name else "ℝ"
            if s.type_name and s.type_name in scope.carriers:
                t = scope.carriers[s.type_name]
            inner = scope.child()
            inner.types[s.variable] = t or "ℝ"
            cond = _Expr(inner, self.untranslated, line).prop(s.condition)
            v = lean_name(s.variable)
            h = self._hyp_name(None, line)
            src = f"  -- from {s.source_label}" if s.source_label else ""
            self.emit(f"{indent}obtain ⟨{v}, {h}⟩ : ∃ {v} : {t or 'ℝ'}, {cond} := by", line)
            self.emit(f"{indent}  sorry{src}", line)
            scope.types[s.variable] = t or "ℝ"
            return _Fact(h, cond)
        if isinstance(s, DeduceNode):
            return self._deduce(s, scope, indent)
        if isinstance(s, StepNode):
            text = expr.prop(s.rhs)
            name = self._fact_name(line)
            self.emit(f"{indent}have {name} : {text} := by", line)
            self.emit(f"{indent}  {self._attempt(s, line, s.rhs, expr)}{self._hint(s, line)}", line)
            return _Fact(name, text)
        if isinstance(s, SubProofNode):
            return self._subproof(s, scope, indent)
        return None

    def _var_decl(self, s: VarDeclNode, scope: _Scope, indent: str, state: "_GoalState") -> Optional[_Fact]:
        line = s.line
        cond = s.condition
        # `Let δ = ε / 3`: a name for a value.
        if len(s.variables) == 1 and isinstance(cond, RelationNode) and cond.op == "=" and _is_var(cond.left, s.variables[0]):
            v = s.variables[0]
            t = "ℤ" if _Expr(scope, [], None).kind(cond.right) == "int" else "ℝ"
            nxt = state.binders[state.taken] if state.taken < len(state.binders) else None
            if nxt is not None and nxt.from_let and nxt.name == v:
                state.take()
                h = self._hyp_name(None, line)
                names = [lean_name(v)]
                if state.next_is("hyp"):
                    state.take()
                    names.append(h)
                self.emit(f"{indent}intro {' '.join(names)}", line)
                scope.types[v] = t
                return None
            if isinstance(cond.right, MatrixNode) and cond.right.rows:
                t = _matrix_type(len(cond.right.rows), len(cond.right.rows[0]))
            elif isinstance(cond.right, VectorNode):
                t = f"Fin {len(cond.right.elements)} → ℝ"
            value = _Expr(scope, self.untranslated, line).term(cond.right)
            scope.lets[v] = cond.right
            h = self._hyp_name(None, line)
            self.emit(f"{indent}set {lean_name(v)} : {t} := {value} with {h}", line)
            scope.types[v] = t
            return _Fact(h, f"{lean_name(v)} = {value}")
        t = self._decl_type(s, scope)
        intros: list[str] = []
        pending: list[str] = []
        for v in s.variables:
            scope.types[v] = t
            if state.next_is("var"):
                state.take()
                intros.append(lean_name(v))
            else:
                pending.append(v)
        for v in pending:
            self.emit(f"{indent}obtain ⟨{lean_name(v)}⟩ : Nonempty ({t}) := by", line)
            self.emit(f"{indent}  sorry  -- not bound by the statement", line)
        if cond is not None:
            h = self._hyp_name(None, line)
            if state.next_is("hyp") and not pending:
                state.take()
                intros.append(h)
            else:
                text = _Expr(scope, self.untranslated, line).prop(cond)
                if intros:
                    self.emit(f"{indent}intro {' '.join(intros)}", line)
                    intros = []
                self.emit(f"{indent}have {h} : {text} := by", line)
                self.emit(f"{indent}  sorry  -- assumed here, but the statement does not say so", line)
        if intros:
            self.emit(f"{indent}intro {' '.join(intros)}", line)
        return None

    def _decl_type(self, s: VarDeclNode, scope: _Scope) -> str:
        if s.type_name in scope.carriers:
            return scope.carriers[s.type_name]
        t = lean_type(s.type_name)
        if t is None:
            self.untranslated.append({"line": s.line, "what": f"the type {s.type_name}"})
            return "ℝ"
        if s.type_name == "Real" and isinstance(s.condition, RelationNode) and s.condition.op == "=":
            if _Expr(scope, [], None).kind(s.condition.right) == "int":
                return "ℤ"
        return t

    def _deduce(self, s: DeduceNode, scope: _Scope, indent: str) -> _Fact:
        line = s.line
        expr = _Expr(scope, self.untranslated, line)
        if s.premise is not None:
            pname = self._fact_name(line, suffix="'")
            self.emit(f"{indent}have {pname} : {expr.prop(s.premise)} := by", line)
            self.emit(f"{indent}  sorry", line)
        text = expr.prop(s.claim)
        name = self._fact_name(line)
        if s.witness is not None and isinstance(s.claim, QuantifierNode) and s.claim.quantifier == "exists":
            t = lean_type(s.claim.var_type) or "ℝ"
            if s.claim.var_type in scope.carriers:
                t = scope.carriers[s.claim.var_type]  # type: ignore[index]
            w = expr.term(s.witness)
            self.emit(f"{indent}have {name} : {text} := ⟨({w} : {t}), by {self._attempt(s, line)}⟩{self._hint(s, line)}", line)
        else:
            self.emit(f"{indent}have {name} : {text} := by", line)
            self.emit(f"{indent}  {self._attempt(s, line, s.claim, expr)}{self._hint(s, line)}", line)
        return _Fact(name, text)

    def _hyp_name(self, label: Optional[str], line: Optional[int]) -> str:
        return lean_name(label) if label else f"h{line}"

    def _fact_name(self, line: Optional[int], suffix: str = "") -> str:
        return f"s{line}{suffix}"

    # -- chains -----------------------------------------------------------------

    def _chain(self, run: list[StatementNode], scope: _Scope, indent: str, prev: Optional["_Chain"]) -> tuple[Optional[_Fact], Optional["_Chain"]]:
        expr = _Expr(scope, self.untranslated, run[0].line)
        links: list[tuple[str, ExprNode, StatementNode]] = []
        head: Optional[ExprNode] = None
        first = run[0]
        if isinstance(first, StepNode) and first.lhs is not None:
            head = first.lhs
        elif prev is not None:
            head = prev.last
        if head is None:
            self.emit(f"{indent}-- this step continues no chain", first.line)
            return None, None
        for s in run:
            if isinstance(s, StepNode):
                links.append((_RELATIONS.get(s.relation, "?"), s.rhs, s))
            else:
                claim = s.claim  # type: ignore[attr-defined]
                links.append((_RELATIONS.get(claim.op, "?"), claim.right, s))
        rels = [r for r, _, _ in links]
        combined: Optional[str] = rels[0]
        for r in rels[1:]:
            combined = _COMBINE.get((combined, r)) if combined else None  # type: ignore[arg-type]
        has_limit = any(isinstance(n, LimitNode) for _, n, _ in links) or isinstance(head, LimitNode)
        if combined is None or "?" in rels or has_limit or len(links) == 1:
            # One link, or relations no calc can join: a `have` each.
            fact = None
            left = head
            for rel, right, s in links:
                node = RelationNode(op=_lemmata_rel(rel), left=left, right=right)
                link = _Expr(scope, self.untranslated, s.line)
                text = link.prop(node)
                name = self._fact_name(s.line)
                self.emit(f"{indent}have {name} : {text} := by", s.line)
                self.emit(f"{indent}  {self._attempt(s, s.line, node, link)}{self._hint(s, s.line)}", s.line)
                fact = _Fact(name, text)
                left = right
            return fact, _Chain(links[-1][1])
        whole = RelationNode(op=_lemmata_rel(combined), left=head, right=links[-1][1])
        whole_text = expr.prop(whole)
        name = self._fact_name(first.line)
        self.emit(f"{indent}have {name} : {whole_text} := by", first.line)
        left = head
        for k, (rel, right, s) in enumerate(links):
            e = _Expr(scope, self.untranslated, s.line)
            rhs = e.term(right, _P_REL + 1)
            goal = RelationNode(op=_lemmata_rel(rel), left=left, right=right)
            left = right
            if k == 0:
                self.emit(f"{indent}  calc {e.term(head, _P_REL + 1)} {rel} {rhs} := by {self._attempt(s, s.line, goal, e)}{self._hint(s, s.line)}", s.line)
            else:
                self.emit(f"{indent}    _ {rel} {rhs} := by {self._attempt(s, s.line, goal, e)}{self._hint(s, s.line)}", s.line)
        return _Fact(name, whole_text), _Chain(links[-1][1])

    # -- blocks -----------------------------------------------------------------

    def _subproof(self, s: SubProofNode, scope: _Scope, indent: str) -> _Fact:
        line = s.line
        inner = scope.child()
        stmt = self._infer_statement(s.statements, inner)
        expr = _Expr(scope, self.untranslated, line)
        text = expr.prop(stmt) if stmt is not None else "True"
        name = self._fact_name(line)
        label = s.label or "Subproof"
        if s.case_condition is not None and label in ("Base case", "Inductive step"):
            label = f"{label} {s.case_condition}"
        self.emit(f"{indent}-- {label}", line)
        self.emit(f"{indent}have {name} : {text} := by", line)
        as_written = self.as_written
        binders, target = _peel(stmt, scope.defs) if stmt is not None else ([], None)
        state = _GoalState(stmt, binders, target)
        state.as_written = as_written
        facts = self._block(s.statements, inner, indent + "  ", state)
        self._close(state, facts, inner, indent + "  ", None)
        return _Fact(name, text, kind=label)

    def _cases(self, cases: list[SubProofNode], scope: _Scope, indent: str) -> _Fact:
        line = cases[0].line
        expr = _Expr(scope, self.untranslated, line)
        conds = [expr.prop(c.case_condition) for c in cases]  # type: ignore[arg-type]
        ends = [self._last_conclusion(c.statements) for c in cases]
        texts = [expr.prop(e) if e is not None else "True" for e in ends]
        target = texts[0] if len(set(texts)) == 1 else " ∨ ".join(f"({t})" for t in texts)
        name = self._fact_name(line)
        names = [f"hc{c.line}" for c in cases]
        self.emit(f"{indent}have {name} : {target} := by", line)
        self.emit(f"{indent}  obtain {' | '.join(names)} : {' ∨ '.join(f'({c})' if '∨' in c or '→' in c or '↔' in c else c for c in conds)} := by", line)
        self.emit(f"{indent}    sorry  -- the cases cover every possibility", line)
        for case, hname in zip(cases, names):
            inner = scope.child()
            self.emit(f"{indent}  · -- Case {expr.prop(case.case_condition)}", case.line)  # type: ignore[arg-type]
            state = _GoalState(None, [], None)
            state.fixed_text = target
            state.case_hyp = (expr.prop(case.case_condition), hname)  # type: ignore[arg-type]
            facts = self._block(case.statements, inner, indent + "    ", state)
            last = facts[-1] if facts else None
            if last is not None and last.text == target and "sorry" not in target:
                self.emit(f"{indent}    exact {last.name}")
            else:
                self.emit(f"{indent}    sorry")
        return _Fact(name, target, kind="cases")

    def _close(
        self,
        state: "_GoalState",
        facts: list[_Fact],
        scope: _Scope,
        indent: str,
        qed_line: Optional[int],
        block_line: Optional[int] = None,
    ) -> None:
        line = qed_line if qed_line is not None else block_line
        goal_text = state.current_text(scope, self.untranslated)
        last = facts[-1] if facts else None
        if last is not None and goal_text is not None and last.text == goal_text and "sorry" not in goal_text:
            self.emit(f"{indent}exact {last.name}", line)
            return
        if (
            last is not None
            and state.as_written is not None
            and state.taken == len(state.binders)
            and last.text == _Expr(scope, [], None).prop(state.as_written)
            and "sorry" not in last.text
        ):
            self.emit(f"{indent}exact {last.name}", line)
            return
        if state.goal is None and state.fixed_text is None:
            self.emit(f"{indent}trivial", line)
            return
        # By induction: `Base case n = 0` and `Inductive step` blocks prove P 0 and P k → P (k + 1).
        induction = self._induction_close(state, facts, scope)
        if induction is not None:
            for text in induction:
                self.emit(f"{indent}{text}", line)
            return
        self.emit(f"{indent}sorry", line)

    def _induction_close(self, state: "_GoalState", facts: list[_Fact], scope: _Scope) -> Optional[list[str]]:
        from aether.engine.context import substitute_mapping

        rest = state.binders[state.taken:]
        if len(rest) != 1 or rest[0].kind != "var" or state.target is None:
            return None
        b = rest[0]
        if lean_type(b.type) != "ℕ":
            return None
        base = next((f for f in facts if f.kind.startswith("Base case")), None)
        step = next((f for f in facts if f.kind.startswith("Inductive step")), None)
        if base is None or step is None:
            return None
        k = "k"
        expr = _Expr(scope.child(), [], None)
        expr.scope.types[k] = "ℕ"
        p0 = expr.prop(substitute_mapping(state.target, {b.name: NumberNode(value="0")}))
        pk = expr.prop(substitute_mapping(state.target, {b.name: SymbolNode(name=k)}))
        pk1 = expr.prop(substitute_mapping(state.target, {b.name: BinaryOpNode(op="+", left=SymbolNode(name=k), right=NumberNode(value="1"))}))
        if base.text != p0:
            return None
        step_forms = {f"∀ {k} : ℕ, {pk} → {pk1}"}
        # The step block may call its variable anything; compare up to that name.
        if _alpha_normal(step.text) not in {_alpha_normal(t) for t in step_forms}:
            return None
        n = lean_name(b.name)
        return [
            f"intro {n}",
            f"induction {n} with",
            f"| zero => exact {base.name}",
            f"| succ {k} ih => exact {step.name} {k} ih",
        ]

    # -- step proofs ------------------------------------------------------------

    def _attempt(self, s: StatementNode, line: Optional[int], goal: Optional[ExprNode] = None, expr: Optional["_Expr"] = None) -> str:
        """The step's proof: the Lean tactic for the rule the kernel checked it
        by, falling back to `sorry` (``first | ring | sorry``), or `sorry` alone
        when the step did not check or no one tactic does what the rule did."""
        result = self.results.get(line) if line is not None else None
        if result is None or getattr(result.status, "value", str(result.status)) == "INVALID":
            return "sorry"
        shape = _Shape()
        if goal is not None and expr is not None:
            quiet = _Expr(expr.scope, [], None)  # rendering here must not report anything
            shape.abs_terms = list(dict.fromkeys(quiet.term(a) for a in _abs_args(goal)))[:3]
            shape.conjunction = isinstance(goal, BinaryOpNode) and goal.op in _AND
            shape.denominators = list(dict.fromkeys(quiet.term(d) for d in _denominators(goal)))[:2]
            shape.text = quiet.prop(goal)
        attempts = _lean_attempts(result.backend, s, self.algebra, shape)
        return "first | " + " | ".join(attempts) + " | sorry" if attempts else "sorry"

    # -- hints ------------------------------------------------------------------

    def _hint(self, s: StatementNode, line: Optional[int]) -> str:
        result = self.results.get(line) if line is not None else None
        if result is None:
            return ""
        status = getattr(result.status, "value", str(result.status))
        if status == "INVALID":
            return "  -- did not check"
        note = f"  -- {result.backend}"
        if status == "WARNING":
            note += " (Lemmata warned about its domain)"
        if isinstance(s, DeduceNode) and s.justification:
            note += f"; by {s.justification}"
        elif isinstance(s, StepNode) and s.justification:
            note += f"; by {s.justification}"
        return note


@dataclass
class _Chain:
    last: ExprNode


class _GoalState:
    """The statement's binders, and how many the proof has introduced so far."""

    def __init__(self, goal: Optional[ExprNode], binders: list[_Binder], target: Optional[ExprNode]):
        self.goal = goal
        self.binders = binders
        self.target = target
        self.taken = 0
        self.fixed_text: Optional[str] = None
        #: In a case: the case's condition and the hypothesis that holds it.
        self.case_hyp: Optional[tuple[str, str]] = None
        #: A claim-less block's conclusion as written (before its `Let`s unfold).
        self.as_written: Optional[ExprNode] = None

    def next_is(self, kind: str) -> bool:
        return self.taken < len(self.binders) and self.binders[self.taken].kind == kind

    def take(self) -> None:
        self.taken += 1

    def current_text(self, scope: _Scope, untranslated: list[dict[str, Any]]) -> Optional[str]:
        if self.fixed_text is not None:
            return self.fixed_text
        if self.goal is None:
            return None
        expr = _Expr(scope, [], None)
        if self.taken == 0:
            return expr.prop(self.goal)
        return expr.prop(_wrap(self.binders[self.taken:], self.target))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Calls that are not abstract functions to bind.
_KNOWN_CALLS = frozenset(
    {"abs", "even", "odd", "multipleof", "divides", "congruent", "cong", "prime", "positive", "nonnegative",
     "negative", "nonzero", "floor", "ceil", "sum", "gcd", "lcm", "factorial", "sqrt", "exp", "ln", "log",
     "sin", "cos", "tan", "arctan", "sinh", "cosh", "max", "min", "diff", "derivative", "integrate", "integral",
     "det", "tr", "transpose", "dot", "norm", "lim", "limit", "group", "abeliangroup", "ring", "field",
     "subgroup", "normalsubgroup", "inv", "inverse", "orthogonal"}
)


def _is_var(node: Any, name: str) -> bool:
    return isinstance(node, (SymbolNode, GreekSymbolNode)) and node.name == name


def _is_typed(s: VarDeclNode) -> bool:
    return not (isinstance(s.condition, RelationNode) and s.condition.op != "=")


def _is_chain_link(s: StatementNode) -> bool:
    if isinstance(s, StepNode):
        return bool(s.relation) and s.relation in _RELATIONS
    if isinstance(s, DeduceNode) and s.premise is None and s.witness is None:
        c = s.claim
        return isinstance(c, RelationNode) and isinstance(c.left, SymbolNode) and c.left.name == "<prev>"
    return False


def _chained(s: StatementNode) -> bool:
    return (isinstance(s, StepNode) and s.lhs is None) or isinstance(s, DeduceNode)


def _lemmata_rel(lean_rel: str) -> str:
    return {"=": "=", "<": "<", ">": ">", "≤": "<=", "≥": ">=", "≠": "!=", "∈": "in", "∉": "notin", "⊂": "subset", "⊆": "subseteq"}.get(lean_rel, lean_rel)


def _is_proposition(node: ExprNode) -> bool:
    if isinstance(node, (RelationNode, QuantifierNode)):
        return True
    if isinstance(node, BinaryOpNode):
        return node.op in _IMPLIES | _IFF | _AND | _OR
    if isinstance(node, UnaryOpNode):
        return node.op in ("not", "\\neg", "~")
    if isinstance(node, FunctionCallNode):
        return node.func.lower() in {"even", "odd", "multipleof", "divides", "congruent", "cong", "prime", "positive", "nonnegative", "negative", "nonzero"} or node.func[:1].isupper()
    return False


def _called_arity(node: Any, name: str) -> Optional[int]:
    if isinstance(node, FunctionCallNode):
        if node.func == name:
            return len(node.args)
        for a in node.args:
            found = _called_arity(a, name)
            if found is not None:
                return found
        return None
    if isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode):
                found = _called_arity(value, name)
                if found is not None:
                    return found
    return None


def _used_in_integer_call(node: Any, name: str) -> bool:
    if isinstance(node, FunctionCallNode):
        if node.func.lower() in _INTEGER_CALLS and name in _names(node.args):
            return True
        return any(_used_in_integer_call(a, name) for a in node.args)
    if isinstance(node, ExprNode):
        return any(_used_in_integer_call(v, name) for v in vars(node).values() if isinstance(v, ExprNode))
    return False


def _nested_defs(stmts: list[StatementNode]) -> set[str]:
    out: set[str] = set()
    for s in stmts:
        if isinstance(s, FuncDefNode):
            out.add(s.name)
        elif isinstance(s, SubProofNode):
            out |= _nested_defs(s.statements)
    return out


def _alpha_normal(text: str) -> str:
    """``∀ m : ℕ, P m → P (m + 1)`` with its bound name made ``k``, to compare step forms."""
    m = re.match(r"∀ (\S+) : ℕ, ", text)
    if not m:
        return text
    name = m.group(1)
    return re.sub(rf"(?<![\w']){re.escape(name)}(?![\w'])", "k", text)


#: The Lean tactics for each rule Lemmata's kernel names (``Kernel: <rule>``),
#: tried in order inside ``first | … | sorry``.  Only rules one tactic can
#: redo are here: the calculus rules (Lean's ``deriv`` and ``Tendsto`` goals
#: need lemmas), "solver only" and "outside the core" stay ``sorry``.
_LEAN_TACTICS: dict[str, tuple[str, ...]] = {
    "ring": ("ring", "norm_num", "(field_simp; ring)", "linarith", "rfl", "decide"),
    "subst": ("(subst_vars; ring)", "ring", "(simp only [*]; ring)", "linarith"),
    "field": ("(field_simp; ring)", "field_simp", "ring", "norm_num", "linarith", "rfl"),
    "simp": ("simp", "norm_num", "(simp; ring)", "linarith"),
    "linarith": ("linarith", "nlinarith", "positivity", "norm_num"),
    "nlinarith": ("nlinarith", "positivity", "norm_num", "(norm_num; nlinarith)"),
    "residues": ("omega", "decide"),
    "hypothesis": ("assumption", "linarith", "omega", "(simp_all)"),
    "closed form, by induction": (),
    "group axioms": ("group", "simp"),
    "group axioms and hypotheses": ("simp_all", "(simp only [mul_assoc] at *; group)"),
    "ring axioms": ("noncomm_ring",),
    "field axioms": ("(field_simp)",),
}
_INTROS = ("∀-intro", "⇒-intro", "∧-intro")


@dataclass
class _Shape:
    """What the goal looks like, for the tactics that need to know."""

    #: The arguments of the absolute values in it, as Lean terms (at most 3).
    abs_terms: list[str] = field(default_factory=list)
    #: Whether it is a conjunction (`A ∧ B`).
    conjunction: bool = False
    #: The denominators in it, as Lean terms (at most 2).
    denominators: list[str] = field(default_factory=list)
    #: The goal as Lean shows it (to recognise a factorial).
    text: str = ""


def _abs_args(node: Any) -> list[ExprNode]:
    out: list[ExprNode] = []
    if isinstance(node, FunctionCallNode) and node.func.lower() in ("abs", "\\abs") and len(node.args) == 1:
        out.append(node.args[0])
    if isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode):
                out.extend(_abs_args(value))
            elif isinstance(value, list):
                for v in value:
                    out.extend(_abs_args(v))
    return out


def _denominators(node: Any) -> list[ExprNode]:
    out: list[ExprNode] = []
    if isinstance(node, BinaryOpNode) and node.op == "/" and not isinstance(node.right, NumberNode):
        out.append(node.right)
    if isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode):
                out.extend(_denominators(value))
            elif isinstance(value, list):
                for v in value:
                    out.extend(_denominators(v))
    return out


def _lean_attempts(backend: str, s: StatementNode, algebra: Optional[str], shape: Optional[_Shape] = None) -> list[str]:
    """What to try for a step the kernel checked by *backend*."""
    shape = shape or _Shape()
    if not backend.startswith("Kernel: "):
        return []
    rules = backend[len("Kernel: ") :].split(", ")
    tactics = list(_LEAN_TACTICS.get(rules[-1], ()))
    if not tactics:
        return []
    if algebra in ("Group", "CommGroup") and rules[-1] in ("ring", "subst"):
        tactics = ["group"]
    if rules[-1] in ("linarith", "nlinarith"):
        if shape.abs_terms:
            # Lemmata's solver splits |t| into its two cases itself; Lean's
            # linarith sees |t| as an atom.  Split each one, then linarith.
            splits = " <;> ".join(f"rcases abs_cases ({t}) with ⟨_, _⟩ | ⟨_, _⟩" for t in shape.abs_terms)
            tactics = [f"({splits} <;> {rules[-1]})"] + tactics
        if shape.conjunction:
            tactics = [f"(refine ⟨?_, ?_⟩ <;> {rules[-1]})"] + tactics
    if rules[-1] in ("ring", "subst", "field", "simp"):
        if shape.abs_terms:
            # An identity between absolute values: by cases, or by |a| |b| = |a b|.
            splits = " <;> ".join(f"rcases abs_cases ({t}) with ⟨_, _⟩ | ⟨_, _⟩" for t in shape.abs_terms)
            tactics += [f"({splits} <;> linarith)", f"({splits} <;> nlinarith)", "(simp only [← abs_mul]; congr 1; ring)", "(rw [abs_sub_comm])"]
        if shape.denominators:
            # field_simp needs each denominator known non-zero: show it first.
            nonzero = "; ".join(
                f"have hd{i} : ({d}) ≠ 0 := by first | positivity | (intro h; nlinarith)" for i, d in enumerate(shape.denominators)
            )
            tactics = [f"({nonzero}; field_simp; ring)"] + tactics
        if "Nat.factorial" in shape.text:
            tactics += ["(rw [Nat.mul_factorial_pred (by omega)])", "(exact (Nat.mul_factorial_pred (by omega)).symm)"]
    if any(r in _INTROS for r in rules):
        # ∀/⇒-introduction: take the binders and hypotheses apart, then the leaf.
        tactics = [f"(intros; {t})" for t in tactics]
    return [_closing(t) for t in tactics]


#: Tactics that either prove the goal or fail.  The rest can succeed with the
#: goal still open (`ring` falls back to `ring_nf`, `field_simp` and `simp`
#: make progress), which `first` would take as done: they get `; done`.
_CLOSES = frozenset({"linarith", "nlinarith", "positivity", "omega", "decide", "assumption"})
#: Tactic texts ending in one of these close or fail too (`… <;> linarith`).
_CLOSING_TAILS = ("<;> linarith)", "<;> nlinarith)")


def _closing(tactic: str) -> str:
    if tactic in _CLOSES or tactic.endswith(_CLOSING_TAILS):
        return tactic
    inner = tactic[1:-1] if tactic.startswith("(") and tactic.endswith(")") else tactic
    return f"({inner}; done)"


#: Calls whose steps no one-word tactic proves.
_NO_TACTIC_CALLS = frozenset({"diff", "derivative", "det", "tr", "transpose", "dot", "sum", "lim", "limit"})


def _calls(node: Any, names: frozenset[str]) -> bool:
    if isinstance(node, FunctionCallNode) and node.func.lower() in names:
        return True
    if isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode) and _calls(value, names):
                return True
            if isinstance(value, list) and any(_calls(v, names) for v in value):
                return True
    return False


def _contains(node: Any, kinds: tuple[type, ...]) -> bool:
    if isinstance(node, kinds):
        return True
    if isinstance(node, ExprNode):
        for value in vars(node).values():
            if isinstance(value, ExprNode) and _contains(value, kinds):
                return True
            if isinstance(value, list) and any(_contains(v, kinds) for v in value):
                return True
    return False


def _nonlinear(node: Any) -> bool:
    if isinstance(node, BinaryOpNode):
        if node.op in ("^", "**"):
            return True
        if node.op == "*" and not isinstance(node.left, NumberNode) and not isinstance(node.right, NumberNode):
            return True
        return _nonlinear(node.left) or _nonlinear(node.right)
    if isinstance(node, (RelationNode,)):
        return _nonlinear(node.left) or _nonlinear(node.right)
    if isinstance(node, UnaryOpNode):
        return _nonlinear(node.operand)
    if isinstance(node, FunctionCallNode):
        return True
    return False


def _flatten_results(reports: list[Any]) -> dict[int, Any]:
    out: dict[int, Any] = {}

    def walk(results: list[Any]) -> None:
        for r in results:
            if r.line is not None and r.line not in out:
                out[r.line] = r
            walk(r.sub_results)

    for rep in reports:
        walk(rep.results)
    return out


def export_to_lean(
    source: str,
    *,
    sources: Optional[Mapping[str, str]] = None,
    citations: Optional[Mapping[str, Any]] = None,
    file_path: Optional[str] = None,
    namespace: str = "Lemmata",
) -> LeanExport:
    """*source* as a Lean 4 + Mathlib skeleton, lined up with its lines.

    Raises the parser's ``ParseError`` when *source* does not parse.  The proof
    is checked too, with the proof kernel at its most permissive level
    (scratch: it decides as the engine does, refusing nothing as too big a
    step), so each step can try the Lean tactic for the rule that checked it.
    """
    from aether.engine.checker import ProofChecker

    checker = ProofChecker(kernel="scratch")
    doc = checker._parser.parse(source)
    try:
        reports = checker.check_source(source, file_path=file_path, sources=sources, citations=citations)
        results = _flatten_results(reports)
    except Exception:  # a proof that does not check still has a statement
        results = {}
    return LeanExporter(source, results, namespace).export(doc)
