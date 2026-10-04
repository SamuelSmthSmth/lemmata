"""Hints: what to do about a step that did not check, and a fix when one is sure.

Hints never change a verdict, so every test here also pins the status.
"""

from aether import ProofChecker


def first_failure(source: str):
    reports = ProofChecker().check_source(source)
    return next(r for rep in reports for r in rep.results if r.status.value != "VALID")


def apply(source: str, fix: dict) -> str:
    """Apply a fix as the editor does."""
    lines = source.split("\n")
    i = fix["line"] - 1
    if "insert_before" in fix:
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        lines.insert(i, indent + fix["insert_before"])
    else:
        text = lines[i]
        lines[i] = text[: fix["col_start"] - 1] + fix["text"] + text[fix["col_end"] - 1 :]
    return "\n".join(lines)


def verdict(source: str) -> str:
    reports = ProofChecker().check_source(source)
    if any(not r.is_valid for r in reports):
        return "INVALID"
    return "WARN" if any(r.has_warnings for r in reports) else "VALID"


def test_a_domain_obligation_offers_to_assume_it_and_the_fix_works():
    source = "Let x : Real\nStep: (x^2 - 1) / (x - 1) = x + 1"
    result = first_failure(source)
    assert result.status.value == "WARNING"
    (hint,) = result.hints
    assert "x - 1 ≠ 0" in hint["message"] and "fails at x=1" in hint["message"]
    assert hint["fix"] == {"line": 2, "insert_before": "Assume x - 1 != 0", "label": "Add Assume x - 1 ≠ 0"}
    assert verdict(apply(source, hint["fix"])) == "VALID"


def test_an_algebra_slip_says_how_far_apart_the_sides_are_in_the_students_symbols():
    result = first_failure("Fix ε > 0\nLet δ = ε / 2\nStep: 3 * δ = ε")
    assert result.status.value == "INVALID"
    assert {"message": "The two sides differ by ε/2."} in result.hints


def test_a_strict_inequality_that_holds_non_strictly_offers_the_swap():
    source = "Let x : Real\nAssume x >= 2\nTherefore x > 2"
    result = first_failure(source)
    hint = next(h for h in result.hints if "holds with" in h["message"])
    assert hint["fix"]["text"] == "≥"
    assert verdict(apply(source, hint["fix"])) == "VALID"


def test_no_swap_is_offered_when_the_weaker_relation_fails_too():
    result = first_failure("Let x : Real\nAssume x >= 2\nTherefore x > 5")
    assert not any("holds with" in h["message"] for h in result.hints)


def test_a_mistyped_label_suggests_the_one_in_scope():
    source = "Let x : Real\nAssume h1: x > 2\nStep: x > 1 by h2"
    result = first_failure(source)
    (hint,) = result.hints
    assert hint["message"] == "There is no h2 here. Did you mean h1?"
    assert hint["fix"]["was"] == "h2"
    assert verdict(apply(source, hint["fix"])) == "VALID"


def test_a_label_from_a_closed_block_says_where_it_was():
    source = (
        'Theorem: "t"\nProof:\n    Let x : Real\n    Case x >= 0:\n        Assume hp: x >= 0\n'
        "        Step: x >= 0\n    Case x < 0:\n        Step: x < 0\n    Step: x * x >= 0 by hp\nQED"
    )
    result = first_failure(source)
    assert result.hints[0]["message"].startswith("hp was introduced on line 5")


def test_a_mistyped_predicate_suggests_the_known_one():
    source = "Let n : Int\nAssume Even(n)\nTherefore Evn(n)"
    result = first_failure(source)
    hint = next(h for h in result.hints if "Did you mean Even" in h["message"])
    assert verdict(apply(source, hint["fix"])) == "VALID"


def test_a_mixed_chain_explains_itself():
    result = first_failure("Let x : Real\nAssume h: x >= 3\nStep: x >= 3\nStep: <= 5")
    assert any("one way" in h["message"] for h in result.hints)


def test_steps_that_check_carry_no_hints():
    reports = ProofChecker().check_source("Let x : Real\nAssume x > 2\nStep: x > 1")
    assert all(r.hints == [] for rep in reports for r in rep.results)


def test_hints_travel_in_the_dict_form():
    result = first_failure("Let x : Real\nAssume x >= 2\nTherefore x > 2")
    assert result.to_dict()["hints"] == result.hints
