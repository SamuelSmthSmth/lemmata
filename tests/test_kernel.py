"""The proof kernel, stage 1: premises a line may use, and how big a step it may take.

The probes are the paper's (§1 of "A Proof Kernel for Lemmata"): proofs whose
lines are true but whose argument is missing or wrong.  The engine without the
kernel accepts them; each level must refuse what it says it refuses, and pass
the proofs written out properly.
"""

import pytest

from aether import ProofChecker

EPSILON_DELTA_ONE_LINE = """\
Theorem: "3x continuous at 2"
Proof:
    Therefore forall e : Real, e > 0 => exists d : Real, d > 0 and (forall x : Real, abs(x - 2) < d => abs(3 * x - 6) < e)
QED
"""

EPSILON_DELTA_WRITTEN_OUT = """\
Theorem: "Continuity of 3x at x=2"
Claim: forall \\epsilon : Real, \\epsilon > 0 => exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - 2| < \\delta => |3 * x - 6| < \\epsilon)
Proof:
    Given \\epsilon : Real where \\epsilon > 0
    Let \\delta = \\epsilon / 3
    Step: \\delta > 0
    Subproof:
        Given x : Real
        Assume |x - 2| < \\delta
        Step: |3 * x - 6| = |3 * (x - 2)|
        Step: = 3 * |x - 2|
        Step: < 3 * \\delta
        Step: = \\epsilon
    Therefore exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - 2| < \\delta => |3 * x - 6| < \\epsilon) [witness: \\epsilon / 3]
QED
"""

SUM_WITHOUT_INDUCTION = """\
Theorem: "Sum of first n odd numbers"
Claim: forall n : Nat, sum(k, 1, n, 2 * k - 1) = n^2
Proof:
    Given n : Nat
    Therefore sum(k, 1, n, 2 * k - 1) = n^2
QED
"""

NO_ARGUMENT = """\
Theorem: "n^3 - n is a multiple of 6"
Claim: forall n : Int, MultipleOf(n^3 - n, 6)
Proof:
    Given n : Int
    Therefore MultipleOf(n^3 - n, 6)
QED
"""


def citing(label: str) -> str:
    return f"Let x : Real\nAssume h1: x > 5\nAssume h2: x = x\nTherefore x^2 > 25 [using {label}]\n"


def check(src: str, kernel=None):
    return ProofChecker(kernel=kernel).check_source(src)[0]


def kernel_findings(report):
    return [r for r in report.all_results if r.backend.startswith("Kernel") and r.status.value == "INVALID"]


class TestWithoutTheKernel:
    """Nothing changes unless the kernel is asked for: these pass as they always have."""

    @pytest.mark.parametrize("src", [EPSILON_DELTA_ONE_LINE, SUM_WITHOUT_INDUCTION, NO_ARGUMENT, citing("h2")])
    def test_the_probes_still_pass(self, src):
        assert check(src).is_valid

    def test_an_unknown_level_is_refused(self):
        with pytest.raises(ValueError, match="exam, course, scratch"):
            ProofChecker(kernel="strict")


class TestPremiseSelection:
    def test_a_line_may_use_only_what_it_cites(self):
        report = check(citing("h2"), kernel="course")
        line = report.results[-1]
        assert line.status.value == "INVALID"
        assert line.backend == "Kernel: premises"
        assert "does not follow from h2 alone" in line.message and "using h1" in line.message

    def test_citing_the_right_fact_passes(self):
        report = check(citing("h1"), kernel="course")
        assert report.is_valid, report.format_report()
        assert report.results[-1].backend == "Kernel: nlinarith"

    def test_scratch_still_selects_premises(self):
        # Premise selection is not a matter of level: a citation means what it says.
        assert not check(citing("h2"), kernel="scratch").is_valid


class TestEvidence:
    def test_an_uncited_line_names_the_lines_it_used(self):
        report = check(EPSILON_DELTA_WRITTEN_OUT, kernel="course")
        assert report.is_valid, report.format_report()
        delta = next(r for r in report.results if r.line == 6)
        assert delta.backend == "Kernel: linarith"
        assert delta.message.endswith("(from line 5 and line 4).")


class TestLevels:
    def test_a_quantified_statement_in_one_line_is_too_big_a_step(self):
        for level in ("exam", "course"):
            findings = kernel_findings(check(EPSILON_DELTA_ONE_LINE, kernel=level))
            assert [f.backend for f in findings] == ["Kernel: auto"], level
            assert "too big a step" in findings[0].message and "witness" in findings[0].message

    def test_the_same_proof_written_out_passes(self):
        for level in ("exam", "course"):
            assert check(EPSILON_DELTA_WRITTEN_OUT, kernel=level).is_valid, level

    def test_checking_every_remainder_is_not_an_argument(self):
        findings = kernel_findings(check(NO_ARGUMENT, kernel="course"))
        assert [f.backend for f in findings] == ["Kernel: residues"]
        assert "Split into cases" in findings[0].message

    def test_a_closed_form_is_a_standard_result_in_a_course_but_not_in_an_exam(self):
        assert check(SUM_WITHOUT_INDUCTION, kernel="course").is_valid
        findings = kernel_findings(check(SUM_WITHOUT_INDUCTION, kernel="exam"))
        assert [f.backend for f in findings] == ["Kernel: calculus.eval"]
        assert "induction" in findings[0].message

    def test_scratch_allows_anything_the_solvers_decide(self):
        for src in (EPSILON_DELTA_ONE_LINE, SUM_WITHOUT_INDUCTION, NO_ARGUMENT):
            assert check(src, kernel="scratch").is_valid

    def test_a_refused_step_is_one_finding_not_a_cascade(self):
        # The line is true, so what follows may use it: only the leap is refused.
        src = "Let n : Int\nTherefore MultipleOf(n^3 - n, 6)\nTherefore MultipleOf(n^3 - n, 6) or n = 0\n"
        report = check(src, kernel="course")
        assert [r.line for r in report.results if r.status.value == "INVALID"] == [2]

    def test_a_since_premise_is_reviewed_like_a_line(self):
        src = "Let x : Real\nAssume h: x > 5\nSince x^2 > 25, x^2 + 1 > 26\n"
        assert check(src, kernel="course").is_valid


CASES = """\
Theorem: "n^2 + n is even"
Claim: forall n : Int, Even(n^2 + n)
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 2 * (2 * k^2 + k)
        Therefore Even(n^2 + n)
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 2 * (2 * k^2 + 3 * k + 1)
        Therefore Even(n^2 + n)
    Therefore Even(n^2 + n)
QED
"""

SUM_OF_SQUARES = """\
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

FACTORIAL_SUM = """\
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
"""


class TestStructuralRules:
    def test_a_conclusion_after_complete_cases_is_by_the_case_rule(self):
        for level in ("exam", "course"):
            report = check(CASES, kernel=level)
            assert report.is_valid, (level, report.format_report())
            conclusion = report.results[-2]
            assert conclusion.backend == "Kernel: cases"
            assert conclusion.message.startswith("By cases:") and "cover every possibility" in conclusion.message

    def test_a_line_that_follows_from_the_line_above_is_not_a_remainder_check(self):
        # Inside a case, Even(n^2 + n) follows from n^2 + n = 2(2k^2 + k): the
        # engine reaches it by checking remainders first, the kernel by the line.
        report = check(CASES, kernel="exam")
        inner = [r for r in report.all_results if r.line in (8, 12)]
        assert inner and all(r.backend != "Kernel: residues" for r in inner)


class TestGoalClosure:
    @pytest.mark.parametrize("given, claim", [
        ("n : Int", "forall n : Int, MultipleOf(n^3 - n, 6)"),
        ("e : Real", "forall e : Real, e > 0 => exists d : Real, d > 0 and "
                     "(forall x : Real, abs(x - 2) < d => abs(3 * x - 6) < e)"),
    ])
    def test_qed_does_not_prove_the_claim_for_you(self, given, claim):
        src = f'Theorem: "t"\nClaim: {claim}\nProof:\n    Given {given}\nQED\n'
        assert check(src).is_valid
        for level in ("exam", "course"):
            qed = check(src, kernel=level).results[-1]
            assert qed.status.value == "INVALID", level
            assert qed.backend.startswith("Kernel") and "never shows" in qed.message

    def test_a_claim_the_proof_reaches_closes(self):
        report = check(EPSILON_DELTA_WRITTEN_OUT, kernel="exam")
        assert report.is_valid and report.results[-1].backend == "QED"

    def test_an_obvious_last_step_is_still_closed_by_qed(self):
        src = 'Theorem: "t"\nClaim: forall x : Real, x > 2 => x > 1\nProof:\n    Given x : Real\n    Assume h: x > 2\nQED\n'
        assert check(src, kernel="exam").is_valid


class TestInductionIsWorking:
    """Under the exam level a sum must be proved, and induction is how: its
    lines (peeling the last term, using the hypothesis) are the working."""

    @pytest.mark.parametrize("src", [SUM_OF_SQUARES, FACTORIAL_SUM])
    def test_an_induction_on_a_sum_passes(self, src):
        report = check(src, kernel="exam")
        assert report.is_valid, report.format_report()
