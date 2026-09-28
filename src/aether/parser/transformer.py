"""AST Transformer for Aether parse trees.

Converts a raw Lark Tree into typed Aether AST nodes with source positions.
"""

from __future__ import annotations

from lark import Transformer, Token, v_args

from aether.core.ast import (
    SymbolNode, GreekSymbolNode, NumberNode,
    BinaryOpNode, UnaryOpNode, FunctionCallNode,
    RelationNode, QuantifierNode, RawMathNode,
    VectorNode, MatrixNode, EmptySetNode,
    IntegralNode, LimitNode, StringLiteralNode,
    VarDeclNode, FuncDefNode, AssumeNode, ObtainNode,
    StepNode, DeduceNode, SubProofNode,
    ProofNode, TheoremNode, DocumentNode,
    StatementNode, ExprNode, ImportNode,
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
    def string_literal(self, token: Token) -> StringLiteralNode:
        ln, col = _pos(token)
        val = _tok(token).strip('"')
        return StringLiteralNode(value=val, line=ln, col=col)

    @v_args(inline=True)
    def raw_math(self, token: Token) -> RawMathNode:
        return RawMathNode(raw_text=_tok(token))

    def diff_spec(self, children: list) -> str:
        if len(children) == 1:
            raw = _tok(children[0])
            if raw.startswith("d") and len(raw) > 1:
                return raw[1:]
            return raw
        raw = _tok(children[1])
        if raw.startswith("d") and len(raw) > 1:
            return raw[1:]
        return raw

    def func_call(self, children: list) -> ExprNode:
        name_tok = children[0]
        args = [c for c in children[1:] if _is_expr(c)]
        ln, col = _pos(name_tok)
        fn_name = _tok(name_tok)
        fn_lower = fn_name.lower()
        if fn_lower in ("integrate", "integral"):
            if len(args) == 2:
                vname = args[1].name if isinstance(args[1], (SymbolNode, GreekSymbolNode)) else str(args[1])
                return IntegralNode(body=args[0], var=vname, line=ln, col=col)
            if len(args) == 4:
                vname = args[1].name if isinstance(args[1], (SymbolNode, GreekSymbolNode)) else str(args[1])
                return IntegralNode(body=args[0], var=vname, lower=args[2], upper=args[3], line=ln, col=col)
        if fn_lower in ("lim", "limit"):
            if len(args) >= 3:
                vname = args[1].name if isinstance(args[1], (SymbolNode, GreekSymbolNode)) else str(args[1])
                dir_str = "+-"
                if len(args) >= 4:
                    if isinstance(args[3], StringLiteralNode):
                        dir_str = args[3].value
                    elif isinstance(args[3], SymbolNode):
                        dir_str = args[3].name
                return LimitNode(body=args[0], var=vname, target=args[2], direction=dir_str, line=ln, col=col)
        return FunctionCallNode(func=fn_name, args=args, line=ln, col=col)

    def latex_definite_int(self, children: list) -> IntegralNode:
        int_tok = children[0]
        ln, col = _pos(int_tok)
        exprs = [c for c in children if _is_expr(c)]
        lower_expr, upper_expr, body_expr = exprs[0], exprs[1], exprs[2]
        var_name = children[-1] if isinstance(children[-1], str) else "x"
        return IntegralNode(body=body_expr, var=var_name, lower=lower_expr, upper=upper_expr, line=ln, col=col)

    def latex_indefinite_int(self, children: list) -> IntegralNode:
        int_tok = children[0]
        ln, col = _pos(int_tok)
        body_expr = next(c for c in children if _is_expr(c))
        var_name = children[-1] if isinstance(children[-1], str) else "x"
        return IntegralNode(body=body_expr, var=var_name, line=ln, col=col)

    def latex_limit(self, children: list) -> LimitNode:
        lim_tok = children[0]
        ln, col = _pos(lim_tok)
        var_tok = next(c for c in children if _is_token(c) and c.type == "CNAME")
        exprs = [c for c in children if _is_expr(c)]
        target_expr, body_expr = exprs[0], exprs[1]
        dir_tok = next((c for c in children if _is_token(c) and c.type == "LIM_DIR"), None)
        dir_str = "+-"
        if dir_tok is not None:
            raw_dir = _tok(dir_tok)
            if "+" in raw_dir:
                dir_str = "+"
            elif "-" in raw_dir:
                dir_str = "-"
        return LimitNode(body=body_expr, var=_tok(var_tok), target=target_expr, direction=dir_str, line=ln, col=col)

    def latex_sum(self, children: list) -> FunctionCallNode:
        # [SUM_KW, CNAME_var, REL_OP('='), lower_expr, POW_OP('^'), upper_expr, body_expr]
        sum_tok = children[0]
        ln, col = _pos(sum_tok)
        var_tok = next(c for c in children if _is_token(c) and c.type == "CNAME")
        exprs = [c for c in children if _is_expr(c)]
        lower_expr, upper_expr, body_expr = exprs[0], exprs[1], exprs[2]
        return FunctionCallNode(
            func="sum",
            args=[SymbolNode(name=_tok(var_tok), line=ln, col=col), lower_expr, upper_expr, body_expr],
            line=ln,
            col=col,
        )

    def abs_expr(self, children: list) -> FunctionCallNode:
        pipe_tok = children[0]
        ln, col = _pos(pipe_tok)
        arg = next(c for c in children if _is_expr(c))
        return FunctionCallNode(func="abs", args=[arg], line=ln, col=col)

    def empty_set(self, children: list) -> EmptySetNode:
        return EmptySetNode()

    def vector_literal(self, children: list) -> ExprNode:
        elements = [c for c in children if _is_expr(c)]
        ln = getattr(elements[0], "line", None) if elements else None
        col = getattr(elements[0], "col", None) if elements else None
        # If all elements are VectorNodes, lift to MatrixNode
        if elements and all(isinstance(e, VectorNode) for e in elements):
            return MatrixNode(rows=[e.elements for e in elements], line=ln, col=col)
        return VectorNode(elements=elements, line=ln, col=col)

    # -------------------------------------------------------------------
    # Unary operators
    # -------------------------------------------------------------------

    def unary_op(self, children: list) -> UnaryOpNode:
        op_tok, operand = children
        ln, col = _pos(op_tok)
        return UnaryOpNode(op=_tok(op_tok), operand=operand, line=ln, col=col)

    def not_op(self, children: list) -> UnaryOpNode:
        op_tok = children[0]
        operand = next(c for c in children if _is_expr(c))
        ln, col = _pos(op_tok)
        return UnaryOpNode(op="not", operand=operand, line=ln, col=col)

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
        if isinstance(exp, SymbolNode) and exp.name == "T":
            return FunctionCallNode(func="transpose", args=[base], line=getattr(base, "line", None), col=getattr(base, "col", None))
        return BinaryOpNode(op="^", left=base, right=exp)

    # -------------------------------------------------------------------
    # Relations
    # -------------------------------------------------------------------

    def mod_spec(self, children: list) -> ExprNode:
        return next(c for c in children if _is_expr(c))

    def rel_expr_bin(self, children: list) -> ExprNode:
        # children: [left, REL_OP, right] or [left, REL_OP, right, mod_expr]
        left, op_tok, right = children[:3]
        if len(children) == 4:
            mod_expr = children[3]
            op_str = _tok(op_tok)
            if op_str in ("=", "\\equiv"):
                return FunctionCallNode(
                    func="Congruent",
                    args=[left, right, mod_expr],
                    line=getattr(left, "line", None),
                    col=getattr(left, "col", None),
                )
        return RelationNode(
            op=_tok(op_tok),
            left=left,
            right=right,
            line=getattr(left, "line", None),
            col=getattr(left, "col", None),
        )

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
        # children: [QUANT_KW, (CNAME|GREEK_LETTER), ?type_name_str, formula]
        var_tok = next(c for c in children if _is_token(c) and c.type in ("CNAME", "GREEK_LETTER"))
        ln, col = _pos(var_tok)
        var = _tok(var_tok).lstrip("\\")
        type_name = next((c for c in children if isinstance(c, str) and not _is_token(c)), None)
        formula = next(c for c in reversed(children) if _is_expr(c))
        return QuantifierNode(quantifier=q, var=var, var_type=type_name,
                              formula=formula, line=ln, col=col)

    # -------------------------------------------------------------------
    # Variable declarations
    # -------------------------------------------------------------------

    def var_decl_typed(self, children: list) -> VarDeclNode:
        # [VAR_INTRO, var_list, type_name_str, ?SUCH_THAT, ?condition]
        kw = children[0]
        ln, col = _pos(kw)
        variables: list[str] = children[1]
        type_name: str = children[2]
        condition = next((c for c in children[3:] if _is_expr(c)), None)
        return VarDeclNode(variables=variables, type_name=type_name,
                           condition=condition, line=ln, col=col)

    def func_def(self, children: list) -> FuncDefNode:
        # [VAR_INTRO|DEFINE_KW, CNAME_name, var_list, REL_OP|IFF_OP, expr]
        kw = children[0]
        ln, col = _pos(kw)
        name_tok = children[1]
        params: list[str] = children[2]
        body: ExprNode = next(c for c in children[3:] if _is_expr(c))
        return FuncDefNode(name=_tok(name_tok), params=params, body=body,
                           line=ln, col=col)

    def var_decl_cond(self, children: list) -> VarDeclNode:
        # [VAR_INTRO, CNAME|GREEK_LETTER, REL_OP, arith_expr]
        kw, name_tok, op_tok, bound = children
        ln, col = _pos(kw)
        vname = _tok(name_tok).lstrip("\\")
        lhs_node: ExprNode = (
            GreekSymbolNode(name=vname, line=ln, col=col)
            if getattr(name_tok, "type", "") == "GREEK_LETTER"
            else SymbolNode(name=vname, line=ln, col=col)
        )
        tname = "Real"
        if isinstance(bound, MatrixNode):
            tname = "Matrix"
        elif isinstance(bound, VectorNode):
            tname = "Vector"
        elif isinstance(bound, EmptySetNode):
            tname = "Set"
        condition = RelationNode(op=_tok(op_tok), left=lhs_node, right=bound, line=ln, col=col)
        return VarDeclNode(variables=[vname], type_name=tname,
                           condition=condition, line=ln, col=col)

    def var_list(self, children: list) -> list[str]:
        return [_tok(t).lstrip("\\") for t in children if _is_token(t)]

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
        # [OBTAIN_KW, CNAME|GREEK_LETTER, ?type_name_str, SUCH_THAT, expr, ?from_CNAME]
        kw = children[0]
        ln, col = _pos(kw)

        # var name is the first CNAME/GREEK_LETTER token (not OBTAIN_KW)
        ident_toks = [c for c in children[1:] if _is_token(c) and c.type in ("CNAME", "GREEK_LETTER")]
        var = _tok(ident_toks[0]).lstrip("\\")
        source_label = _tok(ident_toks[1]) if len(ident_toks) > 1 else None

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
        parts = []
        for t in children:
            s = _tok(t)
            lower = s.lower()
            if lower in skip:
                continue
            if lower.startswith("by "):
                s = s[3:].strip()
            elif lower.startswith("using "):
                s = s[6:].strip()
            parts.append(s)
        res = " ".join(parts).strip()
        if res.lower().startswith("by "):
            res = res[3:].strip()
        elif res.lower().startswith("using "):
            res = res[6:].strip()
        return res

    def witness_clause(self, children: list) -> ExprNode:
        return next(c for c in children if _is_expr(c))

    def import_stmt(self, children: list) -> ImportNode:
        kw = children[0]
        ln, col = _pos(kw)
        path = _tok(children[1]).strip('"')
        return ImportNode(path=path, line=ln, col=col)

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

    def case_block(self, children: list) -> SubProofNode:
        kw = children[0]
        ln, col = _pos(kw)
        cond = next(c for c in children if _is_expr(c))
        stmts = [c for c in children if _is_stmt(c)]
        return SubProofNode(statements=stmts, case_condition=cond, label="Case", line=ln, col=col)

    def base_case_block(self, children: list) -> SubProofNode:
        kw = children[0]
        ln, col = _pos(kw)
        cond = next((c for c in children if _is_expr(c)), None)
        stmts = [c for c in children if _is_stmt(c)]
        return SubProofNode(statements=stmts, case_condition=cond, label="Base case", line=ln, col=col)

    def ind_step_block(self, children: list) -> SubProofNode:
        kw = children[0]
        ln, col = _pos(kw)
        cond = next((c for c in children if _is_expr(c)), None)
        stmts = [c for c in children if _is_stmt(c)]
        return SubProofNode(statements=stmts, case_condition=cond, label="Inductive step", line=ln, col=col)

    def named_block(self, children: list) -> SubProofNode:
        lbl_tok = children[0]
        ln, col = _pos(lbl_tok)
        stmts = [c for c in children if _is_stmt(c)]
        return SubProofNode(statements=stmts, label=_tok(lbl_tok), line=ln, col=col)

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
        imports = [c for c in children if isinstance(c, ImportNode)]
        theorems = [c for c in children if isinstance(c, TheoremNode)]
        statements = [c for c in children
                      if _is_stmt(c) and not isinstance(c, TheoremNode)]
        return DocumentNode(theorems=theorems, statements=statements, imports=imports)
