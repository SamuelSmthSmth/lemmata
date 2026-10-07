"""The tactics: each decides one kind of obligation, and says how strong it is.

They read core terms (``core``) only.  ``weakest`` tries them in order of
strength and names the first that proves the goal from the premises given.
Inside the typed core that answer is the verdict (stage 3, ``review``): a line
passes because a named tactic proved it, and the audit says which:

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

Every Z3 query runs on a Z3 context of its own (``logic.SolverContext``): a
tactic must not change how a later line is decided, nor depend on what was
decided before.  The facts the tactics add about standard functions (ranges,
what a square root squares to, bounds on the root of a number) hold for every
real, so they only remove models that were never real; shadow mode
(tests/lecture_notes/kernel_shadow.py) checks the tactics against the engine on
every pinned proof.
"""

from __future__ import annotations

from typing import Optional

import sympy as sp
import z3

from aether.engine.logic import SolverContext, _range_facts, check_solver, new_solver
from aether.kernel.core import Conn, Divisible, Not, Prop, Rel, Ty, has_division, to_sympy, variables

#: The order ``weakest`` tries them in, with their strengths.
TACTICS: tuple[tuple[str, int], ...] = (
    ("ring", 1),
    ("field", 1),
    ("subst", 1),
    ("simp", 1),
    ("linarith", 2),
    ("nlinarith", 3),
    ("residues", 4),
)

_Z3_TIMEOUT_MS = 1500


def weakest(goal: Prop, premises: list[Prop], up_to: int = 4) -> Optional[str]:
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


#: Above this many operations, simplify is not tried (it can take seconds).
_SIMP_OPS = 80


def simp(goal: Prop, premises: list[Prop]) -> bool:
    """An identity of the standard functions: n! = n (n - 1)!, cosh^2 - sinh^2 = 1,
    sinh x = (e^x - e^-x)/2.  SymPy's own simplification, as the engine's
    SymPy route uses; gcd and lcm on symbols stay uninterpreted (core)."""
    diff = _difference(goal)
    if diff is None or sp.count_ops(diff) > _SIMP_OPS:
        return False
    if sp.simplify(diff) == 0 or sp.combsimp(diff) == 0:
        return True
    return sp.simplify(diff.rewrite(sp.exp)) == 0


#: The residue check's limits, as the engine's (logic._try_residue_divisibility).
_RESIDUE_MODULUS = 1000
_RESIDUE_CASES = 20000


def residues(goal: Prop, premises: list[Prop]) -> bool:
    """`m` divides an integer polynomial for every integer: check each remainder.

    P(n) mod m depends only on n mod m (for P = Q/d with Q integral, m d | Q
    repeats with period m d), so the remainders decide it for every integer.
    Only when no premise mentions the variables, as the engine: a premise
    could rule a remainder out, and then this would not be the argument."""
    if not isinstance(goal, Divisible) or goal.modulus > _RESIDUE_MODULUS:
        return False
    names = variables(goal.term)
    if not names or any(not ty.integral for ty in names.values()):
        return False
    if any(set(variables(p)) & set(names) for p in premises):
        return False
    poly = sp.expand(to_sympy(goal.term))
    symbols = sorted(poly.free_symbols, key=lambda s: s.name)
    if not poly.is_polynomial(*symbols):
        return False
    denominator = sp.ilcm(*[sp.Rational(c).q for c in sp.Poly(poly, *symbols).coeffs()]) if symbols else 1
    period = goal.modulus * int(denominator)
    integral = sp.expand(poly * denominator)
    if period ** len(symbols) > _RESIDUE_CASES:
        return False
    from itertools import product

    for values in product(range(period), repeat=len(symbols)):
        value = integral.subs(dict(zip(symbols, values)))
        if int(value) % period != 0:
            return False
    return True


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
            self.side.extend(self._range(expr, self.atoms[key]))
        return self.atoms[key]

    def _range(self, expr, value: z3.ExprRef) -> list:
        """True facts about a standard function's value, for any argument (the
        engine's own, ``logic._range_facts``): sin and cos in [-1, 1], exp > 0
        and exp(t) >= 1 + t, cosh >= 1, |tanh| < 1, log(t) <= t - 1 for t > 0,
        and a square root >= 0.  They only remove models that were never real."""
        if isinstance(expr, sp.Pow) and expr.args[1] == sp.Rational(1, 2):
            return self._root(expr.args[0], value)
        if isinstance(expr, sp.Function) and len(expr.args) == 1:
            name = type(expr).__name__.lower()
            if name in ("sin", "cos", "exp", "cosh", "tanh", "log"):
                try:
                    return _range_facts(name, z3.ToReal(value) if z3.is_int(value) else value, self.expr(expr.args[0]))
                except Exception:  # noqa: BLE001 - an argument the fragment cannot state
                    return []
        return []

    def _root(self, radicand_expr, value: z3.ExprRef) -> list:
        """What a square root is, only where it is real: sqrt(x - 1) >= 0 is not
        true at x = 0 (the engine refuses it there; shadow mode caught an
        unconditional fact proving it).  Where the radicand r >= 0, the root is
        >= 0 and, non-linearly, squares to r: so sqrt(a) sqrt(b) = sqrt(ab) for
        a, b >= 0.  The root of a positive number also gets exact rational
        bounds (1.414213 < sqrt(2) < 1.414214), so sqrt(2) > 1 is arithmetic."""
        if radicand_expr.is_Rational and radicand_expr > 0:
            facts = [value > 0]
            lo, hi = _root_bounds(sp.Rational(radicand_expr))
            facts += [value > self.num(lo), value < self.num(hi)]
            if not self.linear:
                facts.append(value * value == self.num(radicand_expr))
            return facts
        try:
            radicand = self.expr(radicand_expr)
        except Exception:  # noqa: BLE001
            return []
        facts = [z3.Implies(radicand >= 0, value >= 0)]  # type: ignore[operator]
        if not self.linear:
            facts.append(z3.Implies(radicand >= 0, value * value == radicand))  # type: ignore[operator]
        return facts

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
        if isinstance(e, (sp.Min, sp.Max)):
            # min and max mean what they say: the smaller, the larger.
            parts = [self.expr(a) for a in e.args]
            out = parts[0]
            for p in parts[1:]:
                out = z3.If(out <= p, out, p) if isinstance(e, sp.Min) else z3.If(out >= p, out, p)
            return out
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
            if not self.linear and exp.is_Rational and exp.q == 2 and exp != sp.S.Half:
                # SymPy writes 1/sqrt(x) as x^(-1/2): read b^(k/2) as sqrt(b)^k,
                # so it is the same atom as sqrt(b), with the same facts.
                return self.expr(sp.Pow(sp.sqrt(base), exp.p, evaluate=False))
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


#: The root bounds' resolution: sqrt(c) is pinned between two multiples of this.
_ROOT_STEP = 10**6


def _root_bounds(c: sp.Rational) -> tuple[sp.Rational, sp.Rational]:
    """Rationals lo < sqrt(c) < hi, a millionth apart, checked exactly."""
    from math import isqrt

    n = isqrt(int(c * _ROOT_STEP**2))  # floor(sqrt(c) * STEP), exactly
    lo, hi = sp.Rational(n, _ROOT_STEP), sp.Rational(n + 1, _ROOT_STEP)
    if lo * lo == c:  # a perfect square SymPy did not already simplify
        lo = lo - sp.Rational(1, _ROOT_STEP)
    assert lo * lo < c < hi * hi
    return lo, hi


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


_RUN = {
    "ring": ring,
    "field": field,
    "subst": subst,
    "simp": simp,
    "linarith": linarith,
    "nlinarith": nlinarith,
    "residues": residues,
}

__all__ = ["TACTICS", "weakest", "ring", "field", "subst", "simp", "linarith", "nlinarith", "residues", "variables", "Ty"]
