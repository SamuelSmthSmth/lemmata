"""Show your working: steps that do in one jump what a question asks to see.

SymPy differentiates ``x^2 * sin(x)``, integrates by parts and sums a series in
closed form at once, so ``diff(x^2 * sin(x), x) = 2*x*sin(x) + x^2*cos(x)``
checks in a single line.  That is correct, and for an exam question it skips
the marks: the product rule is the point.  With ``show_working`` on, a step
that makes an operator disappear is looked at for what the jump needed:

- a derivative or integral of a product, a quotient or a composition with a
  non-linear inside needs a rule (product, quotient or chain; by parts or by
  substitution).  Standard results, including linear insides like ``sin(3*x)``
  and ``e^(2*x)`` (the formula booklet's), may be written down directly;
- a sum to a symbolic bound in closed form needs a proof (induction, or the
  method of differences): its own steps, not one line;
- a limit evaluated straight from an indeterminate form needs the algebra
  that resolves it first.

Writing the working out (``diff(u * v, x) = diff(u, x) * v + u * diff(v, x)``
keeps derivatives on the right, so it is not a jump) passes.  The verdict is
a warning naming the rule, never a refusal: the mathematics is right.
"""

from __future__ import annotations

from typing import Optional

import sympy as sp

from aether.core.ast import (
    ExprNode,
    FunctionCallNode,
    IntegralNode,
    LimitNode,
    NumberNode,
    SymbolNode,
    GreekSymbolNode,
)
from aether.engine.algebra import ast_to_sympy
from aether.engine.context import ProofContext

_OPERATORS = ("diff", "integrate", "lim", "sum")

# Functions whose derivative and integral with a linear inside are standard.
_ELEMENTARY = (sp.sin, sp.cos, sp.tan, sp.sec, sp.csc, sp.cot, sp.exp, sp.log, sp.sinh, sp.cosh, sp.tanh)


def _operators(expr: object, out: list[ExprNode]) -> None:
    """Every diff / integrate / lim / sum in *expr*, outermost first."""
    if isinstance(expr, FunctionCallNode) and expr.func.lower() in _OPERATORS:
        out.append(expr)
    elif isinstance(expr, (IntegralNode, LimitNode)):
        out.append(expr)
    if isinstance(expr, (list, tuple)):
        for item in expr:
            _operators(item, out)
    elif hasattr(expr, "__dataclass_fields__"):
        for name in expr.__dataclass_fields__:  # type: ignore[union-attr]
            if name not in ("line", "col"):
                _operators(getattr(expr, name), out)


def _kind(node: ExprNode) -> str:
    if isinstance(node, IntegralNode):
        return "integrate"
    if isinstance(node, LimitNode):
        return "lim"
    return node.func.lower()  # type: ignore[union-attr]


def _linear(expr: sp.Expr, x: sp.Symbol) -> bool:
    try:
        return sp.Poly(expr, x).degree() <= 1
    except (sp.PolynomialError, sp.GeneratorsNeeded):
        return not expr.has(x)


def _rule_needed(f: sp.Expr, x: sp.Symbol) -> Optional[str]:
    """The rule differentiating *f* in x needs, or None for a standard result."""
    if not f.has(x):
        return None
    if f == x:
        return None
    if isinstance(f, sp.Add):
        for term in f.args:
            rule = _rule_needed(term, x)
            if rule:
                return rule
        return None
    if isinstance(f, sp.Mul):
        varying = [a for a in f.args if a.has(x)]
        if len(varying) > 1:
            if any(isinstance(a, sp.Pow) and a.exp.is_negative for a in varying):
                return "the quotient rule"
            return "the product rule"
        return _rule_needed(varying[0], x)
    if isinstance(f, sp.Pow):
        base, exp = f.args
        if exp.has(x):
            if base.has(x) or not _linear(exp, x):
                return "the chain rule"
            return None  # a^(kx + c)
        if base == x:
            return None  # x^n
        if exp.is_negative and _linear(base, x) and exp == -1:
            return None  # 1/(ax + b), whose integral is a standard log
        return "the chain rule"
    if isinstance(f, _ELEMENTARY) or (isinstance(f, sp.Function) and len(f.args) == 1):
        inner = f.args[0]
        if _linear(inner, x):
            return None
        return "the chain rule"
    return None


def _variable(node: ExprNode) -> Optional[str]:
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        return node.name
    return None


def working_gap(lhs: Optional[ExprNode], rhs: Optional[ExprNode], ctx: ProofContext) -> Optional[str]:
    """Why the step from *lhs* to *rhs* skips working, or None if it does not.

    Only an operator that is on the left and gone from the right counts: a
    step that rewrites a derivative into derivatives of its parts is the
    working itself.
    """
    if lhs is None or rhs is None:
        return None
    before: list[ExprNode] = []
    after: list[ExprNode] = []
    _operators(lhs, before)
    _operators(rhs, after)
    remaining = {str(op) for op in after}
    remaining_kinds = {_kind(op) for op in after}
    for op in before:
        if str(op) in remaining:
            continue
        kind = _kind(op)
        if kind in remaining_kinds:
            continue  # rewritten into the same operator on its parts: working shown
        gap = _gap(op, kind, ctx)
        if gap:
            return gap
    return None


def _gap(op: ExprNode, kind: str, ctx: ProofContext) -> Optional[str]:
    try:
        if kind in ("diff", "integrate") and isinstance(op, FunctionCallNode) and len(op.args) >= 2:
            name = _variable(op.args[1])
            if name is None:
                return None
            f = ast_to_sympy(op.args[0], ctx)
            x = next((s for s in f.free_symbols if s.name == name), sp.Symbol(name))
            rule = _rule_needed(f, x)
            if rule is None:
                return None
            if kind == "integrate":
                return (
                    f"this step works out {op} in one go. Integrating {op.args[0]} needs integration "
                    f"by substitution or by parts: write the substitution, or u, dv/dx, du/dx and v, "
                    f"as steps."
                )
            return (
                f"this step works out {op} in one go, which needs {rule}. Write that working "
                f"as steps: name the parts, differentiate each, then combine them."
            )
        if kind == "integrate" and isinstance(op, IntegralNode):
            f = ast_to_sympy(op.body, ctx)
            x = next((s for s in f.free_symbols if s.name == op.var), sp.Symbol(op.var))
            if _rule_needed(f, x) is None:
                return None
            return (
                f"this step works out the integral of {op.body} in one go, which needs integration "
                f"by substitution or by parts: write the steps."
            )
        if kind == "sum" and isinstance(op, FunctionCallNode) and len(op.args) == 4:
            lower, upper = op.args[1], op.args[2]
            if isinstance(lower, NumberNode) and isinstance(upper, NumberNode):
                return None  # a finite sum of numbers is arithmetic
            return (
                f"this step writes {op} in closed form in one go. A formula for a sum to a "
                f"variable bound needs proving: by induction, or by the method of differences."
            )
        if kind == "lim":
            return _limit_gap(op, ctx)
    except Exception:
        return None
    return None


def _limit_gap(op: ExprNode, ctx: ProofContext) -> Optional[str]:
    """A limit is fine to write down when substituting the target gives its value."""
    if isinstance(op, LimitNode):
        body, var, target = op.body, op.var, op.target
    elif isinstance(op, FunctionCallNode) and len(op.args) >= 3 and _variable(op.args[1]):
        body, var, target = op.args[0], _variable(op.args[1]), op.args[2]
    else:
        return None
    f = ast_to_sympy(body, ctx)
    x = next((s for s in f.free_symbols if s.name == var), sp.Symbol(var))
    value = f.subs(x, ast_to_sympy(target, ctx))
    if value.has(sp.nan, sp.zoo) or value is sp.nan:
        return (
            f"this step evaluates {op} in one go, but substituting gives an indeterminate form: "
            f"simplify first (cancel the common factor), then take the limit."
        )
    return None
