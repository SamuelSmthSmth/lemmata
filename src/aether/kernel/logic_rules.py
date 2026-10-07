"""Quantified statements by the rules of natural deduction.

A goal outside the typed core because it has a quantifier or a connective
in it is taken apart the way a written proof takes it apart:

- **∧-intro**: ``A and B`` holds when each does;
- **∀-intro**: ``forall x : T, B`` holds when B does for a fresh x of type T,
  about which nothing else is known;
- **⇒-intro**: ``A => B`` holds when B follows once A is assumed.

What is left at the leaves is inside the core, and a core tactic proves it
from the line's visible premises and the assumptions made on the way down
(``tactics.weakest``).  So the ε–δ line ``ε/3 > 0 and forall x, (|x - a| < ε/3
=> |f(x) - f(a)| < ε)`` is ∧-intro, then ∀-intro, then ⇒-intro, then
``linarith`` with ``|x - a| < ε/3`` assumed.  An ``exists`` without a witness
is not taken apart (choosing one is the proof's job, not a rule's), and a
leaf the core cannot read leaves the whole line to the engine.

``verify(goal, ctx, known)`` returns the rules used, or None.  As with the
other named rules, nothing here changes a verdict.
"""

from __future__ import annotations

from typing import Optional

from aether.core.ast import BinaryOpNode, ExprNode, QuantifierNode, SymbolNode
from aether.engine.context import ProofContext
from aether.engine.logic import substitute_expr
from aether.kernel import core, tactics

_AND = ("and", "\\land", "/\\", "∧")
_IMPLIES = ("=>", "->", "implies", "\\implies", "⇒")
#: How many quantifiers and connectives one line may be taken apart through.
_DEPTH = 8

#: The rules this module names, besides the core tactics at the leaves.
RULES = ("∧-intro", "∀-intro", "⇒-intro")


class _Stop(Exception):
    """The rules do not reach this goal."""


def _fresh(name: str, ctx: ProofContext) -> str:
    for i in range(100):
        candidate = f"{name}_{i}"
        if ctx.get_var(candidate) is None and ctx.get_hypothesis(candidate) is None:
            return candidate
    raise _Stop


def _prove(goal: ExprNode, ctx: ProofContext, premises: list, assumed: list[ExprNode], used: list[str], depth: int) -> None:
    if depth > _DEPTH:
        raise _Stop
    if isinstance(goal, BinaryOpNode) and goal.op.lower() in _AND:
        used.append("∧-intro")
        _prove(goal.left, ctx, premises, assumed, used, depth + 1)
        _prove(goal.right, ctx, premises, assumed, used, depth + 1)
        return
    if isinstance(goal, BinaryOpNode) and goal.op.lower() in _IMPLIES:
        used.append("⇒-intro")
        _prove(goal.right, ctx, premises, assumed + [goal.left], used, depth + 1)
        return
    if isinstance(goal, QuantifierNode) and goal.quantifier == "forall":
        used.append("∀-intro")
        fresh = _fresh(goal.var, ctx)
        body = substitute_expr(goal.formula, goal.var, SymbolNode(name=fresh))
        assumed = [substitute_expr(a, goal.var, SymbolNode(name=fresh)) for a in assumed]
        ctx.push_scope()
        try:
            ctx.declare_variable(fresh, goal.var_type or "Real")
            _prove(body, ctx, premises, assumed, used, depth + 1)
        finally:
            ctx.pop_scope()
        return
    if isinstance(goal, QuantifierNode):
        raise _Stop  # an exists to be witnessed: the proof's job
    # A leaf: inside the core, decided by a tactic from what the line can see.
    leaf = core.elaborate(goal, ctx)
    if leaf is None:
        raise _Stop
    extra = []
    for a in assumed:
        read = core.elaborate(a, ctx)
        if read is None:
            raise _Stop  # an assumption the core cannot read
        extra.append(read.prop)
    known = premises + extra
    # On a line of its own, a division's denominator and a root's radicand
    # are the engine's domain check.  Under a quantifier the rules introduced,
    # nothing else checks them, and the tactics read m * (1/m) as 1 and
    # sqrt(x)^2 as x: each must be shown from what is known first.
    for obligation in _obligations(leaf.prop):
        if tactics.weakest(obligation, known) is None:
            raise _Stop
    tactic = tactics.weakest(leaf.prop, known)
    if tactic is None:
        raise _Stop
    used.append(tactic)


def _obligations(item: object) -> list:
    """What *item* needs to be defined: each denominator non-zero, each
    square root's radicand non-negative, each logarithm's argument positive."""
    from fractions import Fraction

    zero = core.Num(Fraction(0), core.Ty.NAT)
    out: list = []
    if isinstance(item, core.Div):
        out.append(core.Rel("!=", item.den, zero))
    if isinstance(item, core.Pow) and item.exp < 0:
        out.append(core.Rel("!=", item.base, zero))
    if isinstance(item, core.App) and len(item.args) == 1:
        fn = item.fn.lower()
        if fn == "sqrt":
            out.append(core.Rel(">=", item.args[0], zero))
        elif fn in ("log", "ln"):
            out.append(core.Rel(">", item.args[0], zero))
    for value in vars(item).values() if hasattr(item, "__dataclass_fields__") else []:
        children = value if isinstance(value, tuple) else (value,)
        for child in children:
            if hasattr(child, "__dataclass_fields__"):
                out.extend(_obligations(child))
    return out


def verify(goal: ExprNode, ctx: ProofContext, known: list) -> Optional[str]:
    """The natural-deduction rules (and the tactics at the leaves) that show
    *goal* from the line's visible premises *known*; None when they do not."""
    if not (isinstance(goal, QuantifierNode) or (isinstance(goal, BinaryOpNode) and goal.op.lower() in _AND + _IMPLIES)):
        return None
    from aether.kernel.review import _core_premises

    used: list[str] = []
    try:
        _prove(goal, ctx, _core_premises(ctx, known, None, goal), [], used, 0)
    except (_Stop, RecursionError):
        return None
    except Exception:  # noqa: BLE001 - a goal the rules cannot read
        return None
    rules = [r for r in RULES if r in used]
    strongest = max((u for u in used if u not in RULES), key=lambda t: dict(tactics.TACTICS).get(t, 0), default=None)
    return ", ".join(rules + ([strongest] if strongest else []))
