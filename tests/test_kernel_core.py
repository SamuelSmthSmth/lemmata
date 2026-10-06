"""The kernel's typed core and its tactics (aether.kernel.core, aether.kernel.tactics)."""

import pytest

from aether.engine.context import ProofContext
from aether.kernel import core
from aether.kernel.core import Divisible, Rel, Ty, Var, elaborate
from aether.kernel.tactics import weakest
from aether.parser.parser import AetherParser

_parser = AetherParser()


def claim(text: str):
    return _parser.parse(f"Therefore {text}\n").statements[0].claim


def ctx_with(**decls: str) -> ProofContext:
    ctx = ProofContext()
    for name, ty in decls.items():
        ctx.declare_variable(name, ty)
    return ctx


def tactic(ctx: ProofContext, goal: str, *premises: str):
    g = elaborate(claim(goal), ctx)
    assert g is not None, goal
    return weakest(g.prop, [elaborate(claim(p), ctx).prop for p in premises])


class TestElaboration:
    def test_types_are_read_from_the_declarations(self):
        ctx = ctx_with(n="Nat", x="Real")
        prop = elaborate(claim("n - 1 < x"), ctx).prop
        assert isinstance(prop, Rel)
        # A natural minus a natural is an integer, not a natural.
        assert prop.left.ty == Ty.INT and prop.right == Var("x", Ty.REAL)

    def test_a_division_records_its_side_condition(self):
        ctx = ctx_with(x="Real")
        elaborated = elaborate(claim("(x^2 - 4) / (x - 2) = x + 2"), ctx)
        assert len(elaborated.conditions) == 1
        assert elaborated.conditions[0].op == "!="

    @pytest.mark.parametrize("text, modulus", [
        ("Even(n)", 2), ("Odd(n)", 2), ("MultipleOf(n, 6)", 6), ("Divides(3, n)", 3), ("Congruent(n, 1, 4)", 4),
    ])
    def test_divisibility_by_a_number(self, text, modulus):
        prop = elaborate(claim(text), ctx_with(n="Int")).prop
        assert isinstance(prop, Divisible) and prop.modulus == modulus

    @pytest.mark.parametrize("text", [
        "forall x : Real, x = x",          # a quantifier
        "sum(k, 1, n, k) = n",             # binds k
        "x < oo",                          # infinity
        "MultipleOf(n, m)",                # a symbolic modulus
        "n^m = 1",                         # a symbolic exponent
        "Even(x)",                         # divisibility of a real
    ])
    def test_outside_the_core(self, text):
        assert elaborate(claim(text), ctx_with(n="Int", m="Int", x="Real")) is None

    def test_an_unknown_function_is_an_uninterpreted_real(self):
        prop = elaborate(claim("sin(x) <= 1"), ctx_with(x="Real")).prop
        assert isinstance(prop.left, core.App) and prop.left.ty == Ty.REAL


class TestTactics:
    def test_ring(self):
        assert tactic(ctx_with(x="Real"), "(x + 1)^2 = x^2 + 2*x + 1") == "ring"

    def test_field_needs_the_division(self):
        assert tactic(ctx_with(x="Real"), "(x^2 - 4) / (x - 2) = x + 2") == "field"

    def test_subst_uses_an_equation_in_scope(self):
        assert tactic(ctx_with(n="Int", k="Int"), "n^2 = 4 * k^2", "n = 2 * k") == "subst"

    def test_linarith_treats_products_as_atoms(self):
        # The Archimedean step: (n + 1)e <= b gives ne <= b - e linearly,
        # because ne is the same atom on both sides.
        assert tactic(ctx_with(n="Int", e="Real", b="Real"), "n * e <= b - e", "(n + 1) * e <= b") == "linarith"

    def test_nlinarith_when_the_atoms_must_multiply(self):
        assert tactic(ctx_with(x="Real"), "x^2 > 25", "x > 5") == "nlinarith"

    def test_divisibility_from_the_line_above(self):
        assert tactic(ctx_with(n="Int", k="Int"), "Even(n^2 + n)", "n^2 + n = 2 * (2 * k^2 + k)") == "linarith"

    def test_nothing_proves_what_does_not_follow(self):
        ctx = ctx_with(x="Real", n="Int")
        assert tactic(ctx, "x^2 > 25", "x = x") is None
        assert tactic(ctx, "x > 1", "x > 0") is None

    def test_a_remainder_argument_is_the_residues_tactic(self):
        # True for every integer, but only by checking remainders: residues
        # (strength 4) proves it, and nothing weaker does, so the levels that
        # cap at 3 still refuse it as too big a step.
        ctx = ctx_with(n="Int")
        assert tactic(ctx, "MultipleOf(n^3 - n, 6)") == "residues"
        g = elaborate(claim("MultipleOf(n^3 - n, 6)"), ctx)
        assert weakest(g.prop, [], up_to=3) is None
        assert tactic(ctx, "MultipleOf(n^2 + n + 1, 3)") is None  # false at n = 1

    def test_residues_steps_aside_when_a_premise_mentions_the_variable(self):
        assert tactic(ctx_with(n="Int"), "MultipleOf(n^3 - n, 6)", "n > 5") is None

    def test_range_facts_of_standard_functions(self):
        ctx = ctx_with(x="Real")
        assert tactic(ctx, "exp(x) > 0") == "linarith"
        assert tactic(ctx, "abs(sin(x)) <= 1") == "linarith"
        assert tactic(ctx, "sqrt(x) >= 0", "x >= 0") == "linarith"
        assert tactic(ctx, "sin(x) <= 0") is None

    def test_a_square_root_is_non_negative_only_where_it_is_real(self):
        # sqrt(x - 1) >= 0 fails at x = 0, where the root is not real: an
        # unconditional sqrt >= 0 proved it (shadow mode caught it).
        ctx = ctx_with(x="Real")
        assert tactic(ctx, "sqrt(x - 1) >= 0") is None
        assert tactic(ctx, "sqrt(x - 1) >= 0", "x >= 1") == "linarith"

    def test_min_and_max_mean_what_they_say(self):
        ctx = ctx_with(e="Real", d="Real")
        assert tactic(ctx, "d <= e / 2", "e > 0", "d = min(1, e / 2)") == "linarith"

    def test_simp_for_identities_of_standard_functions(self):
        ctx = ctx_with(x="Real", n="Nat")
        assert tactic(ctx, "cosh(x)^2 - sinh(x)^2 = 1") == "simp"
        assert tactic(ctx, "factorial(n) = n * factorial(n - 1)") == "simp"

    def test_a_function_the_notes_name_proves_nothing_about_itself(self):
        assert tactic(ctx_with(x="Real"), "f(x)^2 = x", "x >= 0") is None

    def test_standard_functions_read_as_the_engine_reads_them(self):
        ctx = ctx_with(x="Real")
        assert tactic(ctx, "factorial(3) = 6") == "ring"
        assert tactic(ctx, "gcd(8, 2) = 2") == "ring"

    @pytest.mark.parametrize("goal", ["gcd(n, k) = 1", "lcm(n, k) = n * k", "binomial(n, 2) = n"])
    def test_number_theory_on_symbols_is_not_polynomial_algebra(self, goal):
        # SymPy's gcd of two symbols is the polynomial gcd, 1, and its lcm the
        # product: false for integers, and the Notation pack's traps.  A shadow
        # run of the tactics against the engine caught ring proving both.
        assert tactic(ctx_with(n="Int", k="Int"), goal) is None


SEVEN = """\
Theorem: "7^n - 3^n is divisible by 4"
Claim: forall n : Nat, MultipleOf(7^n - 3^n, 4)
Proof:
    Base case n = 0:
        Step: 7^0 - 3^0 = 0
        Therefore MultipleOf(7^0 - 3^0, 4)
    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(7^k - 3^k, 4)
        Obtain m : Int such that 7^k - 3^k = 4 * m from ih
        Step: 7^(k + 1) - 3^(k + 1) = 7 * (7^k - 3^k) + 4 * 3^k
        Step: = 4 * (7 * m + 3^k)
        Therefore MultipleOf(7^(k + 1) - 3^(k + 1), 4)
    Therefore forall n : Nat, MultipleOf(7^n - 3^n, 4)
QED
"""


class TestTheKernelChangesNoVerdict:
    """The kernel's own queries (evidence, tactics) run on Z3 contexts of their
    own.  On the check's context, the many small questions of a canonical core
    changed what Z3 had seen, and this induction's last step came back
    unknown with the kernel on, though it holds without it."""

    @pytest.mark.parametrize("level", ["exam", "course", "scratch"])
    def test_an_induction_the_engine_proves_still_proves(self, level):
        from aether import ProofChecker

        assert ProofChecker().check_source(SEVEN)[0].is_valid
        report = ProofChecker(kernel=level).check_source(SEVEN)[0]
        assert report.is_valid, report.format_report()


class TestUniversalPremises:
    """A universal fact is used through its instances at the goal's terms."""

    def test_an_instance_at_the_goal(self):
        from aether import ProofChecker

        src = "Given f : Real -> Real\nAssume h: forall x : Real, f(x) > 0\nTherefore f(2) > 0\n"
        line = ProofChecker(kernel="course").check_source(src)[0].results[-1]
        assert line.status.value == "VALID" and line.backend == "Kernel: linarith", line.backend

    def test_a_recurrence_at_k(self):
        from aether import ProofChecker

        src = (
            "Given u : Nat -> Int\nAssume rec: forall n : Nat, n >= 1 => u(n + 1) = 2 * u(n) - 1\n"
            "Let k : Nat\nAssume hk: k >= 1\nTherefore u(k + 1) = 2 * u(k) - 1\n"
        )
        line = ProofChecker(kernel="course").check_source(src)[0].results[-1]
        assert line.status.value == "VALID" and line.backend == "Kernel: linarith", line.backend

    def test_a_natural_quantifier_is_not_instantiated_at_a_real(self):
        from aether.kernel.review import _instances

        ctx = ctx_with(x="Real", k="Nat")
        fact = claim("forall n : Nat, n >= 0")
        terms = [(claim("x = x").left, Ty.REAL), (claim("k = k").left, Ty.NAT)]
        assert [str(i) for i in _instances(fact, terms, ctx)] == ["k >= 0"]


class TestTheKernelUsesTheCore:
    def test_the_archimedean_step_is_linear(self):
        from aether import ProofChecker

        src = "Let n : Int\nLet e, b : Real\nAssume h: (n + 1) * e <= b\nStep: n * e <= b - e\n"
        line = ProofChecker(kernel="exam").check_source(src)[0].results[-1]
        assert line.status.value == "VALID" and line.backend == "Kernel: linarith"
