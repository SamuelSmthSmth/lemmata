"""Z3 SMT solver backend for logical deductions, inequalities, quantifiers, and domain obligations."""

from __future__ import annotations

import functools
import itertools
import re
import time
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
    MatrixNode,
    VectorNode,
)
from aether.core.types import MathType
from aether.engine import trace
from aether.engine.trace import traced
from aether.engine.context import (
    HypothesisInfo,
    ProofContext,
    binding_call,
    collect_free_symbols,
    substitute_mapping,
    DomainObligation,
    canonical_rel,
)
from aether.engine.algebra import (
    AlgebraConversionError,
    ast_to_sympy,
    called_function_names,
    unknown_call_hints,
    verify_algebraic_equality,
)


# Z3 is bounded by *work*, not by time.  A wall-clock timeout makes a verdict
# depend on the machine: the same query that a fast laptop settles in 2 s is
# "unknown" on a slow runner or inside WebAssembly, and a proof would check on
# one and fail on the other.  Z3's resource limit (``rlimit``) counts solver
# steps instead, so a query either finishes within it everywhere or nowhere.
# Every query the repo pins that Z3 decides needs under 35k units; the ones
# that run out of time burn millions, so 500k leaves wide headroom.  The wall
# clock stays only as a backstop for work Z3 does not meter, set far above
# what 500k units take even on a slow machine.
SOLVER_RLIMIT = 500_000
SOLVER_BACKSTOP_MS = 6000


def fresh_solver_context() -> None:
    """Start the next check on a new Z3 context.

    Z3's search depends on the terms its context has seen, so in a long-lived
    process (the server's workers, the browser's worker, a test run) the same
    proof could check, time out or stall depending on what was checked before
    it.  A fresh context per check makes every verdict depend only on the
    proof, as it does in a new process.  Nothing in the engine keeps Z3 terms
    between checks; the old context is freed once nothing refers to it.
    """
    z3.z3._main_ctx = None


class SolverContext:
    """A Z3 context of its own, for queries that must not touch the check's.

    Z3's search depends on the terms its context has seen, so a query made
    only to report something (which premises a line used) could otherwise
    change how a later line is decided, or which core the kernel reports.
    ``with scratch:`` runs the queries inside on this context instead."""

    def __init__(self) -> None:
        self._ctx: Optional[z3.Context] = None
        self._saved: list = []

    def __enter__(self) -> "SolverContext":
        if self._ctx is None:
            self._ctx = z3.Context()
        self._saved.append(z3.z3._main_ctx)
        z3.z3._main_ctx = self._ctx
        return self

    def __exit__(self, *exc: object) -> None:
        z3.z3._main_ctx = self._saved.pop()


def new_solver(timeout_ms: int) -> z3.Solver:
    """A solver bounded by SOLVER_RLIMIT, with a wall-clock backstop.

    *timeout_ms* is kept for the callers' signatures; it only ever raises the
    backstop, so no caller can bring back a machine-dependent cut-off.
    """
    solver = z3.Solver()
    solver.set("rlimit", SOLVER_RLIMIT)
    solver.set("timeout", max(timeout_ms, SOLVER_BACKSTOP_MS))
    return solver


class LogicConversionError(Exception):
    """Raised when an AST node cannot be translated into a Z3 expression."""


# True, if loose, bounds on the mathematical constants.  Without them the
# solver treats `pi` as an arbitrary real: `pi > 3` came back as a satisfied
# query with a "counterexample".  These are facts about the numbers, so adding
# them as hypotheses is sound -- they only narrow the models.
_CONSTANT_BOUNDS: dict[str, tuple[str, str]] = {
    "pi": ("3.14159265", "3.14159266"),
    "e": ("2.718281828", "2.718281829"),
}


# ``(min, max)`` argument counts for the calls the SMT backend interprets.  A
# call that reaches the uninterpreted fallback with one of these names was
# misused -- ``Even(a, a)`` used to become an opaque predicate and be reported
# as a counterexample, when the real problem was the argument list.
_LOGIC_CALL_ARITY: dict[str, tuple[int, Optional[int]]] = {
    "even": (1, 1),
    "odd": (1, 1),
    "positive": (1, 1),
    "nonnegative": (1, 1),
    "multipleof": (2, 2),
    "divides": (2, 2),
    "orthogonal": (2, 2),
    "congruent": (3, 3),
    "cong": (3, 3),
    "cauchyriemann": (2, 4),
    "cauchy_riemann": (2, 4),
    "sqrt": (1, 1),
    "abs": (1, 1),
    "inv": (1, 1),
    "inverse": (1, 1),
    "max": (1, None),
    "min": (1, None),
}

# Functions SymPy settles but Z3 has no theory for.  To the solver they are
# arbitrary functions, so it will answer an inequality about them with a bogus
# "counterexample" (`exp(x) > 0` came back as `x=2`).  The note says so instead
# of letting that read as a maths error.
_SYMPY_ONLY_CALLS: frozenset[str] = frozenset({"exp", "log", "ln", "sin", "cos", "tan"})


def _range_facts(fn: str, value: z3.ExprRef, arg: z3.ExprRef) -> list[z3.ExprRef]:
    """True facts about ``fn(arg)`` for functions Z3 only sees as uninterpreted.

    Z3 has no theory of the transcendental functions, but most inequalities in
    an analysis course do not need one: ``|x sin(1/x)| <= |x|`` needs only
    ``|sin| <= 1``, and the quotient rule's ``exp(x) != 0`` only ``exp > 0``.
    Each fact holds for every real argument, so adding them only removes
    models that were never real -- it cannot make a false claim provable.
    """
    if fn in ("sin", "cos"):
        return [value >= -1, value <= 1]  # type: ignore[operator]
    if fn == "exp":
        # exp(t) > 0, and the tangent line at 0 lies below it: exp(t) >= 1 + t.
        return [value > 0, value >= 1 + arg]  # type: ignore[operator]
    if fn == "cosh":
        return [value >= 1]  # type: ignore[operator]
    if fn == "tanh":
        return [value > -1, value < 1]  # type: ignore[operator]
    if fn in ("log", "ln"):
        # For t > 0, log lies below its tangent at 1: log(t) <= t - 1.
        return [z3.Implies(arg > 0, value <= arg - 1)]  # type: ignore[operator]
    return []


def _infinity_sign(expr: ExprNode, ctx: ProofContext) -> int:
    """+1 for ``oo``, -1 for ``-oo``, 0 for anything else.

    A declared variable called ``oo`` is just a variable.
    """
    if isinstance(expr, SymbolNode) and expr.name == "oo" and ctx.get_var("oo") is None:
        return 1
    if isinstance(expr, UnaryOpNode) and expr.op in ("-", "+"):
        inner = _infinity_sign(expr.operand, ctx)
        return -inner if expr.op == "-" else inner
    return 0


def _mentions_infinity(expr: ExprNode, ctx: ProofContext) -> bool:
    return "oo" in collect_free_symbols(expr) and ctx.get_var("oo") is None


def _compare_with_infinity(rel: str, left: int, right: int) -> Optional[bool]:
    """Decide ``a rel b`` when at least one side is +-oo (``0`` marks a finite side)."""
    if left == right:  # the same infinity on both sides
        return rel in ("=", "<=", ">=")
    if rel == "=":
        return False
    if rel == "!=":
        return True
    # The extended reals are ordered -oo < every real number < +oo.
    less = left < right
    if rel in ("<", "<="):
        return less
    if rel in (">", ">="):
        return not less
    return None


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
    # Matrix and vector entries: `[[1, n], [0, 1]]` at n = k + 1 is
    # `[[1, k + 1], [0, 1]]`.  Without this the entries kept their n, and a
    # matrix-power induction could never match its own step.
    if isinstance(expr, MatrixNode):
        return MatrixNode(
            rows=[[substitute_expr(e, var_name, replacement) for e in row] for row in expr.rows],
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, VectorNode):
        return VectorNode(
            elements=[substitute_expr(e, var_name, replacement) for e in expr.elements],
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
    - ``Prime(p)``         -> ``p > 1 and forall _kd : Int, 1 < _kd < p => not Divides(_kd, p)``
    - ``Coprime(a, b)``    -> ``forall _kc : Int, Divides(_kc, a) and Divides(_kc, b) => _kc = 1 or _kc = -1``
    - ``Rational(x)``      -> ``exists _kp, _kq : Int, _kq > 0 and Coprime(_kp, _kq) and x = _kp / _kq``
    - ``Irrational(x)``    -> ``not Rational(x)``
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

    if fn == "coprime" and len(node.args) == 2:
        # Every common divisor is 1 or -1.
        a, b = node.args
        d = SymbolNode(name=f"{witness_var}c")
        common = BinaryOpNode(
            op="and",
            left=FunctionCallNode(func="Divides", args=[d, a]),
            right=FunctionCallNode(func="Divides", args=[d, b]),
        )
        unit = BinaryOpNode(
            op="or",
            left=RelationNode(op="=", left=d, right=NumberNode(value="1")),
            right=RelationNode(op="=", left=d, right=UnaryOpNode(op="-", operand=NumberNode(value="1"))),
        )
        return QuantifierNode(
            quantifier="forall", var=d.name, var_type="Int",
            formula=BinaryOpNode(op="=>", left=common, right=unit),
        )

    if fn == "rational" and len(node.args) == 1:
        # x = p / q in lowest terms: the form a proof by contradiction uses.
        x = node.args[0]
        p, q = SymbolNode(name=f"{witness_var}p"), SymbolNode(name=f"{witness_var}q")
        body = BinaryOpNode(
            op="and",
            left=BinaryOpNode(
                op="and",
                left=RelationNode(op=">", left=q, right=NumberNode(value="0")),
                right=FunctionCallNode(func="Coprime", args=[p, q]),
            ),
            right=RelationNode(op="=", left=x, right=BinaryOpNode(op="/", left=p, right=q)),
        )
        return QuantifierNode(
            quantifier="exists", var=p.name, var_type="Int",
            formula=QuantifierNode(quantifier="exists", var=q.name, var_type="Int", formula=body),
        )

    if fn == "irrational" and len(node.args) == 1:
        return UnaryOpNode(op="not", operand=FunctionCallNode(func="Rational", args=[node.args[0]]))

    if fn == "prime" and len(node.args) == 1:
        # p > 1, and no d with 1 < d < p divides it.
        p = node.args[0]
        d = SymbolNode(name=f"{witness_var}d")
        in_range = BinaryOpNode(
            op="and",
            left=RelationNode(op=">", left=d, right=NumberNode(value="1")),
            right=RelationNode(op="<", left=d, right=p),
        )
        no_divisor = QuantifierNode(
            quantifier="forall",
            var=d.name,
            var_type="Int",
            formula=BinaryOpNode(
                op="=>",
                left=in_range,
                right=UnaryOpNode(op="not", operand=FunctionCallNode(func="Divides", args=[d, p])),
            ),
        )
        return BinaryOpNode(op="and", left=RelationNode(op=">", left=p, right=NumberNode(value="1")), right=no_divisor)

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
        if name == "oo" and ctx.get_var("oo") is None:
            raise LogicConversionError(
                "oo is not a real number, so the solver cannot do arithmetic with it; "
                "compare against it directly, or evaluate the limit or sum first."
            )
        if (
            name in _CONSTANT_BOUNDS
            and ctx.get_var(name) is None
            and name not in ctx.structure_names()
        ):
            const = z3.Real(name)
            low, high = _CONSTANT_BOUNDS[name]
            if extra_constraints is not None:
                extra_constraints.append(const > z3.RealVal(low))  # type: ignore[operator]
                extra_constraints.append(const < z3.RealVal(high))  # type: ignore[operator]
            return const
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
            # Only for a power fixed in this proof: under `forall n`, `2^n` must
            # stay a term in the bound n.  A constant standing for it would be
            # one number for every n, and "forall n, 2^n = 1" would follow.
            if (
                extra_constraints is not None
                and z3.is_arith(left)
                and not _mentions_any(left, bound_vars)
                and not _mentions_any(right, bound_vars)
            ):
                symbolic = _symbolic_power(left, right, extra_constraints)
                if symbolic is not None:
                    return symbolic
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
        rel = canonical_rel(expr.op)
        left_inf, right_inf = _infinity_sign(expr.left, ctx), _infinity_sign(expr.right, ctx)
        if left_inf or right_inf:
            finite_side = expr.right if left_inf else expr.left
            if (left_inf and right_inf) or not _mentions_infinity(finite_side, ctx):
                decided = _compare_with_infinity(rel, left_inf, right_inf)
                if decided is not None:
                    return z3.BoolVal(decided)
        left = ast_to_z3(expr.left, ctx, bound_vars, extra_constraints)
        right = ast_to_z3(expr.right, ctx, bound_vars, extra_constraints)
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
                # Z3 leaves `x % 0` unconstrained, which made every congruence
                # modulo a possibly-zero m unprovable.  Modulo 0, congruence is
                # equality (0 divides only 0).
                return z3.If(m == 0, a == b, ((a - b) % m) == 0)  # type: ignore[operator]
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
        # Divisibility without a quantifier.  For whole numbers it is `%`.  For a
        # term the solver holds as a real (a power like 3^k, whose wholeness is
        # a separate fact), "a is a multiple of b" is exactly "a / b is a whole
        # number" (b != 0): the same meaning as `exists k : Int, a = b * k`,
        # without asking the solver to find k, which it rarely can.
        if fn == "even" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            if z3.is_int(arg):
                return (arg % 2) == 0  # type: ignore[operator]
            if z3.is_arith(arg):
                return z3.IsInt(arg / 2)  # type: ignore[operator]
        if fn == "odd" and len(expr.args) == 1:
            arg = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            if z3.is_int(arg):
                return (arg % 2) == 1  # type: ignore[operator]
            if z3.is_arith(arg):
                return z3.IsInt((arg - 1) / 2)  # type: ignore[operator]
        if fn == "multipleof" and len(expr.args) == 2:
            a = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            b = ast_to_z3(expr.args[1], ctx, bound_vars, extra_constraints)
            if z3.is_int(a) and z3.is_int(b):
                return z3.If(b == 0, a == 0, (a % b) == 0)  # type: ignore[operator]
            if z3.is_arith(a) and z3.is_arith(b):
                ra, rb = _as_real(a), _as_real(b)
                return z3.If(rb == 0, ra == 0, z3.IsInt(ra / rb))  # type: ignore[operator]
        if fn == "divides" and len(expr.args) == 2:
            a = ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints)
            b = ast_to_z3(expr.args[1], ctx, bound_vars, extra_constraints)
            if z3.is_int(a) and z3.is_int(b):
                return z3.If(a == 0, b == 0, (b % a) == 0)  # type: ignore[operator]
            if z3.is_arith(a) and z3.is_arith(b):
                ra, rb = _as_real(a), _as_real(b)
                return z3.If(ra == 0, rb == 0, z3.IsInt(rb / ra))  # type: ignore[operator]

        if fn == "prime" and len(expr.args) == 1:
            # A number is settled outright (Prime(1681) is a fact, not a search).
            value = z3.simplify(ast_to_z3(expr.args[0], ctx, bound_vars, extra_constraints))
            if z3.is_int_value(value):
                return z3.BoolVal(bool(sp.isprime(value.as_long())))

        expanded = expand_prelude_predicate(expr)
        if expanded is not None:
            return ast_to_z3(expanded, ctx, bound_vars, extra_constraints)

        if binding_call(expr) is not None:
            return _opaque_binding_call(expr, ctx, bound_vars, extra_constraints)

        arity = _LOGIC_CALL_ARITY.get(fn)
        if arity is not None:
            low, high = arity
            if len(expr.args) < low or (high is not None and len(expr.args) > high):
                expected = (
                    f"at least {low}"
                    if high is None
                    else str(low)
                    if low == high
                    else f"{low} to {high}"
                )
                raise LogicConversionError(
                    f"`{expr.func}` takes {expected} argument(s), but got {len(expr.args)}."
                )

        # A declared function (`Given f : Real -> Real`): one symbol, with the
        # declared argument and result sorts, however its arguments are written.
        fvar = ctx.get_var(expr.func) if expr.func not in bound_vars else None
        if fvar is not None and fvar.signature is not None:
            arg_types, result_type = fvar.signature
            if len(expr.args) != len(arg_types):
                raise LogicConversionError(
                    f"`{expr.func}` is declared as {fvar.type_label}, so it takes "
                    f"{len(arg_types)} argument(s), but got {len(expr.args)}."
                )
            z3_args = []
            for a, t in zip(expr.args, arg_types):
                z = ast_to_z3(a, ctx, bound_vars, extra_constraints)
                want = _make_z3_var("_", t).sort()
                if want == z3.RealSort() and z3.is_int(z):
                    z = z3.ToReal(z)
                elif want == z3.IntSort() and z3.is_real(z):
                    z = z3.ToInt(z)
                z3_args.append(z)
            result = _make_z3_var("_", result_type).sort()
            uf = z3.Function(expr.func, *[_make_z3_var("_", t).sort() for t in arg_types], result)
            applied = uf(*z3_args)
            if extra_constraints is not None and result_type == MathType.Nat:
                extra_constraints.append(applied >= 0)  # type: ignore[operator]
            return applied

        # Uninterpreted predicate / function
        z3_args = [ast_to_z3(a, ctx, bound_vars, extra_constraints) for a in expr.args]
        arg_sorts = [a.sort() for a in z3_args]
        return_sort = (
            z3.RealSort()
            if (fn in ("diff", "det", "tr", "norm", "dot", "conj", "re", "im") or expr.func[0].islower())
            else z3.BoolSort()
        )
        uf = z3.Function(expr.func, *arg_sorts, return_sort)
        applied = uf(*z3_args)
        if extra_constraints is not None and len(z3_args) == 1 and z3.is_arith(z3_args[0]):
            arg_real = z3.ToReal(z3_args[0]) if z3.is_int(z3_args[0]) else z3_args[0]
            extra_constraints.extend(_range_facts(fn, applied, arg_real))
        return applied

    if isinstance(expr, QuantifierNode):
        try:
            mt = ctx.resolve_type(expr.var_type)[0] if expr.var_type else MathType.Real
        except ValueError as exc:
            raise LogicConversionError(str(exc)) from exc
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


def _opaque_binding_call(
    expr: FunctionCallNode,
    ctx: ProofContext,
    bound_vars: dict[str, z3.ExprRef],
    extra_constraints: Optional[list] = None,
) -> z3.ExprRef:
    """A sum, definite integral or limit, as the solver sees it.

    The solver has no theory of these, so the call becomes an uninterpreted
    real function of the variables free in it, never of the variable it binds:
    ``sum(r, 1, n, r * r!)`` is a function of n alone.  The function is named
    by the call's shape with those variables as placeholders, so
    ``sum(r, 1, k, r^2)`` and ``sum(r, 1, n, r^2)`` are the same function at k
    and at n, which is what lets a fact about one be used for the other.
    """
    free = sorted(collect_free_symbols(expr))
    placeholders = {name: SymbolNode(name=f"_a{i}") for i, name in enumerate(free)}
    shape = substitute_mapping(expr, placeholders)
    args = [ast_to_z3(SymbolNode(name=name), ctx, bound_vars, extra_constraints) for name in free]
    uf = z3.Function(f"{expr.func.lower()}[{shape}]", *[a.sort() for a in args], z3.RealSort())
    return uf(*args) if args else uf()


def _mentions_any(term: z3.ExprRef, bound_vars: dict[str, z3.ExprRef]) -> bool:
    """Whether *term* uses any variable a quantifier binds here."""
    if not bound_vars:
        return False
    targets = list(bound_vars.values())
    stack = [term]
    while stack:
        node = stack.pop()
        if any(node.eq(t) for t in targets):
            return True
        stack.extend(node.children())
    return False


def _as_real(term: z3.ExprRef) -> z3.ExprRef:
    return z3.ToReal(term) if z3.is_int(term) else term


def _power_atom(base: z3.ExprRef, exponent: z3.ExprRef) -> z3.ExprRef:
    """The solver's name for ``base ^ exponent``: one real constant per pair."""
    return z3.Real(f"pow!{base.sexpr()}!{z3.simplify(exponent).sexpr()}")


def _symbolic_power(
    base: z3.ExprRef,
    exponent: z3.ExprRef,
    extra_constraints: list,
) -> Optional[z3.ExprRef]:
    """``base ^ exponent`` for a symbolic whole-number exponent, as a student uses it.

    Z3's own power is a nonlinear term it can rarely reason about, so ``3^k``
    in ``4 * (7 * m + 3^k)`` was not even known to be a whole number, and a
    divisibility induction could not close.  Instead the power is a constant
    carrying the facts that matter, each guarded by the exponent being
    non-negative (``2^(k - 1)`` at k = 0 is not a whole number):

    - an integer base to a non-negative power is an integer;
    - ``b^0 = 1``, ``b^1 = b``, and a base of at least 1 gives at least 1;
    - ``b^(e + c) = b^c * b^e`` for a constant shift c, which is exactly the
      step an induction takes (``7^(k + 1) = 7 * 7^k``).
    """
    if not z3.is_int(exponent) or z3.is_int_value(z3.simplify(exponent)):
        return None
    exponent = z3.simplify(exponent)
    atom = _power_atom(base, exponent)
    integer_base = z3.is_int(base)
    real_base = z3.ToReal(base) if integer_base else base

    def facts(power: z3.ExprRef, e: z3.ExprRef) -> None:
        nonneg = e >= 0  # type: ignore[operator]
        if integer_base:
            extra_constraints.append(z3.Implies(nonneg, z3.IsInt(power)))
        extra_constraints.append(z3.Implies(e == 0, power == 1))  # type: ignore[operator]
        extra_constraints.append(z3.Implies(e == 1, power == real_base))  # type: ignore[operator]
        extra_constraints.append(z3.Implies(z3.And(nonneg, real_base >= 1), power >= 1))  # type: ignore[operator]
        extra_constraints.append(z3.Implies(real_base > 0, power > 0))  # type: ignore[operator]

    facts(atom, exponent)

    # Split off a constant shift: k + 1 is k shifted by 1, k - 1 by -1.
    shift = 0
    rest = exponent
    if z3.is_add(exponent):
        constants = [a for a in exponent.children() if z3.is_int_value(a)]
        others = [a for a in exponent.children() if not z3.is_int_value(a)]
        if len(constants) == 1 and others:
            shift = constants[0].as_long()
            rest = z3.simplify(z3.Sum(others) if len(others) > 1 else others[0])
    if shift and abs(shift) <= 6:
        base_atom = _power_atom(base, rest)
        facts(base_atom, rest)
        factor = real_base
        for _ in range(abs(shift) - 1):
            factor = factor * real_base  # type: ignore[operator]
        both_nonneg = z3.And(rest >= 0, exponent >= 0)  # type: ignore[operator]
        if shift > 0:
            extra_constraints.append(z3.Implies(both_nonneg, atom == factor * base_atom))  # type: ignore[operator]
        else:
            extra_constraints.append(z3.Implies(both_nonneg, base_atom == factor * atom))  # type: ignore[operator]
    return atom


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
            # The solver's own stand-ins (a power's `pow!…`, a square root's
            # `_sqrt_…`, an opaque sum's `sum[…]`) are not anything the student named.
            if d.arity() == 0 and not d.name().startswith(("pow!", "_")) and "[" not in d.name():
                res[d.name()] = str(model[d])
    return res


def _format_z3_model(model: z3.ModelRef, ctx: ProofContext) -> str:
    m_dict = extract_z3_model_dict(model, ctx)
    return ", ".join(f"{k}={v}" for k, v in m_dict.items())


def _quantifier_type(
    raw: Optional[str],
    ctx: ProofContext,
    default: MathType = MathType.Real,
) -> MathType:
    """The math type a quantifier ranges over; an unknown name counts as the default."""
    if not raw:
        return default
    try:
        return ctx.resolve_type(raw)[0]
    except ValueError:
        return default


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


# Membership, intersection, union and subset are uninterpreted functions over
# the reals, pinned down by three quantified axioms.  Quantifiers are costly:
# while they are present, showing a goal *satisfiable* sends Z3 into model-
# based quantifier instantiation, work its resource limit does not meter, so
# "is x = 1?" under the hypothesis x != 1 could run until the wall-clock
# backstop.  Axioms about functions a problem never mentions cannot change its
# answer, so they are added only to problems that use one of them.
_SET_FUNCTIONS = ("in", "intersect", "union", "subset")


def _add_set_axioms(solver: z3.Solver) -> None:
    S = z3.RealSort()
    st_x, st_A, st_B = z3.Reals("_st_x _st_A _st_B")
    in_fn = z3.Function("in", S, S, z3.BoolSort())
    inter_fn = z3.Function("intersect", S, S, S)
    union_fn = z3.Function("union", S, S, S)
    sub_fn = z3.Function("subset", S, S, z3.BoolSort())
    solver.add(z3.ForAll([st_x, st_A, st_B], in_fn(st_x, inter_fn(st_A, st_B)) == z3.And(in_fn(st_x, st_A), in_fn(st_x, st_B))))
    solver.add(z3.ForAll([st_x, st_A, st_B], in_fn(st_x, union_fn(st_A, st_B)) == z3.Or(in_fn(st_x, st_A), in_fn(st_x, st_B))))
    solver.add(z3.ForAll([st_A, st_B], sub_fn(st_A, st_B) == z3.ForAll([st_x], z3.Implies(in_fn(st_x, st_A), in_fn(st_x, st_B)))))


def _uses_set_functions(solver: z3.Solver) -> bool:
    seen: set[int] = set()
    stack = list(solver.assertions())
    while stack:
        node = stack.pop()
        if node.get_id() in seen:
            continue
        seen.add(node.get_id())
        if z3.is_app(node):
            decl = node.decl()
            if decl.kind() == z3.Z3_OP_UNINTERPRETED and decl.name() in _SET_FUNCTIONS:
                return True
            stack.extend(node.children())
        elif z3.is_quantifier(node):
            stack.append(node.body())
    return False


def check_solver(solver: z3.Solver) -> z3.CheckSatResult:
    if trace.active() is None:
        return _check_solver(solver)
    start = time.perf_counter()
    result = z3.unknown
    try:
        result = _check_solver(solver)
        return result
    finally:
        trace.solver_event(str(result), len(solver.assertions()), start)


def _check_solver(solver: z3.Solver) -> z3.CheckSatResult:
    """``solver.check()``, with the set axioms added when the problem needs them.

    A query that runs out of its budget is *unknown*, never an error.  Z3
    usually reports that as an ``unknown`` result, but some builds (the
    WebAssembly one the browser runs) raise it as an exception instead; both
    mean the same thing, and the caller handles unknown.
    """
    if _uses_set_functions(solver):
        _add_set_axioms(solver)
    try:
        return solver.check()
    except z3.Z3Exception as exc:
        if _is_budget_exhausted(exc):
            return z3.unknown
        raise


def _is_budget_exhausted(exc: z3.Z3Exception) -> bool:
    text = str(exc.value if hasattr(exc, "value") else exc).lower()
    return any(word in text for word in ("resource limit", "canceled", "cancelled", "timeout"))


def _populate_solver_context(solver: z3.Solver, ctx: ProofContext) -> None:
    """Add variable domain constraints (e.g. Nat >= 0), active hypotheses, and chain facts to *solver*."""
    extra: list[z3.ExprRef] = []
    active_vars = ctx.all_variables()
    for vinfo in active_vars.values():
        if vinfo.math_type == MathType.Nat:
            z3_v = _make_z3_var(vinfo.name, MathType.Nat)
            solver.add(z3_v >= 0)  # type: ignore[operator]

    # The set-theory axioms are added by check_solver(), and only when the
    # problem mentions a set operation (see _SET_FUNCTIONS).

    for h in ctx.all_hypotheses():
        for term in hypothesis_terms(h.proposition, ctx, extra):
            solver.add(term)
        _populate_algebra_axioms(solver, h.proposition, ctx)

    chain_rel = chain_fact(ctx)
    if chain_rel is not None:
        try:
            solver.add(ast_to_z3(chain_rel, ctx, extra_constraints=extra))
        except LogicConversionError:
            pass

    for c in extra:
        solver.add(c)


def chain_fact(ctx: ProofContext) -> Optional[RelationNode]:
    """What the active chain has established so far (``head R current``), if any."""
    if ctx.chain is not None and ctx.chain.effective_relation:
        return RelationNode(
            op=ctx.chain.effective_relation,
            left=ctx.chain.head_lhs,
            right=ctx.chain.current_rhs,
        )
    return None


def hypothesis_terms(prop: ExprNode, ctx: ProofContext, extra: list) -> list[z3.ExprRef]:
    """A hypothesis as the solver is given it: the proposition, and for a
    universal one its ground instances at the variables in scope (up to two
    quantifiers deep).  Parts that do not translate are left out."""
    terms: list[z3.ExprRef] = []
    try:
        terms.append(ast_to_z3(prop, ctx, extra_constraints=extra))
    except LogicConversionError:
        pass
    # Eager ground instantiation for universally quantified hypotheses / lemmas
    if isinstance(prop, QuantifierNode) and prop.quantifier == "forall":
        active_vars = ctx.all_variables()
        q1_mt = _quantifier_type(prop.var_type, ctx)
        for v1 in active_vars.values():
            if _types_compatible(q1_mt, v1.math_type):
                inst1 = substitute_expr(prop.formula, prop.var, SymbolNode(name=v1.name))
                if isinstance(inst1, QuantifierNode) and inst1.quantifier == "forall":
                    q2_mt = _quantifier_type(inst1.var_type, ctx)
                    for v2 in active_vars.values():
                        if _types_compatible(q2_mt, v2.math_type):
                            inst2 = substitute_expr(inst1.formula, inst1.var, SymbolNode(name=v2.name))
                            try:
                                terms.append(ast_to_z3(inst2, ctx, extra_constraints=extra))
                            except LogicConversionError:
                                pass
                else:
                    try:
                        terms.append(ast_to_z3(inst1, ctx, extra_constraints=extra))
                    except LogicConversionError:
                        pass
    return terms


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


@traced("Logic", "induction", lambda claim, ctx: str(claim), quiet=True)
def verify_induction_schema(
    claim: ExprNode,
    ctx: ProofContext,
) -> Optional[LogicResult]:
    """Check whether a universal claim is established by mathematical induction.

    The claims it reads, as A Level and the notes state them:

    - ``forall n : Nat, P(n)``: every natural number, from 0;
    - ``forall n : Nat, n >= a => P(n)`` (or ``n > a``, ``a <= n``): from a;
    - ``forall n : Int, n >= a => P(n)``: the integers from a.

    The facts it looks for among the established hypotheses:

    - base cases ``P(a)``, ``P(a + 1)``, … as the Base case blocks export them;
    - an inductive step ``forall k, H => P(k + d)`` for d = 1, 2 or 3, where
      each conjunct of H is one of ``P(k)``, …, ``P(k + d - 1)`` (the
      hypotheses) or a side condition that follows from ``k >= a`` (``k >= 5``
      in a step starting at 5).  d = 2 is a recurrence like
      ``u(n + 2) = 5 u(n + 1) - 6 u(n)``, which needs two base cases.

    Returns None when the proof is not an induction at all, a valid result
    when it establishes the claim, and an invalid one when it is an induction
    that does not, saying why.  Soundness, case by case:

    - Over the integers a claim needs a starting value: a base case and a step
      say nothing about the numbers below the base ("every integer is
      non-negative" has both).  The reals have no induction at all.
    - Unguarded, the claim starts at 0, so a base case at a > 0 leaves P(0),
      …, P(a - 1) open: each must be established or provable directly ("2^n
      >= 2 for every natural n" has a base case at 1 and a valid step, and is
      false at 0; the sum of no squares is 0, so a base case at 1 still proves
      that formula for every natural number).
    - A side condition in the step must follow from ``k >= a``: a step that
      assumes ``k >= 5`` proves nothing about a claim starting at 1.
    """
    expanded_claim = ctx.expand_user_functions(claim) or claim
    if not (isinstance(expanded_claim, QuantifierNode) and expanded_claim.quantifier == "forall"):
        return None

    n_var = expanded_claim.var
    p_n, start = _induction_guard(expanded_claim.formula, n_var)
    hyps = ctx.all_hypotheses()

    def established_by(prop: ExprNode) -> Optional[HypothesisInfo]:
        return next((h for h in hyps if _exprs_match(h.proposition, prop, ctx)), None)

    def established(prop: ExprNode) -> bool:
        return established_by(prop) is not None

    def p_at(value: int) -> ExprNode:
        return substitute_expr(p_n, n_var, _int_node(value))

    # 1. Inductive steps among the established facts: forall k, H => P(k + d).
    found = [(s, h) for s, h in ((_induction_step(h.proposition, p_n, n_var, ctx), h) for h in hyps) if s is not None]
    steps = [s for s, _ in found]
    if not steps:
        return None

    # 2. Base cases: the run P(a), …, P(a + d - 1) a step needs.  Guarded, a is
    # the claim's start; unguarded, the smallest run of established bases.
    candidates = [start] if start is not None else list(range(0, 11))
    chosen: Optional[tuple[int, _InductionStep]] = None
    for a in candidates:
        for step in steps:
            if all(established(p_at(a + j)) for j in range(step.span)):
                chosen = (a, step)
                break
        if chosen is not None:
            break
    if chosen is None:
        if start is None:
            return None
        span = min(s.span for s in steps)
        missing = ", ".join(f"{n_var} = {start + j}" for j in range(span) if not established(p_at(start + j)))
        return LogicResult(
            valid=False,
            message=(
                f"The claim starts at {n_var} = {start}, so the induction needs a base case there"
                f"{'' if span == 1 else f' and at the {span - 1} after it (the step uses {span} earlier values)'}: "
                f"missing {missing}."
            ),
            backend="Induction",
        )
    a, step = chosen

    # 3. It is an induction: is it one that proves this claim?
    mt = _quantifier_type(expanded_claim.var_type, ctx, MathType.Real)
    if mt not in (MathType.Nat, MathType.Int) or (mt == MathType.Int and start is None):
        return LogicResult(
            valid=False,
            message=(
                f"Induction proves a claim about the natural numbers only, but this one is "
                f"over {expanded_claim.var_type or 'an unstated type'}: a base case and an inductive "
                f"step say nothing about the numbers below the base. State it as "
                f"'forall {n_var} : Nat, …', or from a starting value: "
                f"'forall {n_var} : Int, {n_var} >= {a} => …'."
            ),
            backend="Induction",
        )
    if start is None:
        # Unguarded over Nat: everything below the base run must hold as well.
        for j in range(a):
            below = verify_entailment(p_at(j), ctx)
            if not below.valid:
                return LogicResult(
                    valid=False,
                    message=(
                        f"The base case is {n_var} = {a}, but the claim is for every natural number, "
                        f"and {j} is one: '{p_at(j)}' is not established. Prove it as a base case "
                        f"{n_var} = {j}; if it is false at {j}, the claim itself needs changing, "
                        f"for instance to 'forall {n_var} : Nat, {n_var} >= {a} => …'."
                    ),
                    counterexample=below.counterexample,
                    counterexample_dict=below.counterexample_dict,
                    backend="Induction",
                )
    for condition in step.side_conditions:
        if not _follows_from_start(condition, step.var, a, mt, ctx):
            return LogicResult(
                valid=False,
                message=(
                    f"The inductive step assumes '{condition}', but the claim starts at "
                    f"{n_var} = {a}: the step has to hold for every {step.var} >= {a}, so it may only "
                    f"assume what follows from that."
                ),
                backend="Induction",
            )

    shape = "base case + inductive step" if step.span == 1 else f"{step.span} base cases + a {step.span}-step recurrence"
    # What it rested on, for the dependency audit: the base run and the step.
    ctx.induction_sources = [established_by(p_at(a + j)) for j in range(step.span)] + [
        next(h for s, h in found if s is step)
    ]
    return LogicResult(
        valid=True,
        message=f"Verified by Mathematical Induction on {n_var} from {a} ({shape}).",
        backend="Induction",
    )


@dataclass
class _InductionStep:
    """An inductive step as read from ``forall k, H => P(k + span)``."""

    var: str
    span: int
    side_conditions: list[ExprNode]


_IMPLIES_OPS = ("=>", "->", "implies", "\\implies")


def _int_node(value: int) -> ExprNode:
    return NumberNode(value=str(value)) if value >= 0 else UnaryOpNode(op="-", operand=NumberNode(value=str(-value)))


def _int_value(node: ExprNode) -> Optional[int]:
    """A literal whole number (``5``, ``-2``), or None."""
    if isinstance(node, NumberNode) and node.value.isdigit():
        return int(node.value)
    if isinstance(node, UnaryOpNode) and node.op == "-":
        inner = _int_value(node.operand)
        return -inner if inner is not None else None
    return None


def _induction_guard(formula: ExprNode, n_var: str) -> tuple[ExprNode, Optional[int]]:
    """Split ``n >= a => P(n)`` into ``(P(n), a)``; an unguarded claim gives ``(P(n), None)``."""
    if not (isinstance(formula, BinaryOpNode) and formula.op in _IMPLIES_OPS and isinstance(formula.left, RelationNode)):
        return formula, None
    guard = formula.left
    rel = canonical_rel(guard.op)
    is_n = lambda e: isinstance(e, (SymbolNode, GreekSymbolNode)) and e.name == n_var  # noqa: E731
    if is_n(guard.left) and rel in (">=", ">"):
        bound = _int_value(guard.right)
        offset = 1 if rel == ">" else 0
    elif is_n(guard.right) and rel in ("<=", "<"):
        bound = _int_value(guard.left)
        offset = 1 if rel == "<" else 0
    else:
        return formula, None
    if bound is None:
        return formula, None
    return formula.right, bound + offset


def _conjuncts(expr: ExprNode) -> list[ExprNode]:
    if isinstance(expr, BinaryOpNode) and expr.op.lower() in ("and", "\\land", "/\\"):
        return _conjuncts(expr.left) + _conjuncts(expr.right)
    return [expr]


def _induction_step(prop: ExprNode, p_n: ExprNode, n_var: str, ctx: ProofContext) -> Optional[_InductionStep]:
    """Read ``prop`` as an inductive step for P, or None if it is not one."""
    if not (
        isinstance(prop, QuantifierNode)
        and prop.quantifier == "forall"
        and isinstance(prop.formula, BinaryOpNode)
        and prop.formula.op in _IMPLIES_OPS
    ):
        return None
    k = prop.var
    k_node = SymbolNode(name=k)

    def p_shift(j: int) -> ExprNode:
        arg = k_node if j == 0 else BinaryOpNode(op="+", left=k_node, right=NumberNode(value=str(j)))
        return substitute_expr(p_n, n_var, arg)

    for span in (1, 2, 3):
        if not _exprs_match(prop.formula.right, p_shift(span), ctx):
            continue
        side: list[ExprNode] = []
        hypotheses = 0
        for conjunct in _conjuncts(prop.formula.left):
            if any(_exprs_match(conjunct, p_shift(j), ctx) for j in range(span)):
                hypotheses += 1
            else:
                side.append(conjunct)
        # A step with no hypothesis at all proves P(k + span) outright, which
        # the solver can check by itself; it is not what makes an induction.
        if hypotheses:
            return _InductionStep(var=k, span=span, side_conditions=side)
    return None


def _follows_from_start(condition: ExprNode, k: str, a: int, mt: MathType, ctx: ProofContext) -> bool:
    """Whether ``condition`` about k follows from ``k >= a`` (and k's type) alone."""
    fresh = "_ind_k"
    renamed = substitute_expr(condition, k, SymbolNode(name=fresh))
    ctx.push_scope()
    try:
        ctx.declare_variable(fresh, "Nat" if mt == MathType.Nat else "Int", is_witness=False)
        ctx.add_hypothesis(
            RelationNode(op=">=", left=SymbolNode(name=fresh), right=_int_node(a)),
            label=None,
            is_assumption=True,
        )
        # The step's own assumptions are out of scope here; what remains is
        # k >= a and the proof's standing facts.  A condition that follows from
        # those (an instance of an assumed recurrence) holds for every k >= a.
        return verify_entailment(renamed, ctx, _induction=False).valid
    finally:
        ctx.pop_scope()


def _eliminate_divisibility_witnesses(
    diff: sp.Expr,
    modulus: sp.Expr,
    ctx: ProofContext,
) -> tuple[sp.Expr, sp.Expr]:
    """Rewrite *diff* using the divisibility facts in scope.

    ``i = k (mod n)`` says ``i - k = n * t`` for some integer ``t``.  Solving
    that for a variable of the goal (``i = k + n * t``) and substituting lets
    the quotient test see that ``(i + j) - (k + l)`` is ``n * (t1 + t2)``.  Z3
    alone cannot: with a symbolic modulus the question is non-linear.  Each
    witness is a fresh integer symbol, so the rewrite only uses what the
    hypothesis actually asserts.
    """
    for index, hyp in enumerate(ctx.all_hypotheses()):
        prop = ctx.expand_user_functions(hyp.proposition) or hyp.proposition
        if not isinstance(prop, FunctionCallNode):
            continue
        fn = prop.func.lower()
        try:
            if fn in ("congruent", "cong") and len(prop.args) == 3:
                a, b, m = (ast_to_sympy(arg, ctx) for arg in prop.args)
                lhs, mod = a - b, m
            elif fn == "multipleof" and len(prop.args) == 2:
                lhs, mod = ast_to_sympy(prop.args[0], ctx), ast_to_sympy(prop.args[1], ctx)
            elif fn == "divides" and len(prop.args) == 2:
                mod, lhs = ast_to_sympy(prop.args[0], ctx), ast_to_sympy(prop.args[1], ctx)
            else:
                continue
        except AlgebraConversionError:
            continue
        if not all(s.is_integer for s in (lhs - mod).free_symbols):
            continue
        witness = sp.Symbol(f"_t{index}", integer=True)
        relation = lhs - mod * witness
        # Eliminate a variable that occurs in the goal with a unit coefficient,
        # so the substitution introduces no fractions.
        for sym in sorted(diff.free_symbols & lhs.free_symbols, key=lambda s: s.name):
            coeff = sp.diff(relation, sym)
            if coeff in (1, -1) and not coeff.free_symbols:
                solution = sp.solve(relation, sym)
                if len(solution) == 1:
                    diff = sp.expand(diff.subs(sym, solution[0]))
                    modulus = modulus.subs(sym, solution[0])
                    break
    return diff, modulus


_RESIDUE_MODULUS_LIMIT = 1000
_RESIDUE_CASES_LIMIT = 20000


def _divisibility_shape(claim: ExprNode) -> Optional[tuple[ExprNode, ExprNode]]:
    """``(P, m)`` for a claim that says m divides P, else None."""
    if not isinstance(claim, FunctionCallNode):
        return None
    fn, args = claim.func.lower(), claim.args
    if fn == "multipleof" and len(args) == 2:
        return args[0], args[1]
    if fn == "divides" and len(args) == 2:
        return args[1], args[0]
    if fn == "even" and len(args) == 1:
        return args[0], NumberNode(value="2")
    if fn == "odd" and len(args) == 1:
        return BinaryOpNode(op="-", left=args[0], right=NumberNode(value="1")), NumberNode(value="2")
    if fn in ("congruent", "cong") and len(args) == 3:
        return BinaryOpNode(op="-", left=args[0], right=args[1]), args[2]
    return None


def _try_residue_divisibility(claim: ExprNode, ctx: ProofContext) -> Optional[LogicResult]:
    """Decide "m divides P(n)" for a polynomial P over the integers and a number m.

    Nonlinear integer arithmetic is undecidable in general, which is why the
    solver gives up on `MultipleOf(n^3 - n, 6)`.  This shape is not: P(n) mod m
    depends only on n mod m, so checking the remainders 0, …, m - 1 of each
    variable decides it for every integer.  A polynomial with fractional
    coefficients (``n(n + 1)/2``) is P = Q / d with Q integral, and m divides it
    exactly when m·d divides Q, which repeats with period m·d.

    True for every remainder: valid for every integer, whatever else the proof
    assumes.  False for some remainder: a counterexample, but only when nothing
    the proof assumes mentions those variables (an `Assume Even(n)` could rule
    the remainder out); otherwise this says nothing and the solver decides.
    """
    claim = ctx.expand_user_functions(claim) or claim
    shape = _divisibility_shape(claim)
    if shape is None:
        return None
    try:
        p = sp.expand(ast_to_sympy(shape[0], ctx))
        m = sp.sympify(ast_to_sympy(shape[1], ctx))
    except Exception:
        return None
    if not (m.is_Integer and 0 < int(m) <= _RESIDUE_MODULUS_LIMIT):
        return None
    variables = sorted(p.free_symbols, key=str)
    if not variables or not all(v.is_integer for v in variables):
        return None
    try:
        poly = sp.Poly(p, *variables, domain="QQ")
    except Exception:
        return None
    denominator = functools.reduce(sp.ilcm, (sp.Rational(c).q for c in poly.coeffs()), 1)
    q = sp.Poly(poly.as_expr() * denominator, *variables, domain="ZZ")
    modulus = int(m) * int(denominator)
    if modulus > _RESIDUE_MODULUS_LIMIT or modulus ** len(variables) > _RESIDUE_CASES_LIMIT:
        return None

    for residues in itertools.product(range(modulus), repeat=len(variables)):
        if q.eval(dict(zip(variables, residues))) % modulus != 0:
            names = {str(v) for v in variables}
            constrained = any(
                collect_free_symbols(h.proposition) & names for h in ctx.all_hypotheses()
            )
            if constrained:
                return None
            at = ", ".join(f"{v}={r}" for v, r in zip(variables, residues))
            value = p.subs(dict(zip(variables, residues)))
            return LogicResult(
                valid=False,
                message=(
                    f"Claim '{claim}' is false: at {at}, {shape[0]} is {value}, which is not a "
                    f"multiple of {int(m)}."
                ),
                counterexample=at,
                counterexample_dict={str(v): str(r) for v, r in zip(variables, residues)},
                backend="Residues",
            )
    over = " and ".join(str(v) for v in variables)
    return LogicResult(
        valid=True,
        message=(
            f"Verified for every integer {over}: {int(m)} divides {shape[0]} at each of the "
            f"{modulus ** len(variables)} remainder{'s' if modulus ** len(variables) != 1 else ''} "
            f"mod {modulus}, and its remainder depends only on those."
        ),
        backend="Residues",
    )


def _try_common_divisor(claim: ExprNode, ctx: ProofContext, timeout_ms: int) -> Optional[LogicResult]:
    """Prove ``not Coprime(a, b)`` by finding a d > 1 that divides both.

    Coprime is a statement about *every* common divisor, so its negation asks
    the solver to invent one, which it rarely does among a proof's other facts
    (the √2 proof stalled there with Even(p) and Even(q) in hand).  A student
    names it ("2 divides both"); so does this: the small numbers, then any
    number the proof mentions.
    """
    if not (
        isinstance(claim, UnaryOpNode)
        and claim.op in ("not", "\\neg", "~")
        and isinstance(claim.operand, FunctionCallNode)
        and claim.operand.func.lower() == "coprime"
        and len(claim.operand.args) == 2
    ):
        return None
    a, b = claim.operand.args
    candidates = list(range(2, 13))
    for h in ctx.all_hypotheses():
        for value in re.findall(r"(?<![\w.])(\d+)(?![\w.])", str(h.proposition)):
            if 12 < int(value) <= 1000 and int(value) not in candidates:
                candidates.append(int(value))
    for d in candidates:
        both = BinaryOpNode(
            op="and",
            left=FunctionCallNode(func="Divides", args=[NumberNode(value=str(d)), a]),
            right=FunctionCallNode(func="Divides", args=[NumberNode(value=str(d)), b]),
        )
        if verify_entailment(both, ctx, timeout_ms=min(timeout_ms, 800), _induction=False).valid:
            return LogicResult(
                valid=True,
                message=f"Verified: {d} divides both {a} and {b}, so they are not coprime.",
                backend="Z3",
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
                    # The modulus too: with n = d * n1, `n1 * k` over `n` only
                    # reduces once both are written in d.
                    diff = diff.subs(sl, sr)
                    s_m = s_m.subs(sl, sr)
                except Exception:
                    continue
            diff, s_m = _eliminate_divisibility_witnesses(diff, s_m, ctx)
            ratio = sp.simplify(diff / s_m)
            # `1 / 0` is SymPy's zoo, whose denominator is 1: without this guard
            # `a + 1 = a (mod 0)` passed as an integer quotient.
            if (
                not ratio.has(sp.zoo, sp.oo, -sp.oo, sp.nan)
                and sp.denom(sp.together(ratio)) == 1
                and all(s.is_integer for s in ratio.free_symbols)
            ):
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
        var_type = _quantifier_type(target.var_type, ctx, MathType.Int)
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


def _explain_solver_limits(message: str, claim: ExprNode, ctx: ProofContext) -> str:
    """Say why a failed SMT query may not mean the claim is actually false.

    Two things make Z3's answer misleading on its own: a name no backend
    interprets (so the solver reasons about an arbitrary function), and a
    function SymPy settles but Z3 has no theory for.  Either way the
    counterexample that comes back describes the solver's model, not the
    student's mathematics.
    """
    notes = list(unknown_call_hints(claim, ctx))
    opaque = sorted(
        {name for name in called_function_names(claim, ctx) if name.lower() in _SYMPY_ONLY_CALLS}
    )
    if opaque:
        names = ", ".join(f"`{name}`" for name in opaque)
        verb = "have" if len(opaque) > 1 else "has"
        pronoun = "their" if len(opaque) > 1 else "its"
        notes.append(
            f"{names} {verb} no SMT theory: the solver knows only {pronoun} range "
            f"(|sin| <= 1, exp > 0, ...), so the counterexample above may not be a real one."
        )
    for note in dict.fromkeys(notes):
        message = f"{message} {note}"
    return message


@traced("Z3", "entails", lambda claim, ctx, witness=None, **_: f"{claim} [witness: {witness}]" if witness is not None else str(claim))
def verify_entailment(
    claim: ExprNode,
    ctx: ProofContext,
    witness: Optional[ExprNode] = None,
    timeout_ms: int = 2500,
    _induction: bool = True,
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

    # 0. Check Mathematical Induction schema for universal claims.  An
    # induction the schema refuses may still hold for another reason (a claim
    # over the integers the solver proves outright), so the claim gets the
    # usual checks; if those fail too, the student hears why the induction did
    # not prove it, not only that the solver could not.
    ind_res = verify_induction_schema(claim, ctx) if _induction else None
    if ind_res is not None and ind_res.valid:
        return ind_res
    if ind_res is not None:
        fallback = verify_entailment(claim, ctx, witness=witness, timeout_ms=timeout_ms, _induction=False)
        if fallback.valid:
            return fallback
        return LogicResult(
            valid=False,
            message=ind_res.message,
            counterexample=ind_res.counterexample or fallback.counterexample,
            counterexample_dict=ind_res.counterexample_dict or fallback.counterexample_dict,
            backend="Induction",
        )

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
        if alg_res.decisive:
            return LogicResult(valid=False, message=alg_res.message, backend="SymPy")

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

    # 2b. A polynomial's divisibility by a number is decided by its remainders.
    # With show_working on, the student's own argument is tried first (below):
    # the remainders only settle what that argument did not.
    residue_res = _try_residue_divisibility(claim, ctx)
    if residue_res is not None and (not ctx.show_working or not residue_res.valid):
        return residue_res

    # 2c. "a and b are not coprime": find the common divisor, as a student would.
    common_res = _try_common_divisor(claim, ctx, timeout_ms)
    if common_res is not None:
        return common_res

    # 3. Query Z3 SMT solver
    solver = new_solver(timeout_ms)
    _populate_solver_context(solver, ctx)

    extra: list[z3.ExprRef] = []
    try:
        z3_claim = ast_to_z3(claim, ctx, extra_constraints=extra)
    except LogicConversionError as exc:
        if residue_res is not None and residue_res.valid:
            return residue_res
        return LogicResult(valid=False, message=str(exc), backend="Z3")

    for c in extra:
        solver.add(c)
    solver.add(z3.Not(z3_claim))
    result = check_solver(solver)

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
            message=_explain_solver_limits(
                f"Claim '{claim}' does not follow from current hypotheses. {ce_msg}",
                claim,
                ctx,
            ),
            counterexample=ce_str or None,
            counterexample_dict=ce_dict or None,
            backend="Z3",
        )

    # Show your working: the student's argument did not settle it, the
    # remainders do; the checker reports that as a shortcut, not a proof.
    if residue_res is not None and residue_res.valid:
        return residue_res
    return LogicResult(
        valid=False,
        message=_explain_solver_limits(f"Solver inconclusive (unknown) for '{claim}'.", claim, ctx),
        backend="Z3",
    )


def _evaluate_constant_relation(condition: ExprNode, ctx: ProofContext) -> Optional[bool]:
    """Evaluate a relation between closed terms, e.g. ``gcd(8, 2) != 0``.

    The solver sees ``gcd`` as an arbitrary function and cannot rule out zero;
    SymPy can simply compute it.
    """
    if not isinstance(condition, RelationNode):
        return None
    try:
        left = ast_to_sympy(condition.left, ctx)
        right = ast_to_sympy(condition.right, ctx)
    except (AlgebraConversionError, TypeError, ValueError):
        return None
    if not (isinstance(left, sp.Expr) and isinstance(right, sp.Expr)):
        return None
    if left.free_symbols or right.free_symbols or not (left.is_number and right.is_number):
        return None
    rel = canonical_rel(condition.op)
    builders = {"=": sp.Eq, "!=": sp.Ne, "<": sp.Lt, "<=": sp.Le, ">": sp.Gt, ">=": sp.Ge}
    if rel not in builders:
        return None
    try:
        result = builders[rel](left, right)
    except TypeError:
        return None
    if result is sp.true:
        return True
    if result is sp.false:
        return False
    return None


@traced("Z3", "domain", lambda obligation, ctx, **_: str(obligation.reason))
def check_domain_obligation(
    obligation: DomainObligation,
    ctx: ProofContext,
    timeout_ms: int = 2000,
) -> LogicResult:
    """Check whether *obligation* (e.g. ``x - 2 != 0``) is guaranteed by *ctx*."""
    constant = _evaluate_constant_relation(obligation.condition, ctx)
    if constant is True:
        obligation.discharged = True
        return LogicResult(
            valid=True,
            message=f"Domain obligation discharged: {obligation.reason}",
            backend="SymPy (Domain)",
        )
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


@traced("Z3", "cases", lambda conds, ctx, **_: " or ".join(str(c) for c in conds))
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



# ---------------------------------------------------------------------------
# Deciding SymPy side conditions against the proof context
# ---------------------------------------------------------------------------


def _sympy_to_z3(expr: sp.Basic, ctx: ProofContext) -> z3.ExprRef:
    """Translate the small arithmetic/boolean SymPy fragment found in side conditions."""
    if expr is sp.true:
        return z3.BoolVal(True)
    if expr is sp.false:
        return z3.BoolVal(False)
    if isinstance(expr, sp.Symbol):
        vinfo = ctx.get_var(expr.name)
        return _make_z3_var(expr.name, vinfo.math_type if vinfo else MathType.Real)
    if isinstance(expr, sp.Integer):
        return z3.IntVal(int(expr))
    if isinstance(expr, sp.Rational):
        return z3.RealVal(f"{expr.p}/{expr.q}")
    args = [_sympy_to_z3(a, ctx) for a in expr.args]
    if isinstance(expr, sp.Add):
        return z3.Sum(args)
    if isinstance(expr, sp.Mul):
        return z3.Product(args)
    if isinstance(expr, sp.Pow) and isinstance(expr.exp, sp.Integer) and 0 < abs(int(expr.exp)) <= 6:
        acc = args[0]
        for _ in range(abs(int(expr.exp)) - 1):
            acc = acc * args[0]  # type: ignore[operator]
        if expr.exp > 0:
            return acc
        return 1 / (z3.ToReal(acc) if z3.is_int(acc) else acc)  # type: ignore[operator]
    if isinstance(expr, sp.Abs):
        return z3.If(args[0] >= 0, args[0], -args[0])  # type: ignore[operator]
    relations = {
        sp.Eq: lambda a, b: a == b,
        sp.Ne: lambda a, b: a != b,
        sp.Lt: lambda a, b: a < b,
        sp.Le: lambda a, b: a <= b,
        sp.Gt: lambda a, b: a > b,
        sp.Ge: lambda a, b: a >= b,
    }
    for cls, build in relations.items():
        if isinstance(expr, cls):
            return build(*args)
    if isinstance(expr, sp.And):
        return z3.And(args)
    if isinstance(expr, sp.Or):
        return z3.Or(args)
    if isinstance(expr, sp.Not):
        return z3.Not(args[0])
    raise LogicConversionError(f"Cannot translate {expr} for the solver.")


def _decide(condition: sp.Basic, ctx: ProofContext, timeout_ms: int = 1500) -> Optional[bool]:
    """True/False if the proof's facts settle *condition*, else None."""
    try:
        z3_cond = _sympy_to_z3(condition, ctx)
    except (LogicConversionError, TypeError, ValueError, z3.Z3Exception):
        return None
    for goal, answer in ((z3_cond, True), (z3.Not(z3_cond), False)):
        solver = new_solver(timeout_ms)
        _populate_solver_context(solver, ctx)
        solver.add(z3.Not(goal))
        if check_solver(solver) == z3.unsat:
            return answer
    return None


def refine_with_context(value: sp.Expr, ctx: ProofContext) -> sp.Expr:
    """Pick the ``Piecewise`` branch / ``sign`` that the proof's hypotheses force.

    A branch is taken only when its condition is *entailed* (every earlier
    branch having been refuted), so an undecided case split is left as it is
    and the step simply fails to verify.
    """

    def pick_branch(pw: sp.Piecewise) -> sp.Expr:
        for branch, cond in pw.args:
            decided = True if cond is sp.true else _decide(cond, ctx)
            if decided is True:
                return branch
            if decided is None:
                return pw
        return pw

    def pick_sign(sign: sp.Expr) -> sp.Expr:
        arg = sign.args[0]
        if isinstance(arg, sp.log):
            # For u > 0, sign(log u) is the sign of u - 1.
            arg = arg.args[0] - 1
        for cond, value in ((sp.Gt(arg, 0), 1), (sp.Lt(arg, 0), -1), (sp.Eq(arg, 0), 0)):
            if cond is sp.true or _decide(cond, ctx) is True:
                return sp.Integer(value)
        return sign

    refined = value.replace(lambda n: isinstance(n, sp.Piecewise), pick_branch)
    refined = refined.replace(lambda n: isinstance(n, sp.sign), pick_sign)
    return refined
