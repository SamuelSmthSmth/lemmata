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
    VectorNode,
    MatrixNode,
    EmptySetNode,
    IntegralNode,
    LimitNode,
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
    counterexample_dict: Optional[dict[str, str]] = None
    used_substitutions: bool = False


def extract_domain_obligations(
    expr: ExprNode,
    line: Optional[int] = None,
    ctx: Optional[ProofContext] = None,
) -> list[DomainObligation]:
    """Walk *expr* AST prior to CAS simplification and extract domain obligations.

    - Inline user-defined functions ``f(a)`` first so domain obligations inside ``f``
      are checked at the call site ``x = a``.
    - Division ``A / B`` emits ``B != 0``.
    - Square root ``sqrt(A)`` emits ``A >= 0``.
    """
    if ctx is not None:
        expr = ctx.expand_user_functions(expr) or expr

    obligations: list[DomainObligation] = []

    def _walk(node: ExprNode, dest: list[DomainObligation]) -> None:
        if isinstance(node, BinaryOpNode):
            _walk(node.left, dest)
            _walk(node.right, dest)
            if node.op == "/":
                cond = RelationNode(
                    op="!=",
                    left=node.right,
                    right=NumberNode(value="0"),
                    line=line,
                )
                dest.append(
                    DomainObligation(
                        condition=cond,
                        reason=f"non-zero denominator ({node.right} != 0) in {node}",
                        line=line,
                    )
                )
        elif isinstance(node, UnaryOpNode):
            _walk(node.operand, dest)
        elif isinstance(node, FunctionCallNode):
            for arg in node.args:
                _walk(arg, dest)
            if node.func.lower() == "sqrt" and len(node.args) == 1:
                rad = node.args[0]
                cond = RelationNode(
                    op=">=",
                    left=rad,
                    right=NumberNode(value="0"),
                    line=line,
                )
                dest.append(
                    DomainObligation(
                        condition=cond,
                        reason=f"non-negative radicand ({rad} >= 0) in {node}",
                        line=line,
                    )
                )
        elif isinstance(node, RelationNode):
            _walk(node.left, dest)
            _walk(node.right, dest)
        elif isinstance(node, QuantifierNode):
            _walk(node.formula, dest)
        elif isinstance(node, IntegralNode):
            if node.lower is not None:
                _walk(node.lower, dest)
            if node.upper is not None:
                _walk(node.upper, dest)
            sub_obs: list[DomainObligation] = []
            _walk(node.body, sub_obs)
            for ob in sub_obs:
                symbols = collect_free_symbols(ob.condition)
                if node.var not in symbols:
                    dest.append(ob)
        elif isinstance(node, LimitNode):
            _walk(node.target, dest)
            sub_obs: list[DomainObligation] = []
            _walk(node.body, sub_obs)
            for ob in sub_obs:
                symbols = collect_free_symbols(ob.condition)
                if node.var not in symbols:
                    dest.append(ob)

    _walk(expr, obligations)
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
class SetSymbol(sp.Set, sp.Symbol):
    """Symbol representing an abstract set in SymPy."""

    def __new__(cls, name: str):
        return sp.Symbol.__new__(cls, name)


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
    if mt == MathType.Complex:
        return sp.Symbol(name, complex=True)
    if mt == MathType.Set:
        return SetSymbol(name)
    return sp.Symbol(name)


_SYMPY_FUNCS = {
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "max": sp.Max,
    "min": sp.Min,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "factorial": sp.factorial,
}


def ast_to_sympy(
    expr: ExprNode,
    ctx: ProofContext,
    bound_symbols: Optional[dict[str, sp.Symbol]] = None,
) -> sp.Expr:
    """Convert an Aether arithmetic ``ExprNode`` into a SymPy ``Expr``."""
    if bound_symbols is None:
        bound_symbols = {}

    expanded_expr = ctx.expand_user_functions(expr)
    if expanded_expr is not None:
        expr = expanded_expr

    if isinstance(expr, NumberNode):
        if "." in expr.value:
            return sp.Rational(expr.value)
        return sp.Integer(int(expr.value))

    if isinstance(expr, VectorNode):
        elements = [ast_to_sympy(e, ctx, bound_symbols) for e in expr.elements]
        return sp.Matrix(elements)

    if isinstance(expr, MatrixNode):
        rows = [[ast_to_sympy(e, ctx, bound_symbols) for e in r] for r in expr.rows]
        return sp.Matrix(rows)

    if isinstance(expr, EmptySetNode):
        return sp.EmptySet

    if isinstance(expr, IntegralNode):
        var_sym = _make_sympy_symbol(expr.var, ctx)
        inner_bound = dict(bound_symbols)
        inner_bound[expr.var] = var_sym
        s_body = ast_to_sympy(expr.body, ctx, inner_bound)
        if expr.lower is not None and expr.upper is not None:
            s_lower = ast_to_sympy(expr.lower, ctx, bound_symbols)
            s_upper = ast_to_sympy(expr.upper, ctx, bound_symbols)
            return sp.integrate(s_body, (var_sym, s_lower, s_upper))
        return sp.integrate(s_body, var_sym)

    if isinstance(expr, LimitNode):
        var_sym = _make_sympy_symbol(expr.var, ctx)
        inner_bound = dict(bound_symbols)
        inner_bound[expr.var] = var_sym
        s_body = ast_to_sympy(expr.body, ctx, inner_bound)
        s_target = ast_to_sympy(expr.target, ctx, bound_symbols)
        return sp.limit(s_body, var_sym, s_target, dir=expr.direction)

    if isinstance(expr, SymbolNode):
        if expr.name in bound_symbols:
            return bound_symbols[expr.name]
        # Treat 'i' or 'I' as imaginary unit unless explicitly declared as a variable
        if expr.name in ("i", "I") and ctx.get_var(expr.name) is None:
            return sp.I
        vinfo = ctx.get_var(expr.name)
        if (
            vinfo is not None
            and vinfo.condition is not None
            and isinstance(vinfo.condition, RelationNode)
            and canonical_rel(vinfo.condition.op) == "="
            and isinstance(vinfo.condition.left, (SymbolNode, GreekSymbolNode))
            and vinfo.condition.left.name == expr.name
        ):
            if expr.name not in bound_symbols:
                inner_bound = dict(bound_symbols)
                inner_bound[expr.name] = _make_sympy_symbol(expr.name, ctx)
                return ast_to_sympy(vinfo.condition.right, ctx, inner_bound)
        return _make_sympy_symbol(expr.name, ctx)

    if isinstance(expr, GreekSymbolNode):
        if expr.name in bound_symbols:
            return bound_symbols[expr.name]
        vinfo = ctx.get_var(expr.name)
        if (
            vinfo is not None
            and vinfo.condition is not None
            and isinstance(vinfo.condition, RelationNode)
            and canonical_rel(vinfo.condition.op) == "="
            and isinstance(vinfo.condition.left, (SymbolNode, GreekSymbolNode))
            and vinfo.condition.left.name == expr.name
        ):
            if expr.name not in bound_symbols:
                inner_bound = dict(bound_symbols)
                inner_bound[expr.name] = _make_sympy_symbol(expr.name, ctx)
                return ast_to_sympy(vinfo.condition.right, ctx, inner_bound)
        return _make_sympy_symbol(expr.name, ctx)

    if isinstance(expr, UnaryOpNode):
        sub = ast_to_sympy(expr.operand, ctx, bound_symbols)
        if expr.op == "-":
            return -sub
        if expr.op == "+":
            return sub
        raise AlgebraConversionError(f"Unsupported unary operator in algebra: {expr.op!r}")

    if isinstance(expr, BinaryOpNode):
        left = ast_to_sympy(expr.left, ctx, bound_symbols)
        right = ast_to_sympy(expr.right, ctx, bound_symbols)
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
        if expr.op in ("\\circ", "\\cdot"):
            return sp.Function("op")(left, right)
        if expr.op in ("\\cup", "union"):
            try:
                return sp.Union(left, right)
            except (TypeError, ValueError):
                return sp.Function("union")(left, right)
        if expr.op in ("\\cap", "intersect"):
            try:
                return sp.Intersection(left, right)
            except (TypeError, ValueError):
                return sp.Function("intersect")(left, right)
        if expr.op in ("\\setminus", "setminus"):
            try:
                return sp.Complement(left, right)
            except (TypeError, ValueError):
                return sp.Function("setminus")(left, right)
        raise AlgebraConversionError(f"Unsupported binary operator in algebra: {expr.op!r}")

    if isinstance(expr, FunctionCallNode):
        fn_name = expr.func.lower()
        if fn_name in ("inv", "inverse") and len(expr.args) == 1:
            return sp.Function("inv")(ast_to_sympy(expr.args[0], ctx, bound_symbols))
        if fn_name == "sum" and len(expr.args) == 4:
            idx_node, lower_node, upper_node, body_node = expr.args
            if not isinstance(idx_node, (SymbolNode, GreekSymbolNode)):
                raise AlgebraConversionError("First argument to sum() must be an index variable.")
            idx_sym = sp.Symbol(idx_node.name, integer=True, real=True)
            inner_bound = dict(bound_symbols)
            inner_bound[idx_node.name] = idx_sym
            s_lower = ast_to_sympy(lower_node, ctx, bound_symbols)
            s_upper = ast_to_sympy(upper_node, ctx, bound_symbols)
            s_body = ast_to_sympy(body_node, ctx, inner_bound)
            return sp.Sum(s_body, (idx_sym, s_lower, s_upper)).doit()

        if fn_name == "diff" and len(expr.args) >= 2:
            s_target = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            var_node = expr.args[1]
            if isinstance(var_node, (SymbolNode, GreekSymbolNode)):
                s_var = _make_sympy_symbol(var_node.name, ctx)
            else:
                s_var = ast_to_sympy(var_node, ctx, bound_symbols)
            order = 1
            if len(expr.args) >= 3:
                s_order = ast_to_sympy(expr.args[2], ctx, bound_symbols)
                try:
                    order = int(s_order)
                except Exception:
                    order = 1
            return sp.diff(s_target, s_var, order)

        if fn_name in ("conj", "conjugate") and len(expr.args) == 1:
            return sp.conjugate(ast_to_sympy(expr.args[0], ctx, bound_symbols))
        if fn_name in ("re", "realpart") and len(expr.args) == 1:
            return sp.re(ast_to_sympy(expr.args[0], ctx, bound_symbols))
        if fn_name in ("im", "imagpart") and len(expr.args) == 1:
            return sp.im(ast_to_sympy(expr.args[0], ctx, bound_symbols))

        if fn_name in ("det", "determinant") and len(expr.args) == 1:
            s_mat = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            if hasattr(s_mat, "det"):
                return s_mat.det()
        if fn_name in ("tr", "trace") and len(expr.args) == 1:
            s_mat = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            if hasattr(s_mat, "trace"):
                return s_mat.trace()
        if fn_name in ("transpose",) and len(expr.args) == 1:
            s_mat = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            if hasattr(s_mat, "T"):
                return s_mat.T
        if fn_name == "dot" and len(expr.args) == 2:
            s_u = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            s_v = ast_to_sympy(expr.args[1], ctx, bound_symbols)
            if hasattr(s_u, "dot"):
                return s_u.dot(s_v)
            return s_u * s_v
        if fn_name == "norm" and len(expr.args) == 1:
            s_v = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            if hasattr(s_v, "dot"):
                return sp.sqrt(s_v.dot(s_v))
            return sp.Abs(s_v)

        if fn_name in _SYMPY_FUNCS:
            args = [ast_to_sympy(a, ctx, bound_symbols) for a in expr.args]
            return _SYMPY_FUNCS[fn_name](*args)
        # Uninterpreted mathematical function
        sym_fn = sp.Function(expr.func)
        args = [ast_to_sympy(a, ctx, bound_symbols) for a in expr.args]
        return sym_fn(*args)

    raise AlgebraConversionError(f"Cannot convert {type(expr).__name__} to SymPy expression.")


def _is_zero(diff: sp.Expr) -> bool:
    """Robustly check whether *diff* simplifies to 0 in SymPy."""
    if isinstance(diff, sp.MatrixBase):
        return all(_is_zero(entry) for entry in diff)
    if diff == 0 or diff is sp.S.Zero:
        return True
    if diff.has(sp.Abs):
        factored_abs = diff.replace(sp.Abs, lambda a: sp.Abs(sp.factor(a)))
        if factored_abs == 0 or sp.expand(factored_abs) == 0 or sp.simplify(factored_abs) == 0:
            return True
    expanded = sp.expand(diff)
    if expanded == 0:
        return True
    if diff.has(sp.I, sp.conjugate, sp.re, sp.im):
        comp = sp.expand(diff, complex=True)
        if comp == 0 or sp.simplify(comp) == 0:
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
            continue
        # If s_lhs is a sum like (3^k - 1 = 2*m), also try isolating non-constant terms (3^k = 2*m + 1)
        if isinstance(s_lhs, sp.Add):
            for term in s_lhs.args:
                if not term.is_Number:
                    isolated_rhs = s_rhs - (s_lhs - term)
                    if not isolated_rhs.has(term):
                        updated = current.subs(term, isolated_rhs)
                        if updated != current:
                            current = updated
                            used = True
                            break
    return current, used


def find_counterexample_info(
    lhs: ExprNode,
    rhs: ExprNode,
    ctx: ProofContext,
) -> tuple[Optional[str], Optional[dict[str, str]]]:
    """Search for a concrete numeric assignment showing ``lhs != rhs``.
    Returns ``(formatted_string, assignment_dict)``.
    """
    try:
        s_lhs = ast_to_sympy(lhs, ctx)
        s_rhs = ast_to_sympy(rhs, ctx)
    except AlgebraConversionError:
        return None, None

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
                msg = f"LHS evaluates to {s_lhs_sub}, while RHS evaluates to {s_rhs_sub}."
                return msg, {"LHS": str(s_lhs_sub), "RHS": str(s_rhs_sub)}
        except Exception:
            pass
        return None, None

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
                ce_dict = {sym.name: str(val) for sym, val in sub_map.items()}
                ce_dict["LHS"] = str(val_l)
                ce_dict["RHS"] = str(val_r)
                return f"Counterexample at {assign_str}: LHS = {val_l}, RHS = {val_r}", ce_dict
        except Exception:
            continue

    return None, None


def find_counterexample(
    lhs: ExprNode,
    rhs: ExprNode,
    ctx: ProofContext,
) -> Optional[str]:
    """Search for a concrete numeric assignment showing ``lhs != rhs``."""
    msg, _ = find_counterexample_info(lhs, rhs, ctx)
    return msg


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

    if s_lhs.has(sp.zoo, sp.oo, -sp.oo, sp.nan) or s_rhs.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
        return AlgebraResult(
            valid=False,
            message=f"Undefined mathematical expression (division by zero or indeterminate form) in {lhs} = {rhs}.",
        )

    # 0. Set equality check
    if isinstance(s_lhs, sp.Set) or isinstance(s_rhs, sp.Set):
        if s_lhs == s_rhs or (
            hasattr(s_lhs, "is_subset")
            and hasattr(s_rhs, "is_subset")
            and s_lhs.is_subset(s_rhs) is True
            and s_rhs.is_subset(s_lhs) is True
        ):
            return AlgebraResult(
                valid=True,
                message=f"Verified algebraically by SymPy ({lhs} = {rhs}).",
                used_substitutions=False,
            )

    # 1. Direct algebraic simplification
    try:
        if _is_zero(s_lhs - s_rhs):
            return AlgebraResult(
                valid=True,
                message=f"Verified algebraically by SymPy ({lhs} = {rhs}).",
                used_substitutions=False,
            )
    except (TypeError, ValueError, AttributeError, sp.ShapeError):
        pass

    # 2. Try substituting active context equalities (e.g. n = 2 * k)
    try:
        s_lhs_sub, used_l = _apply_context_substitutions(s_lhs, ctx)
        s_rhs_sub, used_r = _apply_context_substitutions(s_rhs, ctx)
        if (used_l or used_r) and _is_zero(s_lhs_sub - s_rhs_sub):
            return AlgebraResult(
                valid=True,
                message=f"Verified by SymPy using context substitutions ({lhs} = {rhs}).",
                used_substitutions=True,
            )
    except (TypeError, ValueError, AttributeError, sp.ShapeError):
        pass

    # 3. Failed — generate concrete counterexample
    ce_str, ce_dict = find_counterexample_info(lhs, rhs, ctx)
    try:
        diff_expr = sp.simplify(s_lhs_sub - s_rhs_sub)
    except Exception:
        diff_expr = f"{s_lhs_sub} != {s_rhs_sub}"
    msg = f"Algebraic step failed: ({lhs}) - ({rhs}) simplifies to {diff_expr} != 0."
    if ce_str:
        msg = f"{msg} {ce_str}"
    return AlgebraResult(
        valid=False,
        message=msg,
        counterexample=ce_str,
        counterexample_dict=ce_dict,
    )
