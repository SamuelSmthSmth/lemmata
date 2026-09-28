"""Aether parser entry point."""

from __future__ import annotations

from pathlib import Path

from lark import Lark, UnexpectedInput

from aether.parser.indenter import AetherIndenter
from aether.parser.transformer import AetherASTTransformer
from aether.core.ast import DocumentNode, ExprNode, AssumeNode

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


class ParseError(Exception):
    """Raised when Aether encounters a syntax or formatting error in the proof."""

    def __init__(self, message: str, line: int | None = None, col: int | None = None):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.line is not None:
            return f"ParseError at line {self.line}, col {self.col}: {self.message}"
        return f"ParseError: {self.message}"


class AetherParser:
    """Parses Aether CNL proof text into a DocumentNode AST."""

    def __init__(self) -> None:
        grammar = _GRAMMAR_PATH.read_text(encoding="utf-8")
        self._lark = Lark(
            grammar,
            parser="lalr",
            lexer="contextual",
            postlex=AetherIndenter(),
            propagate_positions=True,
        )
        self._transformer = AetherASTTransformer()

    def parse(self, source: str) -> DocumentNode:
        """Parse *source* text and return a DocumentNode.

        Raises ``ParseError`` on any syntax error.
        """
        # Ensure the source ends with a newline so the indenter is happy
        if not source.endswith("\n"):
            source += "\n"
        try:
            tree = self._lark.parse(source)
            return self._transformer.transform(tree)
        except UnexpectedInput as exc:
            raise ParseError(
                str(exc),
                line=getattr(exc, "line", None),
                col=getattr(exc, "column", None),
            ) from exc

    def parse_expr(self, expr_source: str) -> ExprNode:
        """Parse a standalone mathematical expression or proposition into an ExprNode."""
        doc = self.parse(f"Assume {expr_source.strip()}\n")
        if not doc.statements or not isinstance(doc.statements[0], AssumeNode):
            raise ParseError(f"Could not parse expression: {expr_source!r}")
        return doc.statements[0].proposition
