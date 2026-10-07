"""A counterexample is shown only when it is one.

Z3 reasons about what it is told: a function it has no theory of is any
function at all, so its model can give floor(-1) the value 7 and call x = -1 a
counterexample to floor(x) <= x.  Two fixes: the facts every value of floor,
ceiling and factorial satisfies, so such lines are proved; and, for what is
left, the model is evaluated with each function's real meaning before it is
shown, and a model at which the claim holds is not called a counterexample.
"""

import pytest

from aether import ProofChecker


def last(source: str, kernel=None):
    return ProofChecker(kernel=kernel).check_source(source)[0].results[-1]


@pytest.mark.parametrize(
    "source",
    [
        "Let x : Real\nStep: floor(x) <= x",
        "Let x : Real\nStep: floor(x) > x - 1",
        "Let x : Real\nStep: ceiling(x) >= x",
        "Let n : Nat\nStep: factorial(n) >= 1",
        "Let n : Nat\nStep: factorial(n) >= n",
    ],
)
@pytest.mark.parametrize("kernel", [None, "course"])
def test_true_facts_about_floor_ceiling_and_factorial_are_proved(source, kernel):
    result = last(source, kernel)
    assert result.status.value == "VALID", result.message


@pytest.mark.parametrize(
    ("source", "counterexample"),
    [
        ("Let x : Real\nStep: floor(x) >= x", "x="),
        ("Let n : Nat\nStep: factorial(n) >= 2", "n=0"),
        ("Let n : Nat\nStep: 3^n >= 3", "n=0"),
        ("Let x : Real\nStep: sin(x) <= 1/2", "x="),
    ],
)
def test_false_claims_keep_their_real_counterexample(source, counterexample):
    result = last(source)
    assert result.status.value == "INVALID"
    assert result.counterexample and result.counterexample.startswith(counterexample)


@pytest.mark.parametrize(
    "source",
    [
        "Let x : Real\nStep: sin(x)^2 + cos(x)^2 >= 1",
        "Let x : Real\nStep: arctan(x) < 2",
    ],
)
def test_a_model_at_which_the_claim_holds_is_not_a_counterexample(source):
    result = last(source)
    assert result.status.value == "INVALID"  # still unproved: the solver lacks a fact
    assert result.counterexample is None
    assert "is not a counterexample" in result.message


def test_a_power_claim_gets_a_second_try_with_the_growth_fact():
    # 3^n >= 3 from n >= 1 needs b^e >= b; stated for every power it slowed the
    # divisibility inductions, so it is only tried when the first query fails.
    assert last("Let n : Nat\nAssume n >= 1\nStep: 3^n >= 3").status.value == "VALID"
    false = last("Let n : Nat\nStep: 3^n >= 3")
    assert false.status.value == "INVALID" and false.counterexample.startswith("n=0")


def test_a_square_root_under_a_quantifier_depends_on_its_variable():
    assert last("Therefore forall x : Real, (x >= 0 => sqrt(x)^2 = x)").status.value == "VALID"
    unguarded = last("Therefore forall x : Real, sqrt(x)^2 = x")
    assert unguarded.status.value == "INVALID"
