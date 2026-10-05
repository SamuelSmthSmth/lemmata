"""Proof state, scope stack, variable tracking, and chain monotonicity for Aether."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Optional

from aether.core.ast import (
    ExprNode,
    SymbolNode,
    GreekSymbolNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    RelationNode,
    QuantifierNode,
    RawMathNode,
    IntegralNode,
    LimitNode,
    NumberNode,
    MatrixNode,
    VectorNode,
)
from aether.core.types import MathType, normalize_type_name, split_function_type


class ContextError(Exception):
    """Base error for proof context violations."""


class VariableCaptureError(ContextError):
    """Raised when a fresh variable (e.g. via Obtain or re-declaration) shadows an existing symbol."""


class MonotonicityError(ContextError):
    """Raised when a chained inequality reverses direction (e.g. mixing <= and >=)."""


class ChainError(ContextError):
    """Raised when a chained step or deduction has no previous expression to chain from."""


class GeneralizationError(ContextError):
    """Raised when universally generalizing a variable constrained by an active assumption."""


_REL_CANONICAL: dict[str, str] = {
    "=": "=",
    "!=": "!=",
    "/=": "!=",
    "\\neq": "!=",
    "<": "<",
    "<=": "<=",
    "\\le": "<=",
    "\\leq": "<=",
    ">": ">",
    ">=": ">=",
    "\\ge": ">=",
    "\\geq": ">=",
    "\\equiv": "=",
    "in": "in",
    "\\in": "in",
}


def canonical_rel(op: str) -> str:
    """Normalize relation operators (e.g. \\leq -> <=, \\neq -> !=)."""
    return _REL_CANONICAL.get(op.strip(), op.strip())


def combine_chain_relations(rel1: str, rel2: str) -> str:
    """Combine two consecutive relations in an equational/inequality chain.

    Raises ``MonotonicityError`` if directions conflict (e.g. ``<=`` followed by ``>=``).
    """
    r1 = canonical_rel(rel1)
    r2 = canonical_rel(rel2)

    if r1 == "" or r2 == "":
        return r2 or r1

    if r1 == "=":
        return r2
    if r2 == "=":
        return r1

    less_ops = {"<", "<="}
    greater_ops = {">", ">="}

    if r1 in less_ops and r2 in less_ops:
        return "<" if ("<" in (r1, r2)) else "<="

    if r1 in greater_ops and r2 in greater_ops:
        return ">" if (">" in (r1, r2)) else ">="

    raise MonotonicityError(
        f"Strict monotonicity violation in chain: cannot combine '{r1}' with '{r2}' "
        f"(inequality directions conflict)."
    )


def binding_call(expr: FunctionCallNode) -> Optional[tuple[str, list[ExprNode], list[ExprNode]]]:
    """The variable a call binds, if it binds one: ``(index, bound_args, free_args)``.

    ``sum(r, 1, n, r^2)`` binds r in its body (and r means nothing outside it),
    as do a definite ``integrate(f, x, a, b)`` and ``lim(f, x, a)``.  Treating
    that variable as free made the solver pick a value for it and report it as
    a counterexample ("r=0").  ``diff(f, x)`` binds nothing: the derivative is
    a function of x.
    """
    fn = expr.func.lower()
    args = expr.args
    if fn == "sum" and len(args) == 4 and isinstance(args[0], (SymbolNode, GreekSymbolNode)):
        return args[0].name, [args[3]], [args[1], args[2]]
    if fn == "integrate" and len(args) == 4 and isinstance(args[1], (SymbolNode, GreekSymbolNode)):
        return args[1].name, [args[0]], [args[2], args[3]]
    if fn == "lim" and len(args) >= 3 and isinstance(args[1], (SymbolNode, GreekSymbolNode)):
        return args[1].name, [args[0]], list(args[2:])
    return None


def collect_free_symbols(expr: ExprNode, bound: Optional[set[str]] = None) -> set[str]:
    """Return the set of free variable/symbol names appearing in *expr*."""
    if bound is None:
        bound = set()

    if isinstance(expr, SymbolNode):
        return {expr.name} if expr.name not in bound and expr.name != "<prev>" else set()
    if isinstance(expr, GreekSymbolNode):
        return {expr.name} if expr.name not in bound else set()
    if isinstance(expr, UnaryOpNode):
        return collect_free_symbols(expr.operand, bound)
    if isinstance(expr, BinaryOpNode):
        return collect_free_symbols(expr.left, bound) | collect_free_symbols(expr.right, bound)
    if isinstance(expr, RelationNode):
        return collect_free_symbols(expr.left, bound) | collect_free_symbols(expr.right, bound)
    if isinstance(expr, FunctionCallNode):
        out: set[str] = set()
        binder = binding_call(expr)
        if binder is not None:
            index, bound_args, free_args = binder
            for arg in bound_args:
                out |= collect_free_symbols(arg, bound | {index})
            for arg in free_args:
                out |= collect_free_symbols(arg, bound)
            return out
        for arg in expr.args:
            out |= collect_free_symbols(arg, bound)
        return out
    if isinstance(expr, QuantifierNode):
        return collect_free_symbols(expr.formula, bound | {expr.var})
    if isinstance(expr, IntegralNode):
        out = collect_free_symbols(expr.body, bound | {expr.var})
        if expr.lower is not None:
            out |= collect_free_symbols(expr.lower, bound)
        if expr.upper is not None:
            out |= collect_free_symbols(expr.upper, bound)
        return out
    if isinstance(expr, LimitNode):
        return collect_free_symbols(expr.body, bound | {expr.var}) | collect_free_symbols(expr.target, bound)
    if isinstance(expr, MatrixNode):
        out = set()
        for row in expr.rows:
            for entry in row:
                out |= collect_free_symbols(entry, bound)
        return out
    if isinstance(expr, VectorNode):
        out = set()
        for entry in expr.elements:
            out |= collect_free_symbols(entry, bound)
        return out
    return set()


def substitute_mapping(
    expr: ExprNode,
    mapping: dict[str, ExprNode],
    bound: Optional[set[str]] = None,
) -> ExprNode:
    """Simultaneously replace free variables in *expr* according to *mapping*."""
    if bound is None:
        bound = set()
    if isinstance(expr, SymbolNode):
        if expr.name not in bound and expr.name in mapping:
            return mapping[expr.name]
        return expr
    if isinstance(expr, GreekSymbolNode):
        if expr.name not in bound and expr.name in mapping:
            return mapping[expr.name]
        return expr
    if isinstance(expr, UnaryOpNode):
        return UnaryOpNode(
            op=expr.op,
            operand=substitute_mapping(expr.operand, mapping, bound),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, BinaryOpNode):
        return BinaryOpNode(
            op=expr.op,
            left=substitute_mapping(expr.left, mapping, bound),
            right=substitute_mapping(expr.right, mapping, bound),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, RelationNode):
        return RelationNode(
            op=expr.op,
            left=substitute_mapping(expr.left, mapping, bound),
            right=substitute_mapping(expr.right, mapping, bound),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, FunctionCallNode):
        # A parameter that is *called* (`f(x)` in `Continuous(f, a) <=> …`) and
        # is bound to a function's name calls that function instead.
        func = expr.func
        target = mapping.get(func) if func not in bound else None
        if isinstance(target, (SymbolNode, GreekSymbolNode)):
            func = target.name
        return FunctionCallNode(
            func=func,
            args=[substitute_mapping(a, mapping, bound) for a in expr.args],
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, QuantifierNode):
        return QuantifierNode(
            quantifier=expr.quantifier,
            var=expr.var,
            var_type=expr.var_type,
            formula=substitute_mapping(expr.formula, mapping, bound | {expr.var}),
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, IntegralNode):
        return IntegralNode(
            body=substitute_mapping(expr.body, mapping, bound | {expr.var}),
            var=expr.var,
            lower=substitute_mapping(expr.lower, mapping, bound) if expr.lower is not None else None,
            upper=substitute_mapping(expr.upper, mapping, bound) if expr.upper is not None else None,
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, LimitNode):
        return LimitNode(
            body=substitute_mapping(expr.body, mapping, bound | {expr.var}),
            var=expr.var,
            target=substitute_mapping(expr.target, mapping, bound),
            direction=expr.direction,
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, MatrixNode):
        return MatrixNode(
            rows=[[substitute_mapping(e, mapping, bound) for e in row] for row in expr.rows],
            line=expr.line,
            col=expr.col,
        )
    if isinstance(expr, VectorNode):
        return VectorNode(
            elements=[substitute_mapping(e, mapping, bound) for e in expr.elements],
            line=expr.line,
            col=expr.col,
        )
    return expr


@dataclass
class VarInfo:
    """Metadata for a declared variable in the proof context."""

    name: str
    math_type: MathType
    scope_depth: int
    is_witness: bool = False
    condition: Optional[ExprNode] = None
    #: The structure an ``Element`` belongs to (``G`` in ``Given a : G``).
    carrier: Optional[str] = None
    #: A ``Function``'s argument types and result type (``Real -> Real``).
    signature: Optional[tuple[tuple[MathType, ...], MathType]] = None

    @property
    def type_label(self) -> str:
        """What the variable is declared as, for display: ``Int``, ``G``, ``Real -> Real``."""
        if self.signature is not None:
            args, result = self.signature
            return " -> ".join([t.value for t in args] + [result.value])
        return self.carrier or self.math_type.value


@dataclass
class FuncDefInfo:
    """Metadata for a user-defined mathematical function (e.g. Let f(x) = ...)."""

    name: str
    params: list[str]
    body: ExprNode
    scope_depth: int = 0


@dataclass
class HypothesisInfo:
    """An active assumption or derived fact in the proof context."""

    proposition: ExprNode
    label: Optional[str] = None
    scope_depth: int = 0
    is_assumption: bool = True  # True for Assume/Suppose; False for Given conditions / derived facts


@dataclass
class DomainObligation:
    """An automatically generated domain obligation (e.g. non-zero denominator).

    Usually a relation (``x - 2 != 0``); inside a sum it is quantified over the
    index range (``forall k : Int, 1 <= k <= n => k^2 != 0``).
    """

    condition: ExprNode
    reason: str
    line: Optional[int] = None
    discharged: bool = False


@dataclass
class ChainState:
    """Tracks the current equational or inequality chain."""

    head_lhs: ExprNode
    current_rhs: ExprNode
    effective_relation: str = "="


@dataclass(frozen=True)
class GroupSignature:
    """The names a group assumption binds: ``Group(G, op, e, inv)``."""

    carrier: str
    op: str = "op"
    identity: str = "e"
    inverse: str = "inv"
    abelian: bool = False


#: Infix spellings of a group's operation when its operands are group elements.
_GROUP_PRODUCT_OPS = frozenset({"*", "\\cdot", "\\circ"})


def _map_children(expr: ExprNode, fn) -> ExprNode:
    """Rebuild *expr* with ``fn`` applied to every child expression."""
    changes = {}
    for f in fields(expr):
        value = getattr(expr, f.name)
        if isinstance(value, ExprNode):
            changes[f.name] = fn(value)
        elif isinstance(value, list) and value and all(isinstance(v, ExprNode) for v in value):
            changes[f.name] = [fn(v) for v in value]
        elif isinstance(value, list) and value and all(isinstance(v, list) for v in value):
            changes[f.name] = [[fn(x) for x in row] for row in value]
    return replace(expr, **changes) if changes else expr


def _integer_literal(expr: ExprNode) -> Optional[int]:
    if isinstance(expr, NumberNode) and "." not in expr.value:
        return int(expr.value)
    if isinstance(expr, UnaryOpNode) and expr.op in ("-", "+"):
        inner = _integer_literal(expr.operand)
        if inner is not None:
            return -inner if expr.op == "-" else inner
    return None


@dataclass
class _ScopeFrame:
    """A single lexical/logical scope frame."""

    depth: int
    variables: dict[str, VarInfo] = field(default_factory=dict)
    functions: dict[str, FuncDefInfo] = field(default_factory=dict)
    hypotheses: list[HypothesisInfo] = field(default_factory=list)
    chain: Optional[ChainState] = None
    cases: list[tuple[ExprNode, ExprNode]] = field(default_factory=list)
    # Whether the cases so far cover every possibility, and whether a
    # conclusion after them has already been told when they do not.
    cases_exhaustive: bool = False
    cases_reviewed: bool = False


class ProofContext:
    """Manages nested scopes, active variables, hypotheses, and equational chains."""

    def __init__(self) -> None:
        self._frames: list[_ScopeFrame] = [_ScopeFrame(depth=0)]
        self.obligations: list[DomainObligation] = []
        # Show your working (ProofChecker(show_working=True)): shortcuts that
        # settle a claim without the student's argument are held back.
        self.show_working = False

    @property
    def scope_depth(self) -> int:
        return len(self._frames) - 1

    @property
    def current_frame(self) -> _ScopeFrame:
        return self._frames[-1]

    @property
    def chain(self) -> Optional[ChainState]:
        for frame in reversed(self._frames):
            if frame.chain is not None:
                return frame.chain
        return None

    def push_scope(self) -> int:
        """Open a nested subproof / assumption scope."""
        new_depth = len(self._frames)
        self._frames.append(_ScopeFrame(depth=new_depth))
        return new_depth

    def pop_scope(self) -> _ScopeFrame:
        """Close the innermost scope and return its frame."""
        if len(self._frames) <= 1:
            raise ContextError("Cannot pop the root proof scope.")
        return self._frames.pop()

    # -------------------------------------------------------------------
    # Variables & User Functions
    # -------------------------------------------------------------------

    def get_var(self, name: str) -> Optional[VarInfo]:
        for frame in reversed(self._frames):
            if name in frame.variables:
                return frame.variables[name]
        return None

    def all_variables(self) -> dict[str, VarInfo]:
        merged: dict[str, VarInfo] = {}
        for frame in self._frames:
            merged.update(frame.variables)
        return merged

    def get_function(self, name: str) -> Optional[FuncDefInfo]:
        for frame in reversed(self._frames):
            if name in frame.functions:
                return frame.functions[name]
        return None

    def all_functions(self) -> dict[str, FuncDefInfo]:
        merged: dict[str, FuncDefInfo] = {}
        for frame in self._frames:
            merged.update(frame.functions)
        return merged

    #: Structure assumptions that bind distinguished elements *by name*.
    #: ``Assume Group(G, op, e, inv)`` makes ``e`` the identity, so a symbol of
    #: that name is the group's identity -- not Euler's number.
    STRUCTURE_PROPOSITIONS: frozenset[str] = frozenset(
        {"group", "abeliangroup", "ring", "field", "subgroup", "normalsubgroup"}
    )

    def structure_names(self) -> set[str]:
        """Names bound by an active structure assumption (identity, zero, one, ...)."""
        names: set[str] = set()
        for hypothesis in self.all_hypotheses():
            proposition = hypothesis.proposition
            if (
                isinstance(proposition, FunctionCallNode)
                and proposition.func.lower() in self.STRUCTURE_PROPOSITIONS
            ):
                for arg in proposition.args:
                    if isinstance(arg, (SymbolNode, GreekSymbolNode)):
                        names.add(arg.name)
        return names

    def declare_function(
        self,
        name: str,
        params: list[str],
        body: ExprNode,
    ) -> FuncDefInfo:
        """Register a user-defined function ``f(x1, ...) = body`` in the current scope."""
        if self.get_var(name) is not None or self.get_function(name) is not None:
            raise VariableCaptureError(
                f"Implicit variable capture: function '{name}' cannot shadow an existing symbol in scope."
            )
        info = FuncDefInfo(
            name=name,
            params=params,
            body=body,
            scope_depth=self.scope_depth,
        )
        self.current_frame.functions[name] = info
        return info

    # -------------------------------------------------------------------
    # Structures: carriers, group signatures, multiplicative notation
    # -------------------------------------------------------------------

    def _structure_calls(self) -> list[FunctionCallNode]:
        return [
            h.proposition
            for h in self.all_hypotheses()
            if isinstance(h.proposition, FunctionCallNode)
            and h.proposition.func.lower() in self.STRUCTURE_PROPOSITIONS
        ]

    def group_signatures(self) -> dict[str, GroupSignature]:
        """Every carrier a group assumption is about, mapped to that group's names.

        ``Subgroup(H, G, op, e, inv)`` makes ``H`` a carrier with ``G``'s
        operation, so ``Given h : H`` elements multiply with ``op`` too.
        """

        def name(arg: ExprNode) -> Optional[str]:
            return arg.name if isinstance(arg, (SymbolNode, GreekSymbolNode)) else None

        out: dict[str, GroupSignature] = {}
        for call in self._structure_calls():
            fn = call.func.lower()
            names = [name(a) for a in call.args]
            if fn in ("group", "abeliangroup") and names and names[0]:
                rest = names[1:4]
                out[names[0]] = GroupSignature(
                    carrier=names[0],
                    op=rest[0] if len(rest) > 0 and rest[0] else "op",
                    identity=rest[1] if len(rest) > 1 and rest[1] else "e",
                    inverse=rest[2] if len(rest) > 2 and rest[2] else "inv",
                    abelian=fn == "abeliangroup",
                )
        for call in self._structure_calls():
            fn = call.func.lower()
            names = [name(a) for a in call.args]
            if fn in ("subgroup", "normalsubgroup") and len(names) >= 2 and names[0] and names[0] not in out:
                parent = out.get(names[1] or "")
                rest = names[2:5]
                out[names[0]] = GroupSignature(
                    carrier=names[0],
                    op=rest[0] if len(rest) > 0 and rest[0] else (parent.op if parent else "op"),
                    identity=rest[1] if len(rest) > 1 and rest[1] else (parent.identity if parent else "e"),
                    inverse=rest[2] if len(rest) > 2 and rest[2] else (parent.inverse if parent else "inv"),
                    abelian=parent.abelian if parent else False,
                )
        return out

    def carrier_names(self) -> set[str]:
        """Names usable as a type: structure carriers and declared sets."""
        names = set(self.group_signatures())
        for call in self._structure_calls():
            if call.args and isinstance(call.args[0], (SymbolNode, GreekSymbolNode)):
                names.add(call.args[0].name)
        for v in self.all_variables().values():
            if v.math_type == MathType.Set:
                names.add(v.name)
        return names

    def resolve_number_type(self, raw_type: str) -> MathType:
        """A function type's part: a number type, or ``ValueError``."""
        math_type = normalize_type_name(raw_type)
        if math_type not in (MathType.Nat, MathType.Int, MathType.Rat, MathType.Real, MathType.Complex, MathType.Bool):
            raise ValueError(
                f"A function's argument and result types are number types (Nat, Int, Rat, Real, Complex), "
                f"not {raw_type!r}."
            )
        return math_type

    def resolve_type(self, raw_type: str | MathType) -> tuple[MathType, Optional[str]]:
        """``(math_type, carrier)`` for a declared type name.

        A number type (``Int``, ``\\mathbb{R}``) resolves as before; the name of
        a structure carrier or a declared set (``G`` after ``Assume Group(G,
        ...)``) makes the variable an ``Element`` of it.  Raises ``ValueError``
        for anything else.
        """
        if isinstance(raw_type, MathType):
            return raw_type, None
        try:
            return normalize_type_name(raw_type), None
        except ValueError:
            carrier = raw_type.strip()
            if carrier in self.carrier_names():
                return MathType.Element, carrier
            raise ValueError(
                f"Unknown type: {raw_type!r}. Use a number type (Nat, Int, Rat, Real, Complex), "
                f"or a structure's carrier after e.g. `Assume Group({carrier}, op, e, inv)`."
            ) from None

    def group_of(self, expr: ExprNode) -> Optional[GroupSignature]:
        """The group *expr* is an element of, if that can be read off its form."""
        groups = self.group_signatures()
        if not groups:
            return None
        if isinstance(expr, (SymbolNode, GreekSymbolNode)):
            v = self.get_var(expr.name)
            if v is not None:
                return groups.get(v.carrier or "")
            return next((g for g in groups.values() if g.identity == expr.name), None)
        if isinstance(expr, FunctionCallNode):
            return next(
                (
                    g
                    for g in groups.values()
                    if (expr.func == g.op and len(expr.args) == 2)
                    or (expr.func == g.inverse and len(expr.args) == 1)
                ),
                None,
            )
        if isinstance(expr, BinaryOpNode) and expr.op in _GROUP_PRODUCT_OPS:
            return self.group_of(expr.left) or self.group_of(expr.right)
        if isinstance(expr, BinaryOpNode) and expr.op in ("^", "**"):
            return self.group_of(expr.left)
        return None

    def elaborate_group_notation(self, expr: ExprNode) -> ExprNode:
        """Rewrite the notes' multiplicative notation into the group's own names.

        For group elements ``a * b`` (or ``a \\cdot b``, ``a \\circ b``) is
        ``op(a, b)``, ``a^-1`` is ``inv(a)``, ``a^3`` is ``op(op(a, a), a)`` and
        ``a^0`` is the identity.  Anything not recognisably a group element
        (a real ``x * y``) is left alone, so nothing changes for proofs that do
        not declare elements.
        """
        if not self.group_signatures():
            return expr

        def walk(node: ExprNode) -> ExprNode:
            node = _map_children(node, walk)
            if isinstance(node, BinaryOpNode) and node.op in _GROUP_PRODUCT_OPS:
                g = self.group_of(node.left) or self.group_of(node.right)
                if g is not None:
                    return FunctionCallNode(func=g.op, args=[node.left, node.right], line=node.line, col=node.col)
            if isinstance(node, BinaryOpNode) and node.op in ("^", "**"):
                g = self.group_of(node.left)
                k = _integer_literal(node.right)
                if g is not None and k is not None:
                    return self._group_power(g, node.left, k)
                if g is not None:
                    # A symbolic exponent stays an opaque power of the element, never
                    # the commutative real power `a^n * b^n = (a*b)^n` would suggest.
                    return FunctionCallNode(func=f"{g.op}_pow", args=[node.left, node.right], line=node.line, col=node.col)
            return node

        return walk(expr)

    @staticmethod
    def _group_power(g: GroupSignature, base: ExprNode, k: int) -> ExprNode:
        if k == 0:
            return SymbolNode(name=g.identity)
        acc = base
        for _ in range(abs(k) - 1):
            acc = FunctionCallNode(func=g.op, args=[acc, base])
        return acc if k > 0 else FunctionCallNode(func=g.inverse, args=[acc])

    def expand_user_functions(self, expr: Optional[ExprNode]) -> Optional[ExprNode]:
        """Inline user-defined functions, then elaborate group notation, in *expr*."""
        expanded = self._expand_user_functions(expr)
        if expanded is None:
            return None
        return self.elaborate_group_notation(expanded)

    def _expand_user_functions(self, expr: Optional[ExprNode]) -> Optional[ExprNode]:
        """Recursively inline any calls to user-defined functions ``f(args)`` in *expr*."""
        if expr is None:
            return None
        if isinstance(expr, UnaryOpNode):
            return UnaryOpNode(
                op=expr.op,
                operand=self._expand_user_functions(expr.operand),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, BinaryOpNode):
            return BinaryOpNode(
                op=expr.op,
                left=self._expand_user_functions(expr.left),  # type: ignore[arg-type]
                right=self._expand_user_functions(expr.right),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, RelationNode):
            return RelationNode(
                op=expr.op,
                left=self._expand_user_functions(expr.left),  # type: ignore[arg-type]
                right=self._expand_user_functions(expr.right),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, QuantifierNode):
            return QuantifierNode(
                quantifier=expr.quantifier,
                var=expr.var,
                var_type=expr.var_type,
                formula=self._expand_user_functions(expr.formula),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, FunctionCallNode):
            expanded_args = [self._expand_user_functions(a) for a in expr.args]
            fn_info = self.get_function(expr.func)
            if fn_info is not None and len(expanded_args) == len(fn_info.params):
                mapping = {p: a for p, a in zip(fn_info.params, expanded_args) if a is not None}
                inlined = substitute_mapping(fn_info.body, mapping)
                return self._expand_user_functions(inlined)
            return FunctionCallNode(
                func=expr.func,
                args=[a for a in expanded_args if a is not None],
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, IntegralNode):
            return IntegralNode(
                body=self._expand_user_functions(expr.body),  # type: ignore[arg-type]
                var=expr.var,
                lower=self._expand_user_functions(expr.lower) if expr.lower is not None else None,
                upper=self._expand_user_functions(expr.upper) if expr.upper is not None else None,
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, LimitNode):
            return LimitNode(
                body=self._expand_user_functions(expr.body),  # type: ignore[arg-type]
                var=expr.var,
                target=self._expand_user_functions(expr.target),  # type: ignore[arg-type]
                direction=expr.direction,
                line=expr.line,
                col=expr.col,
            )
        return expr

    def declare_variable(
        self,
        name: str,
        raw_type: str | MathType,
        is_witness: bool = False,
        condition: Optional[ExprNode] = None,
    ) -> VarInfo:
        """Register a variable in the current scope.

        Raises ``VariableCaptureError`` if *name* already exists in any active scope.
        """
        existing = self.get_var(name)
        if existing is not None:
            kind = "witness variable" if is_witness else "variable"
            raise VariableCaptureError(
                f"Implicit variable capture: {kind} '{name}' cannot shadow existing "
                f"symbol '{name}' ({existing.math_type.value}) declared at scope depth {existing.scope_depth}."
            )

        signature = None
        parts = split_function_type(raw_type) if isinstance(raw_type, str) else None
        if parts is not None:
            *args, result = (self.resolve_number_type(p) for p in parts)
            math_type, carrier, signature = MathType.Function, None, (tuple(args), result)
        else:
            math_type, carrier = self.resolve_type(raw_type)
            if math_type == MathType.Function:
                signature = ((MathType.Real,), MathType.Real)
        if carrier is not None and condition is None:
            # `Given a : G` says a is in G; Subgroup/NormalSubgroup reasoning uses it.
            condition = RelationNode(op="in", left=SymbolNode(name=name), right=SymbolNode(name=carrier))
        info = VarInfo(
            name=name,
            math_type=math_type,
            scope_depth=self.scope_depth,
            is_witness=is_witness,
            condition=condition,
            carrier=carrier,
            signature=signature,
        )
        self.current_frame.variables[name] = info

        if condition is not None:
            self.add_hypothesis(condition, label=None, is_assumption=False)

        return info

    # -------------------------------------------------------------------
    # Hypotheses & facts
    # -------------------------------------------------------------------

    def add_hypothesis(
        self,
        proposition: ExprNode,
        label: Optional[str] = None,
        is_assumption: bool = True,
    ) -> HypothesisInfo:
        info = HypothesisInfo(
            proposition=proposition,
            label=label,
            scope_depth=self.scope_depth,
            is_assumption=is_assumption,
        )
        self.current_frame.hypotheses.append(info)
        return info

    def all_hypotheses(self) -> list[HypothesisInfo]:
        out: list[HypothesisInfo] = []
        for frame in self._frames:
            out.extend(frame.hypotheses)
        return out

    def get_hypothesis(self, label: str) -> Optional[HypothesisInfo]:
        for frame in reversed(self._frames):
            for h in reversed(frame.hypotheses):
                if h.label == label:
                    return h
        return None

    def get_equality_substitutions(self) -> list[tuple[ExprNode, ExprNode]]:
        """Extract active equality pairs ``(lhs, rhs)`` from hypotheses and current chain."""
        subs: list[tuple[ExprNode, ExprNode]] = []
        for h in self.all_hypotheses():
            if isinstance(h.proposition, RelationNode) and canonical_rel(h.proposition.op) == "=":
                subs.append((h.proposition.left, h.proposition.right))
        for v in self.all_variables().values():
            if (
                v.condition is not None
                and isinstance(v.condition, RelationNode)
                and canonical_rel(v.condition.op) == "="
            ):
                subs.append((v.condition.left, v.condition.right))
        if self.chain is not None and self.chain.effective_relation == "=":
            subs.append((self.chain.head_lhs, self.chain.current_rhs))
        return subs

    # -------------------------------------------------------------------
    # Universal generalization check
    # -------------------------------------------------------------------

    def check_generalization_allowed(self, var_name: str) -> None:
        """Ensure *var_name* is not constrained by an active assumption before ∀-introduction.

        Raises ``GeneralizationError`` if constrained.
        """
        var_info = self.get_var(var_name)
        if var_info is not None and var_info.is_witness:
            raise GeneralizationError(
                f"Illegal generalization: cannot generalize existential witness '{var_name}'."
            )

        for h in self.all_hypotheses():
            if h.is_assumption and var_name in collect_free_symbols(h.proposition):
                raise GeneralizationError(
                    f"Illegal generalization: cannot generalize variable '{var_name}' "
                    f"because it is constrained by active assumption '{h.proposition}'."
                )

    # -------------------------------------------------------------------
    # Step chaining
    # -------------------------------------------------------------------

    def resolve_step(
        self,
        lhs: Optional[ExprNode],
        relation: str,
        rhs: ExprNode,
    ) -> tuple[Optional[ExprNode], str, ExprNode, Optional[ChainState]]:
        """Resolve ``(effective_lhs, rel, rhs, next_chain_state)`` without mutating the context.

        Raises ``ChainError`` if ``lhs`` is ``None`` and no chain is active,
        or ``MonotonicityError`` if inequality directions conflict.
        """
        rel = canonical_rel(relation) if relation else ""

        if lhs is not None:
            next_chain = ChainState(
                head_lhs=lhs,
                current_rhs=rhs,
                effective_relation=rel or "=",
            )
            return lhs, rel, rhs, next_chain

        # Chained step (lhs is None)
        if not rel:
            # Bare expression step (e.g. Step: Even(n))
            return None, "", rhs, None

        active = self.chain
        if active is None:
            raise ChainError(
                f"Chained step 'Step: {relation} {rhs}' has no preceding step to chain from."
            )

        prev_rhs = active.current_rhs
        new_eff = combine_chain_relations(active.effective_relation, rel)
        next_chain = ChainState(
            head_lhs=active.head_lhs,
            current_rhs=rhs,
            effective_relation=new_eff,
        )
        return prev_rhs, rel, rhs, next_chain

    def commit_step(self, next_chain: Optional[ChainState]) -> None:
        """Commit a verified step's chain state to the current scope."""
        if next_chain is not None:
            self.current_frame.chain = next_chain
