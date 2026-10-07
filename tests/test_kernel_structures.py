"""The kernel's structure rules: group words, subgroup closure, ring axioms."""

import pytest

from aether import ProofChecker
from aether.kernel import structures

GROUP = "Assume Group(G, op, e, inv)\nGiven a, b, x, y : G\n"


def last(source: str, kernel: str | None = "course"):
    return ProofChecker(kernel=kernel).check_source(source)[0].results[-1]


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (GROUP + "Step: inv(op(a, b)) = op(inv(b), inv(a))", "group axioms"),
        (GROUP + "Step: inv(inv(a)) = a", "group axioms"),
        (GROUP + "Step: (a * b)^-1 = b^-1 * a^-1", "group axioms"),
        (GROUP + "Step: a^2 * a^3 = a^5", "group axioms"),
        (GROUP + "Assume h1: op(a, x) = op(a, y)\nTherefore x = y", "group axioms and hypotheses"),
        (GROUP + "Assume h: op(a, b) = op(b, a)\nStep: op(op(a, b), inv(a)) = b", "group axioms and hypotheses"),
        ("Assume AbelianGroup(G, op, e, inv)\nGiven a, b : G\nStep: (a * b)^-1 = a^-1 * b^-1", "group axioms"),
        (
            "Assume Group(G, op, e, inv)\nAssume Group(H, star, eH, invH)\n"
            "Assume hom: forall x : G, forall y : G, f(op(x, y)) = star(f(x), f(y))\n"
            "Given g1, g2 : G\nAssume k1: f(g1) = eH\nAssume k2: f(g2) = eH\n"
            "Step: f(op(g1, g2)) = star(eH, eH)",
            "group axioms and hypotheses",
        ),
        (
            "Assume Group(G, op, e, inv)\nAssume Subgroup(H, G, op, e, inv)\nGiven x, y, z : G\n"
            "Assume h1: op(inv(x), y) in H\nAssume h2: op(inv(y), z) in H\n"
            "Step: op(op(inv(x), y), op(inv(y), z)) = op(inv(x), z)\nTherefore op(inv(x), z) in H",
            "subgroup closure",
        ),
        # Also the guard against a goal proving itself: by review time the line's
        # own conclusion is recorded, and read as a member it made this
        # "subgroup closure".  Only the line's visible premises count.
        (
            "Assume Group(G, op, e, inv)\nAssume NormalSubgroup(N, G, op, e, inv)\nGiven g, n : G\n"
            "Assume hn: n in N\nTherefore op(op(g, n), inv(g)) in N",
            "normal subgroup",
        ),
        (
            "Assume Ring(R, add, mul, zero, one, neg)\nGiven a, b, c : R\n"
            "Step: mul(a, add(b, c)) = add(mul(a, b), mul(a, c))",
            "ring axioms",
        ),
        (
            "Assume Field(F, add, mul, zero, one, neg, inv)\nGiven x : F\nAssume h1: x != zero\n"
            "Therefore mul(x, inv(x)) = one",
            "field axioms",
        ),
    ],
)
def test_lines_the_structure_rules_show(source, rule):
    result = last(source)
    assert result.status.value == "VALID", result.message
    assert result.backend == f"Kernel: {rule}"


@pytest.mark.parametrize(
    "source",
    [
        GROUP + "Step: op(a, b) = op(b, a)",  # a group need not be abelian
        GROUP + "Step: (a * b)^-1 = a^-1 * b^-1",
        GROUP + "Step: a^2 * b^2 = (a * b)^2",
        # Membership needs a reason: x alone is not known to lie in H.
        "Assume Group(G, op, e, inv)\nAssume Subgroup(H, G, op, e, inv)\nGiven x : G\nTherefore x in H",
    ],
)
def test_false_lines_are_not_shown(source):
    result = last(source)
    assert "group axioms" not in result.backend and "subgroup" not in result.backend


def test_a_field_inverse_needs_the_element_non_zero():
    source = "Assume Field(F, add, mul, zero, one, neg, inv)\nGiven x : F\nStep: mul(x, inv(x)) = one"
    assert "field axioms" not in last(source).backend


def test_real_numbers_are_not_read_as_group_words():
    result = last("Assume Group(G, op, e, inv)\nLet x, y : Real\nStep: x * y = y * x")
    assert result.status.value == "VALID"
    assert "group" not in result.backend


def test_rewriting_terminates_on_cycling_hypotheses():
    source = GROUP + "Assume h1: x = y\nAssume h2: y = x\nStep: op(x, inv(y)) = e"
    result = last(source)
    assert result.status.value == "VALID"
    assert structures._PASSES > 0  # bounded, whatever the rules do
