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
