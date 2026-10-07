"""The kernel's calculus rules: derivatives by the rules, integrals by the FTC.

SymPy may propose (an antiderivative); the kernel checks.  A line the rules
show is named by them; a line they do not reach keeps the engine's verdict.
"""

import pytest
import sympy as sp

from aether import ProofChecker
from aether.kernel import calculus

HEAD = "Let x, n : Real\nLet f, g : Real -> Real\n"


def last(step: str, kernel: str | None = "course"):
    return ProofChecker(kernel=kernel).check_source(HEAD + step)[0].results[-1]


@pytest.mark.parametrize(
    ("step", "rule"),
    [
        ("Step: diff(x^3, x) = 3*x^2", "power rule"),
        ("Step: diff(x^n, x) = n*x^(n-1)", "power rule"),
        ("Step: diff(f(x)*g(x), x) = diff(f(x), x)*g(x) + f(x)*diff(g(x), x)", "product rule"),
        ("Step: diff(sin(x^2), x) = 2*x*cos(x^2)", "chain rule"),
        ("Step: integrate(3*t^2, t, 1, 2) = 7", "FTC"),
        ("Step: integrate(cos(x), x, 0, pi) = 0", "FTC"),
    ],
)
def test_a_line_the_rules_show_is_named_by_them(step, rule):
    result = last(step)
    assert result.status.value == "VALID", result.message
    assert result.backend.startswith("Kernel: ") and rule in result.backend


def test_the_quotient_rule_is_named_once():
    rules = []
    src = HEAD + "Step: diff(f(x)/g(x), x) = (diff(f(x), x)*g(x) - f(x)*diff(g(x), x)) / g(x)^2"
    from aether.kernel import review

    original = review.Kernel._review

    def spy(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed=None):
        rules.append(calculus.verify(obligation, ctx))
        return original(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed)

    review.Kernel._review = spy
    try:
        ProofChecker(kernel="scratch").check_source(src)
    finally:
        review.Kernel._review = original
    assert rules[-1] == ["quotient rule"]


@pytest.mark.parametrize(
    "step",
    [
        "Step: diff(x^3, x) = 3*x^3",  # forgetting to lower the power
        "Step: integrate(1/x^2, x, -1, 1) = -2",  # FTC needs f continuous on [a, b]
    ],
)
def test_false_lines_are_not_shown_by_the_rules(step):
    result = last(step)
    assert result.status.value == "INVALID"
    assert "rule" not in result.backend and "FTC" not in result.backend


def test_the_rules_never_call_sympys_differentiation(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the kernel's rules must not ask SymPy for a derivative")

    monkeypatch.setattr(sp.Expr, "diff", refuse)
    x = sp.Symbol("x", real=True)
    rules: set[str] = set()
    assert sp.simplify(calculus.derivative(sp.sin(x**2) * sp.exp(x), x, rules) - (2 * x * sp.cos(x**2) * sp.exp(x) + sp.sin(x**2) * sp.exp(x))) == 0
    assert {"product rule", "chain rule"} <= rules


def test_a_wrong_antiderivative_from_sympy_would_be_caught(monkeypatch):
    x = sp.Symbol("x", real=True)
    monkeypatch.setattr(sp, "integrate", lambda f, var: x**2)  # not an antiderivative of cos
    with pytest.raises(calculus._Unproven):
        calculus._definite(sp.cos(x), x, sp.Integer(0), sp.pi, set())


def test_off_is_unchanged():
    result = last("Step: diff(x^3, x) = 3*x^2", kernel=None)
    assert result.status.value == "VALID"
    assert not result.backend.startswith("Kernel")
