"""Orchestrating proof checker that walks Aether AST nodes and coordinates Context, SymPy, and Z3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from aether.core.ast import (
    DocumentNode,
    TheoremNode,
    ProofNode,
    StatementNode,
    VarDeclNode,
    AssumeNode,
    ObtainNode,
    StepNode,
    DeduceNode,
    SubProofNode,
    ExprNode,
    SymbolNode,
    RelationNode,
    QuantifierNode,
    BinaryOpNode,
)
from aether.parser.parser import AetherParser
from aether.engine.context import (
    ProofContext,
    ContextError,
    VariableCaptureError,
    MonotonicityError,
    ChainError,
    GeneralizationError,
    canonical_rel,
)
from aether.engine.algebra import (
    extract_domain_obligations,
    verify_algebraic_equality,
)
from aether.engine.logic import (
    verify_entailment,
    check_domain_obligation,
    substitute_expr,
)


class StepStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


@dataclass
class StepResult:
    """Verification outcome and context snapshot for a single proof statement."""

    statement: StatementNode
    line: Optional[int]
    status: StepStatus
    message: str
    backend: str = "Context"
    scope_depth: int = 0
    active_variables: dict[str, str] = field(default_factory=dict)
    active_hypotheses: list[str] = field(default_factory=list)
    domain_warnings: list[str] = field(default_factory=list)
    counterexample: Optional[str] = None


@dataclass
class ProofReport:
    """Complete verification report for a theorem or top-level proof script."""

    theorem_name: Optional[str] = None
    results: list[StepResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return all(r.status != StepStatus.INVALID for r in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(r.status == StepStatus.WARNING or bool(r.domain_warnings) for r in self.results)

    def format_report(self) -> str:
        header = f"=== Theorem: {self.theorem_name} ===" if self.theorem_name else "=== Proof Audit ==="
        lines = [header]
        for r in self.results:
            icon = "✓" if r.status == StepStatus.VALID else ("⚠" if r.status == StepStatus.WARNING else "❌")
            ln_prefix = f"L{r.line:<3}" if r.line is not None else "    "
            indent = "  " * r.scope_depth
            lines.append(f"  {ln_prefix} {icon} {indent}{r.statement}  [{r.backend}]")
            if r.status != StepStatus.VALID:
                lines.append(f"         {indent}↳ {r.message}")
            for dw in r.domain_warnings:
                lines.append(f"         {indent}↳ ⚠ {dw}")
        verdict = "VALID" if self.is_valid else "INVALID"
        if self.is_valid and self.has_warnings:
            verdict = "VALID (with domain warnings)"
        lines.append(f"Result: {verdict}")
        return "\n".join(lines)


class ProofChecker:
    """Walks an Aether DocumentNode or source string and verifies every step."""

    def __init__(self, strict_domains: bool = False) -> None:
        """
        Parameters
        ----------
        strict_domains:
            If True, unresolved domain obligations (like potential division by zero)
            mark the step as ``INVALID`` instead of ``WARNING``.
        """
        self.strict_domains = strict_domains
        self._parser = AetherParser()

    def check_source(self, source: str) -> list[ProofReport]:
        """Parse *source* and check all theorems and top-level statements."""
        doc = self._parser.parse(source)
        return self.check_document(doc)

    def check_document(self, doc: DocumentNode) -> list[ProofReport]:
        reports: list[ProofReport] = []
        for thm in doc.theorems:
            reports.append(self.check_theorem(thm))
        if doc.statements:
            ctx = ProofContext()
            results = [self._check_statement(stmt, ctx) for stmt in doc.statements]
            reports.append(ProofReport(theorem_name=None, results=results))
        return reports

    def check_theorem(self, thm: TheoremNode) -> ProofReport:
        ctx = ProofContext()
        results: list[StepResult] = []
        if thm.proof is not None:
            for stmt in thm.proof.statements:
                results.append(self._check_statement(stmt, ctx))
        return ProofReport(theorem_name=thm.name, results=results)

    # -------------------------------------------------------------------
    # Internal statement dispatch
    # -------------------------------------------------------------------

    def _snapshot(self, ctx: ProofContext) -> tuple[dict[str, str], list[str]]:
        vars_snap = {k: v.math_type.value for k, v in ctx.all_variables().items()}
        hyps_snap = [
            f"{h.label}: {h.proposition}" if h.label else str(h.proposition)
            for h in ctx.all_hypotheses()
        ]
        return vars_snap, hyps_snap

    def _check_domains_for_exprs(
        self,
        exprs: list[Optional[ExprNode]],
        line: Optional[int],
        ctx: ProofContext,
    ) -> list[str]:
        warnings: list[str] = []
        for ex in exprs:
            if ex is None:
                continue
            for ob in extract_domain_obligations(ex, line=line):
                ctx.obligations.append(ob)
                d_res = check_domain_obligation(ob, ctx)
                if not d_res.valid:
                    warnings.append(d_res.message)
        return warnings

    def _apply_domain_status(
        self,
        base_status: StepStatus,
        domain_warnings: list[str],
    ) -> StepStatus:
        if base_status == StepStatus.INVALID or not domain_warnings:
            return base_status
        return StepStatus.INVALID if self.strict_domains else StepStatus.WARNING

    def _check_statement(self, stmt: StatementNode, ctx: ProofContext) -> StepResult:
        if isinstance(stmt, VarDeclNode):
            return self._check_var_decl(stmt, ctx)
        if isinstance(stmt, AssumeNode):
            return self._check_assume(stmt, ctx)
        if isinstance(stmt, ObtainNode):
            return self._check_obtain(stmt, ctx)
        if isinstance(stmt, StepNode):
            return self._check_step(stmt, ctx)
        if isinstance(stmt, DeduceNode):
            return self._check_deduce(stmt, ctx)
        if isinstance(stmt, SubProofNode):
            return self._check_subproof(stmt, ctx)
        vars_snap, hyps_snap = self._snapshot(ctx)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=StepStatus.VALID,
            message="Statement accepted.",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
        )

    def _check_var_decl(self, stmt: VarDeclNode, ctx: ProofContext) -> StepResult:
        domain_warnings = self._check_domains_for_exprs([stmt.condition], stmt.line, ctx)
        try:
            for v in stmt.variables:
                ctx.declare_variable(v, stmt.type_name, is_witness=False, condition=stmt.condition)
        except (VariableCaptureError, ValueError) as exc:
            vars_snap, hyps_snap = self._snapshot(ctx)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=str(exc),
                backend="Context",
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
            )

        vars_snap, hyps_snap = self._snapshot(ctx)
        status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=f"Declared {', '.join(stmt.variables)} : {stmt.type_name}.",
            backend="Context",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
        )

    def _check_assume(self, stmt: AssumeNode, ctx: ProofContext) -> StepResult:
        domain_warnings = self._check_domains_for_exprs([stmt.proposition], stmt.line, ctx)
        ctx.add_hypothesis(stmt.proposition, label=stmt.label, is_assumption=True)
        vars_snap, hyps_snap = self._snapshot(ctx)
        status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
        msg = f"Assumed {stmt.proposition}." if not domain_warnings else domain_warnings[0]
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=msg,
            backend="Context",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
        )

    def _check_obtain(self, stmt: ObtainNode, ctx: ProofContext) -> StepResult:
        domain_warnings = self._check_domains_for_exprs([stmt.condition], stmt.line, ctx)

        # 1. Check variable freshness BEFORE adding to context
        if ctx.get_var(stmt.variable) is not None:
            try:
                ctx.declare_variable(stmt.variable, stmt.type_name or "Int", is_witness=True)
            except VariableCaptureError as exc:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=str(exc),
                    backend="Context",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )

        # 2. Check that the existential is licensed by the source hypothesis (or current context)
        if stmt.source_label is not None:
            src_hyp = ctx.get_hypothesis(stmt.source_label)
            if src_hyp is None:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=f"Unknown hypothesis label '{stmt.source_label}' in Obtain.",
                    backend="Context",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )

        existential_claim = QuantifierNode(
            quantifier="exists",
            var=stmt.variable,
            var_type=stmt.type_name or "Int",
            formula=stmt.condition,
        )
        ent_res = verify_entailment(existential_claim, ctx)
        if not ent_res.valid:
            vars_snap, hyps_snap = self._snapshot(ctx)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=f"Cannot obtain '{stmt.variable}' satisfying '{stmt.condition}': {ent_res.message}",
                backend=ent_res.backend,
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                counterexample=ent_res.counterexample,
            )

        # 3. Register witness variable and condition in context
        ctx.declare_variable(
            stmt.variable,
            stmt.type_name or "Int",
            is_witness=True,
            condition=stmt.condition,
        )
        vars_snap, hyps_snap = self._snapshot(ctx)
        status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=f"Obtained fresh witness {stmt.variable} with {stmt.condition}.",
            backend="Definition+Z3",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
        )

    def _check_step(self, stmt: StepNode, ctx: ProofContext) -> StepResult:
        domain_warnings = self._check_domains_for_exprs([stmt.lhs, stmt.rhs], stmt.line, ctx)

        try:
            eff_lhs, eff_rel, eff_rhs, next_chain = ctx.resolve_step(stmt.lhs, stmt.relation, stmt.rhs)
        except (ChainError, MonotonicityError) as exc:
            vars_snap, hyps_snap = self._snapshot(ctx)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=str(exc),
                backend="ChainGuard",
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                domain_warnings=domain_warnings,
            )

        vars_snap, hyps_snap = self._snapshot(ctx)

        # Case 1: Equational step (eff_lhs = eff_rhs)
        if eff_rel == "=" and eff_lhs is not None:
            alg_res = verify_algebraic_equality(eff_lhs, eff_rhs, ctx)
            if alg_res.valid:
                ctx.commit_step(next_chain)
                status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
                msg = alg_res.message if not domain_warnings else domain_warnings[0]
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=status,
                    message=msg,
                    backend="SymPy",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

            # Fallback to Z3 in case equality depends on logical/modular hypotheses
            rel_node = RelationNode(op="=", left=eff_lhs, right=eff_rhs)
            z3_res = verify_entailment(rel_node, ctx)
            if z3_res.valid:
                ctx.commit_step(next_chain)
                status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
                msg = z3_res.message if not domain_warnings else domain_warnings[0]
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=status,
                    message=msg,
                    backend=z3_res.backend,
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=alg_res.message,
                backend="SymPy",
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                domain_warnings=domain_warnings,
                counterexample=alg_res.counterexample or z3_res.counterexample,
            )

        # Case 2: Inequality or non-equality relation step
        if eff_rel and eff_lhs is not None:
            rel_node = RelationNode(op=eff_rel, left=eff_lhs, right=eff_rhs)
            z3_res = verify_entailment(rel_node, ctx)
            if z3_res.valid:
                ctx.commit_step(next_chain)
                ctx.add_hypothesis(rel_node, label=None, is_assumption=False)
                status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
                msg = z3_res.message if not domain_warnings else domain_warnings[0]
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=status,
                    message=msg,
                    backend=z3_res.backend,
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=z3_res.message,
                backend=z3_res.backend,
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                domain_warnings=domain_warnings,
                counterexample=z3_res.counterexample,
            )

        # Case 3: Bare expression / proposition step
        z3_res = verify_entailment(eff_rhs, ctx)
        if z3_res.valid:
            ctx.add_hypothesis(eff_rhs, label=None, is_assumption=False)
            status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=status,
                message=z3_res.message,
                backend=z3_res.backend,
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                domain_warnings=domain_warnings,
            )
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=StepStatus.INVALID,
            message=z3_res.message,
            backend=z3_res.backend,
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
            counterexample=z3_res.counterexample,
        )

    def _check_deduce(self, stmt: DeduceNode, ctx: ProofContext) -> StepResult:
        claim = stmt.claim

        # Handle chained deduction (`Therefore <= 8 * k^2` where left is `<prev>`)
        if (
            isinstance(claim, RelationNode)
            and isinstance(claim.left, SymbolNode)
            and claim.left.name == "<prev>"
        ):
            if ctx.chain is None:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message="Chained deduction has no preceding step to chain from.",
                    backend="ChainGuard",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )
            claim = RelationNode(op=claim.op, left=ctx.chain.head_lhs, right=claim.right)

        domain_warnings = self._check_domains_for_exprs([claim, stmt.witness], stmt.line, ctx)

        # Guardrail: Check illegal universal generalization over constrained variables
        if isinstance(claim, QuantifierNode) and claim.quantifier == "forall":
            try:
                ctx.check_generalization_allowed(claim.var)
            except GeneralizationError as exc:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=str(exc),
                    backend="ScopeGuard",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

        # If claim is an equality, try SymPy first
        if isinstance(claim, RelationNode) and canonical_rel(claim.op) == "=":
            alg_res = verify_algebraic_equality(claim.left, claim.right, ctx)
            if alg_res.valid:
                ctx.add_hypothesis(claim, label=None, is_assumption=False)
                vars_snap, hyps_snap = self._snapshot(ctx)
                status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
                msg = alg_res.message if not domain_warnings else domain_warnings[0]
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=status,
                    message=msg,
                    backend="SymPy",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

        # Verify via Logic / Z3 / Witness engine
        log_res = verify_entailment(claim, ctx, witness=stmt.witness)
        if log_res.valid:
            ctx.add_hypothesis(claim, label=None, is_assumption=False)
            vars_snap, hyps_snap = self._snapshot(ctx)
            status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
            msg = log_res.message if not domain_warnings else domain_warnings[0]
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=status,
                message=msg,
                backend=log_res.backend,
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                domain_warnings=domain_warnings,
            )

        vars_snap, hyps_snap = self._snapshot(ctx)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=StepStatus.INVALID,
            message=log_res.message,
            backend=log_res.backend,
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
            counterexample=log_res.counterexample,
        )

    def _check_subproof(self, stmt: SubProofNode, ctx: ProofContext) -> StepResult:
        ctx.push_scope()
        sub_results: list[StepResult] = []
        first_assumption: Optional[ExprNode] = None
        last_conclusion: Optional[ExprNode] = None

        for inner in stmt.statements:
            if isinstance(inner, AssumeNode) and first_assumption is None:
                first_assumption = inner.proposition
            res = self._check_statement(inner, ctx)
            sub_results.append(res)
            if isinstance(inner, DeduceNode) and res.status != StepStatus.INVALID:
                last_conclusion = inner.claim

        ctx.pop_scope()

        all_ok = all(r.status != StepStatus.INVALID for r in sub_results)
        if all_ok and first_assumption is not None and last_conclusion is not None:
            imp = BinaryOpNode(op="=>", left=first_assumption, right=last_conclusion)
            ctx.add_hypothesis(imp, label=None, is_assumption=False)

        vars_snap, hyps_snap = self._snapshot(ctx)
        status = StepStatus.VALID if all_ok else StepStatus.INVALID
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=f"Subproof ({len(sub_results)} steps) {'verified' if all_ok else 'failed'}.",
            backend="SubProof",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
        )
