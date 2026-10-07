"""Calculus as named rules: derivatives by the rules a course teaches,
definite integrals by the Fundamental Theorem, limits by the algebra of
limits, and sums by a closed form checked by induction.

The engine settles `diff(...)` and `integrate(...)` by asking SymPy for the
answer.  The kernel does not take that answer on trust: it differentiates by
its own rules (sum, product, quotient, chain, power and the standard
functions), recording which ones it used, and for an integral it lets SymPy
*propose* an antiderivative F and checks it: F' = f by those same rules, f
continuous on the interval, then F(b) - F(a).  SymPy may propose; the kernel
checks.

A limit goes by substitution where the function is continuous, by cancelling
a common factor, by the algebra of limits (sums, products, quotients, the
standard functions at infinity), by L'Hopital's rule with the kernel's own
derivatives, by dominant terms for a rational function at infinity, or by the
squeeze (a bounded factor times one tending to 0).  A finite sum is added up
when its bounds are numbers, telescoped, peeled (the sum to k + 1 is the sum to
k plus a term), or replaced by a closed form SymPy proposes and the kernel
checks by induction: S(first) is the first term, S(N) - S(N - 1) the N-th.
An infinite series is left to the engine: its convergence is not checked here.

``verify(goal, ctx)`` returns the rules that show an equation about
derivatives or integrals, or None when they do not (an unknown function's
integral, a discontinuity, a derivative of |x|): the engine's verdict then
stands, as it did before.  Nothing here changes a verdict; it is what the
audit can say about why a line holds.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import fields, replace
from typing import Optional

import sympy as sp
from sympy.core.function import AppliedUndef

from aether.core.ast import ExprNode, FunctionCallNode, GreekSymbolNode, IntegralNode, LimitNode, RelationNode, SymbolNode
from aether.engine.context import ProofContext

#: The order the audit names rules in, the most telling first.
_ORDER = (
    "FTC",
    "L'Hôpital's rule",
    "squeeze",
    "cancel, then substitute",
    "dominant terms",
    "standard limit",
    "closed form, by induction",
    "telescoping",
    "peeling the last term",
    "direct sum",
    "empty sum",
    "chain rule",
    "quotient rule",
    "product rule",
    "power rule",
    "standard derivative",
    "sum rule",
    "sign near the point",
    "algebra of limits",
    "substitution",
)


#: The rules this module names (what a line's backend reads, after "Kernel: ").
RULES = _ORDER + ("calculus rules",)


class _Unproven(Exception):
    """The rules do not reach this: leave the line to the engine."""


# ---------------------------------------------------------------------------
# Differentiation by rules
# ---------------------------------------------------------------------------


_STANDARD = {
    sp.sin: lambda u: sp.cos(u),
    sp.cos: lambda u: -sp.sin(u),
    sp.tan: lambda u: 1 + sp.tan(u) ** 2,
    sp.exp: lambda u: sp.exp(u),
    sp.log: lambda u: 1 / u,
    sp.sinh: lambda u: sp.cosh(u),
    sp.cosh: lambda u: sp.sinh(u),
    sp.tanh: lambda u: 1 - sp.tanh(u) ** 2,
    sp.asin: lambda u: 1 / sp.sqrt(1 - u**2),
    sp.acos: lambda u: -1 / sp.sqrt(1 - u**2),
    sp.atan: lambda u: 1 / (1 + u**2),
}


def derivative(expr: sp.Expr, x: sp.Symbol, rules: set[str]) -> sp.Expr:
    """d(expr)/dx by the rules, adding the names of those used to *rules*.
    Never calls SymPy's own differentiation."""
    if not expr.has(x):
        return sp.Integer(0)
    if expr == x:
        return sp.Integer(1)
    if isinstance(expr, sp.Add):
        if sum(1 for a in expr.args if a.has(x)) > 1:
            rules.add("sum rule")
        return sp.Add(*[derivative(a, x, rules) for a in expr.args])
    if isinstance(expr, sp.Mul):
        varying = [a for a in expr.args if a.has(x)]
        quotient = len(varying) > 1 and any(_reciprocal(a, x) for a in varying)
        if len(varying) > 1:
            rules.add("quotient rule" if quotient else "product rule")
        terms = []
        for i, a in enumerate(expr.args):
            if not a.has(x):
                continue
            others = expr.args[:i] + expr.args[i + 1 :]
            # SymPy writes f/g as f * g^-1: in a quotient, the reciprocal's own
            # power and chain rules are the quotient rule's, not named again.
            own = set() if quotient and _reciprocal(a, x) else rules
            terms.append(sp.Mul(derivative(a, x, own), *others))
        return sp.Add(*terms)
    if isinstance(expr, sp.Pow):
        base, exp = expr.args
        if not exp.has(x):
            rules.add("power rule")
            inner = _inner(base, x, rules)
            return exp * base ** (exp - 1) * inner
        # b^e = exp(e log b): the exponential, through the chain rule.
        rules.add("standard derivative")
        return expr * derivative(exp * sp.log(base), x, rules)
    if isinstance(expr, AppliedUndef):
        if len(expr.args) != 1:
            raise _Unproven
        (u,) = expr.args
        prime = sp.Function(f"{type(expr).__name__}'")(u)
        return prime * _inner(u, x, rules)
    func = type(expr)
    if func in _STANDARD and len(expr.args) == 1:
        rules.add("standard derivative")
        (u,) = expr.args
        return _STANDARD[func](u) * _inner(u, x, rules)
    raise _Unproven  # |x|, floor, a piecewise function: not by these rules


def _reciprocal(a: sp.Expr, x: sp.Symbol) -> bool:
    return isinstance(a, sp.Pow) and bool(a.exp.is_negative) and a.base.has(x)


def _inner(u: sp.Expr, x: sp.Symbol, rules: set[str]) -> sp.Expr:
    """The chain rule's factor: u' when u is more than the variable itself."""
    if u == x:
        return sp.Integer(1)
    rules.add("chain rule")
    return derivative(u, x, rules)


def _zero(expr: sp.Expr) -> bool:
    try:
        return sp.simplify(expr) == 0 or sp.simplify(sp.expand(sp.together(expr))) == 0
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Integrals by the Fundamental Theorem
# ---------------------------------------------------------------------------


def _definite(f: sp.Expr, x: sp.Symbol, a: sp.Expr, b: sp.Expr, rules: set[str]) -> sp.Expr:
    """The integral of f from a to b as F(b) - F(a), with F proposed by SymPy
    and checked here: F' = f by the rules, and f continuous on [a, b] (on
    every real number when a bound is symbolic)."""
    try:
        domain = sp.Interval(a, b) if a.is_number and b.is_number and a <= b else sp.S.Reals
        if sp.calculus.util.continuous_domain(f, x, domain) != domain:
            raise _Unproven
        proposed = sp.integrate(f, x)
    except _Unproven:
        raise
    except Exception as exc:  # noqa: BLE001 - SymPy could not propose one
        raise _Unproven from exc
    if proposed.has(sp.Integral):
        raise _Unproven
    checking: set[str] = set()
    if not _zero(derivative(proposed, x, checking) - f):
        raise _Unproven  # SymPy's proposal is not an antiderivative
    rules.add("FTC")
    return proposed.subs(x, b) - proposed.subs(x, a)


# ---------------------------------------------------------------------------
# Limits by the algebra of limits
# ---------------------------------------------------------------------------

#: How deep one limit may recurse (L'Hôpital, rewriting) before giving up.
_LIMIT_DEPTH = 8

_AT_INFINITY = {
    # f(u) as u -> oo, and as u -> -oo
    sp.exp: (sp.oo, sp.Integer(0)),
    sp.sinh: (sp.oo, -sp.oo),
    sp.cosh: (sp.oo, sp.oo),
    sp.tanh: (sp.Integer(1), sp.Integer(-1)),
    sp.atan: (sp.pi / 2, -sp.pi / 2),
    sp.log: (sp.oo, None),
}

_CONTINUOUS = (sp.sin, sp.cos, sp.exp, sp.sinh, sp.cosh, sp.tanh, sp.atan, sp.Abs)


def _finite(v: sp.Expr) -> bool:
    return bool(v.is_finite) and not v.has(sp.zoo, sp.nan, sp.oo, -sp.oo)


def _continuous_at(f: sp.Expr, x: sp.Symbol, a: sp.Expr) -> bool:
    """Whether f is continuous at x = a, read off its parts: every
    denominator non-zero there, every logarithm's and fractional power's
    argument positive, every function a continuous one."""
    if not f.has(x) or f.is_Symbol or f.is_Number:
        return True
    if isinstance(f, (sp.Add, sp.Mul)):
        return all(_continuous_at(t, x, a) for t in f.args)
    if isinstance(f, sp.Pow):
        base, exp = f.args
        if exp.has(x):
            return _continuous_at(sp.exp(exp * sp.log(base)), x, a)
        at = sp.simplify(base.subs(x, a))
        if exp.is_negative and at.is_zero is not False:
            return False
        if not exp.is_integer and at.is_positive is not True:
            return False
        return _continuous_at(base, x, a)
    if isinstance(f, sp.log):
        return sp.simplify(f.args[0].subs(x, a)).is_positive is True and _continuous_at(f.args[0], x, a)
    if isinstance(f, sp.tan):
        return sp.simplify(sp.cos(f.args[0]).subs(x, a)).is_zero is False and _continuous_at(f.args[0], x, a)
    if isinstance(f, _CONTINUOUS):
        return all(_continuous_at(t, x, a) for t in f.args)
    return False  # an unknown function, floor, a piecewise one: not known continuous


def _sign_near(p: sp.Expr, x: sp.Symbol, a: sp.Expr, side: str, rules: set[str], depth: int) -> Optional[int]:
    """The sign p takes for x near a (on *side*), or None if it changes or is
    not known.  At a root of a polynomial the multiplicity decides it."""
    if a in (sp.oo, -sp.oo):
        try:
            limit = _lim(p, x, a, "", set(), depth + 1)
        except _Unproven:
            return None
        if limit in (sp.oo, -sp.oo):
            return 1 if limit == sp.oo else -1
        return int(sp.sign(limit)) if _finite(limit) and limit != 0 else None
    at = sp.simplify(p.subs(x, a))
    if _finite(at) and at.is_zero is False and at.is_real:
        return 1 if at.is_positive else -1
    if at != 0 or not p.is_polynomial(x):
        return None
    poly = sp.Poly(p, x)
    m, q = 0, poly
    while q.eval(a) == 0 and m < poly.degree():
        q = sp.Poly(sp.quo(q.as_expr(), x - a, x), x)
        m += 1
    s = sp.sign(sp.simplify(q.as_expr().subs(x, a)))
    if s not in (1, -1):
        return None
    if side == "+":
        return int(s)
    if side == "-":
        return int(s) * (-1) ** m
    return int(s) if m % 2 == 0 else None


def _lim(f: sp.Expr, x: sp.Symbol, a: sp.Expr, side: str, rules: set[str], depth: int = 0) -> sp.Expr:
    """lim f as x -> a (from *side*: "+", "-" or "" for both), by the rules a
    course uses; raises _Unproven when they do not settle it."""
    if depth > _LIMIT_DEPTH:
        raise _Unproven
    if not f.has(x):
        return f
    infinite = a in (sp.oo, -sp.oo)
    if infinite and side:
        raise _Unproven  # a one-sided limit at infinity is not a thing
    if f == x:
        return a
    if not infinite and _continuous_at(f, x, a):
        rules.add("substitution")
        value = sp.simplify(f.subs(x, a))
        if _finite(value):
            return value
        raise _Unproven
    # |u| where u keeps one sign near a is u or -u.
    if f.has(sp.Abs):
        replaced = f.replace(
            lambda e: isinstance(e, sp.Abs) and e.args[0].has(x),
            lambda e: _drop_abs(e, x, a, side, rules, depth),
        )
        if replaced != f:
            return _lim(replaced, x, a, side, rules, depth + 1)
    if not infinite:
        cancelled = sp.cancel(sp.together(f))
        if cancelled != f and _continuous_at(cancelled, x, a):
            rules.add("cancel, then substitute")
            value = sp.simplify(cancelled.subs(x, a))
            if _finite(value):
                return value
    if infinite and f.is_rational_function(x):
        return _dominant(f, x, a, rules)
    num, den = sp.fraction(sp.together(f))
    if den.has(x):
        return _quotient(num, den, x, a, side, rules, depth)
    if isinstance(f, sp.Mul):
        return _product(f, x, a, side, rules, depth)
    if isinstance(f, sp.Add):
        parts = [_lim(t, x, a, side, rules, depth + 1) for t in f.args]
        if sp.oo in parts and -sp.oo in parts:
            factored = sp.factor(f)
            if factored != f:
                return _lim(factored, x, a, side, rules, depth + 1)
            raise _Unproven
        rules.add("algebra of limits")
        return sp.Add(*parts)
    if isinstance(f, sp.Pow):
        base, exp = f.args
        if exp.has(x):
            return _lim(sp.exp(exp * sp.log(base)), x, a, side, rules, depth + 1)
        limit = _lim(base, x, a, side, rules, depth + 1)
        if limit == 0 and exp.is_negative:
            sign = _sign_near(base, x, a, side, rules, depth)
            if sign is None or not exp.is_integer:
                raise _Unproven
            rules.add("algebra of limits")
            return sp.oo if sign ** int(exp) > 0 else -sp.oo
        rules.add("algebra of limits")
        value = limit**exp
        if value.has(sp.zoo, sp.nan):
            raise _Unproven
        return value
    if len(f.args) == 1 and type(f) in _AT_INFINITY:
        limit = _lim(f.args[0], x, a, side, rules, depth + 1)
        if limit in (sp.oo, -sp.oo):
            value = _AT_INFINITY[type(f)][0 if limit == sp.oo else 1]
            if value is None:
                raise _Unproven
            rules.add("standard limit")
            return value
        if _finite(limit) and _continuous_at(type(f)(x), x, limit):
            rules.add("algebra of limits")
            return type(f)(limit)
    if len(f.args) == 1 and isinstance(f, (sp.sin, sp.cos)):
        limit = _lim(f.args[0], x, a, side, rules, depth + 1)
        if _finite(limit):
            rules.add("algebra of limits")
            return type(f)(limit)
    raise _Unproven


def _drop_abs(e: sp.Abs, x: sp.Symbol, a: sp.Expr, side: str, rules: set[str], depth: int) -> sp.Expr:
    sign = _sign_near(e.args[0], x, a, side, rules, depth)
    if sign is None:
        return e
    rules.add("sign near the point")
    return e.args[0] if sign > 0 else -e.args[0]


def _dominant(f: sp.Expr, x: sp.Symbol, a: sp.Expr, rules: set[str]) -> sp.Expr:
    """A rational function at +-oo: the leading terms decide it."""
    num, den = sp.fraction(sp.together(f))
    p, q = sp.Poly(num, x), sp.Poly(den, x)
    ratio = sp.simplify(p.LC() / q.LC())
    if ratio.is_zero is not False or not ratio.is_real:
        raise _Unproven
    gap = p.degree() - q.degree()
    rules.add("dominant terms")
    if gap < 0:
        return sp.Integer(0)
    if gap == 0:
        return ratio
    sign = (1 if ratio.is_positive else -1) * (1 if a == sp.oo else (-1) ** gap)
    return sp.oo if sign > 0 else -sp.oo


def _quotient(num: sp.Expr, den: sp.Expr, x: sp.Symbol, a: sp.Expr, side: str, rules: set[str], depth: int) -> sp.Expr:
    top = _lim(num, x, a, side, rules, depth + 1)
    bottom = _lim(den, x, a, side, rules, depth + 1)
    if _finite(bottom) and bottom.is_zero is False:
        rules.add("algebra of limits")
        value = sp.simplify(top / bottom)
        if value.has(sp.zoo, sp.nan):
            raise _Unproven
        return value
    both_zero = top == 0 and bottom == 0
    both_infinite = top in (sp.oo, -sp.oo) and bottom in (sp.oo, -sp.oo)
    if both_zero or both_infinite:
        rules.add("L'Hôpital's rule")
        steps: set[str] = set()
        ratio = sp.cancel(sp.together(derivative(num, x, steps) / derivative(den, x, steps)))
        return _lim(ratio, x, a, side, rules, depth + 1)
    if bottom == 0 and _finite(top) and top.is_zero is False:
        sign = _sign_near(den, x, a, side, rules, depth)
        if sign is None or not top.is_real:
            raise _Unproven
        rules.add("algebra of limits")
        return sp.oo if sign * (1 if top.is_positive else -1) > 0 else -sp.oo
    if _finite(top) and bottom in (sp.oo, -sp.oo):
        rules.add("algebra of limits")
        return sp.Integer(0)
    raise _Unproven


def _bounded(e: sp.Expr) -> bool:
    """sin(u), cos(u) and their whole powers: between -1 and 1, whatever u does."""
    if isinstance(e, (sp.sin, sp.cos)):
        return True
    return isinstance(e, sp.Pow) and isinstance(e.base, (sp.sin, sp.cos)) and e.exp.is_positive and e.exp.is_integer


def _product(f: sp.Mul, x: sp.Symbol, a: sp.Expr, side: str, rules: set[str], depth: int) -> sp.Expr:
    bounded = [t for t in f.args if t.has(x) and _bounded(t)]
    if bounded:
        rest = sp.Mul(*[t for t in f.args if t not in bounded])
        try:
            if _lim(rest, x, a, side, rules, depth + 1) == 0:
                rules.add("squeeze")
                return sp.Integer(0)
        except _Unproven:
            pass
    parts = [_lim(t, x, a, side, rules, depth + 1) for t in f.args]
    zero = any(p == 0 for p in parts)
    infinite = any(p in (sp.oo, -sp.oo) for p in parts)
    if zero and infinite:
        # 0 * oo: write it as a quotient and let L'Hôpital settle it.
        i = next(i for i, p in enumerate(parts) if p in (sp.oo, -sp.oo))
        others = sp.Mul(*[t for j, t in enumerate(f.args) if j != i])
        return _quotient(others, 1 / f.args[i], x, a, side, rules, depth + 1)
    rules.add("algebra of limits")
    value = sp.Mul(*parts)
    if value.has(sp.zoo, sp.nan):
        raise _Unproven
    return value


# ---------------------------------------------------------------------------
# Sums: a closed form checked by induction, or a term peeled off
# ---------------------------------------------------------------------------

#: Above this many terms, a sum with number bounds is not added up term by term.
_DIRECT_TERMS = 2000

#: How sums are read in this attempt: "closed" (a closed form, checked) or
#: "peel" (the sum kept whole, its last terms peeled off).
_SUM_MODE: ContextVar[str] = ContextVar("_SUM_MODE", default="closed")

#: Names bound by an enclosing sum (its index), as the translator should read them.
_BOUND: ContextVar[dict] = ContextVar("_BOUND", default={})


def _sum(
    body: sp.Expr, i: sp.Symbol, lo: sp.Expr, hi: sp.Expr, rules: set[str], ctx: Optional[ProofContext] = None
) -> sp.Expr:
    if not (_finite(lo) and _finite(hi)):
        raise _Unproven  # an infinite series needs convergence the rules do not check
    count = sp.simplify(hi - lo + 1)
    if count.is_Integer:
        if int(count) <= 0:
            rules.add("empty sum")
            return sp.Integer(0)
        if int(count) <= _DIRECT_TERMS:
            rules.add("direct sum")
            return sp.Add(*[body.subs(i, lo + k) for k in range(int(count))])
        raise _Unproven
    telescoped = _telescoping(body, i, lo, hi)
    if telescoped is not None:
        rules.add("telescoping")
        return telescoped
    if _SUM_MODE.get() == "closed":
        closed = _closed_form(body, i, lo, hi, ctx)
        if closed is not None:
            rules.add("closed form, by induction")
            return closed
    return _peeled(body, i, lo, hi, rules)


def _telescoping(body: sp.Expr, i: sp.Symbol, lo: sp.Expr, hi: sp.Expr) -> Optional[sp.Expr]:
    """sum of g(i) - g(i - 1) from lo to hi is g(hi) - g(lo - 1)."""
    if not isinstance(body, sp.Add) or len(body.args) != 2:
        return None
    for g, minus in (body.args, body.args[::-1]):
        if sp.simplify(minus + g.subs(i, i - 1)) == 0:
            return g.subs(i, hi) - g.subs(i, lo - 1)
    return None


def _closed_form(
    body: sp.Expr, i: sp.Symbol, lo: sp.Expr, hi: sp.Expr, ctx: Optional[ProofContext] = None
) -> Optional[sp.Expr]:
    """SymPy proposes S(N) for the sum from lo to N; it is used only once it
    is checked by induction: S(lo) is the first term, and S(N) - S(N - 1) is
    the N-th term for every N."""
    n = sp.Symbol("_N", integer=True)
    try:
        proposed = sp.summation(body, (i, lo, n))
    except Exception:  # noqa: BLE001
        return None
    # The geometric series comes back split at r = 1.  The general branch is
    # the formula a student writes, and it is the sum only when the proof has
    # ruled the other cases out (`Assume r != 1`): the notes' own trap is the
    # formula stated without that.
    for piece in proposed.atoms(sp.Piecewise):
        if not all(_ruled_out(cond, ctx) for _, cond in piece.args[:-1]):
            return None
    proposed = proposed.replace(lambda e: isinstance(e, sp.Piecewise), lambda e: e.args[-1].expr)
    if proposed.has(sp.Sum) or proposed.has(sp.Piecewise):
        return None
    base = sp.simplify(proposed.subs(n, lo) - body.subs(i, lo))
    step = sp.simplify(sp.expand_func(proposed - proposed.subs(n, n - 1) - body.subs(i, n)))
    if base != 0 or step != 0:
        return None
    return proposed.subs(n, hi)


def _ruled_out(condition: sp.Basic, ctx: Optional[ProofContext]) -> bool:
    """Whether the proof's hypotheses rule out `symbol = number` (the only
    kind of case a closed form is split on here)."""
    if ctx is None or not isinstance(condition, sp.Eq):
        return False
    symbol, value = condition.args
    if not isinstance(symbol, sp.Symbol):
        symbol, value = value, symbol
    if not (isinstance(symbol, sp.Symbol) and value.is_Rational):
        return False
    from aether.core.ast import NumberNode
    from aether.engine.logic import verify_entailment

    claim = RelationNode(op="!=", left=SymbolNode(name=symbol.name), right=NumberNode(value=str(value)))
    try:
        return verify_entailment(claim, ctx).valid
    except Exception:  # noqa: BLE001
        return False


def _peeled(body: sp.Expr, i: sp.Symbol, lo: sp.Expr, hi: sp.Expr, rules: set[str]) -> sp.Expr:
    """The sum kept whole, with its last few terms peeled off: the sum to
    k + 1 is the sum to k plus the term at k + 1."""
    shift, rest = hi.as_coeff_Add()
    if not shift.is_Integer or not 0 <= int(shift) <= 6:
        shift, rest = sp.Integer(0), hi
    canonical = body.subs(i, sp.Symbol("_i", integer=True))
    whole = sp.Function(f"Sum[{sp.srepr(canonical)}|{sp.srepr(lo)}]")(rest)
    if shift:
        rules.add("peeling the last term")
    return whole + sp.Add(*[body.subs(i, rest + k) for k in range(1, int(shift) + 1)])


# ---------------------------------------------------------------------------
# Reading the goal
# ---------------------------------------------------------------------------


def _symbol(name: str, ctx: ProofContext) -> sp.Symbol:
    from aether.engine.algebra import ast_to_sympy

    sym = ast_to_sympy(SymbolNode(name=name), ctx)
    if not isinstance(sym, sp.Symbol):
        raise _Unproven  # a constant such as pi, or a defined name
    return sym


def _value(node: ExprNode, ctx: ProofContext, rules: set[str]) -> sp.Expr:
    """*node* as SymPy, with each derivative and integral in it worked out by
    the rules rather than by SymPy."""
    from aether.engine.algebra import ast_to_sympy

    computed: dict[str, sp.Expr] = {}
    skeleton = _replace_calculus(node, ctx, rules, computed)
    try:
        value = ast_to_sympy(skeleton, ctx, dict(_BOUND.get()))
    except Exception as exc:  # noqa: BLE001
        raise _Unproven from exc
    if not computed:
        return value
    # The placeholders come back as whatever symbols the translator made of
    # them (with its assumptions), so they are matched by name.
    return value.subs({s: computed[s.name] for s in value.free_symbols if s.name in computed})


def _replace_calculus(node: ExprNode, ctx: ProofContext, rules: set[str], computed: dict[str, sp.Expr]) -> ExprNode:
    if isinstance(node, FunctionCallNode) and node.func.lower() == "diff" and len(node.args) in (2, 3):
        target, var = node.args[0], node.args[1]
        if not isinstance(var, (SymbolNode, GreekSymbolNode)):
            raise _Unproven
        x = _symbol(var.name, ctx)
        order = 1
        if len(node.args) == 3:
            try:
                order = int(str(node.args[2]))
            except ValueError as exc:
                raise _Unproven from exc
        value = _value(target, ctx, rules)
        for _ in range(order):
            value = derivative(value, x, rules)
        return _placeholder(value, computed)
    if isinstance(node, FunctionCallNode) and node.func.lower() in ("integrate", "integral") and len(node.args) == 4:
        body, var, lower, upper = node.args
        if not isinstance(var, (SymbolNode, GreekSymbolNode)):
            raise _Unproven
        return _placeholder(_integral(body, var.name, lower, upper, ctx, rules), computed)
    if isinstance(node, IntegralNode) and node.lower is not None and node.upper is not None:
        return _placeholder(_integral(node.body, node.var, node.lower, node.upper, ctx, rules), computed)
    if isinstance(node, LimitNode):
        x = _symbol(node.var, ctx)
        side = {"+": "+", "-": "-"}.get(node.direction.strip("'\""), "")
        value = _lim(_value(node.body, ctx, rules), x, _value(node.target, ctx, rules), side, rules)
        return _placeholder(value, computed)
    if isinstance(node, FunctionCallNode) and node.func.lower() == "sum" and len(node.args) == 4:
        idx, lower, upper, body = node.args
        if not isinstance(idx, (SymbolNode, GreekSymbolNode)):
            raise _Unproven
        i = sp.Symbol(idx.name, integer=True)
        # The index is bound in the body: `i` there is the index, not sqrt(-1).
        token = _BOUND.set({**_BOUND.get(), idx.name: i})
        try:
            term = _value(body, ctx, rules)
        finally:
            _BOUND.reset(token)
        return _placeholder(_sum(term, i, _value(lower, ctx, rules), _value(upper, ctx, rules), rules, ctx), computed)
    if not hasattr(node, "__dataclass_fields__"):
        return node
    changes: dict[str, object] = {}
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, ExprNode):
            new = _replace_calculus(value, ctx, rules, computed)
            if new is not value:
                changes[f.name] = new
        elif isinstance(value, list) and any(isinstance(v, ExprNode) for v in value):
            new_list = [_replace_calculus(v, ctx, rules, computed) if isinstance(v, ExprNode) else v for v in value]
            if any(a is not b for a, b in zip(new_list, value)):
                changes[f.name] = new_list
    return replace(node, **changes) if changes else node


def _integral(body: ExprNode, var: str, lower: ExprNode, upper: ExprNode, ctx: ProofContext, rules: set[str]) -> sp.Expr:
    x = _symbol(var, ctx)
    return _definite(_value(body, ctx, rules), x, _value(lower, ctx, rules), _value(upper, ctx, rules), rules)


def _placeholder(value: sp.Expr, computed: dict[str, sp.Expr]) -> SymbolNode:
    name = f"_calc{len(computed)}"
    computed[name] = value
    return SymbolNode(name=name)


def _mentions_calculus(node: object) -> bool:
    if isinstance(node, IntegralNode):
        return True
    if isinstance(node, LimitNode):
        return True
    if isinstance(node, FunctionCallNode) and node.func.lower() in ("diff", "integrate", "integral", "sum"):
        return True
    if not hasattr(node, "__dataclass_fields__"):
        return False
    for f in fields(node):  # type: ignore[arg-type]
        value = getattr(node, f.name)
        if isinstance(value, ExprNode) and _mentions_calculus(value):
            return True
        if isinstance(value, list) and any(_mentions_calculus(v) for v in value if isinstance(v, ExprNode)):
            return True
    return False


def verify(goal: ExprNode, ctx: ProofContext) -> Optional[list[str]]:
    """The rules that show *goal*, an equation about derivatives or definite
    integrals, most telling first; None when they do not show it."""
    goal = ctx.expand_user_functions(goal) or goal
    if not (isinstance(goal, RelationNode) and goal.op in ("=", "==") and _mentions_calculus(goal)):
        return None
    # Sums are read two ways: by closed forms (a sum equal to its formula) and
    # kept whole with terms peeled off (the sum to k + 1 against the sum to k).
    for mode in ("closed", "peel"):
        rules: set[str] = set()
        token = _SUM_MODE.set(mode)
        try:
            left, right = _value(goal.left, ctx, rules), _value(goal.right, ctx, rules)
        except (_Unproven, RecursionError):
            continue
        except Exception:  # noqa: BLE001 - anything the rules cannot read
            continue
        finally:
            _SUM_MODE.reset(token)
        if _same(left, right):
            return [r for r in _ORDER if r in rules] or ["calculus rules"]
    return None


def _same(left: sp.Expr, right: sp.Expr) -> bool:
    """Equal values, infinities included (oo - oo is not 0, but oo is oo)."""
    if any(v.has(sp.oo, -sp.oo, sp.zoo, sp.nan) for v in (left, right)):
        return left == right and not left.has(sp.zoo, sp.nan)
    return _zero(left - right)
