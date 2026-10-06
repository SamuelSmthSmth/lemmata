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


def premises_used(
    claim: ExprNode,
    premises: list[HypothesisInfo],
    ctx: ProofContext,
    chain: Optional[ExprNode] = None,
    timeout_ms: int = 1500,
) -> Optional[list[object]]:
    """The premises (and possibly ``PREVIOUS_LINE``) a proof of *claim* needs, or None.

    *chain* is what the chain had established before the line (``chain_fact``
    taken then): by the time a line is reviewed, its own link is committed."""
    claim = ctx.expand_user_functions(claim) or claim
    solver = new_solver(timeout_ms)
    extra: list = []
    for vinfo in ctx.all_variables().values():
        if vinfo.math_type == MathType.Nat:
            solver.add(_make_z3_var(vinfo.name, MathType.Nat) >= 0)  # type: ignore[operator]
    tracked: dict[str, object] = {}
    for i, h in enumerate(premises):
        terms = hypothesis_terms(h.proposition, ctx, extra)
        _populate_algebra_axioms(solver, h.proposition, ctx)
        if terms:
            name = f"__premise_{i}"
            solver.assert_and_track(z3.And(*terms), z3.Bool(name))
            tracked[name] = h
    if chain is not None:
        try:
            solver.assert_and_track(ast_to_z3(chain, ctx, extra_constraints=extra), z3.Bool("__chain"))
            tracked["__chain"] = PREVIOUS_LINE
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
        if check_solver(solver) != z3.unsat:
            return None
    except z3.Z3Exception:
        return None
    return [tracked[str(lit)] for lit in solver.unsat_core() if str(lit) in tracked]
