"""Tests for Symbolic Calculus, Limits, and Differential Equation verification in Aether."""

import pytest

from aether import ProofChecker, StepStatus, export_to_latex


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


class TestCalculusAndODEs:
    def test_definite_integrals(self, checker: ProofChecker):
        src = """\
Theorem: "Definite integral of polynomial and trig"
Proof:
    Step: integrate(x^2, x, 0, 3) = 9
    Step: integrate(2 * x + 1, x, 0, 2) = 6
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_latex_integral_syntax(self, checker: ProofChecker):
        src = """\
Theorem: "LaTeX integral syntax"
Proof:
    Step: \\int_{0}^{3} x^2 dx = 9
    Step: \\int 2 * x dx = x^2
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_limits(self, checker: ProofChecker):
        src = """\
Theorem: "Limits at points"
Proof:
    Step: lim(sin(x) / x, x, 0) = 1
    Step: lim((x^2 - 1) / (x - 1), x, 1) = 2
    Step: \\lim_{x -> 1} (x^2 - 1) / (x - 1) = 2
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_directional_limits(self, checker: ProofChecker):
        src = """\
Theorem: "One-sided limits"
Proof:
    Step: lim(abs(x) / x, x, 0, "+") = 1
    Step: lim(abs(x) / x, x, 0, "-") = -1
    Step: \\lim_{x -> 0^+} (abs(x) / x) = 1
    Step: \\lim_{x -> 0^-} (abs(x) / x) = -1
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_first_order_ode_verification(self, checker: ProofChecker):
        src = """\
Theorem: "Exponential decay ODE solution"
Proof:
    Let C : Real
    Let x : Real
    Let y = C * exp(-2 * x)
    Step: diff(y, x) = -2 * C * exp(-2 * x)
    Step: diff(y, x) + 2 * y = 0
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_harmonic_oscillator_second_order_ode(self, checker: ProofChecker):
        src = """\
Theorem: "Simple harmonic oscillator ODE"
Proof:
    Let c1, c2, w, t : Real
    Let y = c1 * cos(w * t) + c2 * sin(w * t)
    Step: diff(y, t, 1) = -c1 * w * sin(w * t) + c2 * w * cos(w * t)
    Step: diff(y, t, 2) = -c1 * w^2 * cos(w * t) - c2 * w^2 * sin(w * t)
    Step: = -w^2 * y
    Step: diff(y, t, 2) + w^2 * y = 0
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_latex_export_with_calculus(self, checker: ProofChecker):
        src = """\
Theorem: "Calculus and ODE"
Proof:
    Step: \\int_{0}^{1} x dx = 1 / 2
    Step: \\lim_{x -> 0} (sin(x) / x) = 1
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid
        tex = export_to_latex(src, report=report)
        assert "\\int_{0}^{1}" in tex
        assert "\\lim_{x \\to 0}" in tex
