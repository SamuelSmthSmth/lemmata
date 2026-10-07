"""The proof kernel decides: inside the typed core, the tactics give the verdict.

A line inside the core passes only when a named tactic proves it from the
premises it could see.  When none does, the kernel either defers to the engine
(a premise it cannot read) or says the solver alone checked it (a warning).
The engine's refusals always stand.
"""

from aether import ProofChecker
from aether.kernel import review, tactics


def last(source: str, kernel: str | None = "course"):
    return ProofChecker(kernel=kernel).check_source(source)[0].results[-1]


LINEAR = "Let x : Real\nAssume h1: x > 1\nStep: x > 0"


def test_a_tactic_decides_a_line_inside_the_core():
    result = last(LINEAR)
    assert result.status.value == "VALID"
    assert result.backend == "Kernel: linarith"


def test_no_tactic_and_every_premise_read_is_the_solver_alone(monkeypatch):
    # The tactics are made to fail, so the solver is the only checker left.
    monkeypatch.setattr(review.tactics, "weakest", lambda goal, premises, up_to=4: None)
    result = last(LINEAR)
    assert result.status.value == "WARNING"
    assert result.backend == "Kernel: solver only"
    assert result.message == review.SOLVER_ONLY


def test_premises_the_core_cannot_read_leave_the_engine_to_decide():
    # |h(5)| <= 1 is in the core; its premise, a definition's predicate
    # (Bounded(h)), is not.  No tactic can prove it, and that is no reason to
    # doubt it.  (Group cancellation used to be the example: the structure
    # rules now show it.)
    source = (
        "Definition: Bounded(f) <=> forall x : Real, abs(f(x)) <= 1\n"
        "Given h : Real -> Real\n"
        "Assume Bounded(h)\n"
        "Therefore abs(h(5)) <= 1\n"
    )
    result = last(source)
    assert result.status == last(source, kernel=None).status
    assert result.status.value == "VALID"
    assert result.backend == "Kernel: outside the core (premises)"


def test_the_engine_refusal_stands_even_when_a_tactic_proves_the_arithmetic():
    # ring proves x + 0 = x, but the cited label does not exist: still refused.
    result = last("Let x : Real\nStep: x + 0 = x [using nowhere]")
    assert result.status.value == "INVALID"
    assert "nowhere" in result.message


def test_roots_are_inside_the_core_now():
    product = "Let x : Real\nAssume h: 1 <= x and x <= 2\nStep: sqrt(4 - x^2) * sqrt(x - 1) = sqrt((4 - x^2) * (x - 1))"
    assert last(product, kernel="scratch").backend == "Kernel: nlinarith"
    dense = "Let r1, r2, t : Real\nAssume h1: r1 < r2\nAssume h2: t = r1 + (r2 - r1) / sqrt(2)\nStep: t > r1"
    assert last(dense, kernel="scratch").backend == "Kernel: nlinarith"


def test_root_bounds_are_exact():
    from sympy import Rational

    for c in (2, 3, 5, Rational(1, 2), Rational(10**6 + 1)):
        lo, hi = tactics._root_bounds(Rational(c))
        assert lo * lo < c < hi * hi


def test_off_is_unchanged():
    result = last(LINEAR, kernel=None)
    assert result.status.value == "VALID"
    assert not result.backend.startswith("Kernel")
