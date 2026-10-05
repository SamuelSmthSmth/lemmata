"""What A Level and Further Mathematics proofs need, and what must still fail.

Each case comes from trying a set of A Level, Further Mathematics and STEP-style
problems as a student would write them.  The valid ones failed before for a
reason in the engine, not in the proof; the invalid ones are the soundness
probes that keep each new ability honest.
"""

import pytest

from aether import ProofChecker


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


def check(checker: ProofChecker, src: str):
    return checker.check_source(src)[0]


class TestPrime:
    def test_prime_numbers_are_decided(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "Primes by number"
Proof:
    Therefore Prime(41)
    Therefore not Prime(1681)
    Therefore Prime(2)
    Therefore not Prime(1)
QED
""")
        assert report.is_valid, report.format_report()

    def test_a_counterexample_to_n2_n_41(self, checker: ProofChecker):
        report = check(checker, """\
Theorem: "n^2 + n + 41 is not always prime"
Proof:
    Let n = 40
    Step: n^2 + n + 41 = 41 * 41
    Therefore Divides(41, n^2 + n + 41)
    Hence not Prime(n^2 + n + 41)
QED
""")
        assert report.is_valid, report.format_report()

    def test_a_prime_is_not_called_composite(self, checker: ProofChecker):
        report = check(checker, 'Theorem: "41 is not prime (false)"\nProof:\n    Therefore not Prime(41)\nQED\n')
        assert not report.is_valid
        assert not any("not a known function" in r.message for r in report.results)


class TestChainedInequalities:
    def test_a_chain_is_both_relations(self, checker: ProofChecker):
        report = check(checker, "Let k : Real\nAssume h: k^2 < 4\nTherefore -2 < k < 2\n")
        assert report.is_valid, report.format_report()

    def test_a_chain_fails_on_its_weak_link(self, checker: ProofChecker):
        report = check(checker, "Let k : Real\nAssume h: k = 3\nTherefore -2 < k < 2\n")
        assert not report.is_valid
        assert report.results[-1].counterexample == "k=3"


class TestPowersOfANaturalNumber:
    def test_divisibility_by_induction(self, checker: ProofChecker):
        report = check(checker, """\
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
""")
        assert report.is_valid, report.format_report()

    def test_a_power_under_forall_is_not_one_number(self, checker: ProofChecker):
        # Standing for 2^n by a single constant would make this follow.
        report = check(checker, 'Theorem: "2^n = 1 (false)"\nProof:\n    Therefore forall n : Nat, 2^n = 1\nQED\n')
        assert not report.is_valid

    def test_a_negative_exponent_is_not_assumed_whole(self, checker: ProofChecker):
        # 2^(k - 1) at k = 0 is 1/2.
        report = check(checker, "Given k : Nat\nTherefore exists q : Int, 2^(k - 1) = q\n")
        assert not report.is_valid

    def test_a_false_divisibility_still_fails(self, checker: ProofChecker):
        report = check(checker, 'Theorem: "Divisible by 8 (false)"\nProof:\n    Therefore forall n : Nat, MultipleOf(7^n - 3^n, 8)\nQED\n')
        assert not report.is_valid


class TestPolynomialDivisibility:
    """m | P(n) depends only on n mod m, so the remainders decide it."""

    @pytest.mark.parametrize("claim", [
        "Given n : Int\nTherefore MultipleOf(n^3 - n, 6)",
        "Given n : Int\nTherefore MultipleOf(n^5 - n, 30)",
        "Given n : Int\nTherefore Even(n * (n + 1))",
        "Given n : Nat\nTherefore Odd(n^2 + n + 1)",
        "Given a, b : Int\nTherefore MultipleOf(a^2 * b - a * b^2, 2)",
        "Given n : Int\nTherefore MultipleOf(n * (n + 1) * (n + 2) / 2, 3)",
    ])
    def test_a_true_divisibility_is_proved(self, checker: ProofChecker, claim: str):
        report = check(checker, claim + "\n")
        assert report.is_valid, report.format_report()

    def test_a_false_one_gets_a_remainder_as_counterexample(self, checker: ProofChecker):
        report = check(checker, "Given n : Int\nTherefore MultipleOf(n^2 + 1, 3)\n")
        assert not report.is_valid
        assert report.results[-1].counterexample == "n=0"

    def test_a_restricted_variable_is_left_to_the_solver(self, checker: ProofChecker):
        # n = 1 is a remainder where 8 does not divide n^2, but Even(n) rules it
        # out; the counterexample must be one the hypothesis allows.
        report = check(checker, "Given n : Int\nAssume h: Even(n)\nTherefore MultipleOf(n^2, 8)\n")
        assert not report.is_valid
        counterexample = report.results[-1].counterexample or ""
        assert counterexample and int(counterexample.split("=")[1]) % 2 == 0, counterexample


ROOT_2 = """\
Theorem: "The square root of {n} is irrational"
Claim: Irrational(sqrt({n}))
Proof:
    Subproof:
        Assume h: Rational(sqrt({n}))
        Obtain p, q : Int such that q > 0 and Coprime(p, q) and sqrt({n}) = p / q from h
{body}    Therefore not Rational(sqrt({n}))
    Hence Irrational(sqrt({n}))
QED
"""

ARGUMENT = """\
        Step: (p / q)^2 = sqrt({n})^2
        Step: = {n}
        Step: p^2 = {n} * q^2
        Therefore Even(p^2)
        Therefore Even(p)
        Obtain k : Int such that p = 2 * k
        Step: 4 * k^2 = {n} * q^2
        Step: q^2 = 2 * k^2
        Therefore Even(q^2)
        Therefore Even(q)
        Therefore not Coprime(p, q)
        Therefore Contradiction
"""


class TestRationals:
    def test_root_two_is_irrational(self, checker: ProofChecker):
        report = check(checker, ROOT_2.format(n=2, body=ARGUMENT.format(n=2)))
        assert report.is_valid, report.format_report()

    def test_the_argument_cannot_be_skipped(self, checker: ProofChecker):
        report = check(checker, ROOT_2.format(n=2, body="        Therefore Contradiction\n"))
        assert not report.is_valid

    def test_the_same_argument_fails_for_root_four(self, checker: ProofChecker):
        # 4k^2 = 4q^2 gives q^2 = k^2, not 2k^2: the step that is false fails.
        report = check(checker, ROOT_2.format(n=4, body=ARGUMENT.format(n=4)))
        assert not report.is_valid
        assert "q ^ 2" in report.format_report()

    def test_coprime_is_decided_for_numbers(self, checker: ProofChecker):
        assert check(checker, "Given p, q : Int\nAssume h: p = 4\nAssume h2: q = 9\nTherefore Coprime(p, q)\n").is_valid
        assert not check(checker, "Given p, q : Int\nAssume h: p = 6\nAssume h2: q = 9\nTherefore Coprime(p, q)\n").is_valid

    def test_obtain_several_witnesses_at_once(self, checker: ProofChecker):
        from aether.core.ast import ObtainNode

        doc = checker._parser.parse("Assume h: exists a : Int, exists b : Int, a + b = 3\nObtain a, b : Int such that a + b = 3 from h\nStep: a + b = 3\n")
        obtains = [s for s in doc.statements if isinstance(s, ObtainNode)]
        assert [o.variable for o in obtains] == ["a", "b"]
        report = check(checker, "Assume h: exists a : Int, exists b : Int, a + b = 3\nObtain a, b : Int such that a + b = 3 from h\nStep: a + b = 3\n")
        assert report.is_valid, report.format_report()


CASES = """\
Theorem: "n^2 + n is even"
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 2 * (2 * k^2 + k)
        Therefore Even(n^2 + n)
{odd}    Therefore Even(n^2 + n)
QED
"""

ODD_CASE = """\
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 2 * (2 * k^2 + 3 * k + 1)
        Therefore Even(n^2 + n)
"""


class TestCaseCoverage:
    def test_complete_cases_are_plainly_valid(self, checker: ProofChecker):
        report = check(checker, CASES.format(odd=ODD_CASE))
        assert report.is_valid and not report.has_warnings, report.format_report()

    def test_a_missing_case_is_flagged_though_the_conclusion_holds(self, checker: ProofChecker):
        # The conclusion is true (the solver proves it outright), so the proof
        # is not invalid; the case analysis is incomplete, and the student hears so.
        report = check(checker, CASES.format(odd=""))
        assert report.is_valid, report.format_report()
        flagged = [r for r in report.results if "do not cover every possibility" in r.message]
        assert flagged and flagged[0].status.value == "WARNING"


class TestSums:
    def test_the_last_term_peels_off(self, checker: ProofChecker):
        # SymPy writes these as harmonic numbers it never related back.
        report = check(checker, "Let k : Nat\nStep: sum(r, 1, k + 1, 1 / r^2) = sum(r, 1, k, 1 / r^2) + 1 / (k + 1)^2\n")
        assert report.is_valid, report.format_report()

    def test_a_wrong_last_term_is_refused(self, checker: ProofChecker):
        report = check(checker, "Let k : Nat\nStep: sum(r, 1, k + 1, 1 / r^2) = sum(r, 1, k, 1 / r^2) + 1 / k^2\n")
        assert not report.is_valid

    def test_a_sums_own_index_is_never_a_counterexample(self, checker: ProofChecker):
        # This used to fail with "Counterexample: r=0", naming the bound index.
        report = check(checker, """\
Theorem: "Sum of r times r factorial"
Claim: forall n : Nat, sum(r, 1, n, r * r!) = (n + 1)! - 1
Proof:
    Base case n = 0:
        Step: sum(r, 1, 0, r * r!) = 0
        Step: = 1! - 1
    Inductive step:
        Given k : Nat
        Assume ih: sum(r, 1, k, r * r!) = (k + 1)! - 1
        Step: sum(r, 1, k + 1, r * r!) = (k + 1)! - 1 + (k + 1) * (k + 1)!
        Step: = (k + 2)! - 1
    Therefore forall n : Nat, sum(r, 1, n, r * r!) = (n + 1)! - 1
QED
""")
        assert report.is_valid, report.format_report()
        assert not any((r.counterexample or "").startswith("r=") for r in report.results)
