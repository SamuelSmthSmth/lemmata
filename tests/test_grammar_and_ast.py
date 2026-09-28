"""Unit tests for Aether grammar, parser, and AST generation."""

import pytest

from aether.parser.parser import AetherParser, ParseError
from aether.core.ast import (
    DocumentNode, TheoremNode, ProofNode,
    VarDeclNode, AssumeNode, ObtainNode, StepNode, DeduceNode,
    BinaryOpNode, RelationNode, FunctionCallNode,
    QuantifierNode, SymbolNode, NumberNode, GreekSymbolNode,
)

# One shared parser instance — Lark compilation is expensive
_parser = AetherParser()


def parse(src: str) -> DocumentNode:
    return _parser.parse(src)


# ---------------------------------------------------------------------------
# Expression-level tests
# ---------------------------------------------------------------------------

class TestArithmeticExpressions:
    def test_parse_arithmetic_expr(self):
        doc = parse("Step: n^2 + 4 * k - 1\n")
        assert isinstance(doc, DocumentNode)
        assert len(doc.statements) == 1
        stmt = doc.statements[0]
        assert isinstance(stmt, StepNode)
        expr = stmt.rhs
        # top-level is subtraction
        assert isinstance(expr, BinaryOpNode)
        assert expr.op == "-"
        # left side is addition
        assert isinstance(expr.left, BinaryOpNode)
        assert expr.left.op == "+"

    def test_parse_relations(self):
        rel = _parser.parse_expr("x^2 - 4 > 0")
        assert isinstance(rel, RelationNode)
        assert rel.op == ">"
        assert isinstance(rel.left, BinaryOpNode)
        assert isinstance(rel.right, NumberNode)
        assert rel.right.value == "0"

    def test_parse_functions_and_greek(self):
        doc = parse("Step: Even(n)\n")
        stmt = doc.statements[0]
        expr = stmt.rhs
        assert isinstance(expr, FunctionCallNode)
        assert expr.func == "Even"
        assert len(expr.args) == 1
        assert isinstance(expr.args[0], SymbolNode)
        assert expr.args[0].name == "n"

    def test_greek_symbol_in_relation(self):
        rel = _parser.parse_expr("\\epsilon > 0")
        assert isinstance(rel, RelationNode)
        assert isinstance(rel.left, GreekSymbolNode)
        assert rel.left.name == "epsilon"

    def test_parse_quantifiers(self):
        doc = parse("Step: exists k : Int, n = 2 * k\n")
        stmt = doc.statements[0]
        expr = stmt.rhs
        assert isinstance(expr, QuantifierNode)
        assert expr.quantifier == "exists"
        assert expr.var == "k"
        assert expr.var_type == "Int"
        assert isinstance(expr.formula, RelationNode)


# ---------------------------------------------------------------------------
# Statement-level tests
# ---------------------------------------------------------------------------

class TestVarDeclarations:
    def test_var_declarations(self):
        src = """\
Given n : Int
Let x, y : Real
Fix epsilon > 0
"""
        doc = parse(src)
        stmts = doc.statements
        assert len(stmts) == 3

        assert isinstance(stmts[0], VarDeclNode)
        assert stmts[0].variables == ["n"]
        assert stmts[0].type_name == "Int"

        assert isinstance(stmts[1], VarDeclNode)
        assert stmts[1].variables == ["x", "y"]
        assert stmts[1].type_name == "Real"

        assert isinstance(stmts[2], VarDeclNode)
        assert stmts[2].variables == ["epsilon"]
        assert isinstance(stmts[2].condition, RelationNode)


class TestAssumptions:
    def test_assumptions(self):
        src = """\
Assume h1: Even(n)
Suppose x > 2
"""
        doc = parse(src)
        stmts = doc.statements
        assert len(stmts) == 2

        assert isinstance(stmts[0], AssumeNode)
        assert stmts[0].label == "h1"
        assert isinstance(stmts[0].proposition, FunctionCallNode)

        assert isinstance(stmts[1], AssumeNode)
        assert stmts[1].label is None
        assert isinstance(stmts[1].proposition, RelationNode)


class TestObtainStatement:
    def test_obtain_statement(self):
        doc = parse("Obtain k : Int such that n = 2 * k from h1\n")
        stmts = doc.statements
        assert len(stmts) == 1
        stmt = stmts[0]
        assert isinstance(stmt, ObtainNode)
        assert stmt.variable == "k"
        assert stmt.type_name == "Int"
        assert isinstance(stmt.condition, RelationNode)
        assert stmt.source_label == "h1"


class TestStepsAndChaining:
    def test_steps_and_equational_chaining(self):
        src = """\
Step: n^2 = (2 * k)^2
Step: = 4 * k^2
Step: <= 8 * k^2
"""
        doc = parse(src)
        stmts = doc.statements
        assert len(stmts) == 3

        assert isinstance(stmts[0], StepNode)
        assert not stmts[0].is_chained
        assert stmts[0].relation == "="

        assert isinstance(stmts[1], StepNode)
        assert stmts[1].is_chained
        assert stmts[1].relation == "="

        assert isinstance(stmts[2], StepNode)
        assert stmts[2].is_chained
        assert stmts[2].relation == "<="


class TestDeduceAndWitness:
    def test_deduce_and_witness(self):
        src = """\
Therefore exists m : Int, n^2 = 4 * m [witness: 2 * k^2]
Hence MultipleOf(n^2, 4)
"""
        doc = parse(src)
        stmts = doc.statements
        assert len(stmts) == 2

        assert isinstance(stmts[0], DeduceNode)
        assert isinstance(stmts[0].claim, QuantifierNode)

        assert isinstance(stmts[1], DeduceNode)
        assert isinstance(stmts[1].claim, FunctionCallNode)


# ---------------------------------------------------------------------------
# Full theorem test
# ---------------------------------------------------------------------------

class TestFullTheoremAndProof:
    def test_full_theorem_and_proof(self):
        src = """\
Theorem: "Even square theorem"
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 4 * m [witness: 2 * k^2]
    Hence MultipleOf(n^2, 4)
QED
"""
        doc = parse(src)
        assert len(doc.theorems) == 1
        thm = doc.theorems[0]
        assert isinstance(thm, TheoremNode)
        assert thm.name == "Even square theorem"
        assert isinstance(thm.proof, ProofNode)
        assert len(thm.proof.statements) == 8


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_document(self):
        doc = parse("")
        assert isinstance(doc, DocumentNode)
        assert len(doc.theorems) == 0
        assert len(doc.statements) == 0

    def test_parse_error_reporting(self):
        with pytest.raises(ParseError) as exc_info:
            parse("Let ::: Real\n")
        err = exc_info.value
        assert isinstance(err, ParseError)
        assert err.line is not None
