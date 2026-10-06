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

Stage 2 adds the structural rules:

4. **Goal closure.**  QED no longer decides the claim: once its `forall`s
   and `=>`s are matched to the proof's `Given`s and `Assume`s, what is left
   must be something the level would accept as a line (``review_closure``).
5. **The case rule.**  A conclusion that every case of a complete split
   showed is accepted by or-elimination ("By cases: …"), not by a solver.
6. **Working, recognised.**  Peeling the last term off a sum and replacing
   a sum by what the inductive hypothesis says of it are the working an
   induction shows, not evaluations; and a line the engine settled by
   checking remainders is classified by the simpler argument when the
   premises it could see already give it.
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
from aether.kernel import core, evidence, policy, premises, tactics
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
        by_cases = self._by_cases(claim, ctx)
        with premises.restricted(ctx, allowed):
            result = check(target, ctx)
        result = replace(result, statement=stmt)
        if by_cases is not None and result.status.value != "INVALID":
            # Or-elimination: each case showed the claim, and the cases cover
            # every possibility.  The rule settles it; no solver decides it.
            return replace(result, message=by_cases, backend="Kernel: cases")
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

        fragment = self._fragment(result.backend or "", result.message, obligation, before, after, ctx, allowed, witnessed)
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

    def _by_tactics(self, goal: ExprNode, ctx: ProofContext, known: list[HypothesisInfo]) -> Optional[str]:
        """The weakest core tactic that proves *goal* from what the line could see."""
        elaborated = core.elaborate(goal, ctx)
        if elaborated is None:
            return None
        return tactics.weakest(elaborated.prop, _core_premises(ctx, known, self._chain, goal))

    @staticmethod
    def _by_cases(claim: ExprNode, ctx: ProofContext) -> Optional[str]:
        """The case rule's message, if *claim* is what every case of a complete split showed."""
        frame = ctx.current_frame
        if not frame.cases or not frame.cases_exhaustive:
            return None
        if not all(_exprs_match(shown, claim, ctx) for _, shown in frame.cases):
            return None
        conditions = ", ".join(str(c) for c, _ in frame.cases)
        return f"By cases: {claim} holds in each case ({conditions}), and the cases cover every possibility."

    def review_closure(self, target: ExprNode, backend: str, message: str, ctx: ProofContext) -> Optional[tuple[str, str]]:
        """QED as goal closure: what is left of the claim must already be shown.

        After the claim's `forall`s and `=>`s are matched to the proof's
        `Given`s and `Assume`s, *target* is what the proof had to reach.  The
        engine settled it (by *backend*); the kernel accepts that only if it is
        a step the level would allow as a line of the proof.  A bare `QED`
        cannot decide a whole quantified claim, a divisibility by remainders,
        or anything else no line of the proof shows.  Returns None to accept,
        or the backend and message of the refusal."""
        self._chain = chain_fact(ctx)
        known = ctx.all_hypotheses()
        before, after = (target.left, target.right) if isinstance(target, RelationNode) else (None, None)
        fragment = self._fragment(backend, message, target, before, after, ctx, known, None)
        if self.policy.allows(fragment, "deduce"):
            return None
        if fragment.tactic == "calculus.eval":
            why = fragment.advice[0].upper() + fragment.advice[1:]
        else:
            why = f"Deciding it here needs {fragment.needs}. {fragment.advice}".rstrip()
        return (
            f"Kernel: {fragment.tactic}",
            f"QED: the proof never shows '{target}', which the claim needs, and QED does not "
            f"prove it for you at the {self.policy.name} level. {why} Then finish with a line "
            f"that states it.",
        )

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
        backend: str,
        message: str,
        obligation: ExprNode,
        before: Optional[ExprNode],
        after: Optional[ExprNode],
        ctx: ProofContext,
        known: list[HypothesisInfo],
        witnessed: Optional[tuple[ExprNode, str, ExprNode]],
    ) -> Fragment:
        """Which kind of reasoning settled the line.

        The engine tries its routes in a fixed order, so the one that answered
        is not always the simplest that would have: `Even(n^2 + n)` right after
        `n^2 + n = 2 * (2k^2 + k)` is settled by checking remainders, though it
        follows from that line directly.  A remainder check that the solver can
        reproduce from the premises the line could see is classified by that
        argument instead."""
        if backend == "Induction":
            return policy.INDUCTION
        if message.startswith("Verified from established hypothesis"):
            return policy.HYPOTHESIS
        if before is not None and after is not None:
            # A sum or derivative replaced by what an equation in scope says it
            # is (the inductive hypothesis, usually) is substitution, not an
            # evaluation: rewrite with those equations before looking for a gap.
            gap = working_gap(_rewrite_with(before, known), after, ctx)
            if gap:
                return policy.evaluation(gap)
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
        # The typed core: the weakest tactic that proves what is left, from the
        # premises the line could see, names the reasoning it needed.
        tactic = self._by_tactics(expanded, ctx, known)
        if tactic is not None:
            return policy.TACTIC_FRAGMENTS[tactic]
        # Outside the core (or beyond its tactics): stage 1's reading of how
        # the engine settled it.
        if backend == "Residues":
            if evidence.premises_used(obligation, known, ctx, chain=self._chain) is None:
                return policy.RESIDUES
            backend = "Z3"
        if backend.startswith("SymPy") and backend != "SymPy+Logic":
            return policy.RING
        if _has_quantifier(expanded):
            return policy.QUANTIFIED
        if _nonlinear(expanded, ctx):
            return policy.NONLINEAR
        return policy.LINEAR


def _matches(a: ExprNode, b: ExprNode, ctx: ProofContext) -> bool:
    """Whether *a* states the fact *b* does: the engine's ``_exprs_match``, but
    deciding equal sides by plain expansion on the typed core.  The engine's own
    test checks each pair of sides with ``verify_algebraic_equality``, which on
    a mismatch (the usual case here, one line against every fact) goes on to
    search for a counterexample: most of the kernel's time went there."""
    ua = ctx.expand_user_functions(a) or a
    ub = ctx.expand_user_functions(b) or b
    if str(ua) == str(ub):
        return True
    if isinstance(ua, QuantifierNode) or isinstance(ub, QuantifierNode):
        if not (isinstance(ua, QuantifierNode) and isinstance(ub, QuantifierNode) and ua.quantifier == ub.quantifier):
            # `Even(n)` states `exists k, n = 2k`: the engine's test unfolds
            # the predicate; a quantifier against anything else is no match.
            if isinstance(ua, FunctionCallNode) or isinstance(ub, FunctionCallNode):
                return _exprs_match(ua, ub, ctx)
            return False
        alpha = SymbolNode(name="_alpha_var")
        return _matches(substitute_expr(ua.formula, ua.var, alpha), substitute_expr(ub.formula, ub.var, alpha), ctx)
    if isinstance(ua, RelationNode) and isinstance(ub, RelationNode):
        from aether.engine.context import canonical_rel

        if canonical_rel(ua.op) != canonical_rel(ub.op):
            return False
        left = core.same_value(ua.left, ub.left, ctx)
        right = core.same_value(ua.right, ub.right, ctx)
        if left is not None and right is not None:
            return left and right
        return _exprs_match(ua, ub, ctx)  # outside the core: the engine's own test
    if isinstance(ua, FunctionCallNode) and isinstance(ub, FunctionCallNode):
        if ua.func.lower() != ub.func.lower() or len(ua.args) != len(ub.args):
            return False
        verdicts = [core.same_value(x, y, ctx) for x, y in zip(ua.args, ub.args)]
        if all(v is not None for v in verdicts):
            return all(verdicts)
        return _exprs_match(ua, ub, ctx)
    if type(ua) is not type(ub):
        return False
    return _exprs_match(ua, ub, ctx)


def _core_premises(
    ctx: ProofContext, known: list[HypothesisInfo], chain: Optional[ExprNode], goal: Optional[ExprNode] = None
) -> list:
    """What a line could see, as core propositions.  A universal fact is
    outside the core, so it is used through its instances at the goal's own
    terms (`forall x, f(x) > 0` gives `f(2) > 0` for a goal about f(2))."""
    out = []
    props = [h.proposition for h in known] + ([chain] if chain is not None else [])
    terms = _goal_terms(goal, ctx) if goal is not None else []
    for prop in props:
        candidates = [prop]
        if isinstance(prop, QuantifierNode) and prop.quantifier == "forall" and terms:
            candidates = _instances(prop, terms, ctx)
        for candidate in candidates:
            elaborated = core.elaborate(candidate, ctx)
            if elaborated is not None:
                out.append(elaborated.prop)
    return out


#: Instances of one universal fact, at most.
_INSTANCES = 40


def _goal_terms(goal: ExprNode, ctx: ProofContext) -> list[tuple[ExprNode, "core.Ty"]]:
    """The terms a universal fact may be instantiated at: the goal's variables
    and the arguments of its applications (k and k + 1 for u(k + 1) = 2u(k) - 1),
    each with its core type."""
    found: dict[str, tuple[ExprNode, core.Ty]] = {}

    def add(node: ExprNode) -> None:
        term = core.elaborate_term(node, ctx)
        if term is not None:
            found.setdefault(str(node), (node, term.ty))

    def walk(node: object) -> None:
        if isinstance(node, (SymbolNode,)) or type(node).__name__ == "GreekSymbolNode":
            add(node)  # type: ignore[arg-type]
        if isinstance(node, FunctionCallNode):
            for arg in node.args:
                add(arg)
        for child in _children(node):
            walk(child)

    walk(ctx.expand_user_functions(goal) or goal)
    return list(found.values())


def _instances(prop: QuantifierNode, terms: list, ctx: ProofContext, depth: int = 0) -> list[ExprNode]:
    """*prop*'s instances at *terms* whose type fits the bound variable's, two
    quantifiers deep.  A ground instance of a true universal is true, so this
    adds nothing false: `forall n : Nat` is never instantiated at a real."""
    from aether.core.types import normalize_type_name

    try:
        bound = core._FROM_MATH.get(normalize_type_name(prop.var_type), None) if prop.var_type else core.Ty.REAL
    except Exception:  # noqa: BLE001 - a structure's carrier, a set: not a number type
        bound = None
    if bound is None:
        return []
    out: list[ExprNode] = []
    for node, ty in terms:
        if ty > bound:
            continue
        body = substitute_expr(prop.formula, prop.var, node)
        if isinstance(body, QuantifierNode) and body.quantifier == "forall" and depth == 0:
            out.extend(_instances(body, terms, ctx, depth=1))
        else:
            out.append(body)
        if len(out) >= _INSTANCES:
            break
    return out[:_INSTANCES]


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


_OPERATORS = ("sum", "diff", "integrate", "lim")


def _has_operator(node: ExprNode) -> bool:
    from aether.core.ast import IntegralNode, LimitNode

    if isinstance(node, (IntegralNode, LimitNode)):
        return True
    if isinstance(node, FunctionCallNode) and node.func.lower() in _OPERATORS:
        return True
    return any(_has_operator(c) for c in _children(node))


def _rewrite_with(node: ExprNode, known: list[HypothesisInfo]) -> ExprNode:
    """*node* as the working would rewrite it: a sum to `k + 1` peeled into the
    sum to `k` plus its last term, then each side of an established relation
    that holds a sum, derivative, integral or limit replaced by the other side
    (an equation, or a bound: `ih: sum(…) <= 2 - 1/k` is used by replacing the
    sum with its bound; whether the step's direction is right is the solver's
    question, not this one)."""
    node = _peel(node)
    rules: dict[str, ExprNode] = {}
    for h in known:
        prop = h.proposition
        if isinstance(prop, RelationNode) and prop.op in ("=", "==", "<", "<=", ">", ">="):
            if _has_operator(prop.left) and not _has_operator(prop.right):
                rules[str(prop.left)] = prop.right
            elif _has_operator(prop.right) and not _has_operator(prop.left):
                rules[str(prop.right)] = prop.left
    if not rules:
        return node
    return _replace(node, rules)


def _peel(node: ExprNode) -> ExprNode:
    """`sum(r, a, k + 1, f)` is `sum(r, a, k, f) + f(k + 1)`: the step every
    induction on a sum takes, written or not."""
    if (
        isinstance(node, FunctionCallNode)
        and node.func.lower() == "sum"
        and len(node.args) == 4
        and isinstance(node.args[0], SymbolNode)
        and isinstance(node.args[2], BinaryOpNode)
        and node.args[2].op == "+"
        and isinstance(node.args[2].right, NumberNode)
        and node.args[2].right.value == "1"
    ):
        index, lower, upper, body = node.args
        shorter = replace(node, args=[index, lower, upper.left, body])
        return BinaryOpNode(op="+", left=shorter, right=substitute_expr(body, index.name, upper))
    if not hasattr(node, "__dataclass_fields__"):
        return node
    changes: dict[str, object] = {}
    for name in node.__dataclass_fields__:
        value = getattr(node, name)
        if isinstance(value, ExprNode):
            new = _peel(value)
            if new is not value:
                changes[name] = new
    return replace(node, **changes) if changes else node


def _replace(node: ExprNode, rules: dict[str, ExprNode]) -> ExprNode:
    hit = rules.get(str(node))
    if hit is not None:
        return hit
    if not hasattr(node, "__dataclass_fields__"):
        return node
    changes: dict[str, object] = {}
    for name in node.__dataclass_fields__:
        value = getattr(node, name)
        if isinstance(value, ExprNode):
            new = _replace(value, rules)
            if new is not value:
                changes[name] = new
        elif isinstance(value, list) and any(isinstance(v, ExprNode) for v in value):
            new_list = [_replace(v, rules) if isinstance(v, ExprNode) else v for v in value]
            if any(a is not b for a, b in zip(new_list, value)):
                changes[name] = new_list
    return replace(node, **changes) if changes else node


def _undischarged(node: ExprNode, ctx: ProofContext, known: list[HypothesisInfo]) -> Optional[ExprNode]:
    """*node* without the conjuncts that are facts already established.

    `exists δ, δ > 0 and (forall x, …) [witness: ε/3]` after a subproof that
    proved the `forall x` part asks only for ε/3 > 0: the quantified part is
    the subproof's, not a leap.  None when nothing is left."""
    if any(_matches(node, h.proposition, ctx) for h in known):
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
