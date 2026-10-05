"""Show your working (ProofChecker(show_working=True)).

A step that does in one jump what a question asks to see (a derivative
needing the product rule, a sum's closed form, a divisibility settled by
checking remainders) is a warning naming what working is expected.  Writing
the working out passes; standard results pass; and with the option off,
nothing changes.
"""

import pytest

from aether import ProofChecker, StepStatus


def run(source: str, working: bool = True):
    return ProofChecker(show_working=working).check_source(source)[0]


def statuses(report):
    return [r.status for r in report.results]


JUMPS = {
    "product rule": "Let x : Real\nStep: diff(x^2 * sin(x), x) = 2 * x * sin(x) + x^2 * cos(x)\n",
    "chain rule": "Let x : Real\nStep: diff((x^2 + 1)^5, x) = 10 * x * (x^2 + 1)^4\n",
    "quotient rule": "Let x : Real\nAssume h: x != -1\nStep: diff(x / (x + 1), x) = 1 / (x + 1)^2\n",
    "by parts": "Let x : Real\nStep: integrate(x * exp(x), x) = x * exp(x) - exp(x)\n",
    "method of differences": "Let a, r : Real\nLet n : Nat\nAssume hr: r != 1\nStep: sum(k, 0, n - 1, a * r^k) = a * (1 - r^n) / (1 - r)\n",
    "indeterminate": "Let x : Real\nStep: lim(((x + h)^2 - x^2) / h, h, 0) = 2 * x\n",
    "remainder": "Given n : Int\nTherefore MultipleOf(n^3 - n, 6)\n",
}

WORKED = {
    "product rule written out": (
        "Let x : Real\n"
        "Step: diff(x^2 * sin(x), x) = diff(x^2, x) * sin(x) + x^2 * diff(sin(x), x)\n"
        "Step: = 2 * x * sin(x) + x^2 * cos(x)\n"
    ),
    "standard results": "Let x : Real\nStep: diff(sin(3 * x), x) = 3 * cos(3 * x)\nStep: diff(x^5, x) = 5 * x^4\nStep: integrate(x^2, x) = x^3 / 3\n",
    "a sum's last term": "Let k : Nat\nStep: sum(r, 1, k + 1, r^2) = sum(r, 1, k, r^2) + (k + 1)^2\n",
    "a limit after cancelling": (
        "Let x : Real\n"
        "Step: lim(((x + h)^2 - x^2) / h, h, 0) = lim(2 * x + h, h, 0)\n"
        "Step: = 2 * x\n"
    ),
}


@pytest.mark.parametrize("name", sorted(JUMPS))
def test_a_jump_warns_with_the_option_on(name: str):
    report = run(JUMPS[name])
    assert report.is_valid, report.format_report()
    flagged = [r for r in report.results if r.status == StepStatus.WARNING and "Show your working" in r.message]
    assert flagged, report.format_report()


@pytest.mark.parametrize("name", sorted(JUMPS))
def test_the_same_jump_is_plainly_valid_with_it_off(name: str):
    report = run(JUMPS[name], working=False)
    assert report.is_valid and not report.has_warnings, report.format_report()


@pytest.mark.parametrize("name", sorted(WORKED))
def test_working_shown_passes(name: str):
    report = run(WORKED[name])
    assert report.is_valid and not report.has_warnings, report.format_report()


def test_the_warning_names_the_rule():
    report = run(JUMPS["product rule"])
    assert "the product rule" in report.results[-1].message


def test_cases_written_out_are_not_called_a_shortcut():
    report = run('''Theorem: "n^2 + n is even"
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 2 * (2 * k^2 + k)
        Therefore Even(n^2 + n)
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 2 * (2 * k^2 + 3 * k + 1)
        Therefore Even(n^2 + n)
    Therefore Even(n^2 + n)
QED
''')
    assert report.is_valid and not report.has_warnings, report.format_report()
