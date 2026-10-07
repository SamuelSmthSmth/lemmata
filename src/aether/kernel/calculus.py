"""Calculus as named rules: derivatives by the rules a course teaches, and
definite integrals by the Fundamental Theorem.

The engine settles `diff(...)` and `integrate(...)` by asking SymPy for the
answer.  The kernel does not take that answer on trust: it differentiates by
its own rules (sum, product, quotient, chain, power and the standard
functions), recording which ones it used, and for an integral it lets SymPy
*propose* an antiderivative F and checks it: F' = f by those same rules, f
continuous on the interval, then F(b) - F(a).  SymPy may propose; the kernel
checks.

``verify(goal, ctx)`` returns the rules that show an equation about
derivatives or integrals, or None when they do not (an unknown function's
integral, a discontinuity, a derivative of |x|): the engine's verdict then
stands, as it did before.  Nothing here changes a verdict; it is what the
audit can say about why a line holds.
"""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Optional

import sympy as sp
from sympy.core.function import AppliedUndef

from aether.core.ast import ExprNode, FunctionCallNode, GreekSymbolNode, IntegralNode, RelationNode, SymbolNode
from aether.engine.context import ProofContext

#: The order the audit names rules in, the most telling first.
_ORDER = ("FTC", "chain rule", "quotient rule", "product rule", "power rule", "standard derivative", "sum rule")


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
        value = ast_to_sympy(skeleton, ctx)
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
    if isinstance(node, FunctionCallNode) and node.func.lower() in ("diff", "integrate", "integral"):
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
    rules: set[str] = set()
    try:
        difference = _value(goal.left, ctx, rules) - _value(goal.right, ctx, rules)
    except (_Unproven, RecursionError):
        return None
    except Exception:  # noqa: BLE001 - anything the rules cannot read
        return None
    if not _zero(difference):
        return None
    return [r for r in _ORDER if r in rules] or ["standard derivative"]
