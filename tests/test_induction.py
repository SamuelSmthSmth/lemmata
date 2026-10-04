"""Induction as A Level and the notes write it, and the ways it must still fail.

The schema (``verify_induction_schema``) reads a claim from a starting value,
an inductive step with side conditions in any order, and recurrences that use
several earlier values; a sequence the question defines is a definition, not a
hypothesis the claim must license.  Each valid proof below failed before for a
reason in the engine; each invalid one is a way a sloppy rule would let a false
theorem through.
"""

import pytest

from aether import ProofChecker


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


def check(checker: ProofChecker, src: str):
    return checker.check_source(src)[0]


def refusal(report) -> str:
    return next(r.message for r in report.results if r.backend in ("Induction", "QED") and r.status.value == "INVALID")


SUM_OF_SQUARES_FROM_1 = """\
Theorem: "Sum of squares, for every positive integer"
Claim: forall n : Nat, n >= 1 => sum(r, 1, n, r^2) = n * (n + 1) * (2 * n + 1) / 6
Proof:
    Base case n = 1:
        Step: sum(r, 1, 1, r^2) = 1
        Step: = 1 * 2 * 3 / 6
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: sum(r, 1, k, r^2) = k * (k + 1) * (2 * k + 1) / 6
        Step: sum(r, 1, k + 1, r^2) = sum(r, 1, k, r^2) + (k + 1)^2
        Step: = k * (k + 1) * (2 * k + 1) / 6 + (k + 1)^2
        Step: = (k + 1) * (k + 2) * (2 * k + 3) / 6
    Therefore forall n : Nat, n >= 1 => sum(r, 1, n, r^2) = n * (n + 1) * (2 * n + 1) / 6
QED
"""

TWO_STEP = """\
Theorem: "A second-order recurrence"
Claim: forall n : Nat, n >= 1 => u(n) = 3^n - 2^n
Proof:
    Given u : Nat -> Int
    Assume rec: forall n : Nat, u(n + 2) = 5 * u(n + 1) - 6 * u(n)
    Assume u1: u(1) = 1
{second_value}    Base case n = 1:
        Step: u(1) = 3^1 - 2^1
{second_base}    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih1: u(k) = 3^k - 2^k
        Assume ih2: u(k + 1) = 3^(k + 1) - 2^(k + 1)
        Step: u(k + 2) = 5 * u(k + 1) - 6 * u(k)
        Step: = 5 * (3^(k + 1) - 2^(k + 1)) - 6 * (3^k - 2^k)
        Step: = 3^(k + 2) - 2^(k + 2)
    Therefore forall n : Nat, n >= 1 => u(n) = 3^n - 2^n
QED
"""


class TestStartingValues:
    def test_from_one_as_a_level_writes_it(self, checker: ProofChecker):
        report = check(checker, SUM_OF_SQUARES_FROM_1)
        assert report.is_valid, report.format_report()

    def test_from_five_with_the_side_condition_first(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "2^n beats n^2 from 5 on"
Claim: forall n : Nat, n >= 5 => 2^n > n^2
Proof:
    Base case n = 5:
        Step: 2^5 = 32
        Step: > 25
    Inductive step:
        Given k : Nat
        Assume hk: k >= 5
        Assume ih: 2^k > k^2
        Step: 2^(k + 1) = 2 * 2^k
        Step: > 2 * k^2
        Step: >= (k + 1)^2
    Therefore forall n : Nat, n >= 5 => 2^n > n^2
QED
""")
        assert report.is_valid, report.format_report()

    def test_the_side_condition_as_a_declaration(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "7^n - 3^n is divisible by 4"
Claim: forall n : Nat, n >= 1 => MultipleOf(7^n - 3^n, 4)
Proof:
    Base case n = 1:
        Step: 7^1 - 3^1 = 4
        Therefore MultipleOf(7^1 - 3^1, 4)
    Inductive step:
        Given k : Nat where k >= 1
        Assume ih: MultipleOf(7^k - 3^k, 4)
        Obtain m : Int such that 7^k - 3^k = 4 * m from ih
        Step: 7^(k + 1) - 3^(k + 1) = 7 * (7^k - 3^k) + 4 * 3^k
        Step: = 4 * (7 * m + 3^k)
        Therefore MultipleOf(7^(k + 1) - 3^(k + 1), 4)
    Therefore forall n : Nat, n >= 1 => MultipleOf(7^n - 3^n, 4)
QED
""")
        assert report.is_valid, report.format_report()

    def test_the_integers_from_a_starting_value(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "Integers from -2"
Claim: forall n : Int, n >= -2 => n + 3 > 0
Proof:
    Base case n = -2:
        Step: -2 + 3 = 1
        Therefore -2 + 3 > 0
    Inductive step:
        Given k : Int
        Assume hk: k >= -2
        Assume ih: k + 3 > 0
        Therefore k + 1 + 3 > 0
    Therefore forall n : Int, n >= -2 => n + 3 > 0
QED
""")
        assert report.is_valid, report.format_report()


class TestMatricesAndComplexNumbers:
    def test_matrix_powers(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "Powers of a shear matrix"
Claim: forall n : Nat, n >= 1 => [[1, 1], [0, 1]]^n = [[1, n], [0, 1]]
Proof:
    Base case n = 1:
        Step: [[1, 1], [0, 1]]^1 = [[1, 1], [0, 1]]
    Inductive step:
        Given k : Nat
        Assume ih: [[1, 1], [0, 1]]^k = [[1, k], [0, 1]]
        Step: [[1, 1], [0, 1]]^(k + 1) = [[1, k], [0, 1]] * [[1, 1], [0, 1]]
        Step: = [[1, k + 1], [0, 1]]
    Therefore forall n : Nat, n >= 1 => [[1, 1], [0, 1]]^n = [[1, n], [0, 1]]
QED
""")
        assert report.is_valid, report.format_report()

    def test_de_moivre(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "De Moivre"
Claim: forall n : Nat, n >= 1 => (cos(t) + i * sin(t))^n = cos(n * t) + i * sin(n * t)
Proof:
    Given t : Real
    Base case n = 1:
        Step: (cos(t) + i * sin(t))^1 = cos(1 * t) + i * sin(1 * t)
    Inductive step:
        Given k : Nat
        Assume ih: (cos(t) + i * sin(t))^k = cos(k * t) + i * sin(k * t)
        Step: (cos(t) + i * sin(t))^(k + 1) = (cos(k * t) + i * sin(k * t)) * (cos(t) + i * sin(t))
        Step: = cos(k * t) * cos(t) - sin(k * t) * sin(t) + i * (sin(k * t) * cos(t) + cos(k * t) * sin(t))
        Step: = cos((k + 1) * t) + i * sin((k + 1) * t)
    Therefore forall n : Nat, n >= 1 => (cos(t) + i * sin(t))^n = cos(n * t) + i * sin(n * t)
QED
""")
        assert report.is_valid, report.format_report()


class TestSequences:
    def test_a_first_order_recurrence(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "A recurrence"
Claim: forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
Proof:
    Given u : Nat -> Int
    Assume u1: u(1) = 2
    Assume rec: forall n : Nat, n >= 1 => u(n + 1) = 2 * u(n) - 1
    Base case n = 1:
        Step: u(1) = 2^0 + 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: u(k) = 2^(k - 1) + 1
        Step: u(k + 1) = 2 * u(k) - 1
        Step: = 2 * (2^(k - 1) + 1) - 1
        Step: = 2^k + 1
    Therefore forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
QED
""")
        assert report.is_valid, report.format_report()
        qed = report.results[-1]
        assert "where u(1) = 2" in qed.message, "the definitions are named in the verdict"

    def test_a_second_order_recurrence(self, checker: ProofChecker):
        second = "    Base case n = 2:\n        Step: u(2) = 3^2 - 2^2\n"
        report = check(checker, TWO_STEP.format(second_value="    Assume u2: u(2) = 5\n", second_base=second))
        assert report.is_valid, report.format_report()


class TestDomainObligationsUnderAGuard:
    def test_a_guard_discharges_a_division(self, checker: ProofChecker):
        # 1/n inside `n >= 1 => …` needs n != 0 only where n >= 1.
        report = check(checker, """\
Theorem: "Sum of reciprocal squares is under 2"
Claim: forall n : Nat, n >= 1 => sum(r, 1, n, 1 / r^2) <= 2 - 1 / n
Proof:
    Base case n = 1:
        Step: sum(r, 1, 1, 1 / r^2) = 1
        Step: <= 2 - 1 / 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: sum(r, 1, k, 1 / r^2) <= 2 - 1 / k
        Step: sum(r, 1, k + 1, 1 / r^2) = sum(r, 1, k, 1 / r^2) + 1 / (k + 1)^2
        Step: <= 2 - 1 / k + 1 / (k + 1)^2
        Step: <= 2 - 1 / (k + 1)
    Therefore forall n : Nat, n >= 1 => sum(r, 1, n, 1 / r^2) <= 2 - 1 / n
QED
""")
        assert report.is_valid, report.format_report()
        assert not report.has_warnings, report.format_report()

    def test_without_a_guard_the_division_is_still_flagged(self, checker: ProofChecker):
        report = checker.check_source("Therefore forall n : Nat, 1 / (n + 1) > 0\nTherefore forall m : Nat, m * (1 / m) = 1\n")[0]
        warned = [r for r in report.results if r.domain_warnings]
        assert len(warned) == 1 and "m" in warned[0].domain_warnings[0], report.format_report()


class TestWhatMustStillFail:
    def test_the_base_case_must_be_at_the_start(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "n^2 >= 2n + 1 from 1 (false at 1 and 2)"
Claim: forall n : Nat, n >= 1 => n^2 >= 2 * n + 1
Proof:
    Base case n = 3:
        Therefore 3^2 >= 2 * 3 + 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: k^2 >= 2 * k + 1
        Step: (k + 1)^2 = k^2 + 2 * k + 1
        Step: >= 2 * k + 1 + 2 * k + 1
        Step: >= 2 * (k + 1) + 1
    Therefore forall n : Nat, n >= 1 => n^2 >= 2 * n + 1
QED
""")
        assert not report.is_valid
        assert "missing n = 1" in refusal(report)

    def test_a_step_may_assume_only_what_the_start_gives(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "2^n > n^2 from 1 (false at 2, 3, 4)"
Claim: forall n : Nat, n >= 1 => 2^n > n^2
Proof:
    Base case n = 1:
        Step: 2^1 = 2
        Step: > 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 5
        Assume ih: 2^k > k^2
        Step: 2^(k + 1) = 2 * 2^k
        Step: > 2 * k^2
        Step: >= (k + 1)^2
    Therefore forall n : Nat, n >= 1 => 2^n > n^2
QED
""")
        assert not report.is_valid
        assert "k >= 5" in refusal(report)

    def test_a_two_step_recurrence_needs_two_base_cases(self, checker: ProofChecker):
        # Without u(2) given or proved, nothing pins the second value down.
        report = check(checker, TWO_STEP.format(second_value="", second_base=""))
        assert not report.is_valid
        assert "missing n = 2" in refusal(report)

    def test_contradictory_definitions_prove_nothing(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "Anything follows from a bad definition"
Claim: forall n : Nat, n >= 1 => u(n) = 7
Proof:
    Given u : Nat -> Int
    Assume a: u(1) = 1
    Assume b: u(1) = 2
    Base case n = 1:
        Step: u(1) = 7
    Inductive step:
        Given k : Nat
        Assume ih: u(k) = 7
        Step: u(k + 1) = 7
    Therefore forall n : Nat, n >= 1 => u(n) = 7
QED
""")
        assert not report.is_valid
        assert "contradict each other" in report.results[-1].message

    def test_a_recurrence_for_every_natural_includes_zero(self, checker: ProofChecker):
        # u(1) = 2u(0) - 1 forces u(0) = 3/2, which an Int-valued u cannot be.
        report = check(checker, """\
Theorem: "A recurrence stated from 0 by mistake"
Claim: forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
Proof:
    Given u : Nat -> Int
    Assume u1: u(1) = 2
    Assume rec: forall n : Nat, u(n + 1) = 2 * u(n) - 1
    Base case n = 1:
        Step: u(1) = 2^0 + 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: u(k) = 2^(k - 1) + 1
        Step: u(k + 1) = 2 * u(k) - 1
        Step: = 2 * (2^(k - 1) + 1) - 1
        Step: = 2^k + 1
    Therefore forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
QED
""")
        assert not report.is_valid
        assert "n = 0" in report.results[-1].message

    def test_the_integers_still_need_a_starting_value(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "Every integer is non-negative (false)"
Claim: forall n : Int, n >= 0
Proof:
    Base case n = 0:
        Therefore 0 >= 0
    Inductive step:
        Given k : Int
        Assume ih: k >= 0
        Therefore k + 1 >= 0
    Therefore forall n : Int, n >= 0
QED
""")
        assert not report.is_valid
