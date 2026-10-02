"""Tests for Complex Analysis, Linear Algebra, Set Theory, and LaTeX Export in Aether."""

import pytest

from aether import ProofChecker, StepStatus, export_to_latex


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


class TestComplexAnalysis:
    def test_complex_arithmetic_and_modulus(self, checker: ProofChecker):
        src = """\
Theorem: "Complex arithmetic"
Proof:
    Step: (1 + 2 * i) * (1 - 2 * i) = 1 - 4 * i^2
    Step: = 5
    Step: |3 + 4 * i| = 5
    Step: (3 + 4 * i) * conj(3 + 4 * i) = 25
    Step: = |3 + 4 * i|^2
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_cauchy_riemann_verification(self, checker: ProofChecker):
        src = """\
Theorem: "Cauchy-Riemann equations for z^2"
Proof:
    Let x, y : Real
    Let u = x^2 - y^2
    Let v = 2 * x * y
    Step: diff(u, x) = 2 * x
    Step: diff(v, y) = 2 * x
    Step: diff(u, y) = -2 * y
    Step: diff(v, x) = 2 * y
    Therefore CauchyRiemann(u, v)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert report.results[-1].status == StepStatus.VALID

    def test_non_holomorphic_counterexample(self, checker: ProofChecker):
        src = """\
Theorem: "f(z) = x + iy is not holomorphic"
Proof:
    Let x, y : Real
    Let u = x
    Let v = -y
    Therefore CauchyRiemann(u, v)
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[-1].status == StepStatus.INVALID


class TestLinearAlgebra:
    def test_matrix_operations_and_properties(self, checker: ProofChecker):
        src = """\
Theorem: "Matrix arithmetic and properties"
Proof:
    Let A = [[1, 2], [3, 4]]
    Let B = [[2, 0], [1, 2]]
    Step: A * B = [[4, 4], [10, 8]]
    Step: det(A) = -2
    Step: tr(A) = 5
    Step: A^T = [[1, 3], [2, 4]]
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_vector_norm_and_orthogonality(self, checker: ProofChecker):
        src = """\
Theorem: "Vector norm and orthogonal vectors"
Proof:
    Let u = [3, 4]
    Step: norm(u) = 5
    Let v = [-4, 3]
    Step: dot(u, v) = 0
    Therefore Orthogonal(u, v)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert report.results[-1].status == StepStatus.VALID

    def test_matrix_dimension_mismatch_rejected(self, checker: ProofChecker):
        src = """\
Theorem: "Dimension mismatch"
Proof:
    Let A = [[1, 2], [3, 4]]
    Step: A = [[1, 2, 3], [4, 5, 6]]
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[1].status == StepStatus.INVALID


    def test_matrix_inverse_is_computed(self, checker: ProofChecker):
        """`inverse(A)` used to be an uninterpreted symbol, so it never held.

        The name was recognised -- `inv`/`inverse` mapped to a plain
        ``sp.Function("inv")`` -- but the result was never evaluated, so every
        inverse step was reported as an algebraic failure instead.
        """
        src = """\
Theorem: "Matrix inverse"
Proof:
    Let A = [[1, 2], [3, 4]]
    Step: inverse(A) * A = [[1, 0], [0, 1]]
    Step: inv(A) = [[-2, 1], [3 / 2, -1 / 2]]
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_wrong_matrix_inverse_is_rejected(self, checker: ProofChecker):
        src = """\
Theorem: "Wrong inverse"
Proof:
    Let A = [[1, 2], [3, 4]]
    Step: inverse(A) = [[1, 0], [0, 1]]
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[1].status == StepStatus.INVALID

    def test_scalar_inv_stays_uninterpreted(self, checker: ProofChecker):
        """The group templates write `inv(a)` for an abstract inverse.

        That has to stay an opaque function rather than be mistaken for a
        matrix inverse.
        """
        src = """\
Theorem: "Group inverse"
Proof:
    Assume Group(G, op, e, inv)
    Given a : Real
    Step: op(a, inv(a)) = e
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()


class TestSetTheory:
    def test_set_empty_set_and_operations(self, checker: ProofChecker):
        src = """\
Theorem: "Set intersection with empty set"
Proof:
    Let S : Set
    Step: S intersect \\emptyset = \\emptyset
    Step: S union \\emptyset = S
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_set_membership_and_subset(self, checker: ProofChecker):
        src = """\
Theorem: "Empty set is subset of any set"
Proof:
    Let S : Set
    Step: \\emptyset subset S
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()


class TestLatexExport:
    def test_export_to_latex_full_document(self):
        src = """\
Theorem: "Even square theorem"
Claim: forall n : Int, Even(n) => MultipleOf(n^2, 4)
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2
    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]
    Hence MultipleOf(n^2, 4)
QED
"""
        latex = export_to_latex(src, standalone=True)
        assert "\\documentclass" in latex
        assert "\\begin{theorem}[Even square theorem]" in latex
        assert "\\begin{proof}" in latex
        assert "\\begin{align*}" in latex
        assert "\\end{align*}" in latex
        assert "\\end{proof}" in latex
        assert "\\end{document}" in latex

    def test_export_to_latex_snippet(self):
        src = """\
Let x : Real
Step: (x + 1)^2 = x^2 + 2 * x + 1
"""
        latex = export_to_latex(src, standalone=False)
        assert "\\documentclass" not in latex
        assert "\\begin{align*}" in latex

    def test_export_to_latex_induction_subproofs(self):
        """A subproof must export, and say what kind of subproof it is.

        SubProofNode carries `label` and `case_condition`; it has neither
        `subproof_type` nor `title`.  Reading the wrong attribute raised
        AttributeError on *every* document containing a subproof, so a proof
        with an induction took down the whole export.
        """
        src = """\
Theorem: "Tiny induction"
Proof:
    Given n : Int
    Base case n = 0:
        Step: 0 = 0
    Inductive step:
        Assume h1: n > 0
        Step: n = n
QED
"""
        latex = export_to_latex(src, standalone=True)
        assert "\\paragraph*{Base case $n = 0$:}" in latex
        assert "\\paragraph*{Inductive step:}" in latex
        assert "\\end{document}" in latex

    def test_export_to_latex_case_and_named_subproofs(self):
        """The other two subproof shapes carry a condition or a bare name."""
        src = """\
Theorem: "Tiny case split"
Proof:
    Let x : Int
    Case x >= 0:
        Step: x = x
    Case x < 0:
        Step: x = x
    SubLemma:
        Step: x = x
QED
"""
        latex = export_to_latex(src, standalone=True)
        assert "\\paragraph*{Case $x \\ge 0$:}" in latex
        assert "\\paragraph*{Case $x < 0$:}" in latex
        assert "\\paragraph*{SubLemma:}" in latex

    def test_export_to_latex_escapes_theorem_names(self):
        """Theorem names are free text, and LaTeX prints them in text mode.

        A name such as `Divisibility of 3^n - 1 by 2` went into
        `\\begin{theorem}[...]` verbatim, where `^` is a math-only token:
        pdfTeX stopped with "Missing $ inserted" and wrote no PDF at all.
        """
        src = """\
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: 1 = 1
Proof:
    Step: 1 = 1
QED
"""
        latex = export_to_latex(src, standalone=True)
        assert "\\begin{theorem}[Divisibility of 3\\textasciicircum{}n - 1 by 2]" in latex
        assert "3^n" not in latex

    def test_export_to_latex_escapes_labels(self):
        """Labels reach LaTeX in text mode too -- `h_1` used to be left raw."""
        src = """\
Let n : Int
Assume h_1: Even(n)
Therefore Even(n)
Sub_lemma:
    Step: n = n
"""
        latex = export_to_latex(src, standalone=True)
        assert "Assume (h\\_1) " in latex
        assert "\\paragraph*{Sub\\_lemma:}" in latex
