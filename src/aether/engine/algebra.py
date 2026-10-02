"""SymPy algebraic verification engine, domain obligation extractor, and counterexample finder."""

from __future__ import annotations

from dataclasses import dataclass, fields
import difflib
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
    #: A failure that no other backend can overturn (see ``_verify_group_identity``).
    decisive: bool = False


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
        elif (
            isinstance(node, FunctionCallNode)
            and node.func.lower() == "sum"
            and len(node.args) == 4
            and isinstance(node.args[0], (SymbolNode, GreekSymbolNode))
        ):
            # `sum(k, 1, oo, 1/k^2)` divides by k^2 only for the k it sums over:
            # an obligation on the index holds over its range, not for every k.
            idx, lower, upper, body = node.args
            _walk(lower, dest)
            _walk(upper, dest)
            body_obs: list[DomainObligation] = []
            _walk(body, body_obs)
            for ob in body_obs:
                if idx.name in collect_free_symbols(ob.condition):
                    in_range = BinaryOpNode(
                        op="and",
                        left=RelationNode(op=">=", left=idx, right=lower),
                        right=RelationNode(op="<=", left=idx, right=upper),
                    )
                    ob.condition = QuantifierNode(
                        quantifier="forall",
                        var=idx.name,
                        var_type="Int",
                        formula=BinaryOpNode(op="=>", left=in_range, right=ob.condition),
                    )
                dest.append(ob)
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
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "coth": sp.coth,
    "sech": sp.sech,
    "csch": sp.csch,
    "sec": sp.sec,
    "csc": sp.csc,
    "cot": sp.cot,
    "asin": sp.asin,
    "arcsin": sp.asin,
    "acos": sp.acos,
    "arccos": sp.acos,
    "atan": sp.atan,
    "arctan": sp.atan,
    "atan2": sp.atan2,
    "floor": sp.floor,
    "ceil": sp.ceiling,
    "ceiling": sp.ceiling,
    "sign": sp.sign,
    "sgn": sp.sign,
    "binomial": sp.binomial,
    "log10": lambda x: sp.log(x, 10),
    "log2": lambda x: sp.log(x, 2),
    "gamma": sp.gamma,
    "erf": sp.erf,
}

# `sympy.gcd` / `sympy.lcm` are *polynomial* gcds: `gcd(n, k)` on two integer
# symbols comes back as 1 and `lcm(n, k)` as `n*k`, which would "prove"
# `gcd(n, k) = 1` for every n and k.  They are evaluated only on literals and
# otherwise stay uninterpreted.
_INTEGER_ONLY_FUNCS = {"gcd": sp.igcd, "lcm": sp.ilcm}

# Every ``f(...)`` name some backend gives a meaning to, in lower case.  This is
# _SYMPY_FUNCS plus the call names special-cased in ``ast_to_sympy`` (matrix ops,
# calculus, complex parts) and the prelude predicates handled in ``logic``.  It
# exists so a call the engine does *not* understand can be reported as such
# rather than silently becoming an uninterpreted SymPy function.
_KNOWN_CALLABLES: frozenset[str] = frozenset(
    set(_SYMPY_FUNCS)
    | {
        "sum", "diff", "integrate", "lim", "gcd", "lcm",
        "conj", "conjugate", "re", "realpart", "im", "imagpart",
        "det", "determinant", "tr", "trace", "transpose", "dot", "norm",
        "inv", "inverse",
        "even", "odd", "multipleof", "divides", "positive", "nonnegative",
        "congruent", "cauchyriemann", "cauchy_riemann", "orthogonal",
    }
)

# Mathematical constants.  A bare ``pi`` (or ``\pi``) and ``e`` name the
# numbers, not free variables: ``sin(\pi) = 0`` used to be reported as
# "Counterexample at pi=3: LHS = sin(3)".  A name that has been declared, or
# that a structure assumption binds (``e`` is the identity in
# ``Assume Group(G, op, e, inv)``), stays a variable.
_SYMPY_CONSTANTS: dict[str, sp.Expr] = {"pi": sp.pi, "e": sp.E, "oo": sp.oo}


def _constant_value(name: str, ctx: ProofContext) -> Optional[sp.Expr]:
    """Return the mathematical value of *name*, if it names a constant here."""
    if name not in _SYMPY_CONSTANTS:
        return None
    if ctx.get_var(name) is not None or name in ctx.structure_names():
        return None
    return _SYMPY_CONSTANTS[name]


# Argument counts for the prelude calls in ``_SYMPY_FUNCS``, as
# ``(min, max)`` with ``None`` meaning "no upper bound".  SymPy is inconsistent
# about arity: ``Abs(x, x)`` raises TypeError, which used to escape
# ``check_source`` as a raw TypeError (a 500 from the API), while ``log(x, 2)``
# silently turns into a base-2 logarithm -- so ``ln(x, 2)`` quietly stopped
# meaning the natural log.  Checking here turns both into a plain INVALID step.
_SYMPY_FUNC_ARITY: dict[str, tuple[int, Optional[int]]] = {
    "sqrt": (1, 1),
    "abs": (1, 1),
    "sin": (1, 1),
    "cos": (1, 1),
    "tan": (1, 1),
    "exp": (1, 1),
    "ln": (1, 1),  # natural log only: `ln(x, 2)` is not base-2
    "log": (1, 2),  # natural log, or an explicit base
    "factorial": (1, 1),
    "sinh": (1, 1),
    "cosh": (1, 1),
    "tanh": (1, 1),
    "coth": (1, 1),
    "sech": (1, 1),
    "csch": (1, 1),
    "sec": (1, 1),
    "csc": (1, 1),
    "cot": (1, 1),
    "asin": (1, 1),
    "arcsin": (1, 1),
    "acos": (1, 1),
    "arccos": (1, 1),
    "atan": (1, 1),
    "arctan": (1, 1),
    "atan2": (2, 2),
    "floor": (1, 1),
    "ceil": (1, 1),
    "ceiling": (1, 1),
    "sign": (1, 1),
    "sgn": (1, 1),
    "binomial": (2, 2),
    "log10": (1, 1),
    "log2": (1, 1),
    "gamma": (1, 1),
    "erf": (1, 1),
    "max": (1, None),
    "min": (1, None),
}

# Calls the algebraic backend interprets itself, rather than via ``_SYMPY_FUNCS``.
# The prelude *predicates* are deliberately absent: ``Even(n)`` inside an
# algebraic equality is meant to stay opaque there.
_ALGEBRA_CALLS: frozenset[str] = frozenset(
    {
        "sum", "diff", "conj", "conjugate", "re", "realpart", "im", "imagpart",
        "det", "determinant", "tr", "trace", "transpose", "dot", "norm",
        "inv", "inverse",
        # Rewritten into nodes by the transformer when the arity fits, so a call
        # still carrying one of these names is an arity the grammar rejected.
        "integrate", "integral", "lim", "limit",
    }
)


def _arity_error(name: str, count: int, arity: tuple[int, Optional[int]]) -> str:
    """Explain a wrong argument count for the call *name*."""
    low, high = arity
    if high is None:
        expected = f"at least {low}"
    elif low == high:
        expected = str(low)
    else:
        expected = f"{low} or {high}"
    return f"`{name}` takes {expected} argument(s), but got {count}."


def _walk_expr(node: ExprNode) -> list[ExprNode]:
    """Return *node* and every :class:`ExprNode` nested inside it, depth-first."""
    found: list[ExprNode] = []
    if not isinstance(node, ExprNode):
        return found
    found.append(node)
    for field_info in fields(node):
        value = getattr(node, field_info.name)
        if isinstance(value, ExprNode):
            found.extend(_walk_expr(value))
        elif isinstance(value, list):
            for item in value:
                found.extend(_walk_expr(item))
    return found


# Standard functions the engine does not implement.  They are not misspellings,
# so offering a different function for them is worse than saying nothing:
# string distance alone suggests `cot` -> `dot`, `asin` -> `sin` and
# `sinh` -> `sin`, each of which is a *different* function.  Calling them out
# explicitly keeps the did-you-mean suggestions for actual typos.
_UNSUPPORTED_CALLS: frozenset[str] = frozenset(
    {
        "arcsec", "arccsc", "arccot", "trunc",
        "beta", "zeta", "digamma", "exp2",
    }
)


def called_function_names(expr: ExprNode, ctx: ProofContext) -> list[str]:
    """The name of every ``f`` in an ``f(...)`` inside *expr*, user calls inlined."""
    expanded = ctx.expand_user_functions(expr) or expr
    return [node.func for node in _walk_expr(expanded) if isinstance(node, FunctionCallNode)]


def unknown_call_hints(expr: ExprNode, ctx: ProofContext) -> list[str]:
    """Explain any ``f(...)`` in *expr* that no backend gives a meaning to.

    Unrecognised calls quietly become uninterpreted functions, which turns a
    typo (``fact(5)`` for ``factorial(5)``) into a step that reports a maths
    error instead of a name error.  These hints are appended to a step's
    failure message, so they only ever explain a rejection that already
    happened.
    """
    expanded = ctx.expand_user_functions(expr) or expr
    declared = {name.lower() for name in ctx.all_functions()}
    # Operations a structure assumption names (`op`, `inv`, `star`) are meant
    # to be abstract; they are not typos.
    declared |= {name.lower() for name in ctx.structure_names()}
    for g in ctx.group_signatures().values():
        declared.add(f"{g.op}_pow".lower())
    hints: list[str] = []
    for node in _walk_expr(expanded):
        if not isinstance(node, FunctionCallNode):
            continue
        name = node.func.lower()
        if name in _KNOWN_CALLABLES or name in declared:
            continue
        if name in _UNSUPPORTED_CALLS:
            hints.append(
                f"`{node.func}` is not a function the engine implements; it is treated as "
                f"an uninterpreted symbol."
            )
            continue
        close = difflib.get_close_matches(name, sorted(_KNOWN_CALLABLES), n=1, cutoff=0.6)
        if close:
            hints.append(f"`{node.func}` is not a known function; did you mean `{close[0]}`?")
        else:
            hints.append(
                f"`{node.func}` is not a known function, so it is treated as uninterpreted."
            )
    return hints


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
        if s_target in (sp.oo, -sp.oo) and expr.direction != "+-":
            raise AlgebraConversionError(f"A limit at {s_target} has no side to approach from in {expr}.")
        # At +-oo there is only one side; SymPy wants it spelled as the default.
        direction = "-" if s_target == sp.oo else "+" if s_target == -sp.oo else expr.direction
        try:
            value = sp.limit(s_body, var_sym, s_target, dir=direction)
        except ValueError as exc:
            # SymPy reports a two-sided limit whose one-sided limits differ this way.
            raise AlgebraConversionError(f"{expr} does not exist: {exc}") from exc
        except (NotImplementedError, TypeError) as exc:
            raise AlgebraConversionError(f"SymPy could not evaluate {expr}: {exc}") from exc
        if value.has(sp.AccumBounds):
            raise AlgebraConversionError(
                f"{expr} does not exist: the expression keeps oscillating within {value}."
            )
        if value is sp.zoo:
            raise AlgebraConversionError(
                f"{expr} does not exist: it tends to +oo from one side and -oo from the other."
            )
        if isinstance(value, sp.Limit):
            raise AlgebraConversionError(f"SymPy could not evaluate {expr}.")
        return _refine_with_context(value, ctx)

    if isinstance(expr, SymbolNode):
        if expr.name in bound_symbols:
            return bound_symbols[expr.name]
        # Treat 'i' or 'I' as imaginary unit unless explicitly declared as a variable
        if expr.name in ("i", "I") and ctx.get_var(expr.name) is None:
            return sp.I
        constant = _constant_value(expr.name, ctx)
        if constant is not None:
            return constant
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
        constant = _constant_value(expr.name, ctx)
        if constant is not None:
            return constant
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
            s_arg = ast_to_sympy(expr.args[0], ctx, bound_symbols)
            # A square matrix has a computable inverse.  Anything else (e.g. the
            # ``inv(a)`` of an abstract group written over the reals) stays
            # uninterpreted, which is what the group templates rely on.
            if hasattr(s_arg, "inv") and getattr(s_arg, "is_square", False):
                try:
                    return s_arg.inv()
                except Exception:
                    pass
            return sp.Function("inv")(s_arg)
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
            return _refine_with_context(sp.Sum(s_body, (idx_sym, s_lower, s_upper)).doit(), ctx)

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

        if fn_name in _INTEGER_ONLY_FUNCS:
            args = [ast_to_sympy(a, ctx, bound_symbols) for a in expr.args]
            if len(args) != 2:
                raise AlgebraConversionError(_arity_error(expr.func, len(args), (2, 2)))
            if all(isinstance(a, sp.Integer) for a in args):
                return sp.Integer(_INTEGER_ONLY_FUNCS[fn_name](int(args[0]), int(args[1])))
            return sp.Function(fn_name)(*args)
        if fn_name in _SYMPY_FUNCS:
            args = [ast_to_sympy(a, ctx, bound_symbols) for a in expr.args]
            arity = _SYMPY_FUNC_ARITY.get(fn_name)
            if arity is not None:
                low, high = arity
                if len(args) < low or (high is not None and len(args) > high):
                    raise AlgebraConversionError(_arity_error(expr.func, len(args), arity))
            try:
                return _SYMPY_FUNCS[fn_name](*args)
            except TypeError as exc:
                raise AlgebraConversionError(
                    f"`{expr.func}` cannot be applied to {len(args)} argument(s)."
                ) from exc
        if fn_name in _ALGEBRA_CALLS:
            # A name this backend claims to understand, reached with a shape it
            # does not handle (e.g. `det(A, A)` or `sum(k, 1, n)`).  Saying so
            # beats quietly making it an uninterpreted function, which reported
            # a maths error where the real problem was the argument list.
            raise AlgebraConversionError(
                f"`{expr.func}` was called with {len(expr.args)} argument(s), which is not a "
                f"shape the algebraic backend recognises."
            )
        # Uninterpreted mathematical function
        sym_fn = sp.Function(expr.func)
        args = [ast_to_sympy(a, ctx, bound_symbols) for a in expr.args]
        return sym_fn(*args)

    raise AlgebraConversionError(f"Cannot convert {type(expr).__name__} to SymPy expression.")


def _refine_with_context(value: sp.Expr, ctx: ProofContext) -> sp.Expr:
    """Settle the case splits SymPy leaves in a closed form, using the proof's facts.

    Summing a geometric series gives ``Piecewise((1/(1 - r), Abs(r) < 1), ...)``
    and a limit with a parameter gives ``exp(oo*sign(log(rho)))``; neither can
    be compared with the student's answer until the hypotheses (``|r| < 1``,
    ``0 < rho < 1``) pick a branch.
    """
    if not isinstance(value, sp.Basic) or not value.has(sp.Piecewise, sp.sign):
        return value
    from aether.engine.logic import refine_with_context  # logic imports this module

    return refine_with_context(value, ctx)


def _infinite_or_undefined(value: sp.Expr) -> bool:
    return value.has(sp.zoo, sp.oo, -sp.oo, sp.nan)


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


class _NotAGroupWord(Exception):
    """Raised when an expression is not built from one group's op / inv / identity."""


def _group_word(expr: ExprNode, group, ctx: ProofContext) -> sp.Expr:
    """*expr* as a word in the free (abelian) group on its symbols.

    Group elements become non-commuting SymPy symbols (commuting ones for an
    ``AbelianGroup``), ``op`` multiplication, ``inv`` the inverse and the
    identity 1.  SymPy cancels ``a * a**-1`` and merges powers but never swaps
    two factors, so two words that come out equal are equal in the free group
    -- and therefore in *every* group, whatever the elements are.
    """
    if isinstance(expr, (SymbolNode, GreekSymbolNode)):
        if expr.name == group.identity and ctx.get_var(expr.name) is None:
            return sp.Integer(1)
        return sp.Symbol(expr.name, commutative=group.abelian)
    if isinstance(expr, FunctionCallNode) and expr.func == group.op and len(expr.args) == 2:
        return _group_word(expr.args[0], group, ctx) * _group_word(expr.args[1], group, ctx)
    if isinstance(expr, FunctionCallNode) and expr.func == group.inverse and len(expr.args) == 1:
        return _invert_word(_group_word(expr.args[0], group, ctx))
    raise _NotAGroupWord()


def _invert_word(word: sp.Expr) -> sp.Expr:
    """``(a b)^-1 = b^-1 a^-1``, which SymPy leaves as ``(a*b)**(-1)``."""
    if isinstance(word, sp.Mul):
        return sp.Mul(*[_invert_word(f) for f in reversed(word.args)])
    if isinstance(word, sp.Pow):
        return word.base ** (-word.exp)
    return word ** -1


def _only_structure_facts(ctx: ProofContext) -> bool:
    """True when every fact in scope is a structure assumption or a carrier membership.

    Then the free group is itself a model of everything assumed, so two words
    that differ there are a genuine counterexample and asking the solver --
    which can search for a non-abelian model for minutes -- adds nothing.
    """
    carriers = ctx.carrier_names()
    for hyp in ctx.all_hypotheses():
        prop = hyp.proposition
        if isinstance(prop, FunctionCallNode) and prop.func.lower() in ctx.STRUCTURE_PROPOSITIONS:
            continue
        if (
            isinstance(prop, RelationNode)
            and canonical_rel(prop.op) == "in"
            and isinstance(prop.right, (SymbolNode, GreekSymbolNode))
            and prop.right.name in carriers
        ):
            continue
        return False
    return True


def _verify_group_identity(lhs: ExprNode, rhs: ExprNode, ctx: ProofContext) -> Optional[AlgebraResult]:
    """Settle ``lhs = rhs`` when both sides are words in a group's operations.

    Returns a *valid* result for an identity, an *invalid* one (with the two
    reduced words) for words that differ, and None when the sides are not
    words.  An invalid result is only a diagnosis: hypotheses such as
    commutativity of particular elements can still make the step true, so the
    caller goes on to the solver.
    """
    groups = ctx.group_signatures()
    if not groups:
        return None
    left = ctx.expand_user_functions(lhs) or lhs
    right = ctx.expand_user_functions(rhs) or rhs
    for group in groups.values():
        try:
            w_left = _group_word(left, group, ctx)
            w_right = _group_word(right, group, ctx)
        except _NotAGroupWord:
            continue
        if w_left == w_right or sp.expand(w_left - w_right) == 0:
            kind = "abelian group" if group.abelian else "group"
            return AlgebraResult(
                valid=True,
                message=(
                    f"Verified as an identity in every {kind} ({lhs} = {rhs}): "
                    f"both sides reduce to the word {w_left}."
                ),
            )
        kind = "abelian group" if group.abelian else "group"
        return AlgebraResult(
            valid=False,
            decisive=_only_structure_facts(ctx),
            message=(
                f"{lhs} = {rhs} is not an identity in every {kind}: the two sides reduce to "
                f"the different words {w_left} and {w_right}, and nothing in scope relates them."
            ),
        )
    return None


def verify_algebraic_equality(
    lhs: ExprNode,
    rhs: ExprNode,
    ctx: ProofContext,
) -> AlgebraResult:
    """Verify whether ``lhs = rhs`` holds by pure algebra or context equality substitution."""
    word_result = _verify_group_identity(lhs, rhs, ctx)
    if word_result is not None and word_result.valid:
        return word_result
    try:
        s_lhs = ast_to_sympy(lhs, ctx)
        s_rhs = ast_to_sympy(rhs, ctx)
    except AlgebraConversionError as exc:
        return AlgebraResult(valid=False, message=str(exc))

    if s_lhs.has(sp.zoo, sp.nan) or s_rhs.has(sp.zoo, sp.nan):
        return AlgebraResult(
            valid=False,
            message=f"Undefined mathematical expression (division by zero or indeterminate form) in {lhs} = {rhs}.",
        )
    if _infinite_or_undefined(s_lhs) or _infinite_or_undefined(s_rhs):
        # Extended-real arithmetic: oo is not a number, so `lhs - rhs` would be
        # the indeterminate oo - oo.  The two sides must agree outright.
        if s_lhs == s_rhs or sp.simplify(s_lhs) == sp.simplify(s_rhs):
            return AlgebraResult(valid=True, message=f"Verified in the extended reals ({lhs} = {rhs}).")
        return AlgebraResult(
            valid=False,
            message=f"In the extended reals {lhs} is {s_lhs}, not {s_rhs}.",
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
    if word_result is not None:
        # Plugging numbers into an abstract group operation proves nothing.
        return word_result
    ce_str, ce_dict = find_counterexample_info(lhs, rhs, ctx)
    try:
        diff_expr = sp.simplify(s_lhs_sub - s_rhs_sub)
    except Exception:
        diff_expr = f"{s_lhs_sub} != {s_rhs_sub}"
    msg = f"Algebraic step failed: ({lhs}) - ({rhs}) simplifies to {diff_expr} != 0."
    if ce_str:
        msg = f"{msg} {ce_str}"
    for hint in dict.fromkeys(unknown_call_hints(lhs, ctx) + unknown_call_hints(rhs, ctx)):
        msg = f"{msg} {hint}"
    return AlgebraResult(
        valid=False,
        message=msg,
        counterexample=ce_str,
        counterexample_dict=ce_dict,
    )
