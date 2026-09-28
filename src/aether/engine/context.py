"""Proof state, scope stack, variable tracking, and chain monotonicity for Aether."""

from __future__ import annotations

from dataclasses import dataclass, field
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
)
from aether.core.types import MathType, normalize_type_name


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
        return FunctionCallNode(
            func=expr.func,
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
    return expr


@dataclass
class VarInfo:
    """Metadata for a declared variable in the proof context."""

    name: str
    math_type: MathType
    scope_depth: int
    is_witness: bool = False
    condition: Optional[ExprNode] = None


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
    """An automatically generated domain obligation (e.g. non-zero denominator)."""

    condition: RelationNode
    reason: str
    line: Optional[int] = None
    discharged: bool = False


@dataclass
class ChainState:
    """Tracks the current equational or inequality chain."""

    head_lhs: ExprNode
    current_rhs: ExprNode
    effective_relation: str = "="


@dataclass
class _ScopeFrame:
    """A single lexical/logical scope frame."""

    depth: int
    variables: dict[str, VarInfo] = field(default_factory=dict)
    functions: dict[str, FuncDefInfo] = field(default_factory=dict)
    hypotheses: list[HypothesisInfo] = field(default_factory=list)
    chain: Optional[ChainState] = None
    cases: list[tuple[ExprNode, ExprNode]] = field(default_factory=list)


class ProofContext:
    """Manages nested scopes, active variables, hypotheses, and equational chains."""

    def __init__(self) -> None:
        self._frames: list[_ScopeFrame] = [_ScopeFrame(depth=0)]
        self.obligations: list[DomainObligation] = []

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

    def expand_user_functions(self, expr: Optional[ExprNode]) -> Optional[ExprNode]:
        """Recursively inline any calls to user-defined functions ``f(args)`` in *expr*."""
        if expr is None:
            return None
        if isinstance(expr, UnaryOpNode):
            return UnaryOpNode(
                op=expr.op,
                operand=self.expand_user_functions(expr.operand),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, BinaryOpNode):
            return BinaryOpNode(
                op=expr.op,
                left=self.expand_user_functions(expr.left),  # type: ignore[arg-type]
                right=self.expand_user_functions(expr.right),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, RelationNode):
            return RelationNode(
                op=expr.op,
                left=self.expand_user_functions(expr.left),  # type: ignore[arg-type]
                right=self.expand_user_functions(expr.right),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, QuantifierNode):
            return QuantifierNode(
                quantifier=expr.quantifier,
                var=expr.var,
                var_type=expr.var_type,
                formula=self.expand_user_functions(expr.formula),  # type: ignore[arg-type]
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, FunctionCallNode):
            expanded_args = [self.expand_user_functions(a) for a in expr.args]
            fn_info = self.get_function(expr.func)
            if fn_info is not None and len(expanded_args) == len(fn_info.params):
                mapping = {p: a for p, a in zip(fn_info.params, expanded_args) if a is not None}
                inlined = substitute_mapping(fn_info.body, mapping)
                return self.expand_user_functions(inlined)
            return FunctionCallNode(
                func=expr.func,
                args=[a for a in expanded_args if a is not None],
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, IntegralNode):
            return IntegralNode(
                body=self.expand_user_functions(expr.body),  # type: ignore[arg-type]
                var=expr.var,
                lower=self.expand_user_functions(expr.lower) if expr.lower is not None else None,
                upper=self.expand_user_functions(expr.upper) if expr.upper is not None else None,
                line=expr.line,
                col=expr.col,
            )
        if isinstance(expr, LimitNode):
            return LimitNode(
                body=self.expand_user_functions(expr.body),  # type: ignore[arg-type]
                var=expr.var,
                target=self.expand_user_functions(expr.target),  # type: ignore[arg-type]
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

        math_type = raw_type if isinstance(raw_type, MathType) else normalize_type_name(raw_type)
        info = VarInfo(
            name=name,
            math_type=math_type,
            scope_depth=self.scope_depth,
            is_witness=is_witness,
            condition=condition,
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
