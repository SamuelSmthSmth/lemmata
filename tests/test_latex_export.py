"""LaTeX export of the notation the lecture notes brought in."""

from __future__ import annotations

import pytest

from aether.core.latex_export import export_to_latex


def body(source: str) -> str:
    return export_to_latex(source, standalone=False)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("Step: lim(1/x, x, oo) = 0", r"\lim_{x \to \infty}"),
        ("Step: -oo < 1", r"-\infty &< 1"),
        ("Let n : Nat\nStep: n! = n * (n - 1)!", r"n! &= n \cdot (n - 1)!"),
        ("Step: x ∈ S", r"x &\in S"),
        ("Therefore ∀ ε > 0, ∃ δ > 0, δ < ε", r"\forall \epsilon > 0,\; \exists \delta > 0,\; \delta < \epsilon"),
        ("Therefore forall x : Real, x = x", r"\forall x \in \mathbb{R}"),
        ("Let ε : Real", r"Let $\epsilon \in \mathbb{R}$"),
    ],
)
def test_notation_is_typeset(source: str, expected: str) -> None:
    assert expected in body(source)


def test_a_structure_carrier_is_a_set_not_a_crash() -> None:
    """`Given a : G` used to raise ValueError("Unknown type: 'G'") out of the export."""
    out = body("Assume Group(G, op, e, inv)\nGiven a, b : G\nTherefore forall x : G, op(x, e) = x")
    assert r"Let $a, b \in G$" in out
    assert r"\forall x \in G" in out


def test_a_bare_proposition_step_has_no_stray_equals() -> None:
    out = body("Step: Even(4)")
    assert r"& \operatorname{Even}(4)" in out
    assert "&= \\operatorname{Even}" not in out
