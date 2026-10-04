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

    def test_base_case_at_one_does_not_cover_zero(self, checker: ProofChecker):
        # Nat starts at 0.  A base case at 1 and a valid step used to "prove"
        # this, which is false at n = 0.
        src = """\
Theorem: "2^n >= 2 for every natural number (false at 0)"
Claim: forall n : Nat, 2^n >= 2
Proof:
    Base case n = 1:
        Step: 2^1 = 2
        Therefore 2^1 >= 2
    Inductive step:
        Given k : Nat
        Assume ih: 2^k >= 2
        Step: 2^(k + 1) = 2 * 2^k
        Step: >= 4
        Therefore 2^(k + 1) >= 2
    Therefore forall n : Nat, 2^n >= 2
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid, report.format_report()
        refusal = next(r for r in report.results if r.backend == "Induction")
        assert "0 is one" in refusal.message

    def test_base_case_at_one_is_fine_when_zero_holds_too(self, checker: ProofChecker):
        # The sum of no squares is 0, which the formula gives at n = 0, so a
        # base case at 1 (as A Level writes it) still proves it for every n.
        src = """\
Theorem: "Sum of squares"
Claim: forall n : Nat, sum(r, 1, n, r^2) = n * (n + 1) * (2 * n + 1) / 6
Proof:
    Base case n = 1:
        Step: sum(r, 1, 1, r^2) = 1
        Step: = 1 * 2 * 3 / 6
    Inductive step:
        Given k : Nat
        Assume ih: sum(r, 1, k, r^2) = k * (k + 1) * (2 * k + 1) / 6
        Step: sum(r, 1, k + 1, r^2) = sum(r, 1, k, r^2) + (k + 1)^2
        Step: = k * (k + 1) * (2 * k + 1) / 6 + (k + 1)^2
        Step: = (k + 1) * (k + 2) * (2 * k + 3) / 6
    Therefore forall n : Nat, sum(r, 1, n, r^2) = n * (n + 1) * (2 * n + 1) / 6
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_induction_over_the_integers_is_refused(self, checker: ProofChecker):
        # A base case and a step say nothing below the base: this "proved"
        # that every integer is non-negative.
        src = """\
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
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid, report.format_report()
        refusal = next(r for r in report.results if r.backend == "Induction")
        assert "natural numbers only" in refusal.message


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



class TestUnknownFunctionDiagnostics:
    """A misspelled function should read as a name error, not a maths error.

    An unrecognised call silently becomes an uninterpreted SymPy function, so
    `fact(5) = 120` was reported as an algebraic failure.  The step is still
    rejected; the message now says which name the engine did not know.
    """

    def test_misspelled_function_suggests_the_real_one(self, checker: ProofChecker):
        src = """\
Let n : Nat
Step: fact(5) = 120
"""
        report = checker.check_source(src)[0]
        step = report.results[1]
        assert step.status == StepStatus.INVALID
        assert "`fact` is not a known function" in step.message
        assert "did you mean `factorial`?" in step.message

    def test_unknown_function_in_an_inequality_is_explained(self, checker: ProofChecker):
        """Z3 will happily offer a counterexample for a call it cannot read."""
        src = """\
Let x : Real
Step: fact(x) > 1
"""
        report = checker.check_source(src)[0]
        step = report.results[1]
        assert step.status == StepStatus.INVALID
        assert "did you mean `factorial`?" in step.message

    def test_known_functions_get_no_hint(self, checker: ProofChecker):
        src = """\
Let x : Real
Assume h: x > 0
Step: ln(exp(x)) = x
"""
        report = checker.check_source(src)[0]
        step = report.results[2]
        assert step.status == StepStatus.VALID
        assert "not a known function" not in step.message

    def test_user_defined_functions_are_not_reported_as_unknown(self, checker: ProofChecker):
        src = """\
Define MyRel(a, b) <=> a = b

Let x, y : Real
Assume h: MyRel(x, y)
Therefore MyRel(x, y)
"""
        report = checker.check_source(src)[0]
        assert all("not a known function" not in r.message for r in report.results)

    def test_uninterpreted_predicate_hypothesis_still_holds(self, checker: ProofChecker):
        """An opaque predicate must keep working as a hypothesis."""
        src = """\
Let x : Real
Assume h: P(x)
Therefore P(x)
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_an_opaque_function_says_so(self, checker: ProofChecker):
        """Z3 knows exp only by its range, so its 'counterexample' may not be real.

        `exp(x) >= 1 + x + x^2/2` holds for x >= 0, but needs more of exp than
        the bounds the solver is given.
        """
        src = """\
Let x : Real
Assume h: x >= 0
Step: exp(x) >= 1 + x + x^2 / 2
"""
        step = checker.check_source(src)[0].results[-1]
        assert step.status == StepStatus.INVALID
        assert "no SMT theory" in step.message

    def test_the_solver_knows_the_range_of_exp_and_sin(self, checker: ProofChecker):
        """True range facts are given to the solver, so routine bounds go through."""
        src = """\
Let x : Real
Step: exp(x) > 0
Step: |sin(x)| <= 1
Step: cos(x) >= -1
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_range_facts_do_not_prove_false_bounds(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: exp(x) > 1
"""
        assert not checker.check_source(src)[0].is_valid

    def test_an_unimplemented_function_is_not_offered_a_lookalike(
        self, checker: ProofChecker
    ):
        """`arccot` is not a misspelling of `arccos`.

        String distance alone suggested lookalikes such as `cot` -> `dot`, which
        points a reader at a different function rather than at the problem.
        """
        src = """\
Let x : Real
Step: arccot(x) = atan(1 / x)
"""
        message = checker.check_source(src)[0].results[-1].message
        assert "not a function the engine implements" in message
        assert "did you mean" not in message

    def test_a_typo_still_gets_a_suggestion(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: sqrtt(x) = x
"""
        message = checker.check_source(src)[0].results[-1].message
        assert "did you mean `sqrt`?" in message


class TestCallArity:
    """A wrong argument count is reported, not crashed or reinterpreted.

    ``_SYMPY_FUNCS[fn](*args)`` used to be called unchecked: ``Abs(x, x)`` raised
    a TypeError that escaped ``check_source`` altogether (a 500 from the API),
    while ``log(x, 2)`` silently became a base-2 logarithm, so ``ln(x, 2)``
    quietly stopped meaning the natural log.
    """

    @pytest.mark.parametrize(
        "source",
        [
            """\
Let x : Real
Step: abs(x, x) = x
""",
            """\
Let x : Real
Step: exp(x, 2) = x
""",
            """\
Let x : Real
Step: sin(x, x) = 0
""",
            """\
Let n : Nat
Step: factorial(n, n) = 0
""",
        ],
    )
    def test_arity_misuse_does_not_escape_the_api(self, checker: ProofChecker, source: str):
        report = checker.check_source(source)[0]
        assert report.results[-1].status == StepStatus.INVALID

    def test_the_arity_is_named(self, checker: ProofChecker):
        src = """\
Let x : Real
Step: abs(x, x) = x
"""
        assert "takes 1 argument(s), but got 2" in checker.check_source(src)[0].results[-1].message

    def test_ln_does_not_quietly_become_base_two(self, checker: ProofChecker):
        """'ln(8, 2) = 3' used to be accepted as log base 2."""
        src = """\
Let x : Real
Step: ln(8, 2) = 3
"""
        step = checker.check_source(src)[0].results[-1]
        assert step.status == StepStatus.INVALID
        assert "`ln` takes 1 argument(s)" in step.message

    @pytest.mark.parametrize(
        "source",
        [
            """\
Let A = [[1, 2], [3, 4]]
Step: det(A, A) = 1
""",
            """\
Let n : Nat
Step: sum(k, 1, n) = n
""",
            """\
Step: integrate(x) = x^2 / 2
""",
            """\
Let a : Int
Step: Even(a, a)
""",
        ],
    )
    def test_a_known_name_with_the_wrong_shape_is_reported(
        self, checker: ProofChecker, source: str
    ):
        step = checker.check_source(source)[0].results[-1]
        assert step.status == StepStatus.INVALID
        assert "argument" in step.message

    def test_the_valid_forms_still_check(self, checker: ProofChecker):
        src = """\
Let n : Nat
Step: sum(k, 1, n, 1) = n
Step: diff(n^2, n) = 2 * n
Step: integrate(2 * n, n) = n^2
Step: lim(sin(n) / n, n, 0) = 1
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_domain_warnings_are_not_repeated(self, checker: ProofChecker):
        """'sqrt(x) + sqrt(x)' extracted the same obligation three times."""
        src = """\
Let x : Real
Step: sqrt(x) + sqrt(x) = 2 * sqrt(x)
"""
        report = checker.check_source(src)[0]
        warnings = report.results[-1].domain_warnings
        assert warnings
        assert len(warnings) == len(set(warnings))


class TestMathematicalConstants:
    r"""`pi` and `e` are the numbers -- unless the name is in use as a variable.

    Both used to be ordinary free variables, so `sin(\pi) = 0` was rejected
    with "Counterexample at pi=3: LHS = sin(3)".
    """

    @pytest.mark.parametrize(
        "source",
        [
            r"Step: sin(\pi) = 0",
            r"Step: sin(pi) = 0",
            r"Step: cos(\pi) = -1",
            r"Step: ln(e) = 1",
            r"Step: exp(1) = e",
        ],
    )
    def test_the_identities_hold(self, checker: ProofChecker, source: str):
        report = checker.check_source(source)[0]
        assert report.is_valid, report.format_report()

    @pytest.mark.parametrize(
        "source",
        ["Step: pi > 3", "Step: pi < 4", "Step: e > 2", "Step: e < 3", "Step: pi != 3"],
    )
    def test_ordinary_comparisons_are_provable(self, checker: ProofChecker, source: str):
        """The SMT backend gives the constants true, if loose, bounds."""
        report = checker.check_source(source)[0]
        assert report.is_valid, report.format_report()

    def test_a_declared_name_is_a_variable_again(self, checker: ProofChecker):
        src = """\
Let pi : Real
Assume h: pi = 5
Step: pi^2 = 25
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()

    def test_a_structure_identity_keeps_its_name(self, checker: ProofChecker):
        """`e` is the group identity in the templates, not Euler's number."""
        src = """\
Theorem: "Identity element"
Proof:
    Assume Group(G, op, e, inv)
    Given a : Real
    Step: op(a, e) = a
    Step: op(a, inv(a)) = e
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()


class TestSubproofAuditing:
    """Verifies that statements inside nested subproofs are audited line-by-line."""

    def test_subproof_auditing_details(self, checker: ProofChecker):
        src = """\
Given x : Int
Case x >= 0:
    Assume h1: x >= 0
    Step: x + 1 >= 1
Case x < 0:
    Assume h2: x < 0
    Step: x - 1 < -1
Hence x >= 0 or x < 0
"""
        report = checker.check_source(src)[0]
        assert report.is_valid
        # Top-level results: Given, Case 1, Case 2, Hence
        assert len(report.results) == 4
        # all_results flattens subproof statements: 4 top-level + 2 in Case 1 + 2 in Case 2 = 8
        assert len(report.all_results) == 8

        case1 = report.results[1]
        assert len(case1.sub_results) == 2
        assert case1.sub_results[0].line == 3
        assert case1.sub_results[0].status == StepStatus.VALID
        assert case1.sub_results[1].line == 4
        assert case1.sub_results[1].status == StepStatus.VALID

        formatted = report.format_report()
        # Verify that the inner statements appear in the formatted audit log
        assert "Assume h1: x >= 0" in formatted
        assert "Step: (x + 1) >= 1" in formatted or "x + 1 >= 1" in formatted
        assert "Assume h2: x < 0" in formatted
        assert "Step: (x - 1) < (-1)" in formatted or "(x - 1) <" in formatted

