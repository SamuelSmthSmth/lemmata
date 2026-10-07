"""Quantified statements by natural deduction: ∧-, ∀- and ⇒-introduction,
with a core tactic at each leaf."""

import pytest

from aether import ProofChecker


def last(source: str, kernel: str = "scratch"):
    return ProofChecker(kernel=kernel).check_source(source)[0].results[-1]


@pytest.mark.parametrize(
    ("source", "backend"),
    [
        ("Therefore forall a : Int, forall b : Int, a + b = b + a", "Kernel: ∀-intro, ring"),
        ("Therefore forall n : Nat, 1 / (n + 1) > 0", "Kernel: ∀-intro, nlinarith"),
        (
            "Therefore forall epsilon, (epsilon > 0 => forall delta, (delta > 0 => epsilon * delta > 0))",
            "Kernel: ∀-intro, ⇒-intro, nlinarith",
        ),
        ("Let c : Real\nAssume hc: c > 0\nTherefore forall x : Real, (x > 0 => c * x > 0)", "Kernel: ∀-intro, ⇒-intro, nlinarith"),
    ],
)
def test_quantified_lines_the_rules_show(source, backend):
    result = last(source)
    assert result.status.value == "VALID", result.message
    assert result.backend == backend


def test_a_false_quantified_line_is_not_shown():
    result = last("Therefore forall a, (a > 0 => forall b, (b > 0 => a - b > 0))")
    assert result.status.value == "INVALID"
    assert "intro" not in result.backend


def test_an_exists_without_a_witness_is_left_to_the_proof():
    result = last("Therefore forall x, exists y : Real, y > x")
    assert "intro" not in result.backend


def test_the_fresh_variable_does_not_escape():
    source = "Therefore forall x : Real, x = x\nLet x_0 : Real\nStep: x_0 = x_0"
    assert last(source).status.value == "VALID"


def test_course_still_asks_for_the_variables_to_be_introduced():
    result = last("Therefore forall a : Int, forall b : Int, a + b = b + a", kernel="course")
    assert result.status.value == "INVALID"
    assert "too big a step" in result.message


@pytest.mark.parametrize(
    "source",
    [
        "Therefore forall m : Nat, m * (1 / m) = 1",  # false at m = 0
        "Therefore forall x : Real, sqrt(x)^2 = x",  # false for x < 0
    ],
)
def test_a_leaf_must_show_its_own_domain(source):
    # Under a quantifier the rules introduced, the engine's domain check does
    # not reach the leaf: field reads m * (1/m) as 1 and ring sqrt(x)^2 as x.
    assert "intro" not in last(source).backend


def test_the_domain_can_come_from_the_assumption():
    result = last("Therefore forall m : Nat, (m >= 1 => m * (1 / m) = 1)")
    assert result.status.value == "VALID"
    assert result.backend == "Kernel: ∀-intro, ⇒-intro, field"
