"""Z3 SMT solver backend for logical deductions, inequalities, quantifiers, and domain obligations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sympy as sp
import z3

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
from aether.core.types import MathType, normalize_type_name
from aether.engine.context import (
    ProofContext,
    DomainObligation,
    canonical_rel,
)
from aether.engine.algebra import (
    AlgebraConversionError,
    ast_to_sympy,
    verify_algebraic_equality,
)


class LogicConversionError(Exception):
    """Raised when an AST node cannot be translated into a Z3 expression."""


@dataclass
class LogicResult:
    """Result of a Z3 / logical entailment check."""

    valid: bool
    message: str
    counterexample: Optional[str] = None
    counterexample_dict: Optional[dict[str, str]] = None
    backend: str = "Z3"


def substitute_expr(expr: ExprNode, var_name: str, replacement: ExprNode) -> ExprNode:
    """Return a copy of *expr* with free occurrences of *var_name* replaced by *replacement*."""
    if isinstance(expr, SymbolNode):
        return replacement if expr.name == var_name else expr
    if isinstance(expr, GreekSymbolNode):
        return replacement if expr.name == var_name else expr
    if isinstance(expr, NumberNode):
        return expr
    if isinstance(expr, UnaryOpNode):
        return UnaryOpNode(
            op=expr.op,
            operand=substitute_expr(expr.operand, var_name, replacement),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, BinaryOpNode):
        return BinaryOpNode(
            op=expr.op,
            left=substitute_expr(expr.left, var_name, replacement),
            right=substitute_expr(expr.right, var_name, replacement),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, RelationNode):
        return RelationNode(
            op=expr.op,
            left=substitute_expr(expr.left, var_name, replacement),
            right=substitute_expr(expr.right, var_name, replacement),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, FunctionCallNode):
        return FunctionCallNode(
            func=expr.func,
            args=[substitute_expr(a, var_name, replacement) for a in expr.args],
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, QuantifierNode):
        if expr.var == var_name:
            return expr  # shadowed by inner quantifier
        return QuantifierNode(
            quantifier=expr.quantifier,
            var=expr.var,
            var_type=expr.var_type,
            formula=substitute_expr(expr.formula, var_name, replacement),
            line=expr.line,
            col=expr.col,
        )
    return expr


def expand_prelude_predicate(node: FunctionCallNode, witness_var: str = "_k") -> Optional[ExprNode]:
    """Expand built-in prelude predicates into their first-order logic definitions.

    Supported predicates:
    - ``Even(x)``          -> ``exists _k : Int, x = 2 * _k``
    - ``Odd(x)``           -> ``exists _k : Int, x = 2 * _k + 1``
    - ``MultipleOf(a, b)`` -> ``exists _k : Int, a = b * _k``
    - ``Divides(a, b)``    -> ``exists _k : Int, b = a * _k``
    - ``Positive(x)``      -> ``x > 0``
    - ``NonNegative(x)``   -> ``x >= 0``
    """
    fn = node.func.lower()
    k_sym = SymbolNode(name=witness_var)

    if fn == "even" and len(node.args) == 1:
        x = node.args[0]
        rhs = BinaryOpNode(op="*", left=NumberNode(value="2"), right=k_sym)
        return QuantifierNode(
            quantifier="exists",
            var=witness_var,
            var_type="Int",
            formula=RelationNode(op="=", left=x, right=rhs),
        )

    if fn == "odd" and len(node.args) == 1:
        x = node.args[0]
        two_k = BinaryOpNode(op="*", left=NumberNode(value="2"), right=k_sym)
        rhs = BinaryOpNode(op="+", left=two_k, right=NumberNode(value="1"))
        return QuantifierNode(
            quantifier="exists",
            var=witness_var,
            var_type="Int",
            formula=RelationNode(op="=", left=x, right=rhs),
        )

    if fn == "multipleof" and len(node.args) == 2:
        a, b = node.args
        rhs = BinaryOpNode(op="*", left=b, right=k_sym)
        return QuantifierNode(
            quantifier="exists",
            var=witness_var,
            var_type="Int",
            formula=RelationNode(op="=", left=a, right=rhs),
        )

    if fn == "divides" and len(node.args) == 2:
        a, b = node.args
        rhs = BinaryOpNode(op="*", left=a, right=k_sym)
        return QuantifierNode(
            quantifier="exists",
            var=witness_var,
            var_type="Int",
            formula=RelationNode(op="=", left=b, right=rhs),
        )

    if fn == "positive" and len(node.args) == 1:
        return RelationNode(op=">", left=node.args[0], right=NumberNode(value="0"))

    if fn == "nonnegative" and len(node.args) == 1:
        return RelationNode(op=">=", left=node.args[0], right=NumberNode(value="0"))

    if fn in ("cauchyriemann", "cauchy_riemann"):
        if len(node.args) == 2:
            u, v = node.args
            x_sym, y_sym = SymbolNode(name="x"), SymbolNode(name="y")
        elif len(node.args) == 4:
            u, v, x_sym, y_sym = node.args
        else:
            return None
        ux = FunctionCallNode(func="diff", args=[u, x_sym])
        vy = FunctionCallNode(func="diff", args=[v, y_sym])
        uy = FunctionCallNode(func="diff", args=[u, y_sym])
        vx = FunctionCallNode(func="diff", args=[v, x_sym])
        neg_vx = UnaryOpNode(op="-", operand=vx)
        eq1 = RelationNode(op="=", left=ux, right=vy)
        eq2 = RelationNode(op="=", left=uy, right=neg_vx)
        return BinaryOpNode(op="and", left=eq1, right=eq2)

    if fn in ("congruent", "cong") and len(node.args) == 3:
        a, b, m = node.args
        diff = BinaryOpNode(op="-", left=a, right=b)
        rhs = BinaryOpNode(op="*", left=m, right=k_sym)
        return QuantifierNode(
            quantifier="exists",
            var=witness_var,
            var_type="Int",
            formula=RelationNode(op="=", left=diff, right=rhs),
        )

    if fn == "orthogonal" and len(node.args) == 2:
        u, v = node.args
        dot_call = FunctionCallNode(func="dot", args=[u, v])
        return RelationNode(op="=", left=dot_call, right=NumberNode(value="0"))

    return None


def _make_z3_var(name: str, mt: MathType) -> z3.ExprRef:
    if mt in (MathType.Nat, MathType.Int):
        return z3.Int(name)
    if mt == MathType.Bool:
        return z3.Bool(name)
    return z3.Real(name)


def is_contradiction_symbol(expr: ExprNode) -> bool:
    """Return True if *expr* represents logical falsity / Contradiction."""
    return isinstance(expr, SymbolNode) and expr.name.lower() in (
        "contradiction",
        "false",
        "absurd",
        "bot",
    )


def ast_to_z3(
    expr: ExprNode,
    ctx: ProofContext,
    bound_vars: Optional[dict[str, z3.ExprRef]] = None,
    extra_constraints: Optional[list[z3.ExprRef]] = None,
) -> z3.ExprRef:
    """Translate an Aether ``ExprNode`` into a Z3 expression or formula."""
    if bound_vars is None:
        bound_vars = {}

    expanded_expr = ctx.expand_user_functions(expr)
    if expanded_expr is not None:
        expr = expanded_expr

    if isinstance(expr, NumberNode):
        if "." in expr.value:
            return z3.RealVal(expr.value)
        return z3.IntVal(int(expr.value))

    if isinstance(expr, (SymbolNode, GreekSymbolNode)):
        name = expr.name
        if isinstance(expr, SymbolNode):
            if is_contradiction_symbol(expr):
                return z3.BoolVal(False)
            if name.lower() == "true":
                return z3.BoolVal(True)
        if name in bound_vars:
            return bound_vars[name]
        vinfo = ctx.get_var(name)
        mt = vinfo.math_type if vinfo else MathType.Real
        return _make_z3_var(name, mt)

    if isinstance(expr, UnaryOpNode):
        sub = ast_to_z3(expr.operand, ctx, bound_vars, extra_constraints)
        if expr.op == "-":
            if z3.is_bool(sub):
                return z3.Not(sub)
            return -sub  # type: ignore[operator]
        if expr.op == "+":
            return sub
        if expr.op in ("not", "\\neg", "~"):
            return z3.Not(sub)
        raise LogicConversionError(f"Unsupported unary operator in Z3: {expr.op!r}")

    if isinstance(expr, BinaryOpNode):
        left = ast_to_z3(expr.left, ctx, bound_vars, extra_constraints)
        right = ast_to_z3(expr.right, ctx, bound_vars, extra_constraints)
        op = expr.op.lower()
        if op == "+":
            return left + right  # type: ignore[operator]
        if op == "-":
            return left - right  # type: ignore[operator]
        if op == "*":
            return left * right  # type: ignore[operator]
        if op == "/":
            return z3.ToReal(left) / z3.ToReal(right) if z3.is_int(left) and z3.is_int(right) else left / right  # type: ignore[operator]
        if op in ("^", "**"):
            # Expand small constant integer powers into multiplication so Z3 avoids transcendental Pow
            if isinstance(expr.right, NumberNode) and "." not in expr.right.value:
                exp_int = int(expr.right.value)
                if 0 <= exp_int <= 6:
                    if exp_int == 0:
                        return z3.IntVal(1) if z3.is_int(left) else z3.RealVal(1)
                    acc = left
                    for _ in range(exp_int - 1):
                        acc = acc * left  # type: ignore[operator]
                    return acc
            return left ** right  # type: ignore[operator]
        if op in ("and", "\\land", "/\\"):
            return z3.And(left, right)
        if op in ("or", "\\lor", "\\/"):
            return z3.Or(left, right)
        if op == "=>":
            return z3.Implies(left, right)
        if op in ("<=>", "iff"):
            return left == right
        if op in ("\\circ", "\\cdot"):
            op_fn = z3.Function("op", z3.RealSort(), z3.RealSort(), z3.RealSort())
            return op_fn(left, right)
        if op in ("\\cap", "intersect"):
            inter_fn = z3.Function("intersect", z3.RealSort(), z3.RealSort(), z3.RealSort())
            return inter_fn(left, right)
        if op in ("\\cup", "union"):
            union_fn = z3.Function("union", z3.RealSort(), z3.RealSort(), z3.RealSort())
            return union_fn(left, right)
        if op in ("\\setminus", "setminus"):
            diff_fn = z3.Function("setminus", z3.RealSort(), z3.RealSort(), z3.RealSort())
            return diff_fn(left, right)
        raise LogicConversionError(f"Unsupported binary operator in Z3: {expr.op!r}")

    if isinstance(expr, RelationNode):
        left = ast_to_z3(expr.left, ctx, bound_vars, extra_constraints)
        right = ast_to_z3(expr.right, ctx, bound_vars, extra_constraints)
        rel = canonical_rel(expr.op)
        if rel in ("=", "\\equiv"):
            return left == right
        if rel == "!=":
            return left != right
        if rel == "<":
            return left < right  # type: ignore[operator]
        if rel == "<=":
            return left <= right  # type: ignore[operator]
        if rel == ">":
            return left > right  # type: ignore[operator]
        if rel == ">=":
            return left >= right  # type: ignore[operator]
        if rel in ("in", "\\in"):
            in_fn = z3.Function("in", z3.RealSort(), z3.RealSort(), z3.BoolSort())
            return in_fn(left, right)
        if rel in ("notin", "\\notin", "not in"):
            in_fn = z3.Function("in", z3.RealSort(), z3.RealSort(), z3.BoolSort())
            return z3.Not(in_fn(left, right))
        if rel in ("subset", "\\subset", "subseteq", "\\subseteq"):
            sub_fn = z3.Function("subset", z3.RealSort(), z3.RealSort(), z3.BoolSort())
            return sub_fn(left, right)
        raise LogicConversionError(f"Unsupported relation in Z3: {expr.op!r}")

    if isinstance(expr, FunctionCallNode):
        fn = expr.func.lower()
        if fn in ("congruent", "cong") and len(expr.args) == 3:
            a = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            b = ast_to_z3(expr.args[1], ctx, bound_vars, extra_constraints)
            m = ast_to_z3(expr.args[2], ctx, bound_vars, extra_constraints)
            if z3.is_int(a) and z3.is_int(b) and z3.is_int(m):
                return ((a - b) % m) == 0  # type: ignore[operator]
            expanded = expand_prelude_predicate(expr)
            if expanded is not None:
                return ast_to_z3(expanded, ctx, bound_vars, extra_constraints)
        if fn in ("inv", "inverse") and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            inv_fn = z3.Function("inv", z3.RealSort(), z3.RealSort())
            return inv_fn(arg)
        if fn == "sqrt" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            arg_real = z3.ToReal(arg) if z3.is_int(arg) else arg
            s_var = z3.Real(f"_sqrt_{expr.args[0]}")
            if extra_constraints is not None:
                extra_constraints.append(
                    z3.Implies(arg_real >= 0, z3.And(s_var >= 0, s_var * s_var == arg_real))  # type: ignore[operator]
                )
            return s_var
        if fn == "abs" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            return z3.If(arg >= 0, arg, -arg)  # type: ignore[operator]
        if fn == "max" and len(expr.args) >= 2:
            z3_args = [ast_to_z3(a, ctx, bound_vars, extra_constraints) for a in expr.args]
            acc = z3_args[0]
            for nxt in z3_args[1:]:
                acc = z3.If(acc >= nxt, acc, nxt)  # type: ignore[operator]
            return acc
        if fn == "min" and len(expr.args) >= 2:
            z3_args = [ast_to_z3(a, ctx, bound_vars, extra_constraints) for a in expr.args]
            acc = z3_args[0]
            for nxt in z3_args[1:]:
                acc = z3.If(acc <= nxt, acc, nxt)  # type: ignore[operator]
            return acc
        if fn == "even" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            if z3.is_int(arg):
                return (arg % 2) == 0  # type: ignore[operator]
        if fn == "odd" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            if z3.is_int(arg):
                return (arg % 2) == 1  # type: ignore[operator]
        if fn == "multipleof" and len(expr.args) == 2:
            a = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            b = ast_to_z3(expr.args[1], ctx, bound_vars, extra_constraints)
            if z3.is_int(a) and z3.is_int(b):
                return (a % b) == 0  # type: ignore[operator]
        if fn == "divides" and len(expr.args) == 2:
            a = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            b = ast_to_z3(expr.args[1], ctx, bound_vars, extra_constraints)
            if z3.is_int(a) and z3.is_int(b):
                return (b % a) == 0  # type: ignore[operator]

        expanded = expand_prelude_predicate(expr)
        if expanded is not None:
            return ast_to_z3(expanded, ctx, bound_vars, extra_constraints)

        # Uninterpreted predicate / function
        z3_args = [ast_to_z3(a, ctx, bound_vars, extra_constraints) for a in expr.args]
        arg_sorts = [a.sort() for a in z3_args]
        return_sort = (
            z3.RealSort()
            if (fn in ("diff", "det", "tr", "norm", "dot", "conj", "re", "im") or expr.func[0].islower())
            else z3.BoolSort()
        )
        uf = z3.Function(expr.func, *arg_sorts, return_sort)
        return uf(*z3_args)

    if isinstance(expr, QuantifierNode):
        mt = normalize_type_name(expr.var_type) if expr.var_type else MathType.Real
        z3_v = _make_z3_var(expr.var, mt)
        new_bound = dict(bound_vars)
        new_bound[expr.var] = z3_v
        body = ast_to_z3(expr.formula, ctx, new_bound, extra_constraints)
        if mt == MathType.Nat:
            if expr.quantifier == "exists":
                body = z3.And(z3_v >= 0, body)  # type: ignore[operator]
            else:
                body = z3.Implies(z3_v >= 0, body)  # type: ignore[operator]
        if expr.quantifier == "exists":
            return z3.Exists([z3_v], body)
        return z3.ForAll([z3_v], body)

    raise LogicConversionError(f"Cannot convert {type(expr).__name__} to Z3.")


def extract_z3_model_dict(model: z3.ModelRef, ctx: ProofContext) -> dict[str, str]:
    """Extract a dictionary of variable assignments from a Z3 counterexample model."""
    res: dict[str, str] = {}
    for var_name in sorted(ctx.all_variables().keys()):
        vinfo = ctx.get_var(var_name)
        if vinfo is None:
            continue
        z3_v = _make_z3_var(var_name, vinfo.math_type)
        val = model.eval(z3_v, model_completion=False)
        if val is not None and not val.eq(z3_v):
            res[var_name] = str(val)
    if not res:
        for d in model.decls():
            if d.arity() == 0:
                res[d.name()] = str(model[d])
    return res


def _format_z3_model(model: z3.ModelRef, ctx: ProofContext) -> str:
    m_dict = extract_z3_model_dict(model, ctx)
    return ", ".join(f"{k}={v}" for k, v in m_dict.items())


def _types_compatible(quant_type: MathType, var_type: MathType) -> bool:
    if quant_type == var_type:
        return True
    if quant_type == MathType.Int and var_type == MathType.Nat:
        return True
    if quant_type == MathType.Real and var_type in (MathType.Rat, MathType.Int, MathType.Nat):
        return True
    return False


def _populate_algebra_axioms(solver: z3.Solver, prop: ExprNode, ctx: ProofContext) -> None:
    if not isinstance(prop, FunctionCallNode):
        return
    fn = prop.func.lower()
    S = z3.RealSort()
    x, y, z = z3.Reals("_alg_x _alg_y _alg_z")

    if fn in ("group", "abeliangroup") and len(prop.args) >= 1:
        op_name = prop.args[1].name if len(prop.args) >= 2 and isinstance(prop.args[1], (SymbolNode, GreekSymbolNode)) else "op"
        e_name = prop.args[2].name if len(prop.args) >= 3 and isinstance(prop.args[2], (SymbolNode, GreekSymbolNode)) else "e"
        inv_name = prop.args[3].name if len(prop.args) >= 4 and isinstance(prop.args[3], (SymbolNode, GreekSymbolNode)) else "inv"

        op = z3.Function(op_name, S, S, S)
        inv = z3.Function(inv_name, S, S)
        e = z3.Real(e_name)

        solver.add(z3.ForAll([x], z3.And(op(x, e) == x, op(e, x) == x)))
        solver.add(z3.ForAll([x], z3.And(op(x, inv(x)) == e, op(inv(x), x) == e)))
        solver.add(z3.ForAll([x, y, z], op(op(x, y), z) == op(x, op(y, z))))
        solver.add(z3.ForAll([x, y], z3.Implies(op(x, y) == e, inv(x) == y)))
        solver.add(z3.ForAll([x], inv(inv(x)) == x))
        solver.add(inv(e) == e)
        solver.add(z3.ForAll([x, y, z], z3.Implies(op(x, y) == op(x, z), y == z)))
        solver.add(z3.ForAll([x, y, z], z3.Implies(op(y, x) == op(z, x), y == z)))

        if fn == "abeliangroup":
            solver.add(z3.ForAll([x, y], op(x, y) == op(y, x)))

    elif fn == "subgroup" and len(prop.args) >= 2:
        h_sym = prop.args[0]
        op_name = prop.args[2].name if len(prop.args) >= 3 and isinstance(prop.args[2], (SymbolNode, GreekSymbolNode)) else "op"
        e_name = prop.args[3].name if len(prop.args) >= 4 and isinstance(prop.args[3], (SymbolNode, GreekSymbolNode)) else "e"
        inv_name = prop.args[4].name if len(prop.args) >= 5 and isinstance(prop.args[4], (SymbolNode, GreekSymbolNode)) else "inv"

        op = z3.Function(op_name, S, S, S)
        inv = z3.Function(inv_name, S, S)
        e = z3.Real(e_name)
        in_fn = z3.Function("in", S, S, z3.BoolSort())

        try:
            h_z3 = ast_to_z3(h_sym, ctx)
            solver.add(in_fn(e, h_z3) == True)
            solver.add(z3.ForAll([x], z3.Implies(in_fn(x, h_z3), in_fn(inv(x), h_z3))))
            solver.add(z3.ForAll([x, y], z3.Implies(z3.And(in_fn(x, h_z3), in_fn(y, h_z3)), in_fn(op(x, y), h_z3))))
            solver.add(z3.ForAll([x, y], z3.Implies(z3.And(in_fn(x, h_z3), in_fn(y, h_z3)), in_fn(op(x, inv(y)), h_z3))))
        except Exception:
            pass

    elif fn == "normalsubgroup" and len(prop.args) >= 2:
        n_sym = prop.args[0]
        g_sym = prop.args[1]
        op_name = prop.args[2].name if len(prop.args) >= 3 and isinstance(prop.args[2], (SymbolNode, GreekSymbolNode)) else "op"
        e_name = prop.args[3].name if len(prop.args) >= 4 and isinstance(prop.args[3], (SymbolNode, GreekSymbolNode)) else "e"
        inv_name = prop.args[4].name if len(prop.args) >= 5 and isinstance(prop.args[4], (SymbolNode, GreekSymbolNode)) else "inv"

        op = z3.Function(op_name, S, S, S)
        inv = z3.Function(inv_name, S, S)
        e = z3.Real(e_name)
        in_fn = z3.Function("in", S, S, z3.BoolSort())

        try:
            n_z3 = ast_to_z3(n_sym, ctx)
            g_z3 = ast_to_z3(g_sym, ctx)
            solver.add(in_fn(e, n_z3) == True)
            solver.add(z3.ForAll([x], z3.Implies(in_fn(x, n_z3), in_fn(inv(x), n_z3))))
            solver.add(z3.ForAll([x, y], z3.Implies(z3.And(in_fn(x, n_z3), in_fn(y, n_z3)), in_fn(op(x, inv(y)), n_z3))))
            solver.add(z3.ForAll([x, y], z3.Implies(z3.And(in_fn(x, g_z3), in_fn(y, n_z3)), in_fn(op(op(x, y), inv(x)), n_z3))))
        except Exception:
            pass

    elif fn in ("ring", "field") and len(prop.args) >= 1:
        add_name = prop.args[1].name if len(prop.args) >= 2 and isinstance(prop.args[1], (SymbolNode, GreekSymbolNode)) else "add"
        mul_name = prop.args[2].name if len(prop.args) >= 3 and isinstance(prop.args[2], (SymbolNode, GreekSymbolNode)) else "mul"
        zero_name = prop.args[3].name if len(prop.args) >= 4 and isinstance(prop.args[3], (SymbolNode, GreekSymbolNode)) else "zero"
        one_name = prop.args[4].name if len(prop.args) >= 5 and isinstance(prop.args[4], (SymbolNode, GreekSymbolNode)) else "one"
        neg_name = prop.args[5].name if len(prop.args) >= 6 and isinstance(prop.args[5], (SymbolNode, GreekSymbolNode)) else "neg"
        inv_name = prop.args[6].name if len(prop.args) >= 7 and isinstance(prop.args[6], (SymbolNode, GreekSymbolNode)) else "inv"

        add = z3.Function(add_name, S, S, S)
        mul = z3.Function(mul_name, S, S, S)
        neg = z3.Function(neg_name, S, S)
        zero = z3.Real(zero_name)
        one = z3.Real(one_name)

        solver.add(z3.ForAll([x], z3.And(add(x, zero) == x, add(zero, x) == x)))
        solver.add(z3.ForAll([x], z3.And(add(x, neg(x)) == zero, add(neg(x), x) == zero)))
        solver.add(z3.ForAll([x, y, z], add(add(x, y), z) == add(x, add(y, z))))
        solver.add(z3.ForAll([x, y], add(x, y) == add(y, x)))

        solver.add(z3.ForAll([x, y, z], mul(mul(x, y), z) == mul(x, mul(y, z))))
        solver.add(z3.ForAll([x], z3.And(mul(x, one) == x, mul(one, x) == x)))

        solver.add(z3.ForAll([x, y, z], mul(x, add(y, z)) == add(mul(x, y), mul(x, z))))
        solver.add(z3.ForAll([x, y, z], mul(add(x, y), z) == add(mul(x, z), mul(y, z))))
        solver.add(z3.ForAll([x], z3.And(mul(x, zero) == zero, mul(zero, x) == zero)))

        if fn == "field":
            inv = z3.Function(inv_name, S, S)
            solver.add(z3.ForAll([x, y], mul(x, y) == mul(y, x)))
            solver.add(z3.ForAll([x], z3.Implies(x != zero, z3.And(mul(x, inv(x)) == one, mul(inv(x), x) == one))))


def _populate_solver_context(solver: z3.Solver, ctx: ProofContext) -> None:
    """Add variable domain constraints (e.g. Nat >= 0), active hypotheses, and chain facts to *solver*."""
    extra: list[z3.ExprRef] = []
    active_vars = ctx.all_variables()
    for vinfo in active_vars.values():
        if vinfo.math_type == MathType.Nat:
            z3_v = _make_z3_var(vinfo.name, MathType.Nat)
            solver.add(z3_v >= 0)  # type: ignore[operator]

    # Set theory axioms
    S = z3.RealSort()
    st_x, st_A, st_B = z3.Reals("_st_x _st_A _st_B")
    in_fn = z3.Function("in", S, S, z3.BoolSort())
    inter_fn = z3.Function("intersect", S, S, S)
    union_fn = z3.Function("union", S, S, S)
    sub_fn = z3.Function("subset", S, S, z3.BoolSort())
    solver.add(z3.ForAll([st_x, st_A, st_B], in_fn(st_x, inter_fn(st_A, st_B)) == z3.And(in_fn(st_x, st_A), in_fn(st_x, st_B))))
    solver.add(z3.ForAll([st_x, st_A, st_B], in_fn(st_x, union_fn(st_A, st_B)) == z3.Or(in_fn(st_x, st_A), in_fn(st_x, st_B))))
    solver.add(z3.ForAll([st_A, st_B], sub_fn(st_A, st_B) == z3.ForAll([st_x], z3.Implies(in_fn(st_x, st_A), in_fn(st_x, st_B)))))

    for h in ctx.all_hypotheses():
        try:
            solver.add(ast_to_z3(h.proposition, ctx, extra_constraints=extra))
        except LogicConversionError:
            pass
        _populate_algebra_axioms(solver, h.proposition, ctx)
        # Eager ground instantiation for universally quantified hypotheses / lemmas
        if isinstance(h.proposition, QuantifierNode) and h.proposition.quantifier == "forall":
            q1_mt = normalize_type_name(h.proposition.var_type) if h.proposition.var_type else MathType.Real
            for v1 in active_vars.values():
                if _types_compatible(q1_mt, v1.math_type):
                    inst1 = substitute_expr(h.proposition.formula, h.proposition.var, SymbolNode(name=v1.name))
                    if isinstance(inst1, QuantifierNode) and inst1.quantifier == "forall":
                        q2_mt = normalize_type_name(inst1.var_type) if inst1.var_type else MathType.Real
                        for v2 in active_vars.values():
                            if _types_compatible(q2_mt, v2.math_type):
                                inst2 = substitute_expr(inst1.formula, inst1.var, SymbolNode(name=v2.name))
                                try:
                                    solver.add(ast_to_z3(inst2, ctx, extra_constraints=extra))
                                except LogicConversionError:
                                    pass
                    else:
                        try:
                            solver.add(ast_to_z3(inst1, ctx, extra_constraints=extra))
                        except LogicConversionError:
                            pass

    if ctx.chain is not None and ctx.chain.effective_relation:
        chain_rel = RelationNode(
            op=ctx.chain.effective_relation,
            left=ctx.chain.head_lhs,
            right=ctx.chain.current_rhs,
        )
        try:
            solver.add(ast_to_z3(chain_rel, ctx, extra_constraints=extra))
        except LogicConversionError:
            pass

    for c in extra:
        solver.add(c)


def _exprs_match(e1: ExprNode, e2: ExprNode, ctx: ProofContext) -> bool:
    """Return True if *e1* and *e2* are syntactically or algebraically identical."""
    u1 = ctx.expand_user_functions(e1) or e1
    u2 = ctx.expand_user_functions(e2) or e2

    if isinstance(u1, FunctionCallNode):
        exp1 = expand_prelude_predicate(u1, witness_var="_m_match")
        if exp1 is not None:
            u1 = exp1
    if isinstance(u2, FunctionCallNode):
        exp2 = expand_prelude_predicate(u2, witness_var="_m_match")
        if exp2 is not None:
            u2 = exp2

    if str(u1) == str(u2):
        return True

    if isinstance(u1, QuantifierNode) and isinstance(u2, QuantifierNode) and u1.quantifier == u2.quantifier:
        alpha_v = "_alpha_var"
        u1_renamed = substitute_expr(u1.formula, u1.var, SymbolNode(name=alpha_v))
        u2_renamed = substitute_expr(u2.formula, u2.var, SymbolNode(name=alpha_v))
        return _exprs_match(u1_renamed, u2_renamed, ctx)

    if (
        isinstance(u1, RelationNode)
        and isinstance(u2, RelationNode)
        and canonical_rel(u1.op) == canonical_rel(u2.op)
    ):
        return (
            verify_algebraic_equality(u1.left, u2.left, ctx).valid
            and verify_algebraic_equality(u1.right, u2.right, ctx).valid
        )
    if (
        isinstance(u1, FunctionCallNode)
        and isinstance(u2, FunctionCallNode)
        and u1.func.lower() == u2.func.lower()
        and len(u1.args) == len(u2.args)
    ):
        return all(verify_algebraic_equality(a1, a2, ctx).valid for a1, a2 in zip(u1.args, u2.args))
    return False


def verify_induction_schema(
    claim: ExprNode,
    ctx: ProofContext,
) -> Optional[LogicResult]:
    """Check whether a universal claim ``forall n : Nat, P(n)`` is established by
    a verified base case ``P(0)`` (or ``P(1)``) and inductive step ``forall k, P(k) => P(k + 1)``.
    """
    expanded_claim = ctx.expand_user_functions(claim) or claim
    if not (isinstance(expanded_claim, QuantifierNode) and expanded_claim.quantifier == "forall"):
        return None

    n_var = expanded_claim.var
    p_n = expanded_claim.formula
    hyps = ctx.all_hypotheses()

    # 1. Check base case P(0) or P(1) in hypotheses
    base_matched = False
    for base_str in ("0", "1"):
        p_base = substitute_expr(p_n, n_var, NumberNode(value=base_str))
        if any(_exprs_match(h.proposition, p_base, ctx) for h in hyps):
            base_matched = True
            break
    if not base_matched:
        return None

    # 2. Check inductive step forall k, P(k) => P(k + 1) in hypotheses
    for h in hyps:
        prop = h.proposition
        if (
            isinstance(prop, QuantifierNode)
            and prop.quantifier == "forall"
            and isinstance(prop.formula, BinaryOpNode)
            and prop.formula.op in ("=>", "->", "implies", "\\implies")
        ):
            k_var = prop.var
            ih_part = prop.formula.left
            step_part = prop.formula.right
            expected_ih = substitute_expr(p_n, n_var, SymbolNode(name=k_var))
            k_plus_1 = BinaryOpNode(op="+", left=SymbolNode(name=k_var), right=NumberNode(value="1"))
            expected_step = substitute_expr(p_n, n_var, k_plus_1)
            if _exprs_match(ih_part, expected_ih, ctx) and _exprs_match(step_part, expected_step, ctx):
                return LogicResult(
                    valid=True,
                    message=f"Verified by Mathematical Induction on {n_var} (base case + inductive step).",
                    backend="Induction",
                )

    return None


def _try_sympy_divisibility_or_existential(
    claim: ExprNode,
    ctx: ProofContext,
) -> Optional[LogicResult]:
    """Check integer divisibility predicates and linear existential equations via SymPy CAS."""
    # Expand user-defined predicates and Even/Odd/MultipleOf/Divides into QuantifierNode if applicable
    raw_target = ctx.expand_user_functions(claim) or claim
    if isinstance(raw_target, FunctionCallNode) and raw_target.func.lower() in ("congruent", "cong") and len(raw_target.args) == 3:
        try:
            s_a = ast_to_sympy(raw_target.args[0], ctx)
            s_b = ast_to_sympy(raw_target.args[1], ctx)
            s_m = ast_to_sympy(raw_target.args[2], ctx)
            diff = s_a - s_b
            for eq_l, eq_r in ctx.get_equality_substitutions():
                try:
                    sl = ast_to_sympy(eq_l, ctx)
                    sr = ast_to_sympy(eq_r, ctx)
                    diff = diff.subs(sl, sr)
                except Exception:
                    continue
            ratio = sp.simplify(diff / s_m)
            if sp.denom(sp.together(ratio)) == 1 and all(s.is_integer for s in ratio.free_symbols):
                return LogicResult(
                    valid=True,
                    message=f"Verified congruence ({claim}) via algebraic quotient {ratio}.",
                    backend="SymPy+Logic",
                )
        except Exception:
            pass

    target = raw_target
    if isinstance(target, FunctionCallNode):
        expanded = expand_prelude_predicate(target, witness_var="_m_auto")
        if expanded is not None:
            target = expanded

    if (
        isinstance(target, QuantifierNode)
        and target.quantifier == "exists"
        and isinstance(target.formula, RelationNode)
        and canonical_rel(target.formula.op) == "="
    ):
        var_name = target.var
        var_type = normalize_type_name(target.var_type) if target.var_type else MathType.Int
        try:
            # Create a temporary SymPy symbol for the existential variable
            m_sym = sp.Symbol(var_name, integer=(var_type in (MathType.Int, MathType.Nat)), real=True)
            s_lhs = ast_to_sympy(target.formula.left, ctx)
            s_rhs = ast_to_sympy(target.formula.right, ctx)
            # Apply context equality substitutions (excluding var_name)
            for eq_l, eq_r in ctx.get_equality_substitutions():
                try:
                    sl = ast_to_sympy(eq_l, ctx)
                    sr = ast_to_sympy(eq_r, ctx)
                    if m_sym not in sl.free_symbols:
                        s_lhs = s_lhs.subs(sl, sr)
                        s_rhs = s_rhs.subs(sl, sr)
                except AlgebraConversionError:
                    continue

            solutions = sp.solve(s_lhs - s_rhs, m_sym)
            if len(solutions) == 1:
                sol = sp.simplify(solutions[0])
                if var_type in (MathType.Int, MathType.Nat):
                    # Verify that sol has only integer coefficients and symbols
                    denom = sp.denom(sp.together(sol))
                    if denom == 1 and all(s.is_integer for s in sol.free_symbols):
                        return LogicResult(
                            valid=True,
                            message=f"Verified by algebraic witness ({var_name} = {sol}).",
                            backend="SymPy+Logic",
                        )
                else:
                    return LogicResult(
                        valid=True,
                        message=f"Verified by algebraic witness ({var_name} = {sol}).",
                        backend="SymPy+Logic",
                    )
        except Exception:
            pass

    return None


def verify_entailment(
    claim: ExprNode,
    ctx: ProofContext,
    witness: Optional[ExprNode] = None,
    timeout_ms: int = 2500,
) -> LogicResult:
    """Verify whether *claim* follows logically from active hypotheses in *ctx*."""
    claim = ctx.expand_user_functions(claim) or claim

    # Fast path: check if claim directly matches an established hypothesis in ctx
    if witness is None and any(_exprs_match(claim, h.proposition, ctx) for h in ctx.all_hypotheses()):
        return LogicResult(
            valid=True,
            message=f"Verified from established hypothesis ({claim}).",
            backend="Z3",
        )

    # 0. Check Mathematical Induction schema for universal claims
    ind_res = verify_induction_schema(claim, ctx)
    if ind_res is not None and ind_res.valid:
        return ind_res

    # Conjunction decomposition: A and B holds if both A and B hold
    if (
        witness is None
        and isinstance(claim, BinaryOpNode)
        and claim.op.lower() in ("and", "\\land", "/\\")
    ):
        res_l = verify_entailment(claim.left, ctx, timeout_ms=timeout_ms)
        if not res_l.valid:
            return LogicResult(
                valid=False,
                message=f"Conjunction failed on left condition: {res_l.message}",
                counterexample=res_l.counterexample,
                counterexample_dict=res_l.counterexample_dict,
                backend=res_l.backend,
            )
        res_r = verify_entailment(claim.right, ctx, timeout_ms=timeout_ms)
        if not res_r.valid:
            return LogicResult(
                valid=False,
                message=f"Conjunction failed on right condition: {res_r.message}",
                counterexample=res_r.counterexample,
                counterexample_dict=res_r.counterexample_dict,
                backend=res_r.backend,
            )
        return LogicResult(
            valid=True,
            message=f"Verified conjunction ({claim}).",
            backend=res_r.backend,
        )

    # Prelude predicate expansion for CauchyRiemann and Orthogonal
    if isinstance(claim, FunctionCallNode) and claim.func.lower() in ("cauchyriemann", "cauchy_riemann", "orthogonal"):
        expanded = expand_prelude_predicate(claim)
        if expanded is not None:
            return verify_entailment(expanded, ctx, witness=witness, timeout_ms=timeout_ms)

    # Algebraic equality verification (for matrices, vectors, complex, calculus)
    if witness is None and isinstance(claim, RelationNode) and canonical_rel(claim.op) == "=":
        alg_res = verify_algebraic_equality(claim.left, claim.right, ctx)
        if alg_res.valid:
            return LogicResult(
                valid=True,
                message=f"Verified algebraically by SymPy ({claim}).",
                backend="SymPy",
            )

    # Set relations verification
    if witness is None and isinstance(claim, RelationNode):
        c_op = claim.op.lower()
        if c_op in ("in", "\\in", "notin", "\\notin", "not in", "subset", "\\subset", "subseteq", "\\subseteq"):
            try:
                s_left = ast_to_sympy(claim.left, ctx)
                s_right = ast_to_sympy(claim.right, ctx)
                if c_op in ("in", "\\in"):
                    cont = sp.Contains(s_left, s_right).doit()
                    if cont is sp.true or cont is True:
                        return LogicResult(valid=True, message=f"Verified set membership ({claim}).", backend="SymPy")
                elif c_op in ("notin", "\\notin", "not in"):
                    cont = sp.Contains(s_left, s_right).doit()
                    if cont is sp.false or cont is False:
                        return LogicResult(valid=True, message=f"Verified non-membership ({claim}).", backend="SymPy")
                elif c_op in ("subset", "\\subset", "subseteq", "\\subseteq"):
                    if hasattr(s_left, "is_subset"):
                        sub = s_left.is_subset(s_right)
                        if sub is True:
                            return LogicResult(valid=True, message=f"Verified subset relation ({claim}).", backend="SymPy")
            except Exception:
                pass

    # 1. If claim is an existential with an explicit [witness: ...], check the witness first
    if isinstance(claim, QuantifierNode) and claim.quantifier == "exists":
        if witness is not None:
            w_expr = witness
            # Allow both [witness: 2*k^2] and [witness: m = 2*k^2]
            if isinstance(witness, RelationNode) and canonical_rel(witness.op) == "=":
                if isinstance(witness.left, (SymbolNode, GreekSymbolNode)) and witness.left.name == claim.var:
                    w_expr = witness.right

            instantiated = substitute_expr(claim.formula, claim.var, w_expr)
            if isinstance(instantiated, RelationNode) and canonical_rel(instantiated.op) == "=":
                alg_res = verify_algebraic_equality(instantiated.left, instantiated.right, ctx)
                if alg_res.valid:
                    return LogicResult(
                        valid=True,
                        message=f"Verified existential claim using witness {claim.var} = {w_expr}.",
                        backend="SymPy (Witness)",
                    )
                auto_res = _try_sympy_divisibility_or_existential(claim, ctx)
                if auto_res is not None and auto_res.valid:
                    return LogicResult(
                        valid=True,
                        message=(
                            f"{auto_res.message} "
                            f"(Note: supplied witness {w_expr} simplified to {instantiated.left} != {instantiated.right})."
                        ),
                        backend=auto_res.backend,
                    )
                return LogicResult(
                    valid=False,
                    message=f"Witness {claim.var} = {w_expr} does not satisfy {claim.formula}: {alg_res.message}",
                    counterexample=alg_res.counterexample,
                    counterexample_dict=alg_res.counterexample_dict,
                    backend="SymPy (Witness)",
                )
            else:
                inst_res = verify_entailment(instantiated, ctx, timeout_ms=timeout_ms)
                if inst_res.valid:
                    return LogicResult(
                        valid=True,
                        message=f"Verified existential claim using witness {claim.var} = {w_expr}.",
                        backend="Z3 (Witness)",
                    )
                return LogicResult(
                    valid=False,
                    message=f"Witness {claim.var} = {w_expr} does not satisfy {claim.formula}: {inst_res.message}",
                    counterexample=inst_res.counterexample,
                    counterexample_dict=inst_res.counterexample_dict,
                    backend="Z3 (Witness)",
                )
        elif ctx.get_var(claim.var) is not None:
            # Bound variable was already constructed in scope (e.g. 'Let \delta = \epsilon / 3')
            ctx_inst_res = verify_entailment(claim.formula, ctx, timeout_ms=timeout_ms)
            if ctx_inst_res.valid:
                return LogicResult(
                    valid=True,
                    message=f"Verified existential claim using constructed variable {claim.var}.",
                    backend="Z3 (Witness)",
                )

    # 2. Try algebraic divisibility / existential witness solver for Even/Odd/MultipleOf/exists
    sym_res = _try_sympy_divisibility_or_existential(claim, ctx)
    if sym_res is not None and sym_res.valid:
        return sym_res

    # 3. Query Z3 SMT solver
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    _populate_solver_context(solver, ctx)

    extra: list[z3.ExprRef] = []
    try:
        z3_claim = ast_to_z3(claim, ctx, extra_constraints=extra)
    except LogicConversionError as exc:
        return LogicResult(valid=False, message=str(exc), backend="Z3")

    for c in extra:
        solver.add(c)
    solver.add(z3.Not(z3_claim))
    result = solver.check()

    if result == z3.unsat:
        return LogicResult(
            valid=True,
            message=f"Verified logically by Z3 ({claim}).",
            backend="Z3",
        )

    if result == z3.sat:
        model = solver.model()
        ce_dict = extract_z3_model_dict(model, ctx)
        ce_str = ", ".join(f"{k}={v}" for k, v in ce_dict.items())
        ce_msg = f"Counterexample: {ce_str}" if ce_str else "Z3 found a counterexample model."
        return LogicResult(
            valid=False,
            message=f"Claim '{claim}' does not follow from current hypotheses. {ce_msg}",
            counterexample=ce_str or None,
            counterexample_dict=ce_dict or None,
            backend="Z3",
        )

    return LogicResult(
        valid=False,
        message=f"Solver inconclusive (unknown) for '{claim}'.",
        backend="Z3",
    )


def check_domain_obligation(
    obligation: DomainObligation,
    ctx: ProofContext,
    timeout_ms: int = 2000,
) -> LogicResult:
    """Check whether *obligation* (e.g. ``x - 2 != 0``) is guaranteed by *ctx*."""
    res = verify_entailment(obligation.condition, ctx, timeout_ms=timeout_ms)
    if res.valid:
        obligation.discharged = True
        return LogicResult(
            valid=True,
            message=f"Domain obligation discharged: {obligation.reason}",
            backend="Z3 (Domain)",
        )

    ce = f" (violated at {res.counterexample})" if res.counterexample else ""
    return LogicResult(
        valid=False,
        message=f"Unresolved domain obligation: requires {obligation.reason}{ce}.",
        counterexample=res.counterexample,
        counterexample_dict=res.counterexample_dict,
        backend="Z3 (Domain)",
    )


def verify_case_exhaustiveness(
    case_conditions: list[ExprNode],
    ctx: ProofContext,
    timeout_ms: int = 2000,
) -> LogicResult:
    """Verify that the disjunction ``C_1 or C_2 or ... or C_k`` covers all possibilities in *ctx*."""
    if not case_conditions:
        return LogicResult(valid=False, message="No case conditions provided.", backend="Z3 (Cases)")
    disjunction = case_conditions[0]
    for cond in case_conditions[1:]:
        disjunction = BinaryOpNode(op="or", left=disjunction, right=cond)
    return verify_entailment(disjunction, ctx, timeout_ms=timeout_ms)

