"""Citing results by name: `by Lemma A`, `By the divisibility lemma, ...`.

The citation index (``check_source(..., citations=...)``) names results held in
``sources``; a cited result is used for the citing step alone, and unknown or
ambiguous citations are reported, never guessed.
"""

from aether import ProofChecker
from aether.engine.citations import CitationIndex, normalise, split_parts

# Proved by induction, so the solver cannot reach it for a symbolic n alone.
LEMMA = """\
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: forall n : Nat, MultipleOf(3^n - 1, 2)
Proof:
    Base case n = 0:
        Step: 3^0 - 1 = 0
        Step: = 2 * 0
        Therefore exists m : Int, 3^0 - 1 = 2 * m [witness: 0]
        Hence MultipleOf(3^0 - 1, 2)

    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(3^k - 1, 2)
        Obtain m : Int such that 3^k - 1 = 2 * m from ih
        Step: 3^(k+1) - 1 = 3 * 3^k - 1
        Step: = 3 * (2 * m + 1) - 1
        Step: = 6 * m + 2
        Step: = 2 * (3 * m + 1)
        Therefore exists j : Int, 3^(k+1) - 1 = 2 * j [witness: 3 * m + 1]
        Hence MultipleOf(3^(k+1) - 1, 2)
QED
"""

SOURCES = {"@me/lemmas/divisibility.aether": LEMMA, "@other/pack/divisibility.aether": LEMMA}
CITATIONS = {
    "Lemma A": [["Lemma A · Divisibility of 3^n - 1 by 2", "@me/lemmas/divisibility.aether"]],
    "the divisibility lemma": "@me/lemmas/divisibility.aether",
    "Theorem 2.1": [["MTH2008 Theorem 2.1", "@me/lemmas/divisibility.aether"], ["MTH2010 Theorem 2.1", "@other/pack/divisibility.aether"]],
}


def last(source: str, citations=CITATIONS):
    reports = ProofChecker().check_source(source, sources=SOURCES, citations=citations)
    return reports[-1].results[-1]


def test_the_lemma_itself_checks():
    assert all(r.is_valid for r in ProofChecker().check_source(LEMMA))


def test_without_the_citation_the_step_fails():
    assert last("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2)").status.value == "INVALID"


def test_citing_it_makes_the_step_check_and_says_so():
    result = last("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma A")
    assert result.status.value == "VALID"
    assert "by Lemma A · Divisibility of 3^n - 1 by 2" in result.message
    assert result.citation["key"] == "@me/lemmas/divisibility.aether"
    assert result.to_dict()["citation"]["cited"] == "Lemma A"


def test_the_by_sentence_form_cites_too():
    assert last("Let j : Nat\nBy the divisibility lemma, MultipleOf(3^j - 1, 2)").status.value == "VALID"
    assert last("Let j : Nat\nStep: MultipleOf(3^j - 1, 2) [by Lemma A]").status.value == "VALID"


def test_a_citation_is_for_its_step_only():
    source = "Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma A\nLet i : Nat\nTherefore MultipleOf(3^i - 1, 2)"
    assert last(source).status.value == "INVALID"


def test_an_ambiguous_citation_lists_the_candidates():
    result = last("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Theorem 2.1")
    assert result.status.value == "INVALID" and result.backend == "Citation"
    assert "MTH2008 Theorem 2.1" in result.message and "MTH2010 Theorem 2.1" in result.message


def test_an_unknown_citation_suggests_near_names():
    result = last("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma B")
    assert result.status.value == "INVALID"
    assert "No result called 'Lemma B'" in result.message and "'Lemma A'" in result.message


def test_labels_and_methods_still_justify():
    assert last("Let x : Real\nAssume h1: x > 2\nStep: x > 1 by h1").status.value == "VALID"
    assert last("Let k : Int\nStep: 2 * k + 2 * k = 4 * k [by algebra]").status.value == "VALID"


def test_without_an_index_nothing_changes():
    result = last("Let x : Real\nAssume h1: x > 2\nStep: x > 1 by h1", citations=None)
    assert result.status.value == "VALID" and result.citation is None


def test_a_justification_ends_at_its_line():
    reports = ProofChecker().check_source("Let k : Int\nStep: 2 * k + 2 * k = 4 * k by algebra\nStep: k = k")
    assert [r.status.value for r in reports[0].results] == ["VALID", "VALID", "VALID"]


def test_names_are_matched_after_normalising():
    assert normalise("The  Triangle Inequality") == "triangle inequality"
    assert normalise("Theorem 1.1 – part") == "theorem 1.1 - part"
    index = CitationIndex({"the triangle inequality": "a.aether"})
    assert index.lookup("Triangle inequality")[0].key == "a.aether"
    assert split_parts("by Theorem 1.1 and h1, algebra") == ["Theorem 1.1", "h1", "algebra"]
