"""Which premises a proof used, from Z3's unsat core.

Each candidate premise is asserted behind its own tracking literal; if the
negated claim is unsatisfiable, the core names the premises the proof needed.
A claim the plain translation cannot settle (a witness, an induction, a
decision procedure) gives no core, and the audit says nothing about premises
rather than guess.
"""

from __future__ import annotations

from typing import Optional

import z3

from aether.engine.trace import traced

from aether.core.ast import ExprNode
from aether.core.types import MathType
from aether.engine.context import HypothesisInfo, ProofContext
from aether.engine.logic import (
    LogicConversionError,
    _make_z3_var,
    _populate_algebra_axioms,
    ast_to_z3,
    check_solver,
    hypothesis_terms,
    new_solver,
)

#: Stands for the chain so far in a core: the line before, in the student's terms.
PREVIOUS_LINE = "the previous line"


@traced("Z3", "core", lambda claim, premises, ctx, **_: f"{claim}, given {len(premises)} fact{'' if len(premises) == 1 else 's'}", none="no core")
def premises_used(
    claim: ExprNode,
    premises: list[HypothesisInfo],
    ctx: ProofContext,
    chain: Optional[ExprNode] = None,
    timeout_ms: int = 1500,
) -> Optional[list[object]]:
    """The premises (and possibly ``PREVIOUS_LINE``) a proof of *claim* needs, or None.

    *chain* is what the chain had established before the line (``chain_fact``
    taken then): by the time a line is reviewed, its own link is committed.

    The answer is canonical.  Z3's unsat core is one set of premises that
    suffices, and which one it finds depends on the order its terms were
    made, so the same line could be reported "from line 14" in one process
    and "from line 16" in another.  Instead, starting from every premise,
    each is dropped in turn, oldest first and the previous line last, if the
    claim still follows without it.  Whether it follows is a fact about the
    mathematics, so the set that remains (minimal, and preferring the most
    recent facts and the line before) is the same wherever it is computed."""
    claim = ctx.expand_user_functions(claim) or claim
    solver = new_solver(timeout_ms)
    extra: list = []
    for vinfo in ctx.all_variables().values():
        if vinfo.math_type == MathType.Nat:
            solver.add(_make_z3_var(vinfo.name, MathType.Nat) >= 0)  # type: ignore[operator]
    tracked: list[tuple[z3.ExprRef, object]] = []
    for i, h in enumerate(premises):
        terms = hypothesis_terms(h.proposition, ctx, extra)
        _populate_algebra_axioms(solver, h.proposition, ctx)
        if terms:
            lit = z3.Bool(f"__premise_{i}")
            solver.add(z3.Implies(lit, z3.And(*terms)))
            tracked.append((lit, h))
    if chain is not None:
        try:
            lit = z3.Bool("__chain")
            solver.add(z3.Implies(lit, ast_to_z3(chain, ctx, extra_constraints=extra)))
            tracked.append((lit, PREVIOUS_LINE))
        except LogicConversionError:
            pass
    try:
        goal = ast_to_z3(claim, ctx, extra_constraints=extra)
    except LogicConversionError:
        return None
    solver.add(z3.Not(goal))
    for c in extra:
        solver.add(c)
    try:
        keep = list(tracked)
        if check_solver(solver, *(lit for lit, _ in keep)) != z3.unsat:
            return None
        for item in list(tracked):
            trial = [k for k in keep if k is not item]
            if check_solver(solver, *(lit for lit, _ in trial)) == z3.unsat:
                keep = trial
    except z3.Z3Exception:
        return None
    return [premise for _, premise in keep]
