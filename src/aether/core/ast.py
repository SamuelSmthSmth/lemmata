"""AST node dataclasses for Aether proof documents.

Hierarchy
---------
ExprNode        — anything that evaluates to a value or proposition
  SymbolNode      — bare identifier, e.g. x, k, n
  GreekSymbolNode — LaTeX Greek letter, e.g. \\epsilon
  NumberNode      — numeric literal
  BinaryOpNode    — arith / logic binary operation
  UnaryOpNode     — negation, logical not
  FunctionCallNode — f(args…)
  RelationNode    — comparison / equality predicate
  QuantifierNode  — exists / forall
  RawMathNode     — verbatim $…$ fallback

StatementNode   — a line in the proof body
  VarDeclNode     — Let / Given / Fix
  AssumeNode      — Assume / Suppose
  ObtainNode      — Obtain k such that …
  StepNode        — Step: lhs op rhs
  DeduceNode      — Therefore / Hence

ProofNode       — ordered list of StatementNodes
TheoremNode     — Theorem/Lemma + optional ProofNode
DocumentNode    — root: theorems + top-level statements
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------


@dataclass
class ExprNode:
    """Base class for all expression-level AST nodes."""

    line: Optional[int] = field(default=None, repr=False, compare=False)
    col: Optional[int] = field(default=None, repr=False, compare=False)


@dataclass
class SymbolNode(ExprNode):
    """Bare identifier: e.g. x, k, n."""

    name: str = ""

    def __str__(self) -> str:
        return self.name


@dataclass
class GreekSymbolNode(ExprNode):
    """LaTeX Greek letter: e.g. \\epsilon becomes GreekSymbolNode('epsilon')."""

    name: str = ""  # the word part, without backslash

    def __str__(self) -> str:
        return f"\\{self.name}"


@dataclass
class NumberNode(ExprNode):
    """Numeric literal."""

    value: str = "0"  # kept as string to preserve exact source form

    def __str__(self) -> str:
        return self.value


@dataclass
class BinaryOpNode(ExprNode):
    """Arithmetic or logical binary operation.

    op is one of: + - * / ^ ** and or => <=>
    """

    op: str = ""
    left: ExprNode = field(default_factory=ExprNode)
    right: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        return f"({self.left} {self.op} {self.right})"


@dataclass
class UnaryOpNode(ExprNode):
    """Unary operation: negation (-) or logical not."""

    op: str = ""
    operand: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        return f"({self.op}{self.operand})"


@dataclass
class FunctionCallNode(ExprNode):
    """Function application: e.g. Even(n), f(x, y)."""

    func: str = ""
    args: list[ExprNode] = field(default_factory=list)

    def __str__(self) -> str:
        args_str = ", ".join(str(a) for a in self.args)
        return f"{self.func}({args_str})"


@dataclass
class RelationNode(ExprNode):
    """Comparison / Relation: e.g. x = y, a <= b, n != 0, x > 2."""

    op: str = ""
    left: ExprNode = field(default_factory=ExprNode)
    right: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        return f"{self.left} {self.op} {self.right}"


@dataclass
class QuantifierNode(ExprNode):
    """Quantified expression: e.g. exists k : Int, n = 2 * k or forall x : Real, x^2 >= 0."""

    quantifier: str = ""      # 'exists' or 'forall'
    var: str = ""
    var_type: Optional[str] = None
    formula: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        typed = f"{self.var} : {self.var_type}" if self.var_type else self.var
        return f"{self.quantifier} {typed}, {self.formula}"


@dataclass
class RawMathNode(ExprNode):
    """Unparsed LaTeX / raw mathematical expression fallback enclosed in $ ... $."""

    raw_text: str = ""

    def __str__(self) -> str:
        return f"${self.raw_text}$"


@dataclass
class VectorNode(ExprNode):
    """Vector literal: e.g. [1, 2, 3]."""

    elements: list[ExprNode] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{', '.join(str(e) for e in self.elements)}]"


@dataclass
class MatrixNode(ExprNode):
    """Matrix literal: e.g. [[1, 2], [3, 4]]."""

    rows: list[list[ExprNode]] = field(default_factory=list)

    def __str__(self) -> str:
        row_strs = [f"[{', '.join(str(e) for e in r)}]" for r in self.rows]
        return f"[{', '.join(row_strs)}]"


@dataclass
class EmptySetNode(ExprNode):
    """Empty set constant: \\emptyset or EmptySet."""

    def __str__(self) -> str:
        return "\\emptyset"


@dataclass
class IntegralNode(ExprNode):
    """Integral expression: e.g. integrate(f, x) or integrate(f, x, a, b) or \\int_{a}^{b} f dx."""

    body: ExprNode = field(default_factory=ExprNode)
    var: str = "x"
    lower: Optional[ExprNode] = None
    upper: Optional[ExprNode] = None

    def __str__(self) -> str:
        if self.lower is not None and self.upper is not None:
            return f"integrate({self.body}, {self.var}, {self.lower}, {self.upper})"
        return f"integrate({self.body}, {self.var})"


@dataclass
class LimitNode(ExprNode):
    """Limit expression: e.g. lim(f, x, a) or \\lim_{x -> a} f."""

    body: ExprNode = field(default_factory=ExprNode)
    var: str = "x"
    target: ExprNode = field(default_factory=ExprNode)
    direction: str = "+-"  # "+-", "+", "-"

    def __str__(self) -> str:
        if self.direction != "+-":
            return f"lim({self.body}, {self.var}, {self.target}, {self.direction!r})"
        return f"lim({self.body}, {self.var}, {self.target})"


@dataclass
class StringLiteralNode(ExprNode):
    """String literal: e.g. "+" or "-". """

    value: str = ""

    def __str__(self) -> str:
        return f'"{self.value}"'


# ---------------------------------------------------------------------------
# Statement nodes
# ---------------------------------------------------------------------------


@dataclass
class StatementNode:
    """Base class for proof statements."""

    line: Optional[int] = field(default=None, repr=False, compare=False)
    col: Optional[int] = field(default=None, repr=False, compare=False)


@dataclass
class VarDeclNode(StatementNode):
    """Variable introduction: e.g. 'Let x, y : Real', 'Given n : Int', 'Fix epsilon > 0'."""

    variables: list[str] = field(default_factory=list)
    type_name: str = ""
    condition: Optional[ExprNode] = None   # for 'Fix epsilon > 0' style

    def __str__(self) -> str:
        vars_str = ", ".join(self.variables)
        base = f"Let {vars_str} : {self.type_name}"
        if self.condition:
            base += f" with {self.condition}"
        return base


@dataclass
class AssumeNode(StatementNode):
    """Hypothesis declaration: e.g. 'Assume h1: Even(n)' or 'Suppose x > 2'."""

    label: Optional[str] = None
    proposition: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        prefix = f"{self.label}: " if self.label else ""
        return f"Assume {prefix}{self.proposition}"


@dataclass
class ObtainNode(StatementNode):
    """Existential elimination / witness extraction:
    e.g. 'Obtain k : Int such that n = 2 * k from h1'.
    """

    variable: str = ""
    type_name: Optional[str] = None
    condition: ExprNode = field(default_factory=ExprNode)
    source_label: Optional[str] = None

    def __str__(self) -> str:
        typed = f"{self.variable} : {self.type_name}" if self.type_name else self.variable
        base = f"Obtain {typed} such that {self.condition}"
        if self.source_label:
            base += f" from {self.source_label}"
        return base


@dataclass
class StepNode(StatementNode):
    """Equational or inequality step in a deduction chain.
    - If lhs is None, this step chains off the RHS of the previous step.
    """

    relation: str = "="
    lhs: Optional[ExprNode] = None   # None → chained step
    rhs: ExprNode = field(default_factory=ExprNode)
    justification: Optional[str] = None

    @property
    def is_chained(self) -> bool:
        return self.lhs is None

    def __str__(self) -> str:
        lhs_str = "" if self.lhs is None else f"{self.lhs} "
        just = f" [{self.justification}]" if self.justification else ""
        return f"Step: {lhs_str}{self.relation} {self.rhs}{just}"


@dataclass
class DeduceNode(StatementNode):
    """Logical deduction or conclusion:
    e.g. 'Therefore exists m : Int, n^2 = 4 * m [witness: m = k^2]'
    or 'Thus Even(n^2)'.
    """

    claim: ExprNode = field(default_factory=ExprNode)
    justification: Optional[str] = None
    witness: Optional[ExprNode] = None

    def __str__(self) -> str:
        base = f"Therefore {self.claim}"
        if self.witness:
            base += f" [witness: {self.witness}]"
        if self.justification:
            base += f" using {self.justification}"
        return base


@dataclass
class FuncDefNode(StatementNode):
    """Function definition: e.g. 'Let f(x) = (x^2 - 4) / (x - 2)'."""

    name: str = ""
    params: list[str] = field(default_factory=list)
    body: ExprNode = field(default_factory=ExprNode)

    def __str__(self) -> str:
        params_str = ", ".join(self.params)
        return f"Let {self.name}({params_str}) = {self.body}"


@dataclass
class QEDNode(StatementNode):
    """Proof completion / goal check node at QED."""

    claim: Optional[ExprNode] = None

    def __str__(self) -> str:
        return f"QED ({self.claim})" if self.claim else "QED"


@dataclass
class ImportNode(StatementNode):
    """Import statement: e.g. 'import "lemmas.aether"'. """

    path: str = ""

    def __str__(self) -> str:
        return f'import "{self.path}"'


# ---------------------------------------------------------------------------
# Proof structure
# ---------------------------------------------------------------------------


@dataclass
class SubProofNode(StatementNode):
    """Indented subproof block (creates a fresh nested scope)."""

    statements: list[StatementNode] = field(default_factory=list)
    case_condition: Optional[ExprNode] = None
    label: Optional[str] = None

    def __str__(self) -> str:
        if self.label and self.case_condition is not None:
            return f"{self.label} {self.case_condition}: ({len(self.statements)} stmts)"
        if self.case_condition is not None:
            return f"Case {self.case_condition}: ({len(self.statements)} stmts)"
        if self.label is not None:
            return f"{self.label}: ({len(self.statements)} stmts)"
        return f"SubProof({len(self.statements)} stmts)"


@dataclass
class ProofNode:
    """A complete proof body containing top-level statements and subproofs."""

    statements: list[StatementNode] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join(str(s) for s in self.statements)


@dataclass
class TheoremNode:
    """Theorem, Lemma, or Claim definition."""

    name: Optional[str] = None
    claim: Optional[ExprNode] = None
    proof: Optional[ProofNode] = None

    def __str__(self) -> str:
        header = f"Theorem {self.name}:" if self.name else "Theorem:"
        body = f" Claim: {self.claim}" if self.claim else ""
        proof_str = f"\nProof:\n{self.proof}" if self.proof else ""
        return f"{header}{body}{proof_str}"


@dataclass
class DocumentNode:
    """Root node representing an entire Aether document or interactive session."""

    theorems: list[TheoremNode] = field(default_factory=list)
    statements: list[StatementNode] = field(default_factory=list)
    imports: list[ImportNode] = field(default_factory=list)
