"""Phrasing as lecture notes write it.

Each form maps onto a statement the checker already knows, so these tests pin
two things: the form parses to that statement, and it checks the same way.
"""

import pytest

from aether import ProofChecker
from aether.core.ast import DeduceNode, VarDeclNode
from aether.parser.parser import AetherParser


def statements(source: str):
    doc = AetherParser().parse(source)
    return list(doc.statements)


def verdict(source: str) -> str:
    reports = ProofChecker().check_source(source)
    if any(not r.is_valid for r in reports):
        return "INVALID"
    return "WARN" if any(r.has_warnings for r in reports) else "VALID"


@pytest.mark.parametrize(
    "line",
    ["Let ε > 0 be given", "Let \\epsilon > 0 be given", "Fix ε > 0", "Let ε > 0"],
)
def test_a_variable_with_a_condition(line):
    (decl,) = statements(line)
    assert isinstance(decl, VarDeclNode)
    assert decl.type_name == "Real"
    assert decl.condition is not None
    assert verdict(f"{line}\nStep: ε / 2 > 0") == "VALID"


@pytest.mark.parametrize("word", ["Take", "Set", "Put", "Let"])
def test_naming_a_value(word):
    source = f"Fix ε > 0\n{word} δ = ε / 3\nStep: δ > 0"
    assert isinstance(statements(source)[1], VarDeclNode)
    assert verdict(source) == "VALID"


def test_set_is_still_a_type():
    assert verdict("Let S : Set\nStep: S = S") == "VALID"


@pytest.mark.parametrize(
    "opener",
    ["We have", "Note that", "Observe that", "Now", "Now,", "Clearly", "Clearly,", "It follows that", "We get", "We see that", "Then", "So"],
)
def test_stating_a_fact(opener):
    source = f"Let x : Real\nAssume x > 2\n{opener} x + 1 > 3"
    assert isinstance(statements(source)[-1], DeduceNode)
    assert verdict(source) == "VALID"
    # ...and a fact that does not follow is still refused.
    assert verdict(f"Let x : Real\nAssume x > 2\n{opener} x > 5") == "INVALID"


def test_opener_words_inside_names_are_not_keywords():
    assert verdict("Let now : Real\nStep: now = now") == "VALID"
    assert verdict("Let clearly2 : Real\nStep: clearly2 + 0 = clearly2") == "VALID"


def test_since_uses_a_premise_that_holds():
    source = "Let x : Real\nAssume x > 2\nSince x > 2, x^2 > 4"
    stmt = statements(source)[-1]
    assert isinstance(stmt, DeduceNode) and stmt.premise is not None
    assert verdict(source) == "VALID"


def test_since_refuses_a_premise_that_does_not_hold():
    reports = ProofChecker().check_source("Let x : Real\nAssume x > 2\nSince x > 3, x^2 > 9")
    last = reports[0].results[-1]
    assert last.status.value == "INVALID"
    assert "premise does not hold" in last.message


def test_since_a_label_is_a_justification():
    assert verdict("Let x : Real\nAssume h1: x > 2\nSince h1, x + 1 > 3") == "VALID"


def test_by_a_label():
    source = "Let x : Real\nAssume h1: x > 2\nBy h1, x^2 > 4"
    stmt = statements(source)[-1]
    assert isinstance(stmt, DeduceNode) and stmt.justification == "h1"
    assert verdict(source) == "VALID"


def test_by_an_unknown_name_is_refused():
    assert verdict("Let x : Real\nAssume h1: x > 2\nBy h7, x^2 > 4") == "INVALID"


def test_existing_justifications_still_parse():
    assert verdict("Let k : Int\nStep: 2 * k + 2 * k = 4 * k [by algebra]") == "VALID"
    assert verdict("Let k : Int\nStep: 2 * k + 2 * k = 4 * k by algebra") == "VALID"
