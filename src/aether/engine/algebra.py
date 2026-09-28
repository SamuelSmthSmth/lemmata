"""SymPy algebraic verification engine, domain obligation extractor, and counterexample finder."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
from typing import Optional

import sympy as sp

from aether.core.ast import (
    ExprNode,
    SymbolNode,
    GreekSymbolNode,
    NumberNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    RelationNode,
    QuantifierNode,
)
from aether.core.types import MathType
from aether.engine.context import (
    ProofContext,
    DomainObligation,
    canonical_rel,
    collect_free_symbols,
)


class AlgebraConversionError(Exception):
    """Raised when an AST node cannot be converted into a pure SymPy algebraic expression."""


@dataclass
class AlgebraResult:
    """Result of checking an algebraic equality step."""

    valid: bool
    message: str
    counterexample: Optional[str] = None
    used_substitutions: bool = False


def extract_domain_obligations(
    expr: ExprNode,
    line: Optional[int] = None,
) -> list[DomainObligation]:
    """Walk *expr* AST prior to CAS simplification and extract domain obligations.

    - Division ``A / B`` emits ``B != 0``.
    - Square root ``sqrt(A)`` emits ``A >= 0``.
    """
    obligations: list[DomainObligation] = []

    def _walk(node: ExprNode) -> None:
        if isinstance(node, BinaryOpNode):
            _walk(node.left)
            _walk(node.right)
            if node.op == "/":
                cond = RelationNode(
                    op="!=",
                    left=node.right,
                    right=NumberNode(value="0"),
                    line=line,
                )
                obligations.append(
                    DomainObligation(
                        condition=cond,
                        reason=f"non-zero denominator ({node.right} != 0) in {node}",
                        line=line,
                    )
                )
        elif isinstance(node, UnaryOpNode):
            _walk(node.operand)
        elif isinstance(node, FunctionCallNode):
            for arg in node.args:
                _walk(arg)
            if node.func.lower() == "sqrt" and len(node.args) == 1:
                rad = node.args[0]
                cond = RelationNode(
                    op=">=",
                    left=rad,
                    right=NumberNode(value="0"),
                    line=line,
                )
                obligations.append(
                    DomainObligation(
                        condition=cond,
                        reason=f"non-negative radicand ({rad} >= 0) in {node}",
                        line=line,
                    )
                )
        elif isinstance(node, RelationNode):
            _walk(node.left)
            _walk(node.right)
        elif isinstance(node, QuantifierNode):
            _walk(node.formula)

    _walk(expr)
    return obligations


def _make_sympy_symbol(name: str, ctx: ProofContext) -> sp.Symbol:
    var_info = ctx.get_var(name)
    mt = var_info.math_type if var_info else MathType.Real
    if mt == MathType.Nat:
        return sp.Symbol(name, integer=True, nonnegative=True, real=True)
    if mt == MathType.Int:
        return sp.Symbol(name, integer=True, real=True)
    if mt == MathType.Rat:
        return sp.Symbol(name, rational=True, real=True)
    if mt == MathType.Real:
        return sp.Symbol(name, real=True)
    return sp.Symbol(name)


_SYMPY_FUNCS = {
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "factorial": sp.factorial,
}


def ast_to_sympy(expr: ExprNode, ctx: ProofContext) -> sp.Expr:
    """Convert an Aether arithmetic ``ExprNode`` into a SymPy ``Expr``."""
    if isinstance(expr, NumberNode):
        if "." in expr.value:
            return sp.Rational(expr.value)
        return sp.Integer(int(expr.value))

    if isinstance(expr, SymbolNode):
        return _make_sympy_symbol(expr.name, ctx)

    if isinstance(expr, GreekSymbolNode):
        return _make_sympy_symbol(expr.name, ctx)

    if isinstance(expr, UnaryOpNode):
        sub = ast_to_sympy(expr.operand, ctx)
        if expr.op == "-":
            return -sub
        if expr.op == "+":
            return sub
        raise AlgebraConversionError(f"Unsupported unary operator in algebra: {expr.op!r}")

    if isinstance(expr, BinaryOpNode):
        left = ast_to_sympy(expr.left, ctx)
        right = ast_to_sympy(expr.right, ctx)
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            return left / right
        if expr.op in ("^", "**"):
            return left ** right
        raise AlgebraConversionError(f"Unsupported binary operator in algebra: {expr.op!r}")

    if isinstance(expr, FunctionCallNode):
        fn_name = expr.func.lower()
        if fn_name in _SYMPY_FUNCS:
            args = [ast_to_sympy(a, ctx) for a in expr.args]
            return _SYMPY_FUNCS[fn_name](*args)
        # Uninterpreted mathematical function
        sym_fn = sp.Function(expr.func)
        args = [ast_to_sympy(a, ctx) for a in expr.args]
        return sym_fn(*args)

    raise AlgebraConversionError(f"Cannot convert {type(expr).__name__} to SymPy expression.")


def _is_zero(diff: sp.Expr) -> bool:
    """Robustly check whether *diff* simplifies to 0 in SymPy."""
    if diff == 0 or diff is sp.S.Zero:
        return True
    expanded = sp.expand(diff)
    if expanded == 0:
        return True
    simplified = sp.simplify(expanded)
    if simplified == 0:
        return True
    together = sp.radsimp(sp.together(expanded))
    return together == 0


def _apply_context_substitutions(
    expr: sp.Expr,
    ctx: ProofContext,
) -> tuple[sp.Expr, bool]:
    """Apply active equality hypotheses ``lhs = rhs`` from *ctx* to *expr*."""
    used = False
    current = expr
    for lhs_node, rhs_node in ctx.get_equality_substitutions():
        try:
            s_lhs = ast_to_sympy(lhs_node, ctx)
            s_rhs = ast_to_sympy(rhs_node, ctx)
        except AlgebraConversionError:
            continue
        if s_lhs == s_rhs:
            continue
        updated = current.subs(s_lhs, s_rhs)
        if updated != current:
            current = updated
            used = True
    return current, used


def find_counterexample(
    lhs: ExprNode,
    rhs: ExprNode,
    ctx: ProofContext,
) -> Optional[str]:
    """Search for a concrete numeric assignment showing ``lhs != rhs``."""
    try:
        s_lhs = ast_to_sympy(lhs, ctx)
        s_rhs = ast_to_sympy(rhs, ctx)
    except AlgebraConversionError:
        return None

    # Apply equality substitutions first so bound variables like n = 2*k are respected
    s_lhs_sub, _ = _apply_context_substitutions(s_lhs, ctx)
    s_rhs_sub, _ = _apply_context_substitutions(s_rhs, ctx)

    free_syms = sorted(
        list(s_lhs_sub.free_symbols | s_rhs_sub.free_symbols),
        key=lambda s: s.name,
    )

    if not free_syms:
        try:
            v_l = sp.N(s_lhs_sub)
            v_r = sp.N(s_rhs_sub)
            if v_l != v_r:
                return f"LHS evaluates to {s_lhs_sub}, while RHS evaluates to {s_rhs_sub}."
        except Exception:
            pass
        return None

    # Collect active inequality hypotheses to filter candidate points
    ineq_checks: list[tuple[sp.Expr, str, sp.Expr]] = []
    for h in ctx.all_hypotheses():
        if isinstance(h.proposition, RelationNode):
            op = canonical_rel(h.proposition.op)
            if op in ("<", "<=", ">", ">=", "!="):
                try:
                    il = ast_to_sympy(h.proposition.left, ctx)
                    ir = ast_to_sympy(h.proposition.right, ctx)
                    il, _ = _apply_context_substitutions(il, ctx)
                    ir, _ = _apply_context_substitutions(ir, ctx)
                    ineq_checks.append((il, op, ir))
                except AlgebraConversionError:
                    pass

    candidate_pool = [3, 2, 1, 4, 5, -1, -2]
    for values in itertools.product(candidate_pool, repeat=len(free_syms)):
        sub_map = dict(zip(free_syms, values))

        # Check Nat non-negativity
        valid_point = True
        for sym, val in sub_map.items():
            vinfo = ctx.get_var(sym.name)
            if vinfo and vinfo.math_type == MathType.Nat and val < 0:
                valid_point = False
                break
        if not valid_point:
            continue

        # Check active inequality hypotheses
        for il, op, ir in ineq_checks:
            try:
                vl = float(il.subs(sub_map))
                vr = float(ir.subs(sub_map))
                if op == "<" and not (vl < vr):
                    valid_point = False
                elif op == "<=" and not (vl <= vr):
                    valid_point = False
                elif op == ">" and not (vl > vr):
                    valid_point = False
                elif op == ">=" and not (vl >= vr):
                    valid_point = False
                elif op == "!=" and not (vl != vr):
                    valid_point = False
            except Exception:
                valid_point = False
            if not valid_point:
                break

        if not valid_point:
            continue

        try:
            val_l = s_lhs_sub.subs(sub_map)
            val_r = s_rhs_sub.subs(sub_map)
            if val_l.has(sp.zoo, sp.oo, -sp.oo, sp.nan) or val_r.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
                continue
            if not _is_zero(val_l - val_r):
                assign_str = ", ".join(f"{sym.name}={val}" for sym, val in sub_map.items())
                return f"Counterexample at {assign_str}: LHS = {val_l}, RHS = {val_r}"
        except Exception:
            continue

    return None


def verify_algebraic_equality(
    lhs: ExprNode,
    rhs: ExprNode,
    ctx: ProofContext,
) -> AlgebraResult:
    """Verify whether ``lhs = rhs`` holds by pure algebra or context equality substitution."""
    try:
        s_lhs = ast_to_sympy(lhs, ctx)
        s_rhs = ast_to_sympy(rhs, ctx)
    except AlgebraConversionError as exc:
        return AlgebraResult(valid=False, message=str(exc))

    # 1. Direct algebraic simplification
    if _is_zero(s_lhs - s_rhs):
        return AlgebraResult(
            valid=True,
            message=f"Verified algebraically by SymPy ({lhs} = {rhs}).",
            used_substitutions=False,
        )

    # 2. Try substituting active context equalities (e.g. n = 2 * k)
    s_lhs_sub, used_l = _apply_context_substitutions(s_lhs, ctx)
    s_rhs_sub, used_r = _apply_context_substitutions(s_rhs, ctx)
    if (used_l or used_r) and _is_zero(s_lhs_sub - s_rhs_sub):
        return AlgebraResult(
            valid=True,
            message=f"Verified by SymPy using context substitutions ({lhs} = {rhs}).",
            used_substitutions=True,
        )

    # 3. Failed — generate concrete counterexample
    ce = find_counterexample(lhs, rhs, ctx)
    diff_expr = sp.simplify(s_lhs_sub - s_rhs_sub)
    msg = f"Algebraic step failed: ({lhs}) - ({rhs}) simplifies to {diff_expr} != 0."
    if ce:
        msg = f"{msg} {ce}"
    return AlgebraResult(
        valid=False,
        message=msg,
        counterexample=ce,
    )
