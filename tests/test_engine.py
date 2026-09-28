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


class TestTheoremGoalVerification:
    def test_valid_claim_at_qed(self, checker: ProofChecker):
        src = """\
Theorem: "Even square with Claim"
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
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        qed_res = report.results[-1]
        assert qed_res.backend == "QED"
        assert qed_res.status == StepStatus.VALID

    def test_invalid_claim_at_qed_wrong_goal(self, checker: ProofChecker):
        src = """\
Theorem: "Wrong conclusion"
Claim: forall n : Int, Even(n) => Odd(n^2)
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
        report = checker.check_source(src)[0]
        assert not report.is_valid
        qed_res = report.results[-1]
        assert qed_res.backend == "QED"
        assert qed_res.status == StepStatus.INVALID

    def test_invalid_claim_extra_unlicensed_assumption(self, checker: ProofChecker):
        src = """\
Theorem: "Unlicensed assumption"
Claim: forall x : Real, x^2 > 4
Proof:
    Given x : Real
    Assume x > 2
    Step: x^2 > 4
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        qed_res = report.results[-1]
        assert qed_res.backend == "QED"
        assert qed_res.status == StepStatus.INVALID
        assert "undischarged assumption" in qed_res.message.lower()


class TestFunctionDefinitionsAndEvaluations:
    def test_function_eval_with_discharged_domain(self, checker: ProofChecker):
        src = """\
Let f(x) = (x^2 - 4) / (x - 2)
Let a : Real
Assume a > 2
Step: f(a) = a + 2
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert not report.has_warnings

    def test_function_eval_at_singularity_rejected(self, checker: ProofChecker):
        src = """\
Let f(x) = (x^2 - 4) / (x - 2)
Step: f(2) = 4
"""
        report = checker.check_source(src)[0]
        step_res = report.results[1]
        assert step_res.status == StepStatus.INVALID
        assert len(step_res.domain_warnings) == 1


class TestSummationsAndSeries:
    def test_functional_sum_closed_form(self, checker: ProofChecker):
        src = """\
Given n : Nat
Step: sum(k, 1, n, 2 * k - 1) = n^2
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_latex_sum_closed_form(self, checker: ProofChecker):
        src = r"""
Given n : Nat
Step: \sum_{k=1}^{n} k = n * (n + 1) / 2
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_invalid_sum_formula_rejected(self, checker: ProofChecker):
        src = """\
Given n : Nat
Step: sum(k, 1, n, 2 * k - 1) = n^2 + 1
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[1].status == StepStatus.INVALID


class TestProofByCasesAndContradiction:
    def test_exhaustive_proof_by_cases(self, checker: ProofChecker):
        src = """\
Given x : Int
Assume x >= -1
Assume x <= 1
Case x = -1:
    Step: x^2 = 1
    Therefore x^2 <= 1
Case x = 0:
    Step: x^2 = 0
    Therefore x^2 <= 1
Case x = 1:
    Step: x^2 = 1
    Therefore x^2 <= 1
Hence x^2 <= 1
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert "exhaustive" in report.results[5].message.lower()

    def test_non_exhaustive_cases_rejected(self, checker: ProofChecker):
        src = """\
Given x : Int
Assume x >= -1
Assume x <= 1
Case x = -1:
    Step: x^2 = 1
Case x = 1:
    Step: x^2 = 1
Hence x^2 = 1
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        assert report.results[-1].status == StepStatus.INVALID

    def test_proof_by_contradiction(self, checker: ProofChecker):
        src = """\
Given x : Real
Assume x > 2
Subproof:
    Assume not (x > 0)
    Therefore Contradiction
Hence x > 0
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()


class TestRealAnalysisToolkit:
    def test_epsilon_delta_continuity_proof(self, checker: ProofChecker):
        src = r"""
Theorem: "Continuity of 3x + 1"
Claim: forall a : Real, forall \epsilon : Real, \epsilon > 0 => exists \delta : Real, \delta > 0 and (forall x : Real, |x - a| < \delta => |(3 * x + 1) - (3 * a + 1)| < \epsilon)
Proof:
    Given a : Real
    Given \epsilon : Real where \epsilon > 0
    Let \delta = \epsilon / 3
    Step: \delta > 0
    Subproof:
        Given x : Real
        Assume |x - a| < \delta
        Step: |(3 * x + 1) - (3 * a + 1)| = |3 * (x - a)|
        Step: = 3 * |x - a|
        Step: < 3 * \delta
        Step: = \epsilon
    Therefore exists \delta : Real, \delta > 0 and (forall x : Real, |x - a| < \delta => |(3 * x + 1) - (3 * a + 1)| < \epsilon) [witness: \epsilon / 3]
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert report.results[-1].backend == "QED"

    def test_min_max_bounds_in_epsilon_delta(self, checker: ProofChecker):
        src = r"""
Given \epsilon : Real where \epsilon > 0
Let \delta = min(1, \epsilon / 2)
Step: \delta > 0
Step: \delta <= 1
Step: \delta <= \epsilon / 2
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()


class TestMathematicalInduction:
    def test_induction_divisibility_proof(self, checker: ProofChecker):
        src = """\
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: forall n : Nat, MultipleOf(3^n - 1, 2)
Proof:
    Base case n = 0:
        Step: 3^0 - 1 = 0
        Step: = 2 * 0
        Therefore exists m : Int, 3^0 - 1 = 2 * m [witness: 0]
        Hence MultipleOf(3^0 - 1, 2)
    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(3^k - 1, 2)
        Obtain m : Int such that 3^k - 1 = 2 * m from ih
        Step: 3^(k + 1) - 1 = 3 * 3^k - 1
        Step: = 3 * (2 * m + 1) - 1
        Step: = 2 * (3 * m + 1)
        Therefore exists q : Int, 3^(k + 1) - 1 = 2 * q [witness: 3 * m + 1]
        Hence MultipleOf(3^(k + 1) - 1, 2)
    Therefore forall n : Nat, MultipleOf(3^n - 1, 2)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert report.results[-2].backend == "Induction"
        assert report.results[-1].backend == "QED"

    def test_induction_summation_proof(self, checker: ProofChecker):
        src = """\
Theorem: "Sum of first n odd numbers by induction"
Claim: forall n : Nat, sum(j, 1, n, 2 * j - 1) = n^2
Proof:
    Base case n = 0:
        Step: sum(j, 1, 0, 2 * j - 1) = 0
        Step: = 0^2
    Inductive step:
        Given k : Nat
        Assume ih: sum(j, 1, k, 2 * j - 1) = k^2
        Step: sum(j, 1, k + 1, 2 * j - 1) = sum(j, 1, k, 2 * j - 1) + (2 * (k + 1) - 1)
        Step: = k^2 + 2 * k + 1
        Step: = (k + 1)^2
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert report.results[-1].backend == "QED"

    def test_induction_missing_base_case_rejected(self, checker: ProofChecker):
        src = """\
Theorem: "False divisibility without base case"
Claim: forall n : Nat, MultipleOf(3^n + 1, 2)
Proof:
    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(3^k + 1, 2)
        Obtain m : Int such that 3^k + 1 = 2 * m from ih
        Step: 3^(k + 1) + 1 = 3 * 3^k + 1
        Step: = 3 * (2 * m - 1) + 1
        Step: = 2 * (3 * m - 1)
        Therefore exists q : Int, 3^(k + 1) + 1 = 2 * q [witness: 3 * m - 1]
        Hence MultipleOf(3^(k + 1) + 1, 2)
    Therefore forall n : Nat, MultipleOf(3^n + 1, 2)
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid


class TestDefinitionsAndLemmaReuse:
    def test_custom_predicate_definition(self, checker: ProofChecker):
        src = """\
Define CongruentMod(a, b, m) <=> Divides(m, a - b)

Lemma: "Congruence is reflexive"
Claim: forall x : Int, forall m : Int, m != 0 => CongruentMod(x, x, m)
Proof:
    Given x : Int
    Given m : Int where m != 0
    Step: x - x = m * 0
    Therefore exists k : Int, x - x = m * k [witness: 0]
    Hence Divides(m, x - x)
    Hence CongruentMod(x, x, m)
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 1
        assert reports[0].is_valid, reports[0].format_report()

    def test_multi_theorem_lemma_reuse(self, checker: ProofChecker):
        src = """\
Lemma: "Even square"
Claim: forall n : Int, Even(n) => Even(n^2)
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 2 * m [witness: 2 * k^2]
    Hence Even(n^2)
QED

Theorem: "Even fourth power"
Claim: forall a : Int, Even(a) => Even(a^4)
Proof:
    Given a : Int
    Assume ha: Even(a)
    Therefore Even(a^2)
    Let b = a^2
    Therefore Even(b)
    Therefore Even(b^2)
    Step: a^4 = b^2
    Hence Even(a^4)
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 2
        assert reports[0].is_valid, reports[0].format_report()
        assert reports[1].is_valid, reports[1].format_report()


class TestStructuredOutputs:
    """Verify first-class structured diagnostic ranges, counterexample dictionaries, and subproof metadata."""

    def test_diagnostic_ranges_and_to_dict(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: x + 1 = x + 2
"""
        reports = checker.check_source(src)
        assert len(reports) == 1
        rep = reports[0]
        rep_dict = rep.to_dict()
        assert rep_dict["is_valid"] is False
        assert len(rep_dict["results"]) == 2

        step0 = rep.results[0]
        assert step0.diagnostic_range is not None
        assert step0.diagnostic_range["start_line"] == 1
        assert step0.diagnostic_range["start_col"] >= 1

        step1 = rep.results[1]
        assert step1.status == StepStatus.INVALID
        assert step1.diagnostic_range is not None
        assert step1.diagnostic_range["start_line"] == 2
        assert step1.counterexample_dict is not None
        assert "LHS" in step1.counterexample_dict and "RHS" in step1.counterexample_dict

    def test_subproof_metadata(self, checker: ProofChecker):
        src = """\
Theorem: "Contradiction Subproof Test"
Claim: not (1 = 0)
Proof:
    Assume h: 1 = 0
    Therefore 1 = 0
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 1
        # Test case with subproof
        src_sub = """\
Theorem: "Cases Test"
Claim: forall x : Real, x >= 0 or x < 0
Proof:
    Given x : Real
    Case x >= 0:
        Therefore x >= 0
    Case x < 0:
        Therefore x < 0
    Therefore x >= 0 or x < 0
QED
"""
        rep_sub = checker.check_source(src_sub)[0]
        assert rep_sub.is_valid
        case_step = rep_sub.results[1]
        assert case_step.subproof_metadata is not None
        assert case_step.subproof_metadata["label"] == "Case"
        assert case_step.subproof_metadata["step_count"] >= 1
        assert case_step.subproof_metadata["all_steps_valid"] is True

