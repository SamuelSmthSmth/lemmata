"""Indentation handler for Aether proof syntax using Lark's Indenter."""

from lark.indenter import Indenter


class AetherIndenter(Indenter):
    """Postlex indenter that tracks Python-style whitespace indentation in Aether proofs."""

    NL_type = "_NL"
    OPEN_PAREN_types = ["LPAR"]
    CLOSE_PAREN_types = ["RPAR"]
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 4
