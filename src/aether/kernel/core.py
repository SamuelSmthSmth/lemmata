"""The typed core: one translation of the proof's expressions, read by every tactic.

Today the engine translates the AST twice, into SymPy and into Z3, and each
translation decides types for itself.  The core is the paper's §4: an
expression is elaborated once into typed terms --

- a number type on every term (Nat < Int < Rat < Real), so "is it whole?" is
  read off the term instead of guessed by a backend;
- subtraction of naturals is an integer, division is rational, and a power's
  exponent is a natural literal (a symbolic one is outside the core);
- each division records its side condition (the denominator is not 0);
- a declared sequence `u : Nat -> Int` applied to an argument is a typed
  application, uninterpreted;
- propositions: relations, connectives, and divisibility by a number (what
  `Even`, `Odd`, `MultipleOf` and `Divides` mean when the modulus is one).

Any other function (`sin`, `sqrt`, an `f` the notes name) is an
uninterpreted real value, which no tactic knows anything about: sound, and a
line that needs a fact about it is simply left to stage 1's reading.
Quantifiers, sums, limits, derivatives, integrals, sets, matrices, complex
numbers and the constants pi, e and oo are outside the core: ``elaborate``
returns None and the kernel falls back to stage 1's reading.

The tactics (``tactics``) read core terms only: SymPy and Z3 each get them
from one translator here, typed the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from fractions import Fraction
from typing import Optional, Union

from aether.core.ast import (
    BinaryOpNode,
    ExprNode,
    FunctionCallNode,
    GreekSymbolNode,
    NumberNode,
    RelationNode,
    SymbolNode,
    UnaryOpNode,
)
from aether.core.types import MathType
from aether.engine.context import ProofContext, canonical_rel


class Ty(IntEnum):
    """The number types the core knows, ordered by inclusion."""

    NAT = 0
    INT = 1
    RAT = 2
    REAL = 3

    @property
    def integral(self) -> bool:
        return self <= Ty.INT


_FROM_MATH = {MathType.Nat: Ty.NAT, MathType.Int: Ty.INT, MathType.Rat: Ty.RAT, MathType.Real: Ty.REAL}


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Num:
    value: Fraction
    ty: Ty


@dataclass(frozen=True)
class Var:
    name: str
    ty: Ty


@dataclass(frozen=True)
class App:
    """A declared function (a sequence `u : Nat -> Int`) applied: uninterpreted."""

    fn: str
    args: tuple["Term", ...]
    ty: Ty


@dataclass(frozen=True)
class Add:
    args: tuple["Term", ...]
    ty: Ty


@dataclass(frozen=True)
class Mul:
    args: tuple["Term", ...]
    ty: Ty


@dataclass(frozen=True)
class Neg:
    arg: "Term"
    ty: Ty


@dataclass(frozen=True)
class Div:
    num: "Term"
    den: "Term"
    ty: Ty = Ty.RAT


@dataclass(frozen=True)
class Pow:
    base: "Term"
    exp: int
    ty: Ty


@dataclass(frozen=True)
class Abs:
    arg: "Term"
    ty: Ty


Term = Union[Num, Var, App, Add, Mul, Neg, Div, Pow, Abs]


# ---------------------------------------------------------------------------
# Propositions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rel:
    op: str  # = != < <= > >=
    left: Term
    right: Term


@dataclass(frozen=True)
class Conn:
    op: str  # and or => <=>
    args: tuple["Prop", ...]


@dataclass(frozen=True)
class Not:
    arg: "Prop"


@dataclass(frozen=True)
class Divisible:
    """`modulus` divides `term`: Even, Odd, MultipleOf, Divides by a number."""

    modulus: int
    term: Term


Prop = Union[Rel, Conn, Not, Divisible]


@dataclass
class Elaborated:
    """A core proposition and the side conditions its terms carry."""

    prop: Prop
    conditions: list[Prop] = field(default_factory=list)


class _Outside(Exception):
    """The expression is outside the core."""


# ---------------------------------------------------------------------------
# Elaboration
# ---------------------------------------------------------------------------

_RELS = {"=", "!=", "<", "<=", ">", ">="}
#: Calls that bind a variable of their own: outside the core.
_BINDERS = {"sum", "diff", "integrate", "int", "lim", "limit", "product"}
_CONNECTIVES = {"and": "and", "\\land": "and", "/\\": "and", "or": "or", "\\lor": "or", "\\/": "or",
                "=>": "=>", "->": "=>", "implies": "=>", "\\implies": "=>", "<=>": "<=>", "iff": "<=>", "\\iff": "<=>"}


def elaborate(expr: ExprNode, ctx: ProofContext) -> Optional[Elaborated]:
    """*expr* as a core proposition, or None when it is outside the core."""
    expanded = ctx.expand_user_functions(expr) or expr
    builder = _Builder(ctx)
    try:
        prop = builder.prop(expanded)
    except _Outside:
        return None
    return Elaborated(prop, builder.conditions)


def elaborate_term(expr: ExprNode, ctx: ProofContext) -> Optional[Term]:
    """*expr* as a core term, or None when it is outside the core."""
    expanded = ctx.expand_user_functions(expr) or expr
    try:
        return _Builder(ctx).term(expanded)
    except _Outside:
        return None


def same_value(a: ExprNode, b: ExprNode, ctx: ProofContext) -> Optional[bool]:
    """Whether two expressions are equal as polynomials (or rational functions)
    in their typed variables: None when either is outside the core.  Plain
    expansion, never a search for a counterexample."""
    import sympy as sp

    ta, tb = elaborate_term(a, ctx), elaborate_term(b, ctx)
    if ta is None or tb is None:
        return None
    diff = to_sympy(ta) - to_sympy(tb)
    if has_division(ta) or has_division(tb):
        return sp.cancel(sp.together(diff)) == 0
    return sp.expand(diff) == 0


class _Builder:
    def __init__(self, ctx: ProofContext) -> None:
        self.ctx = ctx
        self.conditions: list[Prop] = []

    # Propositions -----------------------------------------------------------

    def prop(self, node: ExprNode) -> Prop:
        if isinstance(node, RelationNode):
            op = canonical_rel(node.op)
            if op == "==":
                op = "="
            if op not in _RELS:
                raise _Outside
            return Rel(op, self.term(node.left), self.term(node.right))
        if isinstance(node, BinaryOpNode) and node.op.lower() in _CONNECTIVES:
            op = _CONNECTIVES[node.op.lower()]
            return Conn(op, (self.prop(node.left), self.prop(node.right)))
        if isinstance(node, UnaryOpNode) and node.op.lower() in ("not", "\\neg", "~", "¬"):
            return Not(self.prop(node.operand))
        if isinstance(node, FunctionCallNode):
            return self.predicate(node)
        raise _Outside

    def predicate(self, node: FunctionCallNode) -> Prop:
        fn, args = node.func.lower(), node.args
        if fn == "even" and len(args) == 1:
            return Divisible(2, self.integral(args[0]))
        if fn == "odd" and len(args) == 1:
            t = self.integral(args[0])
            return Divisible(2, Add((t, Num(Fraction(-1), Ty.INT)), Ty.INT))
        if fn == "multipleof" and len(args) == 2:
            return Divisible(self.modulus(args[1]), self.integral(args[0]))
        if fn == "divides" and len(args) == 2:
            return Divisible(self.modulus(args[0]), self.integral(args[1]))
        if fn == "congruent" and len(args) == 3:
            a, b = self.integral(args[0]), self.integral(args[1])
            return Divisible(self.modulus(args[2]), Add((a, Neg(b, Ty.INT)), Ty.INT))
        if fn == "positive" and len(args) == 1:
            return Rel(">", self.term(args[0]), Num(Fraction(0), Ty.NAT))
        if fn == "nonnegative" and len(args) == 1:
            return Rel(">=", self.term(args[0]), Num(Fraction(0), Ty.NAT))
        raise _Outside

    def modulus(self, node: ExprNode) -> int:
        t = self.term(node)
        if isinstance(t, Num) and t.value.denominator == 1 and t.value > 0:
            return int(t.value)
        raise _Outside  # a symbolic modulus is outside the core

    def integral(self, node: ExprNode) -> Term:
        t = self.term(node)
        if not t.ty.integral:
            raise _Outside
        return t

    # Terms ------------------------------------------------------------------

    def term(self, node: ExprNode) -> Term:
        if isinstance(node, NumberNode):
            value = Fraction(node.value)
            return Num(value, Ty.NAT if value.denominator == 1 and value >= 0 else Ty.RAT)
        if isinstance(node, (SymbolNode, GreekSymbolNode)):
            info = self.ctx.get_var(node.name)
            if info is None or info.math_type not in _FROM_MATH:
                raise _Outside  # undeclared, a constant (pi, e, oo), or not a number
            return Var(node.name, _FROM_MATH[info.math_type])
        if isinstance(node, UnaryOpNode) and node.op == "-":
            arg = self.term(node.operand)
            return Neg(arg, max(arg.ty, Ty.INT))
        if isinstance(node, BinaryOpNode):
            return self.binary(node)
        if isinstance(node, FunctionCallNode):
            return self.call(node)
        raise _Outside

    def binary(self, node: BinaryOpNode) -> Term:
        op = node.op
        if op in ("+", "-", "*", "\\cdot", "\\times", "×", "·"):
            left, right = self.term(node.left), self.term(node.right)
            ty = max(left.ty, right.ty)
            if op == "+":
                return Add((left, right), ty)
            if op == "-":
                return Add((left, Neg(right, max(right.ty, Ty.INT))), max(ty, Ty.INT))
            return Mul((left, right), ty)
        if op == "/":
            num, den = self.term(node.left), self.term(node.right)
            if isinstance(den, Num) and den.value == 0:
                raise _Outside
            if not isinstance(den, Num):
                self.conditions.append(Rel("!=", den, Num(Fraction(0), Ty.NAT)))
            return Div(num, den, max(num.ty, den.ty, Ty.RAT))
        if op in ("^", "**"):
            base = self.term(node.left)
            exp = self.term(node.right)
            if not (isinstance(exp, Num) and exp.value.denominator == 1):
                raise _Outside  # a symbolic or fractional exponent
            k = int(exp.value)
            if k < 0:
                if not isinstance(base, Num):
                    self.conditions.append(Rel("!=", base, Num(Fraction(0), Ty.NAT)))
                return Div(Num(Fraction(1), Ty.NAT), Pow(base, -k, base.ty), max(base.ty, Ty.RAT))
            return Pow(base, k, base.ty)
        raise _Outside

    def call(self, node: FunctionCallNode) -> Term:
        fn = node.func
        if fn.lower() in ("abs", "\\abs") and len(node.args) == 1:
            arg = self.term(node.args[0])
            return Abs(arg, Ty.NAT if arg.ty.integral else arg.ty)
        info = self.ctx.get_var(fn)
        if info is not None and info.math_type == MathType.Function and info.signature is not None:
            arg_types, result = info.signature
            if result not in _FROM_MATH or len(arg_types) != len(node.args):
                raise _Outside
            return App(fn, tuple(self.term(a) for a in node.args), _FROM_MATH[result])
        if fn.lower() in _BINDERS or info is not None:
            raise _Outside
        # Any other function (sin, sqrt, a function the notes name f): an
        # uninterpreted real value.  The tactics know nothing about it, so this
        # is always sound; a line that needs a fact about it (sqrt(x)^2 = x)
        # is simply not proved here, and the kernel reads it as stage 1 did.
        return App(fn, tuple(self.term(a) for a in node.args), Ty.REAL)


# ---------------------------------------------------------------------------
# Translation: SymPy
# ---------------------------------------------------------------------------


def sympy_symbol(name: str, ty: Ty):
    import sympy as sp

    if ty == Ty.NAT:
        return sp.Symbol(name, integer=True, nonnegative=True)
    if ty == Ty.INT:
        return sp.Symbol(name, integer=True)
    if ty == Ty.RAT:
        return sp.Symbol(name, rational=True)
    return sp.Symbol(name, real=True)


def to_sympy(term: Term):
    """A core term as a SymPy expression, its symbols carrying their types."""
    import sympy as sp

    if isinstance(term, Num):
        return sp.Rational(term.value.numerator, term.value.denominator)
    if isinstance(term, Var):
        return sympy_symbol(term.name, term.ty)
    if isinstance(term, App):
        args = [to_sympy(a) for a in term.args]
        known = _SYMPY_FUNCTIONS.get(term.fn.lower())
        if known is not None and len(args) == known[1]:
            # A number-theoretic function is evaluated only on numbers:
            # gcd(8, 2) is 2, but SymPy's gcd(n, k) of two symbols is the
            # *polynomial* gcd, 1, and lcm(n, k) is n*k -- both false for
            # integers (the Notation pack's traps; the shadow run caught it).
            if term.fn.lower() in _NUMBERS_ONLY and not all(a.is_Number for a in args):
                return sp.Function(term.fn)(*args)
            # An analytic one reads as the engine's SymPy route reads it:
            # sqrt(x)^2 is x (the radicand's sign is the domain check's
            # question, not the identity's).
            return getattr(sp, known[0])(*args)
        return sp.Function(term.fn)(*args)
    if isinstance(term, Add):
        return sp.Add(*[to_sympy(a) for a in term.args])
    if isinstance(term, Mul):
        return sp.Mul(*[to_sympy(a) for a in term.args])
    if isinstance(term, Neg):
        return -to_sympy(term.arg)
    if isinstance(term, Div):
        return to_sympy(term.num) / to_sympy(term.den)
    if isinstance(term, Pow):
        return to_sympy(term.base) ** term.exp
    if isinstance(term, Abs):
        return sp.Abs(to_sympy(term.arg))
    raise TypeError(term)


#: Functions the identity tactics read as SymPy does (name -> (SymPy name,
#: arity)).  Z3 still treats each application as an opaque atom.
_SYMPY_FUNCTIONS = {
    "factorial": ("factorial", 1), "gcd": ("gcd", 2), "lcm": ("lcm", 2), "binomial": ("binomial", 2),
    "floor": ("floor", 1), "ceiling": ("ceiling", 1), "ceil": ("ceiling", 1), "sqrt": ("sqrt", 1),
    "sin": ("sin", 1), "cos": ("cos", 1), "tan": ("tan", 1), "exp": ("exp", 1), "log": ("log", 1),
    "ln": ("log", 1), "sinh": ("sinh", 1), "cosh": ("cosh", 1), "tanh": ("tanh", 1),
    "arctan": ("atan", 1), "atan": ("atan", 1), "arcsin": ("asin", 1), "asin": ("asin", 1),
    "arccos": ("acos", 1), "acos": ("acos", 1),
}


#: Functions SymPy reads as polynomial operations on symbols: numbers only.
_NUMBERS_ONLY = {"factorial", "gcd", "lcm", "binomial", "floor", "ceiling", "ceil"}


def has_division(term: Term) -> bool:
    if isinstance(term, Div):
        return not isinstance(term.den, Num) or has_division(term.num)
    if isinstance(term, (Add, Mul)):
        return any(has_division(a) for a in term.args)
    if isinstance(term, App):
        return any(has_division(a) for a in term.args)
    if isinstance(term, (Neg, Abs)):
        return has_division(term.arg)
    if isinstance(term, Pow):
        return has_division(term.base)
    return False


def variables(item: Union[Term, Prop]) -> dict[str, Ty]:
    """Every variable in a term or proposition, with its type."""
    out: dict[str, Ty] = {}

    def walk(x) -> None:
        if isinstance(x, Var):
            out[x.name] = x.ty
        elif isinstance(x, (Add, Mul, App, Conn)):
            for a in x.args:
                walk(a)
        elif isinstance(x, (Neg, Abs, Not)):
            walk(x.arg)
        elif isinstance(x, Div):
            walk(x.num)
            walk(x.den)
        elif isinstance(x, Pow):
            walk(x.base)
        elif isinstance(x, Rel):
            walk(x.left)
            walk(x.right)
        elif isinstance(x, Divisible):
            walk(x.term)

    walk(item)
    return out
