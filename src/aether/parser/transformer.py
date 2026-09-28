"""AST Transformer for Aether parse trees.

Converts a raw Lark Tree into typed Aether AST nodes with source positions.
"""

from __future__ import annotations

from lark import Transformer, Token, v_args

from aether.core.ast import (
    SymbolNode, GreekSymbolNode, NumberNode,
    BinaryOpNode, UnaryOpNode, FunctionCallNode,
    RelationNode, QuantifierNode, RawMathNode,
    VarDeclNode, AssumeNode, ObtainNode,
    StepNode, DeduceNode, SubProofNode,
    ProofNode, TheoremNode, DocumentNode,
    StatementNode, ExprNode,
)


def _pos(token: Token) -> tuple[int | None, int | None]:
    return getattr(token, "line", None), getattr(token, "column", None)


def _tok(token) -> str:
    return str(token).strip()


def _is_expr(obj) -> bool:
    return isinstance(obj, ExprNode)


def _is_stmt(obj) -> bool:
    return isinstance(obj, StatementNode)


def _is_token(obj) -> bool:
    return isinstance(obj, Token)


# ---------------------------------------------------------------------------
# Main transformer
# ---------------------------------------------------------------------------

class AetherASTTransformer(Transformer):
    """Transforms a Lark parse tree into typed Aether AST nodes."""

    # -------------------------------------------------------------------
    # Atoms
    # -------------------------------------------------------------------

    @v_args(inline=True)
    def symbol(self, token: Token) -> SymbolNode:
        ln, col = _pos(token)
        return SymbolNode(name=_tok(token), line=ln, col=col)

    @v_args(inline=True)
    def greek_symbol(self, token: Token) -> GreekSymbolNode:
        ln, col = _pos(token)
        return GreekSymbolNode(name=_tok(token).lstrip("\\"), line=ln, col=col)

    @v_args(inline=True)
    def number(self, token: Token) -> NumberNode:
        ln, col = _pos(token)
        return NumberNode(value=_tok(token), line=ln, col=col)

    @v_args(inline=True)
    def raw_math(self, token: Token) -> RawMathNode:
        return RawMathNode(raw_text=_tok(token))

    def func_call(self, children: list) -> FunctionCallNode:
        name_tok = children[0]
        args = [c for c in children[1:] if _is_expr(c)]
        ln, col = _pos(name_tok)
        return FunctionCallNode(func=_tok(name_tok), args=args, line=ln, col=col)

    # -------------------------------------------------------------------
    # Unary operators
    # -------------------------------------------------------------------

    @v_args(inline=True)
    def neg_op(self, operand: ExprNode) -> UnaryOpNode:
        return UnaryOpNode(op="-", operand=operand)

    @v_args(inline=True)
    def pos_op(self, operand: ExprNode) -> UnaryOpNode:
        return UnaryOpNode(op="+", operand=operand)

    @v_args(inline=True)
    def not_op(self, operand: ExprNode) -> UnaryOpNode:
        return UnaryOpNode(op="not", operand=operand)

    # -------------------------------------------------------------------
    # Binary arithmetic / logic — named rules with [left, OP_tok, right]
    # -------------------------------------------------------------------

    def arith_expr(self, children: list) -> ExprNode:
        if len(children) == 1:
            return children[0]
        # children: [left, ADDOP, right]  (left-recursive, so already folded)
        left, op_tok, right = children
        return BinaryOpNode(op=_tok(op_tok), left=left, right=right)

    def term(self, children: list) -> ExprNode:
        if len(children) == 1:
            return children[0]
        # children: [left, MULOP, right]
        left, op_tok, right = children
        return BinaryOpNode(op=_tok(op_tok), left=left, right=right)

    def power(self, children: list) -> ExprNode:
        if len(children) == 1:
            return children[0]
        # children: [base, POW_OP, exp]
        base, op_tok, exp = children
        return BinaryOpNode(op="^", left=base, right=exp)

    # -------------------------------------------------------------------
    # Relations
    # -------------------------------------------------------------------

    def rel_expr_bin(self, children: list) -> RelationNode:
        # children: [left, REL_OP, right]
        left, op_tok, right = children
        return RelationNode(op=_tok(op_tok), left=left, right=right,
                            line=getattr(left, "line", None),
                            col=getattr(left, "col", None))

    # -------------------------------------------------------------------
    # Logic connectives — children: [expr, OP_tok, expr, OP_tok, expr, …]
    # -------------------------------------------------------------------

    def _logic_fold(self, children: list) -> ExprNode:
        """Left-fold a sequence [expr, op, expr, op, expr, …]."""
        result = children[0]
        i = 1
        while i < len(children):
            op = _tok(children[i])
            right = children[i + 1]
            result = BinaryOpNode(op=op, left=result, right=right)
            i += 2
        return result  # type: ignore[return-value]

    def iff_expr(self, children: list) -> ExprNode:
        return children[0] if len(children) == 1 else self._logic_fold(children)

    def impl_expr(self, children: list) -> ExprNode:
        return children[0] if len(children) == 1 else self._logic_fold(children)

    def or_expr(self, children: list) -> ExprNode:
        return children[0] if len(children) == 1 else self._logic_fold(children)

    def and_expr(self, children: list) -> ExprNode:
        return children[0] if len(children) == 1 else self._logic_fold(children)

    # -------------------------------------------------------------------
    # Quantifiers
    # -------------------------------------------------------------------

    def exists_expr(self, children: list) -> QuantifierNode:
        return self._quantifier("exists", children)

    def forall_expr(self, children: list) -> QuantifierNode:
        return self._quantifier("forall", children)

    def _quantifier(self, q: str, children: list) -> QuantifierNode:
        # children: [QUANT_KW, CNAME, ?type_name_str, formula]
        var_tok = next(c for c in children if _is_token(c) and c.type == "CNAME")
        ln, col = _pos(var_tok)
        var = _tok(var_tok)
        type_name = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        formula = next(c for c in reversed(children) if _is_expr(c))
        return QuantifierNode(quantifier=q, var=var, var_type=type_name,
                              formula=formula, line=ln, col=col)

    # -------------------------------------------------------------------
    # Variable declarations
    # -------------------------------------------------------------------

    def var_decl_typed(self, children: list) -> VarDeclNode:
        # [VAR_INTRO, var_list, type_name_str, ?condition]
        kw = children[0]
        ln, col = _pos(kw)
        variables: list[str] = children[1]
        type_name: str = children[2]
        condition = children[3] if len(children) > 3 else None
        return VarDeclNode(variables=variables, type_name=type_name,
                           condition=condition, line=ln, col=col)

    def var_decl_cond(self, children: list) -> VarDeclNode:
        # [VAR_INTRO, CNAME, REL_OP, arith_expr]
        kw, name_tok, op_tok, bound = children
        ln, col = _pos(kw)
        condition = RelationNode(op=_tok(op_tok),
                                 left=SymbolNode(name=_tok(name_tok)),
                                 right=bound)
        return VarDeclNode(variables=[_tok(name_tok)], type_name="Real",
                           condition=condition, line=ln, col=col)

    def var_list(self, children: list) -> list[str]:
        return [_tok(t) for t in children if _is_token(t)]

    def type_name(self, children: list) -> str:
        return "".join(_tok(t) for t in children if _is_token(t))

    # -------------------------------------------------------------------
    # Assume
    # -------------------------------------------------------------------

    def assume_stmt(self, children: list) -> AssumeNode:
        # [ASSUME_KW, ?CNAME_label, expr]
        kw = children[0]
        ln, col = _pos(kw)
        labels = [c for c in children[1:] if _is_token(c) and c.type == "CNAME"]
        prop = next(c for c in children if _is_expr(c))
        label = _tok(labels[0]) if labels else None
        return AssumeNode(label=label, proposition=prop, line=ln, col=col)

    # -------------------------------------------------------------------
    # Obtain
    # -------------------------------------------------------------------

    def obtain_stmt(self, children: list) -> ObtainNode:
        # [OBTAIN_KW, CNAME, ?type_name_str, SUCH_THAT, expr, ?from_CNAME]
        kw = children[0]
        ln, col = _pos(kw)

        # var name is the first CNAME token (not OBTAIN_KW)
        cnames = [c for c in children[1:] if _is_token(c) and c.type == "CNAME"]
        var = _tok(cnames[0])
        source_label = _tok(cnames[1]) if len(cnames) > 1 else None

        type_name = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        condition = next(c for c in children if _is_expr(c))

        return ObtainNode(variable=var, type_name=type_name, condition=condition,
                          source_label=source_label, line=ln, col=col)

    # -------------------------------------------------------------------
    # Steps (step_binary is gone; step_single handles both forms via expr)
    # -------------------------------------------------------------------

    def step_single(self, children: list) -> StepNode:
        # [STEP_KW, expr, ?just_str]
        kw = children[0]
        ln, col = _pos(kw)
        expr = next(c for c in children if _is_expr(c))
        just = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)

        # If expr is a RelationNode, split into lhs/op/rhs for StepNode
        if isinstance(expr, RelationNode):
            return StepNode(relation=expr.op, lhs=expr.left, rhs=expr.right,
                            justification=just, line=ln, col=col)
        # Otherwise it's a bare expression step (function call, quantifier, etc.)
        return StepNode(relation="", lhs=None, rhs=expr,
                        justification=just, line=ln, col=col)

    def step_chained(self, children: list) -> StepNode:
        # [STEP_KW, REL_OP, arith_expr, ?just_str]
        kw = children[0]
        ln, col = _pos(kw)
        op_tok = children[1]
        rhs = children[2]
        just = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        return StepNode(relation=_tok(op_tok), lhs=None, rhs=rhs,
                        justification=just, line=ln, col=col)

    # -------------------------------------------------------------------
    # Deduce
    # -------------------------------------------------------------------

    def deduce_expr(self, children: list) -> DeduceNode:
        # [DEDUCE_KW, expr, ?just_str, ?witness_expr]
        kw = children[0]
        ln, col = _pos(kw)
        exprs = [c for c in children if _is_expr(c)]
        claim = exprs[0]
        witness = exprs[1] if len(exprs) > 1 else None
        just = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        return DeduceNode(claim=claim, justification=just, witness=witness,
                          line=ln, col=col)

    def deduce_chained(self, children: list) -> DeduceNode:
        # [DEDUCE_KW, REL_OP, arith_expr, ?just_str]
        kw = children[0]
        ln, col = _pos(kw)
        op_tok = children[1]
        rhs = children[2]
        rel = RelationNode(op=_tok(op_tok),
                           left=SymbolNode(name="<prev>"),
                           right=rhs)
        just = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        return DeduceNode(claim=rel, justification=just, line=ln, col=col)

    # -------------------------------------------------------------------
    # Justification & witness
    # -------------------------------------------------------------------

    def justification(self, children: list) -> str:
        skip = {"using", "by", "[", "]"}
        parts = [_tok(t) for t in children
                 if _is_token(t) and _tok(t).lower() not in skip]
        return " ".join(parts)

    def witness_clause(self, children: list) -> ExprNode:
        return next(c for c in children if _is_expr(c))

    # -------------------------------------------------------------------
    # Proof / theorem / document passthrough
    # -------------------------------------------------------------------

    def simple_stmt(self, children: list) -> StatementNode:
        return children[0]

    def line_stmt(self, children: list) -> StatementNode:
        return children[0]

    def block_stmt(self, children: list) -> SubProofNode:
        stmts = [c for c in children if _is_stmt(c)]
        return SubProofNode(statements=stmts)

    def proof_stmt(self, children: list) -> ProofNode:
        stmts = [c for c in children if _is_stmt(c)]
        return ProofNode(statements=stmts)

    def theorem_stmt(self, children: list) -> TheoremNode:
        name: str | None = None
        claim = None
        proof = None
        for item in children:
            if _is_token(item) and item.type in ("CNAME", "STRING"):
                name = _tok(item).strip('"')
            elif isinstance(item, str):
                name = item.strip('"')
            elif isinstance(item, ExprNode):
                claim = item
            elif isinstance(item, ProofNode):
                proof = item
        return TheoremNode(name=name, claim=claim, proof=proof)

    def claim_stmt(self, children: list) -> ExprNode:
        return next(c for c in children if _is_expr(c))

    def item(self, children: list):
        return children[0]

    def start(self, children: list) -> DocumentNode:
        theorems = [c for c in children if isinstance(c, TheoremNode)]
        statements = [c for c in children
                      if _is_stmt(c) and not isinstance(c, TheoremNode)]
        return DocumentNode(theorems=theorems, statements=statements)
