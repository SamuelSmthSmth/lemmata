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


# ---------------------------------------------------------------------------
# Limits and sums
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "rule"),
    [
        ("Step: lim(x + 1, x, 2) = 3", "substitution"),
        ("Step: lim(((x + h)^2 - x^2) / h, h, 0) = 2*x", "cancel, then substitute"),
        ("Step: lim(x * sin(1/x), x, 0) = 0", "squeeze"),
        ("Step: lim(sin(x) / x, x, 0) = 1", "L'Hôpital's rule"),
        ("Step: lim((2*x^2 - x + 1) / (3*x^2 + 2*x - 1), x, oo) = 2/3", "dominant terms"),
        ("Step: lim(1/x, x, 0, \"+\") = oo", "algebra of limits"),
        ("Step: lim(x / abs(x), x, 0, \"-\") = -1", "sign near the point"),
        ("Step: lim((1 + 1/x)^x, x, oo) = e", "L'Hôpital's rule"),
        ("Step: sum(k, 1, n, 2*k - 1) = n^2", "closed form, by induction"),
        ("Step: sum(k, 1, 4, k^2) = 30", "direct sum"),
        ("Step: sum(k, 1, 0, k) = 0", "empty sum"),
        ("Step: sum(r, 1, n + 1, f(r)) = sum(r, 1, n, f(r)) + f(n + 1)", "peeling the last term"),
    ],
)
def test_limits_and_sums_the_rules_show(step, rule):
    result = last(step)
    assert result.status.value == "VALID", result.message
    assert rule in result.backend


@pytest.mark.parametrize(
    "step",
    [
        "Step: lim(1/x, x, 0) = oo",  # two-sided: -oo from the left
        "Step: lim(sin(1/x), x, 0) = 0",  # no limit
        "Step: lim(x / abs(x), x, 0) = 1",  # the one-sided limits differ
        "Step: sum(k, 1, n, 2*k - 1) = n^2 + 1",
        "Step: sum(r, 1, n + 1, 1/r^2) = sum(r, 1, n, 1/r^2) + 1/n^2",  # peeled the wrong term
    ],
)
def test_the_pack_traps_are_not_shown_by_the_rules(step):
    result = last(step)
    assert result.status.value == "INVALID"
    assert "calculus" not in result.message


def test_a_closed_form_sympy_proposes_is_checked_by_induction(monkeypatch):
    k, n = sp.Symbol("k", integer=True), sp.Symbol("n", integer=True)
    # A wrong proposal (n^2 + 1 for the sum of odd numbers) fails the check.
    monkeypatch.setattr(sp, "summation", lambda body, limits: limits[2] ** 2 + 1)
    assert calculus._closed_form(2 * k - 1, k, sp.Integer(1), n) is None


def test_an_index_named_i_is_the_index_not_the_imaginary_unit():
    result = last("Let y : Nat -> Real\nStep: sum(i, 1, n, y(i) - y(i - 1)) = y(n) - y(0)")
    assert result.status.value == "VALID", result.message
    assert "telescoping" in result.backend


def test_the_geometric_sum_needs_r_not_1_before_the_rules_show_it():
    head = "Let r : Real\nLet n : Nat\n"
    step = "Step: sum(k, 0, n, r^k) = (1 - r^(n+1)) / (1 - r)"
    bare = ProofChecker(kernel="course").check_source(head + step)[0].results[-1]
    assert "closed form" not in bare.backend  # the notes' own trap: false at r = 1
    assumed = ProofChecker(kernel="course").check_source(head + "Assume h: r != 1\n" + step)[0].results[-1]
    assert assumed.status.value == "VALID"
    assert "closed form, by induction" in assumed.backend


def test_a_line_named_by_the_rules_keeps_its_premises_complete():
    # The dependency audit reads a line's premises from the engine's algebra
    # when its backend says that is where the verdict came from; the named
    # rules' backends must count, or the proof graph loses every such line.
    src = HEAD + "Assume h: x > 0\nStep: lim(x + 1, x, 2) = 3\nStep: diff(x^3, x) = 3*x^2"
    for result in ProofChecker(kernel="course", dependencies=True).check_source(src)[0].results[-2:]:
        assert result.backend.startswith("Kernel: ")
        assert result.premises_complete, result.backend
