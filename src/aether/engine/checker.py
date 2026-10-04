"""Orchestrating proof checker that walks Aether AST nodes and coordinates Context, SymPy, and Z3."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Any

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import re

from aether.core.ast import (
    DocumentNode,
    TheoremNode,
    ProofNode,
    StatementNode,
    VarDeclNode,
    FuncDefNode,
    AssumeNode,
    ObtainNode,
    StepNode,
    DeduceNode,
    SubProofNode,
    QEDNode,
    ExprNode,
    SymbolNode,
    GreekSymbolNode,
    UnaryOpNode,
    RelationNode,
    QuantifierNode,
    BinaryOpNode,
    ImportNode,
    FunctionCallNode,
)
from aether.parser.parser import AetherParser
from aether.engine.hints import hints_for
from aether.engine.citations import (
    CitationIndex,
    Target,
    ambiguous_message,
    looks_like_a_result,
    split_parts,
    unknown_message,
)
from aether.engine.context import (
    ProofContext,
    ContextError,
    VariableCaptureError,
    MonotonicityError,
    ChainError,
    GeneralizationError,
    canonical_rel,
    collect_free_symbols,
    substitute_mapping,
)
from aether.engine.algebra import (
    extract_domain_obligations,
    verify_algebraic_equality,
)
from aether.engine.logic import (
    fresh_solver_context,
    verify_entailment,
    check_domain_obligation,
    verify_case_exhaustiveness,
    verify_induction_schema,
    is_contradiction_symbol,
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
    col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None
    diagnostic_range: Optional[dict[str, int]] = None
    counterexample_dict: Optional[dict[str, str]] = None
    subproof_metadata: Optional[dict[str, Any]] = None
    sub_results: list[StepResult] = field(default_factory=list)
    # The result a `by …` citation used: {"cited", "label", "key", "claim"}.
    citation: Optional[dict[str, str]] = None
    # What to do about it: [{"message", "fix"?: {"line", "insert"|"replace", "text", "label"}}].
    hints: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.col is None and hasattr(self.statement, "col"):
            self.col = self.statement.col
        if self.line is None and hasattr(self.statement, "line"):
            self.line = self.statement.line
        if self.diagnostic_range is None and self.line is not None:
            self.diagnostic_range = {
                "start_line": self.line,
                "start_col": self.col or 1,
                "end_line": self.end_line or self.line,
                "end_col": self.end_col or ((self.col or 1) + len(str(self.statement))),
            }

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": str(self.statement),
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "message": self.message,
            "backend": self.backend,
            "scope_depth": self.scope_depth,
            "active_variables": dict(self.active_variables),
            "active_hypotheses": list(self.active_hypotheses),
            "domain_warnings": list(self.domain_warnings),
            "counterexample": self.counterexample,
            "counterexample_dict": self.counterexample_dict,
            "diagnostic_range": self.diagnostic_range,
            "subproof_metadata": self.subproof_metadata,
            "sub_results": [r.to_dict() for r in self.sub_results],
            "citation": self.citation,
            "hints": list(self.hints),
        }


@dataclass
class ProofReport:
    """Complete verification report for a theorem or top-level proof script."""

    theorem_name: Optional[str] = None
    results: list[StepResult] = field(default_factory=list)

    @property
    def all_results(self) -> list[StepResult]:
        """Flattened list of all verification results including nested subproof steps."""
        flat: list[StepResult] = []

        def _collect(res: StepResult) -> None:
            flat.append(res)
            for sub in res.sub_results:
                _collect(sub)

        for r in self.results:
            _collect(r)
        return flat

    @property
    def is_valid(self) -> bool:
        return all(r.status != StepStatus.INVALID for r in self.all_results)

    @property
    def has_warnings(self) -> bool:
        return any(r.status == StepStatus.WARNING or bool(r.domain_warnings) for r in self.all_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "theorem_name": self.theorem_name,
            "results": [r.to_dict() for r in self.results],
            "is_valid": self.is_valid,
            "has_warnings": self.has_warnings,
        }

    def format_report(self) -> str:
        header = f"=== Theorem: {self.theorem_name} ===" if self.theorem_name else "=== Proof Audit ==="
        lines = [header]

        def _format_step(r: StepResult) -> None:
            icon = "✓" if r.status == StepStatus.VALID else ("⚠" if r.status == StepStatus.WARNING else "❌")
            ln_prefix = f"L{r.line:<3}" if r.line is not None else "    "
            indent = "  " * r.scope_depth
            lines.append(f"  {ln_prefix} {icon} {indent}{r.statement}  [{r.backend}]")
            if r.status != StepStatus.VALID:
                lines.append(f"         {indent}↳ {r.message}")
            if r.counterexample:
                lines.append(f"         {indent}↳ Counterexample: {r.counterexample}")
            for dw in r.domain_warnings:
                lines.append(f"         {indent}↳ ⚠ {dw}")
            for sub in r.sub_results:
                _format_step(sub)

        for r in self.results:
            _format_step(r)

        verdict = "VALID" if self.is_valid else "INVALID"
        if self.is_valid and self.has_warnings:
            verdict = "VALID (with domain warnings)"
        lines.append(f"Result: {verdict}")
        return "\n".join(lines)


class ProofChecker:
    """Walks an Aether DocumentNode or source string and verifies every step."""

    def __init__(
        self,
        strict_domains: bool = False,
        base_dir: Optional[Path | str] = None,
    ) -> None:
        """
        Parameters
        ----------
        strict_domains:
            If True, unresolved domain obligations (like potential division by zero)
            mark the step as ``INVALID`` instead of ``WARNING``.
        base_dir:
            Optional base directory used to resolve relative proof imports.
        """
        self.strict_domains = strict_domains
        self.base_dir = Path(base_dir).resolve() if base_dir else None
        self._parser = AetherParser()
        self._sources: Optional[dict[str, str]] = None
        self._citations: Optional[CitationIndex] = None
        self._lines: list[str] = []
        self._import_cache: dict[Path, tuple[list[FuncDefNode], list[tuple[Optional[str], ExprNode]], bool]] = {}

    def clear_cache(self) -> None:
        """Clear the cached results of imported libraries."""
        self._import_cache.clear()

    #: Root of the virtual tree that ``sources`` files live under.  A path
    #: here never exists on disk, so in-memory files cannot collide with real
    #: ones in the import cache or the cycle check.
    VIRTUAL_ROOT = PurePosixPath("/aether-workspace")

    def check_source(
        self,
        source: str,
        file_path: Optional[Path | str] = None,
        sources: Optional[Mapping[str, str]] = None,
        citations: Optional[Mapping[str, Any]] = None,
    ) -> list[ProofReport]:
        """Parse *source* and check all theorems and top-level statements.

        ``sources`` maps workspace paths (``"lemmas.aether"``,
        ``"groups/basics.aether"``) to their text, so ``import`` statements
        resolve against files held in memory -- a browser workspace -- before
        the disk is searched.  When it is given, ``file_path`` may be the
        importing file's own workspace path, and relative imports resolve from
        its folder.

        ``citations`` maps the names a step may cite (``by Theorem 1.1``,
        ``By the triangle inequality, ...``) to the ``sources`` key that proves
        each (see ``aether.engine.citations``).  A cited result is used for
        that step alone, and the step's result says which one it was.
        """
        doc = self._parser.parse(source)
        fresh_solver_context()
        previous_lines = self._lines
        self._lines = source.splitlines()
        previous = self._sources
        previous_index = self._citations
        self._sources = dict(sources) if sources else None
        self._citations = CitationIndex(citations) if citations else None
        try:
            if self._sources is not None:
                # In-memory files may change between calls; never reuse a cached import.
                self.clear_cache()
                virtual = self._virtual_path(str(file_path) if file_path else "__main__.aether")
                return self._check_document_internal(doc, virtual_file=virtual, import_chain=[virtual])[0]
            return self.check_document(doc, file_path=file_path)
        finally:
            self._sources = previous
            self._citations = previous_index
            self._lines = previous_lines

    def check_file(self, file_path: Path | str) -> list[ProofReport]:
        """Read *file_path* from disk and verify its proof document."""
        p = Path(file_path).resolve()
        with open(p, "r", encoding="utf-8") as f:
            source = f.read()
        return self.check_source(source, file_path=p)

    def check_document(
        self,
        doc: DocumentNode,
        file_path: Optional[Path | str] = None,
        import_chain: Optional[list[Path]] = None,
    ) -> list[ProofReport]:
        reports, _, _ = self._check_document_internal(
            doc, file_path=file_path, import_chain=import_chain
        )
        return reports

    @staticmethod
    def _close_claim(thm: TheoremNode, claim: ExprNode) -> Optional[ExprNode]:
        """The fact a proven theorem may lend to later theorems and importers.

        A conclusion only holds under the proof's own hypotheses, about the
        proof's own variables.  Exporting it bare would let ``Assume x > 2 ...
        Therefore x > 1`` vouch for ``x > 1`` about anybody's ``x``, so the
        claim is closed over its top-level declarations and assumptions:

            forall v1 : T1, ..., (conditions and assumptions) => claim

        A claim that mentions an ``Obtain`` witness has no closed form here
        (the witness exists only inside the proof), so it is not exported.
        """
        statements = thm.proof.statements if thm.proof is not None else []
        decls: list[tuple[str, str]] = []
        antecedents: list[ExprNode] = []
        witnesses: set[str] = set()
        for stmt in statements:
            if isinstance(stmt, VarDeclNode):
                decls.extend((v, stmt.type_name) for v in stmt.variables)
                if stmt.condition is not None:
                    antecedents.append(stmt.condition)
            elif isinstance(stmt, AssumeNode):
                antecedents.append(stmt.proposition)
            elif isinstance(stmt, ObtainNode):
                witnesses.add(stmt.variable)

        if collect_free_symbols(claim) & witnesses:
            return None
        if not antecedents and not decls:
            return claim

        body = claim
        if antecedents:
            premise = antecedents[0]
            for extra in antecedents[1:]:
                premise = BinaryOpNode(op="and", left=premise, right=extra)
            if collect_free_symbols(premise) & witnesses:
                return None
            body = BinaryOpNode(op="=>", left=premise, right=claim)

        mentioned = collect_free_symbols(body)
        for name, type_name in reversed(decls):
            if name in mentioned:
                body = QuantifierNode(quantifier="forall", var=name, var_type=type_name, formula=body)
        return body

    @staticmethod
    def _with_default_extension(*paths: str) -> list[str]:
        """Each path as written, then (if it has no extension) with ``.aether``.

        ``import "lemmas"`` finds ``lemmas.aether``; an exact match is tried first.
        """
        out: list[str] = []
        for path in paths:
            out.append(path)
            if not path.endswith(".aether"):
                out.append(f"{path}.aether")
        return out

    def _virtual_path(self, workspace_path: str) -> Path:
        """The pseudo-path a workspace file is known by (never a real file)."""
        clean = PurePosixPath("/", workspace_path.replace("\\", "/"))
        parts = [p for p in clean.parts[1:] if p not in ("", ".")]
        resolved: list[str] = []
        for part in parts:
            if part == "..":
                if resolved:
                    resolved.pop()
            else:
                resolved.append(part)
        return Path(str(self.VIRTUAL_ROOT.joinpath(*resolved)))

    def _is_virtual(self, path: Path) -> bool:
        return PurePosixPath(path.as_posix()).is_relative_to(self.VIRTUAL_ROOT)

    def _workspace_key(self, virtual: Path) -> Optional[str]:
        """The ``sources`` key for a virtual path, or None if it is not in the workspace."""
        if self._sources is None:
            return None
        try:
            rel = PurePosixPath(virtual.as_posix()).relative_to(self.VIRTUAL_ROOT).as_posix()
        except ValueError:
            return None
        if rel in self._sources:
            return rel
        normalized = {k.replace("\\", "/").lstrip("./"): k for k in self._sources}
        return normalized.get(rel)

    def _check_document_internal(
        self,
        doc: DocumentNode,
        file_path: Optional[Path | str] = None,
        import_chain: Optional[list[Path]] = None,
        virtual_file: Optional[Path] = None,
    ) -> tuple[list[ProofReport], list[FuncDefNode], list[tuple[Optional[str], ExprNode]]]:
        reports: list[ProofReport] = []
        shared_defs: list[FuncDefNode] = [s for s in doc.statements if isinstance(s, FuncDefNode)]
        verified_claims: list[tuple[Optional[str], ExprNode]] = []
        import_results: list[StepResult] = []

        cur_file = virtual_file if virtual_file is not None else (Path(file_path).resolve() if file_path else None)
        chain = list(import_chain) if import_chain else ([cur_file] if cur_file else [])

        # Process imports
        for stmt in doc.statements:
            if isinstance(stmt, ImportNode):
                res = self._process_import(stmt, cur_file, chain, shared_defs, verified_claims)
                import_results.append(res)

        for thm in doc.theorems:
            rep = self.check_theorem(thm, shared_defs=shared_defs, verified_claims=verified_claims)
            reports.append(rep)
            if rep.is_valid:
                claim = thm.claim
                if claim is None and rep.results:
                    for r in reversed(rep.results):
                        if isinstance(r.statement, DeduceNode):
                            claim = r.statement.claim
                            break
                closed = self._close_claim(thm, claim) if claim is not None else None
                if closed is not None:
                    verified_claims.append((thm.name, closed))

        has_non_def_stmts = any(not isinstance(s, (FuncDefNode, ImportNode)) for s in doc.statements)
        if doc.statements and (not doc.theorems or has_non_def_stmts or import_results):
            ctx = ProofContext()
            for fn_def in shared_defs:
                if fn_def not in doc.statements:
                    try:
                        ctx.declare_function(fn_def.name, fn_def.params, fn_def.body)
                    except VariableCaptureError:
                        pass
            for name, claim in verified_claims:
                ctx.add_hypothesis(claim, label=name, is_assumption=False)

            results: list[StepResult] = []
            for stmt in doc.statements:
                if isinstance(stmt, ImportNode):
                    matching = next((r for r in import_results if r.statement is stmt), None)
                    if matching:
                        results.append(matching)
                    else:
                        results.append(self._process_import(stmt, cur_file, chain, shared_defs, verified_claims))
                else:
                    results.append(self._check_statement(stmt, ctx))

            if results:
                reports.append(ProofReport(theorem_name=None, results=results))
        return reports, shared_defs, verified_claims

    def _process_import(
        self,
        stmt: ImportNode,
        cur_file: Optional[Path],
        chain: list[Path],
        shared_defs: list[FuncDefNode],
        verified_claims: list[tuple[Optional[str], ExprNode]],
    ) -> StepResult:
        target_path: Optional[Path] = None
        virtual_text: Optional[str] = None
        search_dirs: list[Path] = []
        if self._sources is not None:
            # Relative to the importing file's folder first, then the workspace root.
            is_virtual = cur_file is not None and self._is_virtual(cur_file)
            importer_dir = cur_file.parent if is_virtual else Path(str(self.VIRTUAL_ROOT))
            rel_dir = PurePosixPath(importer_dir.as_posix()).relative_to(self.VIRTUAL_ROOT).as_posix()
            for candidate_key in self._with_default_extension(
                f"{rel_dir}/{stmt.path}" if rel_dir != "." else stmt.path, stmt.path
            ):
                virtual = self._virtual_path(candidate_key)
                key = self._workspace_key(virtual)
                if key is not None:
                    target_path, virtual_text = virtual, self._sources[key]
                    break

        if target_path is None:
            if cur_file and not self._is_virtual(cur_file):
                search_dirs.append(cur_file.parent)
            if self.base_dir:
                search_dirs.append(self.base_dir)
            search_dirs.append(Path.cwd().resolve())
            for d in search_dirs:
                for name in self._with_default_extension(stmt.path):
                    candidate = (d / name).resolve()
                    if candidate.is_file():
                        target_path = candidate
                        break
                if target_path is not None:
                    break

        if target_path is None:
            if self._sources is not None:
                search_dirs.insert(0, Path("the workspace"))
            searched = ", ".join(str(d) for d in search_dirs)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=f"Import not found: '{stmt.path}' (searched: {searched})",
                backend="Library",
            )

        if target_path in chain:
            chain_str = " -> ".join(p.name for p in chain)
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=f"Cyclic import detected: {chain_str} -> {target_path.name}",
                backend="Library",
            )

        if target_path in self._import_cache:
            cache_defs, cache_claims, is_valid = self._import_cache[target_path]
            for d in cache_defs:
                if d not in shared_defs:
                    shared_defs.append(d)
            for c in cache_claims:
                if c not in verified_claims:
                    verified_claims.append(c)
            status = StepStatus.VALID if is_valid else StepStatus.WARNING
            msg = f"Imported '{stmt.path}' ({len(cache_claims)} theorems, {len(cache_defs)} definitions)"
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=status,
                message=msg,
                backend="Library",
            )

        try:
            if virtual_text is not None:
                content = virtual_text
            else:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read()
        except OSError as e:
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=f"Failed to read '{target_path}': {e}",
                backend="Library",
            )

        try:
            sub_doc = self._parser.parse(content)
        except Exception as pe:
            msg = getattr(pe, "message", str(pe))
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=f"Parse error in library '{stmt.path}': {msg}",
                backend="Library",
            )

        sub_reports, sub_defs, sub_claims = self._check_document_internal(
            sub_doc,
            file_path=None if virtual_text is not None else target_path,
            virtual_file=target_path if virtual_text is not None else None,
            import_chain=chain + [target_path],
        )
        sub_results = [r for rep in sub_reports for r in rep.results]
        cyclic = next((r for r in sub_results if "Cyclic import" in r.message), None)
        if cyclic:
            return StepResult(
                statement=stmt,
                line=stmt.line,
                status=StepStatus.INVALID,
                message=cyclic.message,
                backend="Library",
            )

        all_valid = all(r.is_valid for r in sub_reports)

        self._import_cache[target_path] = (sub_defs, sub_claims, all_valid)
        for d in sub_defs:
            if d not in shared_defs:
                shared_defs.append(d)
        for c in sub_claims:
            if c not in verified_claims:
                verified_claims.append(c)

        status = StepStatus.VALID if all_valid else StepStatus.WARNING
        msg = f"Imported '{stmt.path}' ({len(sub_claims)} theorems, {len(sub_defs)} definitions)"
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=msg,
            backend="Library",
        )

    def _validate_justification(
        self,
        justification: Optional[str],
        ctx: ProofContext,
    ) -> tuple[bool, Optional[str]]:
        if not justification or not justification.strip():
            return True, None

        raw = justification.strip().strip("[]\"'")
        if raw.lower().startswith("by "):
            raw = raw[3:].strip()
        elif raw.lower().startswith("using "):
            raw = raw[6:].strip()

        standard_keywords = {
            "algebra", "arithmetic", "ring", "field", "sympy",
            "z3", "smt", "logic", "definition", "def",
            "hypothesis", "hypotheses", "assumption", "assumptions",
            "axiom", "axioms", "tautology", "refl", "reflexivity",
            "transitivity", "symmetry", "induction", "base case",
            "inductive step", "contradiction", "cases", "exhaustiveness",
        }

        def norm(s: str) -> str:
            return s.strip("\"'").lower().replace(" ", "").replace("_", "")

        active_labels = [h.label for h in ctx.all_hypotheses() if h.label]
        norm_labels = {norm(lbl) for lbl in active_labels}
        active_vars = {norm(v) for v in ctx.all_variables()}
        active_funcs = {norm(fn) for fn in ctx.all_functions()}

        parts = re.split(r"[,;]|\band\b", raw)
        for part in parts:
            tok = part.strip().strip("\"'")
            if not tok or tok.lower() in ("by", "using", "from", "&"):
                continue
            if tok.lower() in standard_keywords:
                continue

            n_tok = norm(tok)
            if n_tok in norm_labels or n_tok in active_vars or n_tok in active_funcs:
                continue

            if any(n_tok == nl or n_tok in nl for nl in norm_labels):
                continue

            return False, f"Unknown or out-of-scope justification: '{tok}'"

        return True, None

    def check_theorem(
        self,
        thm: TheoremNode,
        shared_defs: Optional[list[FuncDefNode]] = None,
        verified_claims: Optional[list[tuple[Optional[str], ExprNode]]] = None,
    ) -> ProofReport:
        ctx = ProofContext()
        if shared_defs:
            for fn_def in shared_defs:
                try:
                    ctx.declare_function(fn_def.name, fn_def.params, fn_def.body)
                except VariableCaptureError:
                    pass
        if verified_claims:
            for name, claim in verified_claims:
                ctx.add_hypothesis(claim, label=name, is_assumption=False)

        results: list[StepResult] = []
        if thm.proof is not None:
            for stmt in thm.proof.statements:
                results.append(self._check_statement(stmt, ctx))
        if thm.claim is not None:
            results.append(self._verify_qed_claim(thm.claim, results, ctx))
        return ProofReport(theorem_name=thm.name, results=results)

    # -------------------------------------------------------------------
    # Internal statement dispatch
    # -------------------------------------------------------------------

    @staticmethod
    def _defines_declared_function(prop: ExprNode, ctx: ProofContext) -> bool:
        """Whether *prop* only says something about functions the proof declared.

        ``u(1) = 2`` and ``forall n : Nat, u(n + 1) = 2 * u(n) - 1`` about a
        ``Given u : Nat -> Int`` define u: they mention it and no other free
        variable.  ``u(k) = 5`` (about some k) or ``x > 0`` does not.
        """
        functions = {name for name, v in ctx.all_variables().items() if v.signature is not None}
        if not functions:
            return False
        calls: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, FunctionCallNode):
                calls.append(node.func)
            if isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)
            elif hasattr(node, "__dataclass_fields__"):
                for name in node.__dataclass_fields__:
                    if name not in ("line", "col"):
                        walk(getattr(node, name))

        walk(prop)
        mentions = [c for c in calls if c in functions]
        return bool(mentions) and not (collect_free_symbols(prop) - functions)

    @staticmethod
    def _contradictory(definitions: list, ctx: ProofContext) -> bool:
        """Whether the definitions alone entail a contradiction (``u(1) = 1`` and ``u(1) = 2``)."""
        check = ProofContext()
        for vinfo in ctx.all_variables().values():
            if not vinfo.is_witness:
                check.declare_variable(vinfo.name, vinfo.type_label if vinfo.signature else vinfo.math_type)
        for h in definitions:
            check.add_hypothesis(h.proposition, is_assumption=True)
        return verify_entailment(SymbolNode(name="false"), check).valid

    def _snapshot(self, ctx: ProofContext) -> tuple[dict[str, str], list[str]]:
        vars_snap = {k: v.type_label for k, v in ctx.all_variables().items()}
        hyps_snap = [
            f"def {fn.name}({', '.join(fn.params)}) = {fn.body}"
            for fn in ctx.all_functions().values()
        ] + [
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
            for ob in extract_domain_obligations(ex, line=line, ctx=ctx):
                ctx.obligations.append(ob)
                d_res = check_domain_obligation(ob, ctx)
                # `sqrt(x) + sqrt(x) = 2 * sqrt(x)` extracts the same obligation
                # once per occurrence, which reported the identical warning three
                # times over; each distinct one is worth saying only once.
                if not d_res.valid and d_res.message not in warnings:
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
        justification = getattr(stmt, "justification", None)
        if justification and self._citations is not None:
            result = self._check_citing(stmt, justification, ctx)
        else:
            result = self._dispatch(stmt, ctx)
        if result.status != StepStatus.VALID and not result.hints:
            try:
                result.hints = hints_for(result, stmt, ctx, self._lines, lambda rel: verify_entailment(rel, ctx).valid)
            except Exception:  # noqa: BLE001 - a hint must never cost the verdict
                result.hints = []
        return result

    def _check_citing(self, stmt: StatementNode, justification: str, ctx: ProofContext) -> StepResult:
        """A step that cites results: resolve each, use them for this step only."""
        index = self._citations
        cited: list[tuple[str, Target, list[tuple[Optional[str], ExprNode]]]] = []
        cited_defs: list[FuncDefNode] = []
        rest: list[str] = []
        for part in split_parts(justification):
            targets = index.lookup(part)
            if not targets:
                if looks_like_a_result(part) and not self._is_label_or_keyword(part, ctx):
                    return self._citation_failure(stmt, ctx, unknown_message(part, index))
                rest.append(part)
                continue
            if len(targets) > 1:
                return self._citation_failure(stmt, ctx, ambiguous_message(part, targets))
            claims, problem, defs = self._cited_claims(targets[0])
            if problem:
                return self._citation_failure(stmt, ctx, problem)
            cited.append((part, targets[0], claims))
            cited_defs.extend(defs)

        if not cited:
            return self._dispatch(stmt, ctx)
        # Known by the name it was cited as, so the step, its message and the
        # hypotheses all call the result the same thing.
        added = [ctx.add_hypothesis(claim, label=target.label, is_assumption=False) for _, target, claims in cited for _, claim in claims]
        # The definitions the cited result is stated in come with it, for this
        # step, unless the proof already has its own of that name.
        lent = [
            ctx.declare_function(d.name, d.params, d.body).name
            for d in cited_defs
            if ctx.get_function(d.name) is None and ctx.get_var(d.name) is None
        ]
        try:
            stripped = replace(stmt, justification=", ".join(rest) or None)
            result = self._dispatch(stripped, ctx)
        finally:
            for frame in ctx._frames:
                frame.hypotheses[:] = [h for h in frame.hypotheses if not any(h is a for a in added)]
            for name in lent:
                ctx.current_frame.functions.pop(name, None)
        part, target, claims = cited[0]
        statement_text = "; ".join(str(claim) for _, claim in claims)
        if result.status == StepStatus.INVALID:
            message = f"{result.message} (The cited result says {statement_text}.)"
        else:
            message = f"{result.message.rstrip('.')}, by {target.label}."
        return replace(
            result,
            statement=stmt,
            message=message,
            citation={"cited": part, "label": target.label, "key": target.key, "claim": statement_text},
        )

    def _is_label_or_keyword(self, part: str, ctx: ProofContext) -> bool:
        valid, _ = self._validate_justification(part, ctx)
        return valid

    def _cited_claims(
        self, target: Target
    ) -> tuple[list[tuple[Optional[str], ExprNode]], Optional[str], list[FuncDefNode]]:
        """The proved claims of a cited source and the definitions they use, or why it cannot be used."""
        defs: list[FuncDefNode] = []
        claims: list[tuple[Optional[str], ExprNode]] = []
        root = self._virtual_path("__main__.aether")
        result = self._process_import(ImportNode(path=target.key), root, [root], defs, claims)
        if result.status == StepStatus.INVALID:
            return [], f"'{target.label}' cannot be used: {result.message}", []
        if not claims:
            return [], f"'{target.label}' does not state a proved result to use (it has no theorem with a claim).", []
        return claims, None, defs

    def _citation_failure(self, stmt: StatementNode, ctx: ProofContext, message: str) -> StepResult:
        vars_snap, hyps_snap = self._snapshot(ctx)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=StepStatus.INVALID,
            message=message,
            backend="Citation",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
        )

    def _dispatch(self, stmt: StatementNode, ctx: ProofContext) -> StepResult:
        if isinstance(stmt, ImportNode):
            return self._process_import(stmt, None, [], [], [])
        if isinstance(stmt, VarDeclNode):
            return self._check_var_decl(stmt, ctx)
        if isinstance(stmt, FuncDefNode):
            return self._check_func_def(stmt, ctx)
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

    def _is_int_expr(self, expr: ExprNode, ctx: ProofContext) -> bool:
        from aether.core.ast import NumberNode
        if isinstance(expr, NumberNode):
            return "." not in expr.value
        if isinstance(expr, (SymbolNode, GreekSymbolNode)):
            vinfo = ctx.get_var(expr.name)
            return vinfo is not None and vinfo.math_type.value in ("Int", "Nat")
        if isinstance(expr, UnaryOpNode):
            return expr.op in ("+", "-") and self._is_int_expr(expr.operand, ctx)
        if isinstance(expr, BinaryOpNode):
            return (
                expr.op in ("+", "-", "*", "^", "**")
                and self._is_int_expr(expr.left, ctx)
                and self._is_int_expr(expr.right, ctx)
            )
        return False

    def _check_var_decl(self, stmt: VarDeclNode, ctx: ProofContext) -> StepResult:
        domain_warnings = self._check_domains_for_exprs([stmt.condition], stmt.line, ctx)
        effective_type = stmt.type_name
        if (
            stmt.type_name == "Real"
            and len(stmt.variables) == 1
            and isinstance(stmt.condition, RelationNode)
            and canonical_rel(stmt.condition.op) == "="
            and isinstance(stmt.condition.left, (SymbolNode, GreekSymbolNode))
            and stmt.condition.left.name == stmt.variables[0]
            and self._is_int_expr(stmt.condition.right, ctx)
        ):
            effective_type = "Int"

        try:
            for v in stmt.variables:
                ctx.declare_variable(v, effective_type, is_witness=False, condition=stmt.condition)
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
            message=f"Declared {', '.join(stmt.variables)} : {effective_type}.",
            backend="Context",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            domain_warnings=domain_warnings,
        )

    def _check_func_def(self, stmt: FuncDefNode, ctx: ProofContext) -> StepResult:
        try:
            ctx.declare_function(stmt.name, stmt.params, stmt.body)
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

        vars_snap, hyps_snap = self._snapshot(ctx)
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=StepStatus.VALID,
            message=f"Defined function {stmt.name}({', '.join(stmt.params)}) = {stmt.body}.",
            backend="Context",
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
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

        if stmt.justification:
            valid, err_msg = self._validate_justification(stmt.justification, ctx)
            if not valid:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=err_msg or "Invalid justification.",
                    backend="ScopeGuard",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

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
                if stmt.justification and not domain_warnings:
                    msg = f"{msg} [justified by {stmt.justification}]"
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

            # If user explicitly requested algebraic verification and it failed, do not fall back to SMT
            # (nor when the algebra itself settled the question).
            if alg_res.decisive or (stmt.justification and any(
                k in stmt.justification.lower() for k in ("algebra", "arithmetic", "ring", "field")
            )):
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=(
                        alg_res.message
                        if alg_res.decisive
                        else f"Algebraic verification failed for step [by {stmt.justification}]: {alg_res.message}"
                    ),
                    backend="SymPy",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                    counterexample=alg_res.counterexample,
                    counterexample_dict=alg_res.counterexample_dict,
                )

            # Fallback to Z3 in case equality depends on logical/modular hypotheses
            rel_node = RelationNode(op="=", left=eff_lhs, right=eff_rhs)
            z3_res = verify_entailment(rel_node, ctx)
            if z3_res.valid:
                ctx.commit_step(next_chain)
                status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
                msg = z3_res.message if not domain_warnings else domain_warnings[0]
                if stmt.justification and not domain_warnings:
                    msg = f"{msg} [justified by {stmt.justification}]"
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
                counterexample_dict=alg_res.counterexample_dict or z3_res.counterexample_dict,
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
                if stmt.justification and not domain_warnings:
                    msg = f"{msg} [justified by {stmt.justification}]"
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
                counterexample_dict=z3_res.counterexample_dict,
            )

        # Case 3: Bare expression / proposition step
        z3_res = verify_entailment(eff_rhs, ctx)
        if z3_res.valid:
            ctx.add_hypothesis(eff_rhs, label=None, is_assumption=False)
            status = self._apply_domain_status(StepStatus.VALID, domain_warnings)
            msg = z3_res.message if not domain_warnings else domain_warnings[0]
            if stmt.justification and not domain_warnings:
                msg = f"{msg} [justified by {stmt.justification}]"
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
            counterexample_dict=z3_res.counterexample_dict,
        )

    def _check_premise(self, stmt: DeduceNode, ctx: ProofContext) -> Optional[StepResult]:
        """`Since A, B`: A must already hold.  A label (`Since h1, …`) is a
        justification; anything else is checked as a step of its own, which on
        success also makes it a fact B can use.  Returns the failure, or None."""
        premise = stmt.premise
        if isinstance(premise, SymbolNode) and ctx.get_hypothesis(premise.name) is not None:
            return None
        check = self._check_deduce(DeduceNode(claim=premise, line=stmt.line, col=stmt.col), ctx)
        if check.status == StepStatus.INVALID:
            return replace(
                check,
                statement=stmt,
                message=f"The premise does not hold here, so it cannot be used: {check.message}",
            )
        return None

    def _check_deduce(self, stmt: DeduceNode, ctx: ProofContext) -> StepResult:
        if stmt.premise is not None:
            premise_failed = self._check_premise(stmt, ctx)
            if premise_failed is not None:
                return premise_failed
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

        if stmt.justification:
            valid, err_msg = self._validate_justification(stmt.justification, ctx)
            if not valid:
                vars_snap, hyps_snap = self._snapshot(ctx)
                return StepResult(
                    statement=stmt,
                    line=stmt.line,
                    status=StepStatus.INVALID,
                    message=err_msg or "Invalid justification.",
                    backend="ScopeGuard",
                    scope_depth=ctx.scope_depth,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                    domain_warnings=domain_warnings,
                )

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
                if stmt.justification and not domain_warnings:
                    msg = f"{msg} [justified by {stmt.justification}]"
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
            if stmt.justification and not domain_warnings:
                msg = f"{msg} [justified by {stmt.justification}]"
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
            counterexample_dict=log_res.counterexample_dict,
        )

    def _check_subproof(self, stmt: SubProofNode, ctx: ProofContext) -> StepResult:
        ctx.push_scope()
        sub_results: list[StepResult] = []
        first_assumption: Optional[ExprNode] = None
        last_conclusion: Optional[ExprNode] = None
        local_givens: list[tuple[str, str]] = []
        base_var_val: Optional[tuple[str, ExprNode]] = None

        if stmt.case_condition is not None:
            if (
                stmt.label == "Base case"
                and isinstance(stmt.case_condition, RelationNode)
                and canonical_rel(stmt.case_condition.op) == "="
                and isinstance(stmt.case_condition.left, (SymbolNode, GreekSymbolNode))
            ):
                bvar = stmt.case_condition.left.name
                bval = stmt.case_condition.right
                base_var_val = (bvar, bval)
                if ctx.get_var(bvar) is None:
                    ctx.declare_variable(bvar, "Nat", is_witness=False, condition=stmt.case_condition)
                else:
                    ctx.add_hypothesis(stmt.case_condition, label=None, is_assumption=True)
            else:
                ctx.add_hypothesis(stmt.case_condition, label=None, is_assumption=True)
            first_assumption = stmt.case_condition

        # An inductive step's facts are all its assumptions together: the
        # hypothesis and any side condition (`Assume hk: k >= 5`, or `Given k :
        # Nat where k >= 5`), in whatever order the student wrote them.  Every
        # other block keeps exporting its first assumption only.
        inductive = stmt.label == "Inductive step"
        step_assumptions: list[ExprNode] = []
        for inner in stmt.statements:
            if isinstance(inner, VarDeclNode) and (inner.condition is None or inductive):
                for vname in inner.variables:
                    local_givens.append((vname, inner.type_name or "Real"))
                if inductive and inner.condition is not None:
                    step_assumptions.append(inner.condition)
            if isinstance(inner, AssumeNode):
                if first_assumption is None:
                    first_assumption = inner.proposition
                step_assumptions.append(inner.proposition)
            res = self._check_statement(inner, ctx)
            sub_results.append(res)
            if res.status != StepStatus.INVALID:
                if isinstance(inner, DeduceNode):
                    last_conclusion = inner.claim
                elif isinstance(inner, StepNode) and ctx.chain is not None:
                    last_conclusion = RelationNode(
                        op=ctx.chain.effective_relation,
                        left=ctx.chain.head_lhs,
                        right=ctx.chain.current_rhs,
                    )

        ctx.pop_scope()

        all_ok = all(r.status != StepStatus.INVALID for r in sub_results)
        backend = "SubProof"
        detail_msg = f"Subproof ({len(sub_results)} steps) {'verified' if all_ok else 'failed'}."

        if all_ok and stmt.label == "Base case" and last_conclusion is not None:
            base_fact = last_conclusion
            if base_var_val is not None:
                base_fact = substitute_expr(base_fact, base_var_val[0], base_var_val[1])
            ctx.add_hypothesis(base_fact, label=None, is_assumption=False)
            backend = "Induction (Base)"
            detail_msg = f"Base case verified ({len(sub_results)} steps): establishes '{base_fact}'."
        elif all_ok and first_assumption is not None and last_conclusion is not None:
            # Proof by Contradiction (RAA): Assumed A and derived Contradiction -> export ~A (or P if A was ~P)
            if is_contradiction_symbol(last_conclusion):
                if isinstance(first_assumption, UnaryOpNode) and first_assumption.op == "not":
                    discharged_fact = first_assumption.operand
                else:
                    discharged_fact = UnaryOpNode(op="not", operand=first_assumption)
                ctx.add_hypothesis(discharged_fact, label=None, is_assumption=False)
                backend = "Contradiction"
                detail_msg = (
                    f"Proof by contradiction verified ({len(sub_results)} steps): "
                    f"discharged '{first_assumption}' to conclude '{discharged_fact}'."
                )
            else:
                premise = first_assumption
                if inductive and len(step_assumptions) > 1:
                    premise = step_assumptions[0]
                    for extra in step_assumptions[1:]:
                        premise = BinaryOpNode(op="and", left=premise, right=extra)
                exported: ExprNode = BinaryOpNode(op="=>", left=premise, right=last_conclusion)
                if stmt.case_condition is None and local_givens:
                    for gv_name, gv_type in reversed(local_givens):
                        exported = QuantifierNode(
                            quantifier="forall",
                            var=gv_name,
                            var_type=gv_type,
                            formula=exported,
                        )
                ctx.add_hypothesis(exported, label=None, is_assumption=False)

                if stmt.label == "Inductive step":
                    backend = "Induction (Step)"
                    detail_msg = f"Inductive step verified ({len(sub_results)} steps): establishes '{exported}'."
                elif stmt.case_condition is not None:
                    backend = "CaseSplit"
                    ctx.current_frame.cases.append((stmt.case_condition, last_conclusion))
                    detail_msg = f"Case '{stmt.case_condition}' verified ({len(sub_results)} steps): establishes '{last_conclusion}'."

                    # Check if accumulated cases in this scope are now exhaustive
                    if len(ctx.current_frame.cases) >= 2:
                        conds = [c for c, _ in ctx.current_frame.cases]
                        ex_res = verify_case_exhaustiveness(conds, ctx)
                        if ex_res.valid:
                            # Add the exhaustive disjunction C_1 or C_2 or ... to ctx
                            disj = conds[0]
                            for c in conds[1:]:
                                disj = BinaryOpNode(op="or", left=disj, right=c)
                            ctx.add_hypothesis(disj, label=None, is_assumption=False)
                            # If all cases reached the same conclusion Q, also add Q directly
                            conclusions = [q for _, q in ctx.current_frame.cases]
                            if all(str(q) == str(conclusions[0]) for q in conclusions):
                                ctx.add_hypothesis(conclusions[0], label=None, is_assumption=False)
                            detail_msg += f" Cases ({' or '.join(str(c) for c in conds)}) are exhaustive!"

        if not all_ok:
            failed_msgs = [r.message for r in sub_results if r.status == StepStatus.INVALID]
            if failed_msgs:
                detail_msg = f"{detail_msg} First error: {failed_msgs[0]}"

        vars_snap, hyps_snap = self._snapshot(ctx)
        status = StepStatus.VALID if all_ok else StepStatus.INVALID
        failed_cex = next((r.counterexample for r in sub_results if r.counterexample), None)
        failed_cex_dict = next((r.counterexample_dict for r in sub_results if r.counterexample_dict), None)
        subproof_meta = {
            "kind": backend,
            "label": stmt.label or ("Case" if stmt.case_condition else "Subproof"),
            "case_condition": str(stmt.case_condition) if stmt.case_condition else None,
            "step_count": len(sub_results),
            "all_steps_valid": all_ok,
            "sub_results": [r.to_dict() for r in sub_results],
        }
        return StepResult(
            statement=stmt,
            line=stmt.line,
            status=status,
            message=detail_msg,
            backend=backend,
            scope_depth=ctx.scope_depth,
            active_variables=vars_snap,
            active_hypotheses=hyps_snap,
            counterexample=failed_cex,
            counterexample_dict=failed_cex_dict,
            subproof_metadata=subproof_meta,
            sub_results=sub_results,
        )

    def _verify_qed_claim(
        self,
        claim: ExprNode,
        prior_results: list[StepResult],
        ctx: ProofContext,
    ) -> StepResult:
        """Verify at QED that the theorem's declared ``Claim:`` has been established."""
        qed_node = QEDNode(claim=claim, line=getattr(claim, "line", None))
        vars_snap, hyps_snap = self._snapshot(ctx)

        if any(r.status == StepStatus.INVALID for r in prior_results):
            return StepResult(
                statement=qed_node,
                line=qed_node.line,
                status=StepStatus.INVALID,
                message=f"QED failed: cannot establish '{claim}' because earlier proof steps failed.",
                backend="QED",
                scope_depth=ctx.scope_depth,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
            )

        root_assumptions = [
            h for h in ctx.all_hypotheses() if h.is_assumption and h.scope_depth == 0
        ]

        # A sequence the question defines ("u_1 = 2, u_{n+1} = 2u_n - 1"):
        # assumptions about a function the proof declared, and nothing else, are
        # that function's definition, not hypotheses the claim must license.  The
        # theorem proved is "for u so defined, the claim", and the message says
        # so.  Definitions that contradict each other would make anything follow,
        # so they must be consistent.
        definitions = [h for h in root_assumptions if self._defines_declared_function(h.proposition, ctx)]
        root_assumptions = [h for h in root_assumptions if h not in definitions]
        where = ""
        if definitions:
            if self._contradictory(definitions, ctx):
                return StepResult(
                    statement=qed_node,
                    line=qed_node.line,
                    status=StepStatus.INVALID,
                    message=(
                        "QED failed: the definitions "
                        + ", ".join(f"'{h.proposition}'" for h in definitions)
                        + " contradict each other, so anything would follow from them."
                        + (
                            " A recurrence stated 'for all n : Nat' also applies at n = 0;"
                            " if the sequence starts at 1, state it as 'forall n : Nat, n >= 1 => …'."
                            if any(isinstance(h.proposition, QuantifierNode) for h in definitions)
                            else ""
                        )
                    ),
                    backend="QED",
                    scope_depth=0,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )
            where = " where " + " and ".join(str(h.proposition) for h in definitions)

        # If there are no undischarged root assumptions, check if the full quantified claim
        # is already established via Mathematical Induction or an explicit deduction.
        if not root_assumptions:
            ind_res = verify_induction_schema(claim, ctx)
            if ind_res is not None and ind_res.valid:
                return StepResult(
                    statement=qed_node,
                    line=qed_node.line,
                    status=StepStatus.VALID,
                    message=f"QED: Theorem claim '{claim}'{where} verified ({ind_res.message})",
                    backend="QED",
                    scope_depth=0,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )

        ctx.push_scope()
        try:
            target = claim
            licensed_antecedents: list[ExprNode] = []

            # Peel universal quantifiers (forall x : T, ...) and implications (P => Q)
            while True:
                if isinstance(target, QuantifierNode) and target.quantifier == "forall":
                    existing = ctx.get_var(target.var)
                    if existing is not None and existing.is_witness:
                        return StepResult(
                            statement=qed_node,
                            line=qed_node.line,
                            status=StepStatus.INVALID,
                            message=f"QED failed: bound variable '{target.var}' in claim was only obtained as an existential witness.",
                            backend="QED",
                            scope_depth=0,
                            active_variables=vars_snap,
                            active_hypotheses=hyps_snap,
                        )
                    if existing is None:
                        ctx.declare_variable(target.var, target.var_type or "Real", is_witness=False)
                    target = target.formula
                elif isinstance(target, BinaryOpNode) and target.op in ("=>", "->", "implies", "\\implies"):
                    licensed_antecedents.append(target.left)
                    target = target.right
                elif (
                    isinstance(target, FunctionCallNode)
                    and (fn := ctx.get_function(target.func)) is not None
                    and len(fn.params) == len(target.args)
                ):
                    # A defined claim (`Claim: Continuous(g, 2)`) is proved as its
                    # definition says: its ∀s and ⇒s license the proof's Given/Assume.
                    target = substitute_mapping(fn.body, dict(zip(fn.params, target.args)))
                else:
                    break

            # Check that any top-level Assume in the proof body is licensed by the claim's antecedents
            if root_assumptions:
                if not licensed_antecedents:
                    unlicensed = root_assumptions[0].proposition
                    return StepResult(
                        statement=qed_node,
                        line=qed_node.line,
                        status=StepStatus.INVALID,
                        message=(
                            f"QED failed: proof relies on undischarged assumption '{unlicensed}' "
                            f"not present in theorem claim '{claim}'."
                        ),
                        backend="QED",
                        scope_depth=0,
                        active_variables=vars_snap,
                        active_hypotheses=hyps_snap,
                    )
                # Verify that every root assumption is entailed by the claim's antecedents
                ant_ctx = ProofContext()
                for vinfo in ctx.all_variables().values():
                    if not vinfo.is_witness:
                        ant_ctx.declare_variable(
                            vinfo.name, vinfo.type_label if vinfo.signature else vinfo.math_type
                        )
                for ant in licensed_antecedents:
                    ant_ctx.add_hypothesis(ant, is_assumption=True)
                for h in root_assumptions:
                    check_ant = verify_entailment(h.proposition, ant_ctx)
                    if not check_ant.valid:
                        return StepResult(
                            statement=qed_node,
                            line=qed_node.line,
                            status=StepStatus.INVALID,
                            message=(
                                f"QED failed: proof assumes '{h.proposition}', which is not licensed "
                                f"by theorem claim '{claim}'."
                            ),
                            backend="QED",
                            scope_depth=0,
                            active_variables=vars_snap,
                            active_hypotheses=hyps_snap,
                        )

            for ant in licensed_antecedents:
                ctx.add_hypothesis(ant, is_assumption=False)

            # Check target via SymPy (if equality) or Z3/Logic
            if isinstance(target, RelationNode) and canonical_rel(target.op) == "=":
                alg_res = verify_algebraic_equality(target.left, target.right, ctx)
                if alg_res.valid:
                    return StepResult(
                        statement=qed_node,
                        line=qed_node.line,
                        status=StepStatus.VALID,
                        message=f"QED: Theorem claim '{claim}'{where} verified.",
                        backend="QED",
                        scope_depth=0,
                        active_variables=vars_snap,
                        active_hypotheses=hyps_snap,
                    )

            log_res = verify_entailment(target, ctx)
            if log_res.valid:
                return StepResult(
                    statement=qed_node,
                    line=qed_node.line,
                    status=StepStatus.VALID,
                    message=f"QED: Theorem claim '{claim}'{where} verified.",
                    backend="QED",
                    scope_depth=0,
                    active_variables=vars_snap,
                    active_hypotheses=hyps_snap,
                )

            return StepResult(
                statement=qed_node,
                line=qed_node.line,
                status=StepStatus.INVALID,
                message=f"QED failed: Theorem claim '{claim}' was not established by the proof. {log_res.message}",
                backend="QED",
                scope_depth=0,
                active_variables=vars_snap,
                active_hypotheses=hyps_snap,
                counterexample=log_res.counterexample,
            )
        finally:
            ctx.pop_scope()
