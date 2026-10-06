"""The tactics: each decides one kind of obligation, and says how strong it is.

They read core terms (``core``) only.  ``weakest`` tries them in order of
strength and names the first that proves the goal from the premises given, so
the kernel's audit says what a line actually needed:

| tactic      | decides                                                   | strength |
| ----------- | --------------------------------------------------------- | -------- |
| `ring`      | a polynomial identity: both sides expand to the same      | 1        |
| `field`     | an identity with division, under its side conditions       | 1        |
| `subst`     | an identity after substituting `x = t` premises           | 1        |
| `linarith`  | linear arithmetic and logic, products of unknowns as atoms | 2        |
| `nlinarith` | non-linear arithmetic (Z3's NRA / NIA)                     | 3        |

`linarith` treats each product or power of unknowns as an opaque atom, as
Lean's does after `ring_nf`: `(n + 1)ε ≤ β` gives `nε ≤ β − ε` linearly,
because `nε` is the same atom on both sides.  Only when the atoms must be
multiplied out does a line need `nlinarith`.

Every Z3 query runs on a Z3 context of its own (``logic.SolverContext``):
the tactics only label a line, and must not change how a later line is
decided, nor depend on what was decided before.
"""

from __future__ import annotations

from typing import Optional

import sympy as sp
import z3

from aether.engine.logic import SolverContext, check_solver, new_solver
from aether.kernel.core import Conn, Divisible, Not, Prop, Rel, Ty, has_division, to_sympy, variables

#: The order ``weakest`` tries them in, with their strengths.
TACTICS: tuple[tuple[str, int], ...] = (
    ("ring", 1),
    ("field", 1),
    ("subst", 1),
    ("linarith", 2),
    ("nlinarith", 3),
)

_Z3_TIMEOUT_MS = 1500


def weakest(goal: Prop, premises: list[Prop], up_to: int = 3) -> Optional[str]:
    """The weakest tactic (at most strength *up_to*) that proves *goal* from *premises*."""
    for name, strength in TACTICS:
        if strength > up_to:
            break
        try:
            if _RUN[name](goal, premises):
                return name
        except Exception:  # noqa: BLE001 - a tactic that cannot read the goal does not prove it
            continue
    return None


# ---------------------------------------------------------------------------
# Identities (SymPy)
# ---------------------------------------------------------------------------


def _difference(goal: Prop):
    if not (isinstance(goal, Rel) and goal.op == "="):
        return None
    return to_sympy(goal.left) - to_sympy(goal.right)


def ring(goal: Prop, premises: list[Prop]) -> bool:
    if not isinstance(goal, Rel) or has_division(goal.left) or has_division(goal.right):
        return False
    diff = _difference(goal)
    return diff is not None and sp.expand(diff) == 0


def field(goal: Prop, premises: list[Prop]) -> bool:
    diff = _difference(goal)
    return diff is not None and sp.cancel(sp.together(diff)) == 0


def subst(goal: Prop, premises: list[Prop]) -> bool:
    diff = _difference(goal)
    if diff is None:
        return False
    rules = {}
    for p in premises:
        if isinstance(p, Rel) and p.op == "=":
            left, right = to_sympy(p.left), to_sympy(p.right)
            if left.is_Symbol and left not in right.free_symbols:
                rules[left] = right
            elif right.is_Symbol and right not in left.free_symbols:
                rules[right] = left
    if not rules:
        return False
    for _ in range(3):
        diff = diff.subs(rules)
    return sp.cancel(sp.together(sp.expand(diff))) == 0


# ---------------------------------------------------------------------------
# Arithmetic (Z3)
# ---------------------------------------------------------------------------


class _Z3:
    """Core propositions as Z3 terms; *linear* makes non-linear monomials atoms."""

    def __init__(self, linear: bool) -> None:
        self.linear = linear
        self.atoms: dict[str, z3.ExprRef] = {}
        self.side: list[z3.ExprRef] = []

    def var(self, sym) -> z3.ExprRef:
        key = sym.name
        if key not in self.atoms:
            if sym.is_integer:
                self.atoms[key] = z3.Int(key)
                if sym.is_nonnegative:
                    self.side.append(self.atoms[key] >= 0)
            else:
                self.atoms[key] = z3.Real(key)
        return self.atoms[key]

    def atom(self, expr) -> z3.ExprRef:
        key = f"atom!{sp.srepr(expr)}"
        if key not in self.atoms:
            self.atoms[key] = z3.Int(key) if expr.is_integer else z3.Real(key)
            if expr.is_integer and expr.is_nonnegative:
                self.side.append(self.atoms[key] >= 0)
        return self.atoms[key]

    def num(self, expr) -> z3.ExprRef:
        r = sp.Rational(expr)
        return z3.IntVal(int(r)) if r.q == 1 else z3.RealVal(f"{r.p}/{r.q}")

    def expr(self, e) -> z3.ExprRef:
        if e.is_Number:
            return self.num(e)
        if e.is_Symbol:
            return self.var(e)
        if isinstance(e, sp.Add):
            return z3.Sum(*[self.expr(a) for a in e.args])
        if isinstance(e, sp.Abs):
            a = self.expr(e.args[0])
            return z3.If(a >= 0, a, -a)
        if isinstance(e, sp.Mul):
            coeff, rest = e.as_coeff_Mul()
            if coeff != 1:
                # A number times the rest: linear in whatever the rest is.
                return self.num(coeff) * self.expr(rest)
            if self.linear:
                return self.atom(e)  # a product of unknowns: one atom
            out = self.expr(e.args[0])
            for a in e.args[1:]:
                out = out * self.expr(a)
            return out
        if isinstance(e, sp.Pow):
            base, exp = e.args
            if self.linear or not exp.is_Integer:
                return self.atom(e)
            k = int(exp)
            b = self.expr(base)
            out = b
            for _ in range(abs(k) - 1):
                out = out * b
            if k > 0:
                return out
            return 1 / (z3.ToReal(out) if z3.is_int(out) else out)
        # A sequence's value, or anything else SymPy keeps whole: one atom each.
        return self.atom(e)

    def prop(self, p: Prop) -> z3.ExprRef:
        if isinstance(p, Rel):
            d = sp.expand(to_sympy(p.left) - to_sympy(p.right)) if self.linear else to_sympy(p.left) - to_sympy(p.right)
            lhs, zero = self.expr(d), 0
            return {
                "=": lambda: lhs == zero,
                "!=": lambda: lhs != zero,
                "<": lambda: lhs < zero,
                "<=": lambda: lhs <= zero,
                ">": lambda: lhs > zero,
                ">=": lambda: lhs >= zero,
            }[p.op]()
        if isinstance(p, Divisible):
            e = sp.expand(to_sympy(p.term))
            t = self.expr(e)
            if not z3.is_int(t):
                raise ValueError("divisibility of a non-integer")
            return t % p.modulus == 0
        if isinstance(p, Not):
            return z3.Not(self.prop(p.arg))
        if isinstance(p, Conn):
            a, b = (self.prop(x) for x in p.args)
            return {"and": z3.And, "or": z3.Or, "=>": z3.Implies}.get(p.op, lambda x, y: x == y)(a, b)
        raise TypeError(p)


def _z3_proves(goal: Prop, premises: list[Prop], linear: bool) -> bool:
    with SolverContext():
        tr = _Z3(linear)
        solver = new_solver(_Z3_TIMEOUT_MS)
        for p in premises:
            try:
                solver.add(tr.prop(p))
            except (ValueError, TypeError, z3.Z3Exception):
                continue  # a premise the fragment cannot state is not used
        solver.add(z3.Not(tr.prop(goal)))
        for s in tr.side:
            solver.add(s)
        return check_solver(solver) == z3.unsat


def linarith(goal: Prop, premises: list[Prop]) -> bool:
    return _z3_proves(goal, premises, linear=True)


def nlinarith(goal: Prop, premises: list[Prop]) -> bool:
    return _z3_proves(goal, premises, linear=False)


_RUN = {"ring": ring, "field": field, "subst": subst, "linarith": linarith, "nlinarith": nlinarith}

__all__ = ["TACTICS", "weakest", "ring", "field", "subst", "linarith", "nlinarith", "variables", "Ty"]
