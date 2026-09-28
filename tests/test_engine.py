"""Unit and integration tests for the Aether verification engine (Context, SymPy, Z3, ProofChecker)."""

import pytest

from aether.engine.checker import ProofChecker, StepStatus


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


class TestEvenSquareTheorem:
    def test_valid_even_square_proof(self, checker: ProofChecker):
        src = """\
Theorem: "Even square theorem"
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]
    Hence MultipleOf(n^2, 4)
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 1
        report = reports[0]
        assert report.theorem_name == "Even square theorem"
        assert report.is_valid
        assert not report.has_warnings
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_odd_square_is_odd(self, checker: ProofChecker):
        src = """\
Theorem: "Odd square theorem"
Proof:
    Given n : Int
    Assume h1: Odd(n)
    Obtain k : Int such that n = 2 * k + 1 from h1
    Step: n^2 = (2 * k + 1)^2
    Step: = 4 * k^2 + 4 * k + 1
    Step: = 2 * (2 * k^2 + 2 * k) + 1
    Therefore Odd(n^2)
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 1
        assert reports[0].is_valid


class TestAlgebraicStepChecking:
    def test_algebraic_error_with_counterexample(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: 2 * (x + 3) + 4 * x = 2 * x + 6 + 4 * x
Step: = 6 * x + 5
"""
        reports = checker.check_source(src)
        report = reports[0]
        assert not report.is_valid
        assert report.results[0].status == StepStatus.VALID
        assert report.results[1].status == StepStatus.VALID
        assert report.results[2].status == StepStatus.INVALID
        assert report.results[2].counterexample is not None
        assert "LHS" in report.results[2].counterexample


class TestInequalitiesAndMonotonicity:
    def test_valid_z3_inequality_step(self, checker: ProofChecker):
        src = """\
Given x : Real
Assume x > 2
Step: x^2 - 4 > 0
"""
        report = checker.check_source(src)[0]
        assert report.is_valid
        assert report.results[2].status == StepStatus.VALID

    def test_invalid_z3_inequality_step(self, checker: ProofChecker):
        src = """\
Given x : Real
Assume x > 1
Step: x^2 - 4 > 0
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[2].status == StepStatus.INVALID

    def test_strict_monotonicity_violation_in_chain(self, checker: ProofChecker):
        src = """\
Given k : Int
Step: 4 * k^2 <= 8 * k^2
Step: >= 2 * k^2
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[2].status == StepStatus.INVALID
        assert "monotonicity" in report.results[2].message.lower()


class TestDomainObligations:
    def test_division_by_zero_obligation_flagged_when_unguarded(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: (x^2 - 4) / (x - 2) = x + 2
"""
        report = checker.check_source(src)[0]
        # In default mode, algebraic simplification succeeds with a WARNING for x - 2 != 0
        assert report.has_warnings
        step_res = report.results[1]
        assert step_res.status == StepStatus.WARNING
        assert len(step_res.domain_warnings) == 1
        assert "(x - 2) != 0" in step_res.domain_warnings[0]
        assert "x=2" in step_res.domain_warnings[0]

        # In strict_domains mode, unguarded division by zero is INVALID
        strict_checker = ProofChecker(strict_domains=True)
        strict_report = strict_checker.check_source(src)[0]
        assert not strict_report.is_valid
        assert strict_report.results[1].status == StepStatus.INVALID

    def test_division_by_zero_obligation_discharged_by_assumption(self, checker: ProofChecker):
        src = """\
Let x : Real
Assume x > 2
Step: (x^2 - 4) / (x - 2) = x + 2
"""
        report = checker.check_source(src)[0]
        assert report.is_valid
        assert not report.has_warnings
        assert report.results[2].status == StepStatus.VALID
        assert report.results[2].domain_warnings == []

    def test_sqrt_domain_obligation(self, checker: ProofChecker):
        src_unguarded = """\
Let x : Real
Step: sqrt(x - 1) >= 0
"""
        rep1 = checker.check_source(src_unguarded)[0]
        assert rep1.has_warnings
        assert any("(x - 1) >= 0" in w for w in rep1.results[1].domain_warnings)

        src_guarded = """\
Let x : Real
Assume x >= 1
Step: sqrt(x - 1) >= 0
"""
        rep2 = checker.check_source(src_guarded)[0]
        assert rep2.is_valid
        assert not rep2.has_warnings


class TestScopeAndVariableGuardrails:
    def test_implicit_variable_capture_rejected(self, checker: ProofChecker):
        src = """\
Given n : Int
Given k : Int
Assume h1: Even(n)
Obtain k : Int such that n = 2 * k from h1
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        obtain_res = report.results[3]
        assert obtain_res.status == StepStatus.INVALID
        assert "capture" in obtain_res.message.lower() or "shadow" in obtain_res.message.lower()

    def test_illegal_universal_generalization_rejected(self, checker: ProofChecker):
        src = """\
Let x : Real
Assume x > 0
Step: x^2 > 0
Therefore forall x : Real, x^2 > 0
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        deduce_res = report.results[3]
        assert deduce_res.status == StepStatus.INVALID
        assert "illegal generalization" in deduce_res.message.lower()

    def test_invalid_obtain_rejected(self, checker: ProofChecker):
        src = """\
Given n : Int
Assume h1: Odd(n)
Obtain k : Int such that n = 2 * k from h1
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[2].status == StepStatus.INVALID
