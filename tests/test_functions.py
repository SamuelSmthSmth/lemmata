"""Functions as the notes use them: declared, defined, and talked about.

`Given f : Real -> Real` declares an abstract function; a definition may take a
function as an argument (`Continuous(f, a)`), and the notes' own heading
`Definition 2.6 (Continuity): …` introduces one.
"""

import pytest

from aether import ParseError, ProofChecker

CONTINUOUS = (
    "Definition 2.6 (Continuity): Continuous(f, a) <=> forall ε > 0, exists δ > 0, "
    "forall x : Real, abs(x - a) < δ => abs(f(x) - f(a)) < ε"
)


def statuses(source: str, **kwargs) -> list[str]:
    reports = ProofChecker().check_source(source, **kwargs)
    return [r.status.value for rep in reports for r in rep.results]


def last(source: str, **kwargs):
    return ProofChecker().check_source(source, **kwargs)[-1].results[-1]


def test_a_declared_function_is_one_function_whatever_its_arguments_look_like():
    source = "Given f : Real -> Real\nAssume forall x : Real, f(x) > 0\nTherefore f(2) > 0"
    assert statuses(source) == ["VALID"] * 3


@pytest.mark.parametrize("spelling", ["Real -> Real", "ℝ → ℝ", "R -> R", "\\mathbb{R} \\to \\mathbb{R}"])
def test_function_types_are_written_as_the_notes_write_them(spelling):
    result = ProofChecker().check_source(f"Let f : {spelling}")[0].results[0]
    assert result.status.value == "VALID"
    assert result.active_variables == {"f": "Real -> Real"}


def test_an_integer_function_keeps_its_type():
    source = "Given g : Int -> Int\nAssume forall n : Int, g(n) = 2 * n\nTherefore g(3) = 6"
    assert statuses(source) == ["VALID"] * 3


def test_a_function_of_two_arguments():
    source = "Given F : Real -> Real -> Real\nAssume forall x : Real, forall y : Real, F(x, y) = F(y, x)\nTherefore F(1, 2) = F(2, 1)"
    assert statuses(source)[-1] == "VALID"


def test_calling_a_function_with_the_wrong_number_of_arguments_is_reported():
    result = last("Given f : Real -> Real\nTherefore f(1, 2) > 0")
    assert result.status.value == "INVALID" and "takes 1 argument" in result.message


def test_a_function_type_names_number_types_only():
    result = last("Given f : Real -> Vector")
    assert result.status.value == "INVALID" and "number types" in result.message


def test_without_the_hypothesis_nothing_is_known_about_f():
    assert last("Given f : Real -> Real\nTherefore f(2) > 0").status.value == "INVALID"


@pytest.mark.parametrize(
    "heading", ["Definition:", "Definition 2.6:", "Definition 2.6 (Big numbers):", "definition (Big):", "Define"]
)
def test_the_notes_definition_heading(heading):
    source = f"{heading} Big(x) <=> x > 10\nLet y : Real\nAssume Big(y)\nTherefore y > 5"
    assert statuses(source) == ["VALID"] * 4


def test_definition_alone_is_still_a_parse_error_without_a_body():
    with pytest.raises(ParseError):
        ProofChecker().check_source("Definition 2.6 (Continuity):")


def test_a_definition_about_functions_is_used_when_assumed():
    source = (
        "Definition: Bounded(f) <=> forall x : Real, abs(f(x)) <= 1\n"
        "Given h : Real -> Real\nAssume Bounded(h)\nTherefore abs(h(5)) <= 1"
    )
    assert statuses(source) == ["VALID"] * 4


def test_a_definition_about_functions_is_not_satisfied_by_any_function():
    source = "Definition: Bounded(f) <=> forall x : Real, abs(f(x)) <= 1\nGiven h : Real -> Real\nTherefore Bounded(h)"
    assert last(source).status.value == "INVALID"


def test_a_defined_function_can_be_the_argument():
    source = f"{CONTINUOUS}\nLet g(x) = 3 * x\nTherefore Continuous(g, 2)"
    assert statuses(source) == ["VALID"] * 3


def test_continuity_proved_as_the_notes_prove_it():
    source = f"""{CONTINUOUS}
Let g(x) = 3 * x
Theorem: "3x is continuous at 2"
Claim: Continuous(g, 2)
Proof:
    Given ε : Real
    Assume h1: ε > 0
    Let δ = ε / 3
    Step: δ > 0
    Subproof:
        Given x : Real
        Assume hx: abs(x - 2) < δ
        Step: abs(g(x) - g(2)) = 3 * abs(x - 2)
        Step: < 3 * δ
        Step: = ε
    Therefore exists d > 0, forall x : Real, abs(x - 2) < d => abs(g(x) - g(2)) < ε [witness: δ]
QED
"""
    reports = ProofChecker().check_source(source)
    assert all(rep.is_valid for rep in reports)
    assert reports[-1].results[-1].message == "QED: Theorem claim 'Continuous(g, 2)' verified."


def test_a_proof_whose_assumption_the_definition_does_not_license_fails_at_qed():
    source = f"""{CONTINUOUS}
Let g(x) = 3 * x
Theorem: "wrong"
Claim: Continuous(g, 2)
Proof:
    Given ε : Real
    Assume h1: ε > 5
    Therefore exists d > 0, forall x : Real, abs(x - 2) < d => abs(g(x) - g(2)) < ε [witness: ε / 3]
QED
"""
    assert ProofChecker().check_source(source)[-1].results[-1].status.value == "INVALID"


# Proved by induction, so the solver cannot reach the claim for a symbolic n
# alone; it is stated through a definition the citing proof does not have.
LEMMA = """\
Definition: TwoDivides(m) <=> MultipleOf(m, 2)
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: forall n : Nat, TwoDivides(3^n - 1)
Proof:
    Base case n = 0:
        Step: 3^0 - 1 = 2 * 0
        Therefore exists m : Int, 3^0 - 1 = 2 * m [witness: 0]
        Hence TwoDivides(3^0 - 1)

    Inductive step:
        Given k : Nat
        Assume ih: TwoDivides(3^k - 1)
        Obtain m : Int such that 3^k - 1 = 2 * m from ih
        Step: 3^(k+1) - 1 = 3 * (2 * m + 1) - 1
        Step: = 2 * (3 * m + 1)
        Therefore exists j : Int, 3^(k+1) - 1 = 2 * j [witness: 3 * m + 1]
        Hence TwoDivides(3^(k+1) - 1)
QED
"""
SOURCES = {"lemma.aether": LEMMA}
CITATIONS = {"Lemma A": "lemma.aether"}


def test_the_lemma_itself_checks():
    assert all(rep.is_valid for rep in ProofChecker().check_source(LEMMA))


def test_a_cited_results_definitions_come_with_it():
    result = last("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma A", sources=SOURCES, citations=CITATIONS)
    assert result.status.value == "VALID", result.message


def test_lent_definitions_are_for_the_citing_step_only():
    source = "Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma A\nTherefore TwoDivides(3^j - 1)"
    result = last(source, sources=SOURCES, citations=CITATIONS)
    assert result.status.value == "INVALID"
    assert not any("TwoDivides" in h for h in result.active_hypotheses)
