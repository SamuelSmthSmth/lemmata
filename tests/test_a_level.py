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
