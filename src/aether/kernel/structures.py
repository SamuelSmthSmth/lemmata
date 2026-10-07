"""Algebraic structures as named rules: groups by word reduction, subgroups by
closure, rings and fields by their axioms.

**Groups.**  An element built from a group's ``op``, ``inv`` and identity is a
*word*: a list of atoms, each to the power +1 or -1.  The group axioms are
exactly what reduces a word: associativity flattens it, the identity drops
out, and an atom beside its inverse cancels.  Two words that reduce to the
same word are equal in every group (the free group's normal form), so that is
the rule ``group axioms``; no solver is asked.  Anything that is not ``op``,
``inv`` or the identity is an atom -- a variable, or an application such as
``f(g1)`` -- with its arguments themselves reduced, so ``f(op(g, inv(g)))``
is the atom ``f(e)``.

Hypotheses join in as equations between words, and a universal one (``hom:
forall x, y : G, f(op(x, y)) = star(f(x), f(y))``) through its instances at the
goal's own terms, instantiated only at terms known to lie in the group it
quantifies over.  An equation with a single atom on one side rewrites that
atom (``f(g) = eH`` removes it; ``f(op(x, y))`` becomes ``f(x) f(y)``); any
other is a relator ``w1 w2^-1 = e``, and a goal whose word is a conjugate of a
relator holds (cancellation: ``a x = a y`` gives ``x = y``).  That is the rule
``group axioms and hypotheses``.

**Subgroups.**  ``t in H`` holds when t's word is the identity, a member, a
member's inverse, or a product of up to three of those (``subgroup
closure``); in a normal subgroup also a conjugate of a member (``normal
subgroup``).  Members are the hypotheses ``m in H`` and the elements declared
in H.

**Rings and fields.**  ``add``, ``mul``, ``zero``, ``one`` and ``neg`` are the
ring operations: two sides that agree as polynomials in non-commuting
unknowns (commuting, in a field) are equal in every ring (``ring axioms``).  A
field's ``inv(x)`` is the reciprocal only where a hypothesis says x is not
zero.

``verify(goal, ctx)`` returns the rule that shows the goal, or None; nothing
here changes a verdict, as with ``calculus``.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

import sympy as sp

from aether.core.ast import (
    BinaryOpNode,
    ExprNode,
    FunctionCallNode,
    GreekSymbolNode,
    NumberNode,
    QuantifierNode,
    RelationNode,
    SymbolNode,
)
from aether.engine.context import GroupSignature, ProofContext, canonical_rel
from aether.engine.logic import substitute_expr

Word = tuple[tuple[str, int], ...]

#: The rules this module names (what a line's backend reads, after "Kernel: ").
RULES = (
    "group axioms",
    "group axioms and hypotheses",
    "subgroup closure",
    "normal subgroup",
    "ring axioms",
    "field axioms",
)

#: Instances of the universal hypotheses, at most, per goal.
_INSTANCES = 80
#: Rewriting passes before giving up (rules can cycle; equalities stay sound).
_PASSES = 25


class _NotWord(Exception):
    """Not an element built from this group's operations."""


#: The facts the line under review could see (set by ``verify``).  Never the
#: line's own conclusion: by review time it is recorded in the context, and a
#: goal must not be its own hypothesis.
_PREMISES: ContextVar[Optional[tuple[list[ExprNode], str]]] = ContextVar("_PREMISES", default=None)


def _hypotheses(ctx: ProofContext) -> list[ExprNode]:
    known = _PREMISES.get()
    if known is None:
        return [h.proposition for h in ctx.all_hypotheses()]
    props, goal = known
    return [p for p in props if str(p) != goal]


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


def _reduce(word: Word, abelian: bool = False) -> Word:
    if abelian:
        totals: dict[str, int] = {}
        for atom, power in word:
            totals[atom] = totals.get(atom, 0) + power
        return tuple(sorted((a, p) for a, p in totals.items() if p))
    out: list[tuple[str, int]] = []
    for atom, power in word:
        if out and out[-1][0] == atom and out[-1][1] == -power:
            out.pop()
        else:
            out.append((atom, power))
    return tuple(out)


def _inverse(word: Word) -> Word:
    return tuple((a, -p) for a, p in reversed(word))


def _cyclic(word: Word) -> Word:
    """The word with matching ends cancelled: a conjugate's core."""
    while len(word) >= 2 and word[0][0] == word[-1][0] and word[0][1] == -word[-1][1]:
        word = word[1:-1]
    return word


def _rotation_of(a: Word, b: Word) -> bool:
    if len(a) != len(b):
        return False
    if not a:
        return True
    doubled = b + b
    return any(doubled[i : i + len(a)] == a for i in range(len(b)))


def _word(node: ExprNode, group: GroupSignature, ctx: ProofContext) -> Word:
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        if node.name == group.identity and ctx.get_var(node.name) is None:
            return ()
        return ((node.name, 1),)
    if isinstance(node, FunctionCallNode):
        if node.func == group.op and len(node.args) == 2:
            return _reduce(_word(node.args[0], group, ctx) + _word(node.args[1], group, ctx), group.abelian)
        if node.func == group.inverse and len(node.args) == 1:
            return _inverse(_word(node.args[0], group, ctx))
        if node.func[0].isupper():
            raise _NotWord  # a predicate, not an element
        return ((_atom_key(node, ctx), 1),)
    raise _NotWord


#: Each atom's weight, for orienting rewrite rules (see ``_weight``).
_WEIGHTS: dict[str, tuple] = {}


def _atom_key(node: FunctionCallNode, ctx: ProofContext) -> str:
    """f(t) with t in its reduced form, so f(op(g, inv(g))) is f(e)."""
    parts = [_arg_key(a, ctx) for a in node.args]
    key = f"{node.func}({', '.join(p for p, _ in parts)})"
    size = sum(len(w) for _, w in parts if w is not None)
    inverses = sum(1 for _, w in parts if w is not None for _a, p in w if p < 0)
    _WEIGHTS[key] = (1 + size, inverses, len(key), key)
    return key


def _arg_key(arg: ExprNode, ctx: ProofContext) -> tuple[str, Optional[Word]]:
    for group in ctx.group_signatures().values():
        if not _uses(arg, group, ctx):
            continue
        try:
            word = _word(arg, group, ctx)
        except _NotWord:
            continue
        return _show(word, group), word
    return str(arg), ((str(arg), 1),)


def _weight(atom: str) -> tuple:
    """A strict order on atoms: an application weighs more the longer and the
    more inverted its argument word; a variable weighs least.  Rules only
    rewrite an atom into strictly lighter ones, so rewriting terminates."""
    return _WEIGHTS.get(atom, (0, 0, len(atom), atom))


def _uses(node: ExprNode, group: GroupSignature, ctx: ProofContext) -> bool:
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        return node.name == group.identity and ctx.get_var(node.name) is None
    if isinstance(node, FunctionCallNode):
        return node.func in (group.op, group.inverse) or any(_uses(a, group, ctx) for a in node.args)
    return False


def _show(word: Word, group: GroupSignature) -> str:
    if not word:
        return group.identity
    return " ".join(a if p == 1 else f"{a}^{p}" for a, p in word)


# ---------------------------------------------------------------------------
# Hypotheses: rewrite rules and relators
# ---------------------------------------------------------------------------


def _subterms(node: object) -> list[ExprNode]:
    out: list[ExprNode] = []
    if isinstance(node, (SymbolNode, GreekSymbolNode, FunctionCallNode)):
        out.append(node)  # type: ignore[arg-type]
    for value in vars(node).values() if hasattr(node, "__dict__") else []:
        if isinstance(value, ExprNode):
            out.extend(_subterms(value))
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, ExprNode):
                    out.extend(_subterms(v))
    return out


def _in_carrier(term: ExprNode, carrier: str, ctx: ProofContext) -> bool:
    """Whether *term* is known to lie in *carrier*: declared there, assumed
    there, the identity, or built from such by the group's operations."""
    group = ctx.group_signatures().get(carrier)
    if isinstance(term, (SymbolNode, GreekSymbolNode)):
        if group is not None and term.name == group.identity and ctx.get_var(term.name) is None:
            return True
        info = ctx.get_var(term.name)
        if info is not None and info.carrier == carrier:
            return True
        return any(
            isinstance(prop, RelationNode)
            and canonical_rel(prop.op) == "in"
            and str(prop.left) == str(term)
            and isinstance(prop.right, (SymbolNode, GreekSymbolNode))
            and prop.right.name == carrier
            for prop in _hypotheses(ctx)
        )
    if isinstance(term, FunctionCallNode) and group is not None:
        if term.func == group.op and len(term.args) == 2:
            return all(_in_carrier(a, carrier, ctx) for a in term.args)
        if term.func == group.inverse and len(term.args) == 1:
            return _in_carrier(term.args[0], carrier, ctx)
    return False


def _instances(prop: QuantifierNode, terms: list[ExprNode], ctx: ProofContext, depth: int = 0) -> list[ExprNode]:
    """*prop* at the goal's terms that lie where its variable ranges."""
    if prop.quantifier != "forall":
        return []
    out: list[ExprNode] = []
    for term in terms:
        if prop.var_type and not _in_carrier(term, prop.var_type, ctx):
            continue
        body = substitute_expr(prop.formula, prop.var, term)
        if isinstance(body, QuantifierNode) and depth == 0:
            out.extend(_instances(body, terms, ctx, depth=1))
        elif not isinstance(body, QuantifierNode):
            out.append(body)
        if len(out) >= _INSTANCES:
            break
    return out[:_INSTANCES]


def _equations(goal: ExprNode, group: GroupSignature, ctx: ProofContext) -> list[tuple[Word, Word]]:
    terms: list[ExprNode] = []
    seen: set[str] = set()
    for t in _subterms(goal):
        if str(t) not in seen:
            seen.add(str(t))
            terms.append(t)
    props: list[ExprNode] = []
    for prop in _hypotheses(ctx):
        prop = ctx.elaborate_group_notation(prop)
        if isinstance(prop, QuantifierNode):
            props.extend(_instances(prop, terms, ctx))
        else:
            props.append(prop)
    out: list[tuple[Word, Word]] = []
    for prop in props:
        if isinstance(prop, RelationNode) and canonical_rel(prop.op) in ("=", "=="):
            try:
                out.append((_word(prop.left, group, ctx), _word(prop.right, group, ctx)))
            except _NotWord:
                continue
    return out


def _rewrite(word: Word, rules: dict[str, Word], abelian: bool) -> Word:
    for _ in range(_PASSES):
        changed = False
        out: list[tuple[str, int]] = []
        for atom, power in word:
            if atom in rules:
                out.extend(rules[atom] if power == 1 else _inverse(rules[atom]))
                changed = True
            else:
                out.append((atom, power))
        word = _reduce(tuple(out), abelian)
        if not changed:
            break
    return word


def _group_identity(left: ExprNode, right: ExprNode, ctx: ProofContext) -> Optional[str]:
    for group in ctx.group_signatures().values():
        try:
            goal = _reduce(_word(left, group, ctx) + _inverse(_word(right, group, ctx)), group.abelian)
        except _NotWord:
            continue
        if not goal:
            return "group axioms"
        rules: dict[str, Word] = {}
        relators: list[Word] = []
        for w1, w2 in _equations(RelationNode(op="=", left=left, right=right), group, ctx):
            for lone, other in ((w1, w2), (w2, w1)):
                if (
                    len(lone) == 1
                    and lone[0][1] == 1
                    and lone[0][0] not in rules
                    and all(_weight(a) < _weight(lone[0][0]) for a, _ in other)
                ):
                    rules[lone[0][0]] = other
                    break
            else:
                relator = _reduce(w1 + _inverse(w2), group.abelian)
                if relator:
                    relators.append(relator)
        reduced = _rewrite(goal, rules, group.abelian)
        if not reduced:
            return "group axioms and hypotheses"
        core = _cyclic(reduced)
        for relator in relators:
            r = _cyclic(_rewrite(relator, rules, group.abelian))
            if r and (_rotation_of(core, r) or _rotation_of(core, _cyclic(_inverse(r)))):
                return "group axioms and hypotheses"
            if group.abelian and (core == r or core == _reduce(_inverse(r), True)):
                return "group axioms and hypotheses"
    return None


# ---------------------------------------------------------------------------
# Subgroups
# ---------------------------------------------------------------------------


def _subgroup_kind(name: str, ctx: ProofContext) -> Optional[str]:
    for prop in _hypotheses(ctx):
        if (
            isinstance(prop, FunctionCallNode)
            and prop.func.lower() in ("subgroup", "normalsubgroup")
            and prop.args
            and isinstance(prop.args[0], (SymbolNode, GreekSymbolNode))
            and prop.args[0].name == name
        ):
            return prop.func.lower()
    return None


def _member(term: ExprNode, carrier: ExprNode, ctx: ProofContext) -> Optional[str]:
    if isinstance(carrier, BinaryOpNode) and carrier.op.lower() in ("intersect", "\\cap", "∩"):
        a, b = _member(term, carrier.left, ctx), _member(term, carrier.right, ctx)
        return a if a and b else None
    if isinstance(carrier, BinaryOpNode) and carrier.op.lower() in ("union", "\\cup", "∪"):
        return _member(term, carrier.left, ctx) or _member(term, carrier.right, ctx)
    if not isinstance(carrier, (SymbolNode, GreekSymbolNode)):
        return None
    kind = _subgroup_kind(carrier.name, ctx)
    group = ctx.group_signatures().get(carrier.name)
    if kind is None or group is None:
        return None
    try:
        target = _word(term, group, ctx)
    except _NotWord:
        return None
    if not target:
        return "subgroup closure"
    members: list[Word] = []
    for prop in _hypotheses(ctx):
        if (
            isinstance(prop, RelationNode)
            and canonical_rel(prop.op) == "in"
            and isinstance(prop.right, (SymbolNode, GreekSymbolNode))
            and prop.right.name == carrier.name
        ):
            try:
                members.append(_word(prop.left, group, ctx))
            except _NotWord:
                continue
    for name in ctx.all_variables():
        info = ctx.get_var(name)
        if info is not None and info.carrier == carrier.name:
            members.append(((name, 1),))
    pool = [m for m in members] + [_inverse(m) for m in members]
    products: list[Word] = list(pool)
    for a in pool:
        for b in pool:
            products.append(_reduce(a + b, group.abelian))
            if len(pool) <= 8:
                products.extend(_reduce(a + b + c, group.abelian) for c in pool)
    if target in products:
        return "subgroup closure"
    if kind == "normalsubgroup":
        core = _cyclic(target)
        if any(_rotation_of(core, _cyclic(m)) for m in pool):
            return "normal subgroup"
    return None


# ---------------------------------------------------------------------------
# Rings and fields
# ---------------------------------------------------------------------------


def _ring_value(node: ExprNode, names: dict[str, str], commutative: bool, ctx: ProofContext) -> sp.Expr:
    if isinstance(node, (SymbolNode, GreekSymbolNode)):
        if node.name == names.get("zero") and ctx.get_var(node.name) is None:
            return sp.Integer(0)
        if node.name == names.get("one") and ctx.get_var(node.name) is None:
            return sp.Integer(1)
        return sp.Symbol(node.name, commutative=commutative)
    if isinstance(node, NumberNode) and node.value.isdigit():
        return sp.Integer(int(node.value))
    if isinstance(node, FunctionCallNode):
        args = [_ring_value(a, names, commutative, ctx) for a in node.args]
        if node.func == names.get("add") and len(args) == 2:
            return args[0] + args[1]
        if node.func == names.get("mul") and len(args) == 2:
            return args[0] * args[1]
        if node.func == names.get("neg") and len(args) == 1:
            return -args[0]
        if node.func == names.get("inv") and len(args) == 1 and _nonzero(node.args[0], names, ctx):
            return 1 / args[0]
    raise _NotWord


def _nonzero(node: ExprNode, names: dict[str, str], ctx: ProofContext) -> bool:
    """A hypothesis says *node* is not the ring's zero."""
    for prop in _hypotheses(ctx):
        if isinstance(prop, RelationNode) and canonical_rel(prop.op) == "!=":
            sides = {str(prop.left), str(prop.right)}
            if sides == {str(node), names.get("zero", "")}:
                return True
    return False


def _ring_identity(left: ExprNode, right: ExprNode, ctx: ProofContext) -> Optional[str]:
    fields = ("carrier", "add", "mul", "zero", "one", "neg", "inv")
    for prop in _hypotheses(ctx):
        if not (isinstance(prop, FunctionCallNode) and prop.func.lower() in ("ring", "field")):
            continue
        names = {
            f: a.name for f, a in zip(fields, prop.args) if isinstance(a, (SymbolNode, GreekSymbolNode))
        }
        field = prop.func.lower() == "field"
        try:
            difference = _ring_value(left, names, field, ctx) - _ring_value(right, names, field, ctx)
        except (_NotWord, ZeroDivisionError):
            continue
        if sp.expand(difference) == 0:
            return "field axioms" if field else "ring axioms"
    return None


# ---------------------------------------------------------------------------
# The goal
# ---------------------------------------------------------------------------


def verify(goal: ExprNode, ctx: ProofContext, known: Optional[list] = None) -> Optional[str]:
    """The structure rule that shows *goal* from the facts *known* (the line's
    visible premises: HypothesisInfo or propositions), or None."""
    props = [getattr(k, "proposition", k) for k in (known if known is not None else ctx.all_hypotheses())]
    token = _PREMISES.set(([ctx.elaborate_group_notation(p) for p in props], str(ctx.elaborate_group_notation(goal))))
    try:
        return _verify(goal, ctx)
    finally:
        _PREMISES.reset(token)


def _verify(goal: ExprNode, ctx: ProofContext) -> Optional[str]:
    # `a * b`, `a^-1` and `a^2` for group elements are op and inv (the
    # context's own reading, which leaves real numbers' products alone).
    goal = ctx.elaborate_group_notation(goal)
    if not isinstance(goal, RelationNode):
        return None
    try:
        rel = canonical_rel(goal.op)
        if rel in ("=", "=="):
            return _group_identity(goal.left, goal.right, ctx) or _ring_identity(goal.left, goal.right, ctx)
        if rel == "in":
            return _member(goal.left, goal.right, ctx)
    except RecursionError:
        return None
    return None
