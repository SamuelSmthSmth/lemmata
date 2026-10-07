"""What each line of a proof used: the premises behind a checked statement.

``ProofChecker(dependencies=True)`` fills ``StepResult.premises`` with the
facts a statement that checked was proved from, and ``premises_complete``
with whether that list is the whole story:

- a step SymPy proved names the equalities it substituted (none, for an
  identity);
- a step the engine matched to a fact already established names that fact;
- a step an induction proved names its base cases and its step;
- any other step Z3 proved names the premises in the unsat core of its
  proof, over the facts it could see (``aether.kernel.evidence``);
- a step that continues a chain names the line the chain had reached;
- ``Obtain … from h1`` names h1, and a result cited by name is named as such;
- a block names what its lines used from outside it, and QED the fact that
  states the claim (or the induction that proves it).

Each premise is ``{"kind", "line", "label", "fact"}``: ``kind`` is
``"hypothesis"`` (a fact established in this proof, on ``line``: a case
condition is its block's), ``"chain"`` (the chain so far, as of ``line``),
``"result"`` (an earlier theorem or an import, known by ``label``) or
``"citation"`` (a result cited with ``by …``; ``key`` says which source).

A statement whose evidence the engine cannot recover (a divisibility settled
by remainders, a solver that found no core) keeps what is certain -- the
chain, a citation -- with ``premises_complete`` False, so a reader is never
shown a guess as the reason.  A statement that only introduces something
(``Let``, ``Given``, ``Assume``, a definition) uses nothing and is complete.
A statement that did not check has no premises.

The unsat cores are asked on a Z3 context of the audit's own
(``logic.SolverContext``): a query on the check's context could change how a
later line is decided.  Nothing here changes a verdict or a message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from aether.core.ast import (
    AssumeNode,
    BinaryOpNode,
    DeduceNode,
    ExprNode,
    FuncDefNode,
    ImportNode,
    ObtainNode,
    QuantifierNode,
    RelationNode,
    StatementNode,
    StepNode,
    SubProofNode,
    SymbolNode,
    VarDeclNode,
)
from aether.engine.context import CHAIN, ChainError, HypothesisInfo, MonotonicityError, ProofContext, VarInfo
from aether.engine.logic import SolverContext, _exprs_match, chain_fact, substitute_expr
from aether.kernel import evidence

if TYPE_CHECKING:
    from aether.engine.checker import StepResult

#: Backends whose verdict can come from ``verify_algebraic_equality`` (the kernel
#: renames them by fragment); one that did leaves its sources on the context.
_ALGEBRA_BACKENDS = {"SymPy", "Kernel: ring", "Kernel: calculus.eval"}
def _algebra_backend(backend: str) -> bool:
    """Whether *backend* can have come from ``verify_algebraic_equality``: one
    of the above, or the kernel's named rules (``Kernel: product rule``,
    ``Kernel: group axioms``), which rename a line the engine's algebra
    checked too.  When it did, its sources are on the context."""
    if backend in _ALGEBRA_BACKENDS:
        return True
    if not backend.startswith("Kernel: "):
        return False
    from aether.kernel.calculus import RULES as CALCULUS_RULES
    from aether.kernel.structures import RULES as STRUCTURE_RULES

    names = backend[len("Kernel: ") :].split(", ")
    return all(n in CALCULUS_RULES or n in STRUCTURE_RULES for n in names)


#: Backends whose verdict came from ``verify_induction_schema``.
_INDUCTION_BACKENDS = {"Induction", "Kernel: induction"}
#: How ``verify_entailment`` says it matched an established fact.
_RESTATED = "Verified from established hypothesis"


@dataclass
class Before:
    """The state a statement started from."""

    hypotheses: list[HypothesisInfo]
    chain: Optional[ExprNode]
    chain_line: Optional[int]
    obligation: Optional[ExprNode] = None
    chained: bool = False


@dataclass
class Dependencies:
    """Tracks where each fact came from and names the premises of each statement."""

    #: The line each fact was established on, None for one the proof was
    #: given from outside (an earlier theorem, an import).  The facts are kept
    #: alive so their ids stay unique.
    _origin: dict[int, tuple[HypothesisInfo, Optional[int]]] = field(default_factory=dict)
    #: The contexts seen so far (one per theorem), kept alive likewise.
    _contexts: dict[int, ProofContext] = field(default_factory=dict)
    #: The lines of the blocks being checked, innermost last.
    _blocks: list[Optional[int]] = field(default_factory=list)
    #: The line each chain state was reached on.
    _chains: dict[int, tuple[object, Optional[int]]] = field(default_factory=dict)
    #: Where the audit's own solver queries run, apart from the check's.
    _scratch: SolverContext = field(default_factory=SolverContext)
    #: Results lent to the current step by a citation: id -> (fact, citation).
    lent: dict[int, tuple[HypothesisInfo, dict[str, str]]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def before(self, stmt: StatementNode, ctx: ProofContext) -> Before:
        self._adopt(ctx)
        ctx.algebra_sources = None  # type: ignore[assignment]
        ctx.induction_sources = None
        if isinstance(stmt, SubProofNode):
            self._blocks.append(stmt.line)
        chain = ctx.chain
        state = Before(
            hypotheses=list(ctx.all_hypotheses()),
            chain=chain_fact(ctx),
            chain_line=self._chains[id(chain)][1] if chain is not None and id(chain) in self._chains else None,
        )
        if isinstance(stmt, StepNode):
            try:
                lhs, rel, rhs, _ = ctx.resolve_step(stmt.lhs, stmt.relation, stmt.rhs)
            except (ChainError, MonotonicityError):
                return state
            state.obligation = RelationNode(op=rel, left=lhs, right=rhs) if rel and lhs is not None else rhs
            state.chained = stmt.lhs is None and bool(rel)
        elif isinstance(stmt, DeduceNode):
            claim = stmt.claim
            if isinstance(claim, RelationNode) and isinstance(claim.left, SymbolNode) and claim.left.name == "<prev>":
                if ctx.chain is None:
                    return state
                claim = RelationNode(op=claim.op, left=ctx.chain.head_lhs, right=claim.right)
                state.chained = True
            state.obligation = _instance(claim, stmt.witness)
        elif isinstance(stmt, ObtainNode):
            state.obligation = QuantifierNode(
                quantifier="exists", var=stmt.variable, var_type=stmt.type_name or "Int", formula=stmt.condition
            )
        return state

    def record(self, ctx: ProofContext, stmt: StatementNode) -> None:
        """Note the line that established each fact and chain state that is new."""
        if isinstance(stmt, SubProofNode) and self._blocks:
            self._blocks.pop()
        self._note(ctx, stmt.line)
        for frame in ctx._frames:
            if frame.chain is not None and id(frame.chain) not in self._chains:
                self._chains[id(frame.chain)] = (frame.chain, stmt.line)

    def _note(self, ctx: ProofContext, line: Optional[int]) -> None:
        for h in ctx.all_hypotheses():
            if id(h) not in self._origin and id(h) not in self.lent:
                self._origin[id(h)] = (h, line)

    def _adopt(self, ctx: ProofContext) -> None:
        """Facts a statement finds that no earlier statement established.

        In a context seen for the first time they were given to the proof
        (earlier theorems, imports).  Inside a block they are what the block
        opened with: its case condition, or a base case's value."""
        if id(ctx) not in self._contexts:
            self._contexts[id(ctx)] = ctx
            self._note(ctx, None)
        elif self._blocks:
            self._note(ctx, self._blocks[-1])

    def _core(self, claim: ExprNode, premises: list[HypothesisInfo], ctx: ProofContext, chain=None):
        """The unsat core of *claim* over *premises*, asked on the audit's own context."""
        with self._scratch:
            return evidence.premises_used(claim, premises, ctx, chain=chain)

    # ------------------------------------------------------------------
    # Naming premises
    # ------------------------------------------------------------------

    def describe(self, premise: object, ctx: ProofContext, state: Before) -> Optional[dict[str, Any]]:
        if premise is CHAIN or premise == evidence.PREVIOUS_LINE:
            return self._chain_premise(state)
        if isinstance(premise, VarInfo):
            # A `Given … where x = …` condition is also a fact in its own right.
            match = next((h for h in ctx.all_hypotheses() if h.proposition is premise.condition), None)
            if match is None:
                return None
            premise = match
        if not isinstance(premise, HypothesisInfo):
            return None
        lent = self.lent.get(id(premise))
        if lent is not None:
            return _citation(lent[1])
        origin = self._origin.get(id(premise))
        if origin is None or origin[1] is None:
            return {"kind": "result", "line": None, "label": premise.label, "fact": str(premise.proposition)}
        return {"kind": "hypothesis", "line": origin[1], "label": premise.label, "fact": str(premise.proposition)}

    def _chain_premise(self, state: Before) -> Optional[dict[str, Any]]:
        if state.chain is None:
            return None
        return {"kind": "chain", "line": state.chain_line, "label": None, "fact": str(state.chain)}

    # ------------------------------------------------------------------
    # The audit
    # ------------------------------------------------------------------

    def audit(
        self,
        result: "StepResult",
        stmt: StatementNode,
        ctx: ProofContext,
        state: Before,
        candidates: Optional[list[HypothesisInfo]] = None,
    ) -> None:
        """Fill *result*'s premises from what the statement was proved with."""
        if result.status.value == "INVALID":
            result.premises, result.premises_complete = [], False
            return
        if isinstance(stmt, (VarDeclNode, FuncDefNode, AssumeNode, ImportNode)):
            result.premises, result.premises_complete = [], True
            return
        if isinstance(stmt, SubProofNode):
            self._audit_block(result, stmt)
            return

        found: list[dict[str, Any]] = []
        complete = False
        if state.chained:
            found.append(self._chain_premise(state))
        pool = self._with_premise(stmt, candidates if candidates is not None else state.hypotheses, ctx, state)
        if isinstance(stmt, ObtainNode) and stmt.source_label is not None:
            source = ctx.get_hypothesis(stmt.source_label)
            if source is not None:
                found.append(self.describe(source, ctx, state))
                complete = True
        elif _algebra_backend(result.backend) and ctx.algebra_sources is not None:
            found.extend(self.describe(s, ctx, state) for s in ctx.algebra_sources)
            complete = True
        elif result.backend in _INDUCTION_BACKENDS and ctx.induction_sources:
            found.extend(self.describe(s, ctx, state) for s in ctx.induction_sources)
            complete = True
        elif state.obligation is not None and result.message.startswith(_RESTATED):
            # The engine matched the line to a fact already established, and
            # that fact is what it used (the solver might not need even that).
            match = next((h for h in pool if _exprs_match(state.obligation, h.proposition, ctx)), None)
            if match is not None:
                found.append(self._expand(match, stmt, ctx, state))
                complete = True
        if not complete and state.obligation is not None:
            used = self._core(state.obligation, pool, ctx, chain=state.chain)
            if used is not None:
                found.extend(self._expand(u, stmt, ctx, state) for u in used)
                complete = True
        result.premises = _dedupe([p for p in found if p is not None])
        result.premises_complete = complete

    def name_citation(self, result: "StepResult") -> None:
        """A line that cites a result by name names it among its premises.

        The core may do without it (the line was true anyway), but the
        student's reason was that result."""
        if result.citation and not any(p["kind"] == "citation" for p in result.premises):
            result.premises = result.premises + [_citation(result.citation)]

    def _with_premise(
        self, stmt: StatementNode, pool: list[HypothesisInfo], ctx: ProofContext, state: Before
    ) -> list[HypothesisInfo]:
        """`Since A, B` established A on the same line: B may use it."""
        if not isinstance(stmt, DeduceNode) or stmt.premise is None:
            return pool
        seen = {id(h) for h in pool}
        return pool + [h for h in ctx.all_hypotheses() if id(h) not in seen and h.proposition is stmt.premise]

    def _expand(self, used: object, stmt: StatementNode, ctx: ProofContext, state: Before) -> Optional[dict[str, Any]]:
        """A premise, or for the `Since A` part of the same line, what A used."""
        if (
            isinstance(stmt, DeduceNode)
            and isinstance(used, HypothesisInfo)
            and used.proposition is stmt.premise
            and id(used) not in self._origin
        ):
            inner = self._core(stmt.premise, state.hypotheses, ctx, chain=state.chain)
            if inner:
                return {"kind": "group", "items": [self.describe(u, ctx, state) for u in inner]}
            return None
        return self.describe(used, ctx, state)

    def _audit_block(self, result: "StepResult", stmt: SubProofNode) -> None:
        """A block uses what its lines use from outside it."""
        lines = {r.line for r in _flatten(result.sub_results)} | {stmt.line}
        outside = [
            p
            for r in _flatten(result.sub_results)
            for p in r.premises
            if p["kind"] != "hypothesis" or p["line"] not in lines
        ]
        result.premises = _dedupe([p for p in outside if p["kind"] != "chain" or p["line"] not in lines])
        result.premises_complete = all(r.premises_complete for r in _flatten(result.sub_results))

    def before_qed(self, ctx: ProofContext) -> None:
        self._adopt(ctx)
        ctx.induction_sources = None

    def audit_qed(self, result: "StepResult", claim: ExprNode, ctx: ProofContext) -> None:
        """QED: the facts the theorem's claim follows from."""
        if result.status.value == "INVALID":
            result.premises, result.premises_complete = [], False
            return
        state = Before(hypotheses=list(ctx.all_hypotheses()), chain=None, chain_line=None)
        used: Optional[list[object]] = list(ctx.induction_sources) if ctx.induction_sources else None
        if used is None:
            stated = _stated(claim, state.hypotheses, ctx)
            used = [stated] if stated is not None else self._core(claim, state.hypotheses, ctx)
        result.premises = _dedupe([p for p in (self.describe(u, ctx, state) for u in used or []) if p])
        result.premises_complete = used is not None


def _stated(claim: ExprNode, hypotheses: list[HypothesisInfo], ctx: ProofContext) -> Optional[HypothesisInfo]:
    """The latest fact that states the claim, or what is left of it once QED
    peels its ``forall``s and ``=>``s as it checks it."""
    target: Optional[ExprNode] = claim
    while target is not None:
        match = next((h for h in reversed(hypotheses) if _exprs_match(target, h.proposition, ctx)), None)
        if match is not None:
            return match
        if isinstance(target, QuantifierNode) and target.quantifier == "forall":
            target = target.formula
        elif isinstance(target, BinaryOpNode) and target.op in ("=>", "->", "implies", "\\implies"):
            target = target.right
        else:
            target = None
    return None


def _citation(cited: dict[str, str]) -> dict[str, Any]:
    return {"kind": "citation", "line": None, "label": cited["label"], "fact": cited["claim"], "key": cited["key"]}


def _instance(claim: ExprNode, witness: Optional[ExprNode]) -> ExprNode:
    """`exists m, P(m) [witness: t]` is decided as P(t)."""
    if witness is None or not (isinstance(claim, QuantifierNode) and claim.quantifier == "exists"):
        return claim
    if isinstance(witness, RelationNode) and isinstance(witness.left, SymbolNode) and witness.left.name == claim.var:
        witness = witness.right
    return substitute_expr(claim.formula, claim.var, witness)


def _flatten(results: list["StepResult"]) -> list["StepResult"]:
    out: list["StepResult"] = []
    for r in results:
        out.append(r)
        out.extend(_flatten(r.sub_results))
    return out


def _dedupe(premises: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten `Since` groups and drop repeats, keeping the first of each."""
    flat: list[dict[str, Any]] = []
    for p in premises:
        flat.extend(i for i in p["items"] if i) if p.get("kind") == "group" else flat.append(p)
    out: list[dict[str, Any]] = []
    for p in flat:
        if p not in out:
            out.append(p)
    # The chain, then this proof's facts in line order, then results from outside it.
    order = {"chain": 0, "hypothesis": 1, "result": 2, "citation": 3}
    return sorted(out, key=lambda p: (order.get(p["kind"], 4), p["line"] or 0))
