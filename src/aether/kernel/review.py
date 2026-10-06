"""Stage 1 of the proof kernel: chain links and deductions, reviewed.

The engine's own checks still decide whether a line is true.  The kernel
changes what they are allowed to see and what their answer means:

1. **Premise selection.**  A line that cites its premises is checked with
   those alone (``premises.select``).  `x^2 > 25 [using h2]` is refused when
   h2 does not give it, and the message names what would.
2. **Strength.**  A line that checks is classified by the fragment that
   settled it (``policy``): an identity, linear reasoning, non-linear
   arithmetic, an evaluation, checking remainders, a quantified statement.
   A fragment stronger than the level allows is refused as too big a step,
   with what to write instead.  Its conclusion is still recorded, so one
   oversized line is one finding, not a cascade.
3. **Evidence.**  A line Z3 settled names the premises it used, from the
   unsat core (``evidence``), so the audit reads "linarith, from h1".
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Callable, Optional

from aether.core.ast import (
    BinaryOpNode,
    DeduceNode,
    ExprNode,
    FunctionCallNode,
    NumberNode,
    QuantifierNode,
    RelationNode,
    StepNode,
    SymbolNode,
)
from aether.engine.context import ChainError, HypothesisInfo, MonotonicityError, ProofContext, collect_free_symbols
from aether.engine.logic import _exprs_match, chain_fact, substitute_expr
from aether.engine.working import working_gap
from aether.kernel import evidence, policy, premises
from aether.kernel.policy import Fragment, Policy

if TYPE_CHECKING:
    from aether.engine.checker import StepResult

#: Functions whose value is not a polynomial in their argument.
_TRANSCENDENTAL = {
    "sin", "cos", "tan", "sec", "csc", "cot", "exp", "log", "ln", "sqrt",
    "sinh", "cosh", "tanh", "arcsin", "arccos", "arctan", "factorial",
}
#: Predicates whose second argument is a modulus.
_MODULAR = {"multipleof": 1, "divides": 0, "congruent": 2}


class Kernel:
    """Reviews each chain link and deduction against a level (``policy.LEVELS``)."""

    def __init__(self, level: str) -> None:
        if level not in policy.LEVELS:
            raise ValueError(f"Unknown kernel level {level!r}: expected one of {', '.join(policy.LEVELS)}.")
        self.policy: Policy = policy.LEVELS[level]
        #: The line each fact was established on, for naming unlabelled premises.
        self._origin: dict[int, Optional[int]] = {}
        #: Results cited by name for the current step (set by the checker).
        self.lent: list[HypothesisInfo] = []
        #: What the chain had established before the line under review.
        self._chain: Optional[ExprNode] = None

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def record(self, ctx: ProofContext, before: set[int], line: Optional[int]) -> None:
        """Note the line that established each fact added since *before*."""
        for h in ctx.all_hypotheses():
            if id(h) not in before and id(h) not in self._origin:
                self._origin[id(h)] = line

    def name(self, premise: object) -> str:
        if isinstance(premise, str):
            return premise
        assert isinstance(premise, HypothesisInfo)
        if premise.label:
            return premise.label
        line = self._origin.get(id(premise))
        return f"line {line}" if line else str(premise.proposition)

    def names(self, premises_: list[object]) -> str:
        parts = [self.name(p) for p in premises_]
        if len(parts) <= 1:
            return "".join(parts)
        return ", ".join(parts[:-1]) + " and " + parts[-1]

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def check_step(
        self,
        stmt: StepNode,
        ctx: ProofContext,
        check: Callable[[StepNode, ProofContext], "StepResult"],
        is_definition: Callable[[ExprNode, ProofContext], bool],
    ) -> "StepResult":
        try:
            lhs, rel, rhs, _ = ctx.resolve_step(stmt.lhs, stmt.relation, stmt.rhs)
        except (ChainError, MonotonicityError):
            return check(stmt, ctx)  # the chain guard reports it
        obligation: ExprNode = RelationNode(op=rel, left=lhs, right=rhs) if rel and lhs is not None else rhs
        cited = premises.cited_labels(stmt.justification, ctx) + self.lent
        allowed = premises.select(cited, ctx, is_definition)
        self._chain = chain_fact(ctx)
        with premises.restricted(ctx, allowed):
            result = check(stmt, ctx)
        return self._review(result, obligation, "step", cited, allowed, ctx, before=lhs, after=rhs)

    def check_deduce(
        self,
        stmt: DeduceNode,
        ctx: ProofContext,
        check: Callable[[DeduceNode, ProofContext], "StepResult"],
        is_definition: Callable[[ExprNode, ProofContext], bool],
    ) -> "StepResult":
        cited = premises.cited_labels(stmt.justification, ctx) + self.lent
        target = stmt
        if stmt.premise is not None:
            if isinstance(stmt.premise, SymbolNode) and ctx.get_hypothesis(stmt.premise.name) is not None:
                cited.append(ctx.get_hypothesis(stmt.premise.name))  # type: ignore[arg-type]
            else:
                # `Since A, B`: A is a line of its own, reviewed the same way;
                # once it holds, B may use it and what B cites.
                before = {id(h) for h in ctx.all_hypotheses()}
                premise_stmt = DeduceNode(claim=stmt.premise, line=stmt.line, col=stmt.col)
                lent, self.lent = self.lent, []
                try:
                    held = self.check_deduce(premise_stmt, ctx, check, is_definition)
                finally:
                    self.lent = lent
                if held.status.value == "INVALID":
                    return replace(
                        held,
                        statement=stmt,
                        message=f"The premise does not hold here, so it cannot be used: {held.message}",
                    )
                cited += [h for h in ctx.all_hypotheses() if id(h) not in before]
            target = replace(stmt, premise=None)

        claim = stmt.claim
        if isinstance(claim, RelationNode) and isinstance(claim.left, SymbolNode) and claim.left.name == "<prev>":
            if ctx.chain is not None:
                claim = RelationNode(op=claim.op, left=ctx.chain.head_lhs, right=claim.right)
        obligation = _instance(claim, stmt.witness)
        allowed = premises.select(cited, ctx, is_definition)
        self._chain = chain_fact(ctx)
        with premises.restricted(ctx, allowed):
            result = check(target, ctx)
        result = replace(result, statement=stmt)
        before_, after_ = (claim.left, claim.right) if isinstance(claim, RelationNode) else (None, None)
        witnessed = (
            (claim.formula, claim.var, _witness_value(claim, stmt.witness))
            if stmt.witness is not None and isinstance(claim, QuantifierNode) and claim.quantifier == "exists"
            else None
        )
        return self._review(
            result, obligation, "deduce", cited, allowed, ctx, before=before_, after=after_, witnessed=witnessed
        )

    # ------------------------------------------------------------------
    # The review
    # ------------------------------------------------------------------

    def _review(
        self,
        result: "StepResult",
        obligation: ExprNode,
        kind: str,
        cited: list[HypothesisInfo],
        allowed: list[HypothesisInfo],
        ctx: ProofContext,
        before: Optional[ExprNode],
        after: Optional[ExprNode],
        witnessed: Optional[tuple[ExprNode, str, ExprNode]] = None,
    ) -> "StepResult":
        if result.status.value == "INVALID":
            return self._missing_premise(result, obligation, cited, ctx) if cited else result

        fragment = self._fragment(result, obligation, before, after, ctx, allowed, witnessed)
        used: Optional[list[object]] = None
        if fragment.strength >= policy.LINEAR.strength and fragment.tactic in ("linarith", "nlinarith", "auto"):
            used = evidence.premises_used(obligation, allowed, ctx, chain=self._chain)

        if not self.policy.allows(fragment, kind):
            if fragment.tactic == "calculus.eval":
                why = fragment.advice[0].upper() + fragment.advice[1:]
                message = f"True, but too big a step for the {self.policy.name} level. {why}"
            else:
                message = (
                    f"True, but too big a step for the {self.policy.name} level: this line needs "
                    f"{fragment.needs}. {fragment.advice}"
                ).rstrip()
            return replace(
                result,
                status=type(result.status)("INVALID"),
                message=message,
                backend=f"Kernel: {fragment.tactic}",
                counterexample=None,
                counterexample_dict=None,
            )

        message = result.message
        if used and not cited:
            message = f"{message.rstrip('.')} (from {self.names(used)})."
        return replace(result, message=message, backend=f"Kernel: {fragment.tactic}")

    def _missing_premise(
        self,
        result: "StepResult",
        obligation: ExprNode,
        cited: list[HypothesisInfo],
        ctx: ProofContext,
    ) -> "StepResult":
        """A cited step that failed: say which facts it would follow from, if any."""
        used = evidence.premises_used(obligation, ctx.all_hypotheses(), ctx, chain=self._chain)
        if not used:
            return result
        missing = [p for p in used if not any(p is c for c in cited)]
        if not missing:
            return result
        return replace(
            result,
            message=(
                f"This does not follow from {self.names(list(cited))} alone. "
                f"It follows using {self.names(used)}: cite {'it' if len(missing) == 1 else 'them'} too."
            ),
            backend="Kernel: premises",
            counterexample=None,
            counterexample_dict=None,
        )

    def _fragment(
        self,
        result: "StepResult",
        obligation: ExprNode,
        before: Optional[ExprNode],
        after: Optional[ExprNode],
        ctx: ProofContext,
        known: list[HypothesisInfo],
        witnessed: Optional[tuple[ExprNode, str, ExprNode]],
    ) -> Fragment:
        """Which kind of reasoning settled the line."""
        backend = result.backend or ""
        if backend == "Induction":
            return policy.INDUCTION
        if backend == "Residues":
            return policy.RESIDUES
        if result.message.startswith("Verified from established hypothesis"):
            return policy.HYPOTHESIS
        if before is not None and after is not None:
            gap = working_gap(before, after, ctx)
            if gap:
                return policy.evaluation(gap)
        if backend.startswith("SymPy") and backend != "SymPy+Logic":
            return policy.RING
        # Only facts the line could see count as already established: by now
        # its own conclusion has been recorded too.
        if witnessed is not None:
            body, var, value = witnessed
            rest = _undischarged(ctx.expand_user_functions(body) or body, ctx, known)
            expanded = None if rest is None else substitute_expr(rest, var, value)
        else:
            expanded = _undischarged(ctx.expand_user_functions(obligation) or obligation, ctx, known)
        if expanded is None:
            return policy.HYPOTHESIS
        if _has_quantifier(expanded):
            return policy.QUANTIFIED
        if _nonlinear(expanded, ctx):
            return policy.NONLINEAR
        return policy.LINEAR


def _instance(claim: ExprNode, witness: Optional[ExprNode]) -> ExprNode:
    """`exists m, P(m) [witness: t]` is decided as P(t)."""
    if witness is None or not (isinstance(claim, QuantifierNode) and claim.quantifier == "exists"):
        return claim
    return substitute_expr(claim.formula, claim.var, _witness_value(claim, witness))


def _witness_value(claim: QuantifierNode, witness: ExprNode) -> ExprNode:
    """`[witness: t]` and `[witness: m = t]` both name t."""
    if isinstance(witness, RelationNode) and isinstance(witness.left, SymbolNode) and witness.left.name == claim.var:
        return witness.right
    return witness


def _undischarged(node: ExprNode, ctx: ProofContext, known: list[HypothesisInfo]) -> Optional[ExprNode]:
    """*node* without the conjuncts that are facts already established.

    `exists δ, δ > 0 and (forall x, …) [witness: ε/3]` after a subproof that
    proved the `forall x` part asks only for ε/3 > 0: the quantified part is
    the subproof's, not a leap.  None when nothing is left."""
    if any(_exprs_match(node, h.proposition, ctx) for h in known):
        return None
    if isinstance(node, BinaryOpNode) and node.op.lower() in ("and", "\\land", "/\\"):
        left, right = _undischarged(node.left, ctx, known), _undischarged(node.right, ctx, known)
        if left is None or right is None:
            return right if left is None else left
        return replace(node, left=left, right=right)
    return node


def _children(node: object) -> list[ExprNode]:
    out: list[ExprNode] = []
    for value in vars(node).values() if hasattr(node, "__dict__") else []:
        if isinstance(value, ExprNode):
            out.append(value)
        elif isinstance(value, list):
            out.extend(v for v in value if isinstance(v, ExprNode))
    return out


def _has_quantifier(node: ExprNode) -> bool:
    if isinstance(node, QuantifierNode):
        return True
    return any(_has_quantifier(c) for c in _children(node))


def _symbolic(node: ExprNode, ctx: ProofContext) -> bool:
    """Whether *node* mentions an unknown: a declared variable, not a constant like pi."""
    return any(ctx.get_var(name) is not None for name in collect_free_symbols(node))


def _nonlinear(node: ExprNode, ctx: ProofContext) -> bool:
    if isinstance(node, BinaryOpNode):
        op = node.op
        if op == "*" and _symbolic(node.left, ctx) and _symbolic(node.right, ctx):
            return True
        if op == "/" and _symbolic(node.right, ctx):
            return True
        if op == "^" and _symbolic(node.left, ctx) and not (
            isinstance(node.right, NumberNode) and node.right.value in ("0", "1")
        ):
            return True
        if op == "^" and _symbolic(node.right, ctx):
            return True
    if isinstance(node, FunctionCallNode):
        fn = node.func.lower()
        if fn in _TRANSCENDENTAL and any(_symbolic(a, ctx) for a in node.args):
            return True
        modulus = _MODULAR.get(fn)
        if modulus is not None and len(node.args) > modulus and _symbolic(node.args[modulus], ctx):
            return True
    return any(_nonlinear(c, ctx) for c in _children(node))
