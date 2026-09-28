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

    return None


def _make_z3_var(name: str, mt: MathType) -> z3.ExprRef:
    if mt in (MathType.Nat, MathType.Int):
        return z3.Int(name)
    if mt == MathType.Bool:
        return z3.Bool(name)
    return z3.Real(name)


def ast_to_z3(
    expr: ExprNode,
    ctx: ProofContext,
    bound_vars: Optional[dict[str, z3.ExprRef]] = None,
    extra_constraints: Optional[list[z3.ExprRef]] = None,
) -> z3.ExprRef:
    """Translate an Aether ``ExprNode`` into a Z3 expression or formula."""
    if bound_vars is None:
        bound_vars = {}

    if isinstance(expr, NumberNode):
        if "." in expr.value:
            return z3.RealVal(expr.value)
        return z3.IntVal(int(expr.value))

    if isinstance(expr, (SymbolNode, GreekSymbolNode)):
        name = expr.name
        if name in bound_vars:
            return bound_vars[name]
        vinfo = ctx.get_var(name)
        mt = vinfo.math_type if vinfo else MathType.Real
        return _make_z3_var(name, mt)

    if isinstance(expr, UnaryOpNode):
        sub = ast_to_z3(expr.operand, ctx, bound_vars, extra_constraints)
        if expr.op == "-":
            return -sub  # type: ignore[operator]
        if expr.op == "+":
            return sub
        if expr.op == "not":
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
        raise LogicConversionError(f"Unsupported binary operator in Z3: {expr.op!r}")

    if isinstance(expr, RelationNode):
        left = ast_to_z3(expr.left, ctx, bound_vars, extra_constraints)
        right = ast_to_z3(expr.right, ctx, bound_vars, extra_constraints)
        rel = canonical_rel(expr.op)
        if rel == "=":
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
        raise LogicConversionError(f"Unsupported relation in Z3: {expr.op!r}")

    if isinstance(expr, FunctionCallNode):
        fn = expr.func.lower()
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
        uf = z3.Function(expr.func, *arg_sorts, z3.BoolSort())
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


def _format_z3_model(model: z3.ModelRef, ctx: ProofContext) -> str:
    parts: list[str] = []
    for var_name in sorted(ctx.all_variables().keys()):
        vinfo = ctx.get_var(var_name)
        if vinfo is None:
            continue
        z3_v = _make_z3_var(var_name, vinfo.math_type)
        val = model.eval(z3_v, model_completion=False)
        if val is not None and not val.eq(z3_v):
            parts.append(f"{var_name}={val}")
    if not parts:
        for d in model.decls():
            if d.arity() == 0:
                parts.append(f"{d.name()}={model[d]}")
    return ", ".join(parts)


def _populate_solver_context(solver: z3.Solver, ctx: ProofContext) -> None:
    """Add variable domain constraints (e.g. Nat >= 0), active hypotheses, and chain facts to *solver*."""
    extra: list[z3.ExprRef] = []
    for vinfo in ctx.all_variables().values():
        if vinfo.math_type == MathType.Nat:
            z3_v = _make_z3_var(vinfo.name, MathType.Nat)
            solver.add(z3_v >= 0)  # type: ignore[operator]

    for h in ctx.all_hypotheses():
        try:
            solver.add(ast_to_z3(h.proposition, ctx, extra_constraints=extra))
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


def _try_sympy_divisibility_or_existential(
    claim: ExprNode,
    ctx: ProofContext,
) -> Optional[LogicResult]:
    """Check integer divisibility predicates and linear existential equations via SymPy CAS."""
    # Expand Even/Odd/MultipleOf/Divides into QuantifierNode if applicable
    target = claim
    if isinstance(claim, FunctionCallNode):
        expanded = expand_prelude_predicate(claim, witness_var="_m_auto")
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
    # 1. If claim is an existential with an explicit [witness: ...], check the witness first
    if isinstance(claim, QuantifierNode) and claim.quantifier == "exists" and witness is not None:
        w_expr = witness
        # Allow both [witness: 2*k^2] and [witness: m = 2*k^2]
        if isinstance(witness, RelationNode) and canonical_rel(witness.op) == "=":
            if isinstance(witness.left, SymbolNode) and witness.left.name == claim.var:
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
            # Check if the existential itself is valid even though the witness expression had a mismatch,
            # or report the witness failure clearly.
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
                backend="SymPy (Witness)",
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
        ce_str = _format_z3_model(model, ctx)
        ce_msg = f"Counterexample: {ce_str}" if ce_str else "Z3 found a counterexample model."
        return LogicResult(
            valid=False,
            message=f"Claim '{claim}' does not follow from current hypotheses. {ce_msg}",
            counterexample=ce_str or None,
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
        backend="Z3 (Domain)",
    )
