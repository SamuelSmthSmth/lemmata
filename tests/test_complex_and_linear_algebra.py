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
