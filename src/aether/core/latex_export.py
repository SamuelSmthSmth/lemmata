"""LaTeX Export engine for Aether CNL proofs.

Converts Aether AST documents and proof reports into clean, publication-ready
LaTeX mathematical documents with theorem/proof environments and align* blocks.
"""

from __future__ import annotations

from typing import Optional, Union

from aether.core.ast import (
    StatementNode,
    DocumentNode,
    TheoremNode,
    ProofNode,
    VarDeclNode,
    FuncDefNode,
    AssumeNode,
    ObtainNode,
    StepNode,
    DeduceNode,
    SubProofNode,
    ExprNode,
    SymbolNode,
    GreekSymbolNode,
    NumberNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    RelationNode,
    QuantifierNode,
    EmptySetNode,
    VectorNode,
    MatrixNode,
    IntegralNode,
    LimitNode,
    ImportNode,
)
from aether.core.types import MathType, normalize_type_name
from aether.engine.checker import ProofReport, ProofChecker


TYPE_LATEX_MAP: dict[str, str] = {
    "Nat": "\\mathbb{N}",
    "Int": "\\mathbb{Z}",
    "Rat": "\\mathbb{Q}",
    "Real": "\\mathbb{R}",
    "Complex": "\\mathbb{C}",
    "Bool": "\\mathbb{B}",
    "Vector": "\\mathbb{R}^n",
    "Matrix": "\\mathbb{R}^{m \\times n}",
    "Set": "\\mathcal{S}",
}


def math_type_to_latex(type_str: str) -> str:
    """Format an Aether type string as standard LaTeX blackboard bold."""
    norm = normalize_type_name(type_str)
    return TYPE_LATEX_MAP.get(norm.value, f"\\text{{{type_str}}}")


def expr_to_latex(expr: Optional[ExprNode], precedence: int = 0) -> str:
    """Convert an AST ExprNode into clean LaTeX math code."""
    if expr is None:
        return ""

    if isinstance(expr, EmptySetNode):
        return "\\emptyset"

    if isinstance(expr, NumberNode):
        return expr.value

    if isinstance(expr, GreekSymbolNode):
        return f"\\{expr.name}"

    if isinstance(expr, SymbolNode):
        if expr.name.lower() in ("i", "i_unit"):
            return "i"
        if expr.name.startswith("\\"):
            return expr.name
        return expr.name

    if isinstance(expr, VectorNode):
        elements = [expr_to_latex(e) for e in expr.elements]
        rows_str = " \\\\ ".join(elements)
        return f"\\begin{{pmatrix}} {rows_str} \\end{{pmatrix}}"

    if isinstance(expr, MatrixNode):
        rows = [" & ".join(expr_to_latex(c) for c in row) for row in expr.rows]
        rows_str = " \\\\ ".join(rows)
        return f"\\begin{{pmatrix}} {rows_str} \\end{{pmatrix}}"

    if isinstance(expr, UnaryOpNode):
        operand_str = expr_to_latex(expr.operand, precedence=60)
        if expr.op == "-":
            return f"-{operand_str}"
        if expr.op in ("not", "\\neg", "~"):
            return f"\\neg {operand_str}"
        return f"{expr.op}{operand_str}"

    if isinstance(expr, BinaryOpNode):
        op = expr.op.lower()
        if op == "/":
            return f"\\frac{{{expr_to_latex(expr.left)}}}{{{expr_to_latex(expr.right)}}}"
        if op in ("^", "**"):
            base_str = expr_to_latex(expr.left, precedence=70)
            exp_str = expr_to_latex(expr.right)
            return f"{{{base_str}}}^{{{exp_str}}}"

        # Standard binary operators
        op_map = {
            "+": " + ",
            "-": " - ",
            "*": " \\cdot ",
            "\\cup": " \\cup ",
            "union": " \\cup ",
            "\\cap": " \\cap ",
            "intersect": " \\cap ",
            "\\setminus": " \\setminus ",
            "setminus": " \\setminus ",
            "and": " \\land ",
            "\\land": " \\land ",
            "/\\": " \\land ",
            "or": " \\lor ",
            "\\lor": " \\lor ",
            "\\/": " \\lor ",
            "=>": " \\implies ",
            "\\implies": " \\implies ",
            "<=>": " \\iff ",
            "iff": " \\iff ",
            "\\iff": " \\iff ",
            "\\circ": " \\circ ",
        }
        symbol = op_map.get(op, f" {expr.op} ")
        l_str = expr_to_latex(expr.left, precedence=20)
        r_str = expr_to_latex(expr.right, precedence=20)
        res = f"{l_str}{symbol}{r_str}"
        if precedence > 20:
            return f"({res})"
        return res

    if isinstance(expr, RelationNode):
        rel_map = {
            "=": " = ",
            "\\equiv": " \\equiv ",
            "!=": " \\neq ",
            "/=": " \\neq ",
            "\\neq": " \\neq ",
            "<=": " \\le ",
            "\\le": " \\le ",
            "\\leq": " \\le ",
            ">=": " \\ge ",
            "\\ge": " \\ge ",
            "\\geq": " \\ge ",
            "<": " < ",
            ">": " > ",
            "in": " \\in ",
            "\\in": " \\in ",
            "notin": " \\notin ",
            "not in": " \\notin ",
            "\\notin": " \\notin ",
            "subset": " \\subset ",
            "\\subset": " \\subset ",
            "subseteq": " \\subseteq ",
            "\\subseteq": " \\subseteq ",
        }
        op_str = rel_map.get(expr.op.lower(), f" {expr.op} ")
        l_str = expr_to_latex(expr.left)
        r_str = expr_to_latex(expr.right)
        return f"{l_str}{op_str}{r_str}"

    if isinstance(expr, FunctionCallNode):
        fn = expr.func.lower()
        if fn == "abs" and len(expr.args) == 1:
            return f"|{expr_to_latex(expr.args[0])}|"
        if fn == "norm" and len(expr.args) == 1:
            return f"\\|{expr_to_latex(expr.args[0])}\\|"
        if fn == "sqrt" and len(expr.args) == 1:
            return f"\\sqrt{{{expr_to_latex(expr.args[0])}}}"
        if fn in ("conj", "conjugate") and len(expr.args) == 1:
            return f"\\overline{{{expr_to_latex(expr.args[0])}}}"
        if fn in ("re", "realpart") and len(expr.args) == 1:
            return f"\\operatorname{{Re}}({expr_to_latex(expr.args[0])})"
        if fn in ("im", "imagpart") and len(expr.args) == 1:
            return f"\\operatorname{{Im}}({expr_to_latex(expr.args[0])})"
        if fn in ("det", "determinant") and len(expr.args) == 1:
            return f"\\det({expr_to_latex(expr.args[0])})"
        if fn in ("tr", "trace") and len(expr.args) == 1:
            return f"\\operatorname{{tr}}({expr_to_latex(expr.args[0])})"
        if fn == "transpose" and len(expr.args) == 1:
            return f"{{{expr_to_latex(expr.args[0])}}}^T"
        if fn == "dot" and len(expr.args) == 2:
            return f"{expr_to_latex(expr.args[0])} \\cdot {expr_to_latex(expr.args[1])}"
        if fn in ("cauchyriemann", "cauchy_riemann"):
            args_str = ", ".join(expr_to_latex(a) for a in expr.args)
            return f"\\operatorname{{CauchyRiemann}}({args_str})"
        if fn == "orthogonal" and len(expr.args) == 2:
            return f"{expr_to_latex(expr.args[0])} \\perp {expr_to_latex(expr.args[1])}"
        if fn == "diff" and len(expr.args) >= 2:
            target = expr_to_latex(expr.args[0])
            var = expr_to_latex(expr.args[1])
            if len(expr.args) >= 3:
                order = expr_to_latex(expr.args[2])
                return f"\\frac{{\\partial^{{{order}}} {target}}}{{\\partial {var}^{{{order}}}}}"
            return f"\\frac{{\\partial {target}}}{{\\partial {var}}}"
        if fn in ("congruent", "cong") and len(expr.args) == 3:
            return f"{expr_to_latex(expr.args[0])} \\equiv {expr_to_latex(expr.args[1])} \\pmod{{{expr_to_latex(expr.args[2])}}}"
        if fn in ("inv", "inverse") and len(expr.args) == 1:
            return f"{{{expr_to_latex(expr.args[0])}}}^{{-1}}"
        if fn == "sum" and len(expr.args) == 4:
            idx = expr_to_latex(expr.args[0])
            low = expr_to_latex(expr.args[1])
            up = expr_to_latex(expr.args[2])
            body = expr_to_latex(expr.args[3])
            return f"\\sum_{{{idx}={low}}}^{{{up}}} {body}"

        # Standard user-defined or mathematical function
        args_str = ", ".join(expr_to_latex(a) for a in expr.args)
        return f"\\operatorname{{{expr.func}}}({args_str})"

    if isinstance(expr, QuantifierNode):
        q_sym = "\\forall" if expr.quantifier.lower() == "forall" else "\\exists"
        type_annot = f" \\in {math_type_to_latex(expr.var_type)}" if expr.var_type else ""
        form_str = expr_to_latex(expr.formula)
        return f"{q_sym} {expr.var}{type_annot},\\; {form_str}"

    if isinstance(expr, IntegralNode):
        body_str = expr_to_latex(expr.body)
        var_str = expr.var
        if expr.lower is not None and expr.upper is not None:
            low_str = expr_to_latex(expr.lower)
            up_str = expr_to_latex(expr.upper)
            return f"\\int_{{{low_str}}}^{{{up_str}}} {body_str} \\, d{var_str}"
        return f"\\int {body_str} \\, d{var_str}"

    if isinstance(expr, LimitNode):
        body_str = expr_to_latex(expr.body)
        var_str = expr.var
        target_str = expr_to_latex(expr.target)
        dir_suffix = ""
        if expr.direction == "+":
            dir_suffix = "^+"
        elif expr.direction == "-":
            dir_suffix = "^-"
        return f"\\lim_{{{var_str} \\to {target_str}{dir_suffix}}} {body_str}"

    return str(expr)


class LatexProofExporter:
    """Renders Aether AST objects to styled LaTeX documents."""

    def __init__(self, indent_spaces: int = 4) -> None:
        self.indent_unit = " " * indent_spaces

    def export_document(
        self,
        doc: DocumentNode,
        report: Optional[ProofReport] = None,
        standalone: bool = True,
    ) -> str:
        body_lines: list[str] = []

        # 1. Functions / Definitions
        defs = [s for s in doc.statements if isinstance(s, FuncDefNode)]
        if defs:
            for d in defs:
                params_str = ", ".join(d.params)
                body_str = expr_to_latex(d.body)
                body_lines.append(f"\\noindent \\textbf{{Definition:}} Let ${d.name}({params_str}) = {body_str}$.\\\\[0.5em]")

        # 2. Theorems
        for thm in doc.theorems:
            body_lines.append(self._export_theorem(thm))

        # 3. Scratchpad statements if present
        scratch_stmts = [s for s in doc.statements if not isinstance(s, FuncDefNode)]
        if scratch_stmts:
            body_lines.append("\\section*{Proof Scratchpad}")
            body_lines.append(self._export_statements(scratch_stmts))

        content = "\n\n".join(body_lines)

        if not standalone:
            return content

        return (
            "\\documentclass[11pt]{article}\n"
            "\\usepackage{amsmath,amssymb,amsthm}\n"
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{microtype}\n\n"
            "\\theoremstyle{definition}\n"
            "\\newtheorem{theorem}{Theorem}\n"
            "\\newtheorem{lemma}{Lemma}\n"
            "\\newtheorem{definition}{Definition}\n\n"
            "\\title{\\textbf{Aether Verified Proof Document}}\n"
            "\\author{Generated by Aether Proof Intern}\n"
            "\\date{\\today}\n\n"
            "\\begin{document}\n"
            "\\maketitle\n\n"
            f"{content}\n\n"
            "\\end{document}\n"
        )

    def _export_theorem(self, thm: TheoremNode) -> str:
        lines: list[str] = []
        name_attr = f"[{thm.name}]" if thm.name else ""
        lines.append(f"\\begin{{theorem}}{name_attr}")

        if thm.claim is not None:
            claim_str = expr_to_latex(thm.claim)
            lines.append(f"    \\[ {claim_str} \\]")
        lines.append("\\end{theorem}")

        if thm.proof is not None:
            lines.append("\\begin{proof}")
            lines.append(self._export_statements(thm.proof.statements, indent_level=1))
            lines.append("\\end{proof}")

        return "\n".join(lines)

    def _export_statements(self, stmts: list[StatementNode], indent_level: int = 0) -> str:
        lines: list[str] = []
        ind = self.indent_unit * indent_level

        i = 0
        n = len(stmts)
        while i < n:
            stmt = stmts[i]

            # Sequence of StepNodes -> align* environment
            if isinstance(stmt, StepNode):
                step_block: list[StepNode] = []
                while i < n and isinstance(stmts[i], StepNode):
                    step_block.append(stmts[i])  # type: ignore[arg-type]
                    i += 1
                lines.append(self._export_step_chain(step_block, indent_level))
                continue

            if isinstance(stmt, ImportNode):
                lines.append(f"{ind}% \\input{{{stmt.path}}}")
                i += 1
                continue

            if isinstance(stmt, VarDeclNode):
                vars_str = ", ".join(stmt.variables)
                t_latex = math_type_to_latex(stmt.type_name)
                decl_str = f"Let ${vars_str} \\in {t_latex}$"
                if stmt.condition is not None:
                    decl_str += f" such that ${expr_to_latex(stmt.condition)}$"
                lines.append(f"{ind}{decl_str}.")

            elif isinstance(stmt, AssumeNode):
                p_str = expr_to_latex(stmt.proposition)
                lbl = f"({stmt.label}) " if stmt.label else ""
                lines.append(f"{ind}Assume {lbl}${p_str}$.")

            elif isinstance(stmt, ObtainNode):
                t_str = f" \\in {math_type_to_latex(stmt.type_name)}" if stmt.type_name else ""
                c_str = expr_to_latex(stmt.condition)
                from_str = f" from {stmt.source_label}" if stmt.source_label else ""
                lines.append(f"{ind}Obtain ${stmt.variable}{t_str}$ such that ${c_str}${from_str}.")

            elif isinstance(stmt, DeduceNode):
                c_str = expr_to_latex(stmt.claim)
                w_str = f" [witness: ${expr_to_latex(stmt.witness)}$]" if stmt.witness else ""
                j_str = f" \\quad \\text{{[by {stmt.justification}]}}" if stmt.justification else ""
                lines.append(f"{ind}Therefore, ${c_str}${w_str}{j_str}.")

            elif isinstance(stmt, SubProofNode):
                tag = stmt.subproof_type.title()
                header = f"{tag}:"
                if stmt.title:
                    header = f"{tag} (${stmt.title}$):"
                lines.append(f"\n{ind}\\paragraph*{{{header}}}")
                lines.append(self._export_statements(stmt.statements, indent_level + 1))

            i += 1

        return "\n".join(lines)

    def _export_step_chain(self, steps: list[StepNode], indent_level: int) -> str:
        ind = self.indent_unit * indent_level
        lines: list[str] = [f"{ind}\\begin{{align*}}"]

        for idx, step in enumerate(steps):
            rel = step.relation or "="
            rel_map = {
                "=": "=",
                "!=": "\\neq",
                "<=": "\\le",
                ">=": "\\ge",
                "<": "<",
                ">": ">",
            }
            rel_sym = rel_map.get(rel.lower(), rel)
            rhs_str = expr_to_latex(step.rhs)

            if step.lhs is not None:
                lhs_str = expr_to_latex(step.lhs)
                line_str = f"{ind}    {lhs_str} &{rel_sym} {rhs_str}"
            else:
                line_str = f"{ind}    &{rel_sym} {rhs_str}"

            if step.justification:
                line_str += f" && \\text{{({step.justification})}}"

            if idx < len(steps) - 1:
                line_str += " \\\\"
            lines.append(line_str)

        lines.append(f"{ind}\\end{{align*}}")
        return "\n".join(lines)


def export_to_latex(
    doc_or_source: Union[DocumentNode, str],
    report: Optional[ProofReport] = None,
    standalone: bool = True,
) -> str:
    """High-level export function to convert an Aether source or DocumentNode to LaTeX."""
    if isinstance(doc_or_source, str):
        checker = ProofChecker()
        doc = checker._parser.parse(doc_or_source)
    else:
        doc = doc_or_source

    exporter = LatexProofExporter()
    return exporter.export_document(doc, report=report, standalone=standalone)
