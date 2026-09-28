# Aether System Architecture & AI Agent Reference Manual

This document is the comprehensive technical reference for AI assistants, autonomous coding agents, and compiler/tooling engineers working with the **Aether** Controlled Natural Language (CNL) mathematical proof-checking engine.

It covers the formal grammar, AST node specifications, scope management algorithms, CAS and SMT verification backends, guardrails, API schemas, and generation rules for synthetic proof authoring.

---

## 1. System Architecture Pipeline

The Aether verification engine operates as a sequential pipeline with no circular dependencies:

```
Source Code (.aether or string)
      │
      ▼
1. Lexer & Indentation Preprocessor (`AetherIndenter`)
      │  Emits synthetic _INDENT, _DEDENT, and _NL tokens
      ▼
2. LALR(1) Parser (`grammar.lark` + Lark Parser)
      │  Constructs parse tree
      ▼
3. AST Transformer (`AetherTransformer`)
      │  Transforms parse tree into typed immutable AST nodes (`DocumentNode`)
      ▼
4. Proof Orchestrator (`ProofChecker`)
      │
      ├──> Import & Library Resolver (`ProofChecker._process_import`)
      │      - Resolves relative file paths
      │      - Detects cyclic dependencies (`A -> B -> A`)
      │      - Caches parsed ASTs & verification results
      │      - Transistively registers imported functions & verified theorem claims
      │
      ├──> Scope & Frame Manager (`ProofContext`)
      │      - Variable types & witness bindings
      │      - Active hypothesis stack
      │      - Deduction chain monotonicity tracking
      │      - Generalization legality guardrails
      │      - User function & predicate definitions
      │      - Inter-theorem lemma registry
      │      - Step justification validator (`_validate_justification`)
      │
      ├──> CAS Engine (`SymPy` Backend)
      │      - Pre-simplification domain obligation extraction
      │      - Equational rewrite verification (zero-testing `lhs - rhs`)
      │      - Symbolic calculus: derivatives (`diff`), integrals (`integrate`), limits (`lim`), series
      │      - ODE solution verification
      │      - Context equality substitution
      │      - Concrete numeric counterexample grid search
      │
      └──> SMT Solver (`Z3` Backend)
             - Inequalities, propositional logic, boolean connectives
             - Quantifiers (`exists`, `forall`) and witness validation
             - Prelude predicates (`Even`, `Odd`, `MultipleOf`, `Divides`, `Positive`)
             - Abstract algebra: Group axioms (identity, inverse, cancellation, shoes-and-socks), rings, fields
             - Subgroups and normal subgroup conjugation properties
             - Modular arithmetic & congruences (`a = b (mod m)`)
             - Domain obligation discharge via refutation (`UNSAT`)
             - Counterexample model extraction (`extract_z3_model_dict`)
             - Case split exhaustiveness verification
             - Peano Mathematical Induction schema checking
      │
      ▼
ProofReport / StepResult / REST API JSON
      │
      ├──> LaTeX Formatter (`aether.core.latex_export`)
      │      - Standalone or snippet LaTeX with align* environments
      │      - Aligned justifications and import comments
      │
      └──> PDF Compiler (`/usr/bin/pdflatex` via `ui.app`)
             - Isolated temporary build environment
             - Streams compiled PDF binary to HTTP clients
```

---

## 2. Formal Grammar Specification

Aether uses Lark with a Python-style indentation tracking indenter (`AetherIndenter`).

### 2.1 Grammar Rules (EBNF Summary)

```lark
start: _NL* (toplevel_item _NL*)*

toplevel_item: import_stmt
             | theorem
             | func_def
             | custom_predicate_def
             | statement

import_stmt: IMPORT_KW STRING

theorem: (THEOREM_KW | LEMMA_KW | PROP_KW) STRING _NL (CLAIM_KW rel_expr _NL)? proof

proof: PROOF_KW COLON _NL _INDENT statement+ _DEDENT QED_KW

func_def: LET_KW CNAME "(" param_list ")" "=" arith_expr
custom_predicate_def: DEFINE_KW CNAME "(" param_list ")" (IFF_OP | "=") expr

statement: var_decl
         | assume_stmt
         | obtain_stmt
         | step_stmt
         | deduce_stmt
         | subproof_stmt

var_decl: (LET_KW | GIVEN_KW | FIX_KW | TAKE_KW) var_list COLON TYPE_NAME (WHERE_KW rel_expr)?
        | LET_KW (CNAME | GREEK_SYM) "=" arith_expr

assume_stmt: (ASSUME_KW | SUPPOSE_KW | HYP_KW) (CNAME COLON)? expr
obtain_stmt: (OBTAIN_KW | CHOOSE_KW | PICK_KW) CNAME (COLON TYPE_NAME)? SUCH_THAT_KW expr (FROM_KW CNAME)?
step_stmt: STEP_KW COLON (arith_expr REL_OP)? arith_expr justification?
deduce_stmt: (THEREFORE_KW | THUS_KW | HENCE_KW | SO_KW | CONCLUDE_KW) expr (LBRACKET WITNESS_KW COLON arith_expr RBRACKET)? justification?

justification: LBRACKET (BY_KW | USING_KW)? JUST_TEXT RBRACKET
             | USING_KW JUST_TEXT

subproof_stmt: (SUBPROOF_KW COLON | CASE_KW expr COLON | BASE_CASE_KW (expr)? COLON | IND_STEP_KW COLON) _NL _INDENT statement+ _DEDENT
```

### 2.2 Operators and Precedence
From lowest to highest binding power:
1. `iff` / `<=>`
2. `implies` / `=>` / `->`
3. `or`
4. `and`
5. `not` / `~`
6. Relations (`=`, `<`, `<=`, `>`, `>=`, `!=`, `\equiv`, `mod`)
7. Summation (`sum(k, a, b, f)` / `\sum_{k=a}^b f`) & Integration (`\int_{a}^{b} f dx`) & Limits (`\lim_{x -> a} f`)
8. Addition & Subtraction (`+`, `-`)
9. Multiplication & Division (`*`, `/`)
10. Unary negation (`-x`)
11. Exponentiation (`^`, right-associative)
12. Primary (`(expr)`, `|expr|`, function call `f(x)`, variable, number, Greek letter)

---

## 3. AST Dataclass Node Taxonomy (`aether.core.ast`)

Every AST node inherits from `ExprNode` or `StatementNode` and tracks `line: Optional[int]` and `col: Optional[int]`:

### Expression Nodes (`ExprNode`)
- `SymbolNode(name: str)` — Identifier (`x`, `k`, `n`).
- `GreekSymbolNode(name: str)` — LaTeX Greek symbol (`epsilon`, `delta`, `alpha`, etc.).
- `NumberNode(value: str)` — Numeric constant (`"2"`, `"3.14"`).
- `BinaryOpNode(op: str, left: ExprNode, right: ExprNode)` — Operators: `+`, `-`, `*`, `/`, `^`, `and`, `or`, `=>`, `<=>`.
- `UnaryOpNode(op: str, operand: ExprNode)` — Unary negation (`-`) or logical negation (`not`).
- `FunctionCallNode(func: str, args: list[ExprNode])` — User function or built-in (`abs`, `min`, `max`, `sqrt`, `sum`, `diff`, `integrate`, `lim`, `Even`, `Odd`, `MultipleOf`, `Divides`, `Group`, `AbelianGroup`, `Ring`, `Field`, `Subgroup`, `NormalSubgroup`, `Congruent`).
- `IntegralNode(body: ExprNode, var: str, lower: Optional[ExprNode], upper: Optional[ExprNode])` — Definite or indefinite integral.
- `LimitNode(body: ExprNode, var: str, target: ExprNode, direction: str)` — Two-sided or directional limit.
- `RelationNode(op: str, left: ExprNode, right: ExprNode)` — Comparison predicate (`=`, `<`, `<=`, `>`, `>=`, `!=`, `mod`).
- `QuantifierNode(quantifier: str, var: str, var_type: Optional[str], formula: ExprNode)` — `exists` or `forall`.
- `SumNode(index_var: str, lower: ExprNode, upper: ExprNode, body: ExprNode)` — Summation node.
- `VectorNode(elements: list[ExprNode])` — Vector literal `[1, 2, 3]`.
- `MatrixNode(rows: list[list[ExprNode]])` — Matrix literal `[[1, 0], [0, 1]]`.

### Statement Nodes (`StatementNode`)
- `ImportNode(path: str)` — File import statement `import "path/to/file.aether"`.
- `VarDeclNode(variables: list[str], type_name: str, condition: Optional[ExprNode])`
- `AssumeNode(label: Optional[str], proposition: ExprNode)`
- `ObtainNode(variable: str, type_name: Optional[str], condition: ExprNode, source_label: Optional[str])`
- `StepNode(relation: str, lhs: Optional[ExprNode], rhs: ExprNode, justification: Optional[str])`
- `DeduceNode(claim: ExprNode, justification: Optional[str], witness: Optional[ExprNode])`
- `SubProofNode(statements: list[StatementNode], case_condition: Optional[ExprNode], label: Optional[str])`
- `FuncDefNode(name: str, params: list[str], body: ExprNode)`
- `CustomPredicateDefNode(name: str, params: list[str], body: ExprNode)`
- `QEDNode(claim: Optional[ExprNode])`
- `TheoremNode(name: Optional[str], claim: Optional[ExprNode], proof: Optional[ProofNode])`
- `DocumentNode(theorems: list[TheoremNode], statements: list[StatementNode], imports: list[ImportNode])`

---

## 4. Scope, Context & Library Management (`ProofContext` & `ProofChecker`)

### 4.1 Multi-File Import Resolution (`ProofChecker._process_import`)
When `import "relative/path.aether"` is encountered:
1. **Path Resolution:** Resolved relative to the current file's directory (or `base_dir` / CWD).
2. **Cycle Detection:** Maintains an active import stack (`_active_import_stack: set[Path]`). If an import loop is detected (e.g. `A -> B -> A`), a clear diagnostic `Import cycle detected` is raised.
3. **Caching:** Results are cached in `_import_cache: dict[Path, tuple[list[ProofReport], list[FuncDefNode], list[ExprNode]]]`.
4. **Transitive Export:** Successfully verified imports contribute:
   - All `FuncDefNode` definitions (recursively declared in the current `ProofContext`).
   - All verified theorem `Claim:` propositions (registered in the inter-theorem lemma registry).

### 4.2 Step Justification Validation (`ProofChecker._validate_justification`)
When a step includes `[by ...]` or `[using ...]`:
- **Allowed Keywords:** `algebra`, `definition`, `hypothesis`, `by definition`, `by algebra`, `by hypothesis`, etc.
- **Label Resolution:** Citations like `[using h1, lemma_name]` are verified against:
  - Active hypothesis labels in the current scope stack (`ctx.get_active_hypotheses()`).
  - Active variable names in scope.
  - Document and imported theorem/lemma names.
  - Defined function and predicate names.
- **Scope Guard:** Citing an undefined label raises `ScopeGuard` error.
- **Enforced Algebraic Checking:** When `[by algebra]` is specified, the CAS engine is enforced; if algebraic evaluation fails, the step reports failure without masking via SMT fallback.

### 4.3 Monotonicity, Capture & Generalization Guards
- **Strict Monotonicity:** Mixing directions ($\le$ and $\ge$) within an equational/inequality chain raises `MonotonicityError`.
- **Variable Capture:** Deducing with `Obtain k ...` when `k` is already in scope raises `VariableCaptureError`.
- **Universal Generalization:** Generalizing $\forall x, P(x)$ while $x$ appears free in undischarged hypotheses raises `GeneralizationError`.

---

## 5. Algebraic Backend (`aether.engine.algebra`)

Powered by SymPy (`import sympy as sp`).

### 5.1 Symbolic Calculus & ODE Handling
- **Derivatives:** Evaluated via `sp.diff(expr, var, order)`.
- **Integrals:** Evaluated via `sp.integrate(expr, var)` (indefinite) or `sp.integrate(expr, (var, lower, upper))` (definite).
- **Limits:** Evaluated via `sp.limit(expr, var, target, dir=...)`.
- **Series:** Taylor / Maclaurin expansions via `sp.series(expr, var, pt, n).removeO()`.
- **Differential Equations:** Given a declared function `y(t) = ...`, substitutions for `diff(y, t)` and `diff(y, t, 2)` into an ODE expression (e.g. `diff(y, t, 2) + w^2 * y = 0`) are evaluated by substituting the explicit function derivatives and testing $s_{\text{diff}} = 0$.

### 5.2 Pre-simplification Domain Extraction
`extract_domain_obligations(expr)` walks the un-simplified AST:
- $A / B \implies B \neq 0$
- $\sqrt{A} \implies A \ge 0$
- $\ln(A) \implies A > 0$

---

## 6. Logic & SMT Backend (`aether.engine.logic`)

Powered by Z3 (`import z3`).

### 6.1 Abstract Algebra Axiomatization
When `Assume Group(G, op, e, inv)` is in scope:
- **Axioms Grounded in SMT:**
  1. Identity: $\forall x \in G, \text{op}(x, e) = x \land \text{op}(e, x) = x$
  2. Inverses: $\forall x \in G, \text{op}(x, \text{inv}(x)) = e \land \text{op}(\text{inv}(x), x) = e$
  3. Associativity: $\forall x, y, z \in G, \text{op}(\text{op}(x, y), z) = \text{op}(x, \text{op}(y, z))$
  4. Cancellation: $\text{op}(a, x) = \text{op}(a, y) \implies x = y$
  5. Product Inverse (Shoes-and-Socks): $\text{inv}(\text{op}(a, b)) = \text{op}(\text{inv}(b), \text{inv}(a))$
- **Abelian Groups:** Adds commutativity $\text{op}(x, y) = \text{op}(y, x)$.
- **Subgroups:** Enforces closure, identity containment ($e \in H$), and normal subgroup conjugation ($g \cdot n \cdot g^{-1} \in N$).

### 6.2 Modular Arithmetic Axiomatization
- `a = b (mod m)` is encoded as $\exists k \in \mathbb{Z}, a - b = m \cdot k$ (or $m \mid (a - b)$ with $m \neq 0$).
- Proves modular addition, multiplication, and power identities via Z3 integer arithmetic.

---

## 7. LaTeX Export & PDF Compilation

### 7.1 LaTeX Formatter (`aether.core.latex_export`)
- Function: `export_to_latex(source: str, report: Optional[ProofReport] = None, standalone: bool = True) -> str`
- **Features:**
  - Emits `align*` mathematical step chains with proper `& =` and `&& \text{([by algebra])}` alignment.
  - Converts Greek symbols to LaTeX macro names (`\epsilon`, `\delta`).
  - Converts integrals, limits, and summations to standard LaTeX display notation (`\int_{a}^{b}`, `\lim_{x \to a}`, `\sum_{k=1}^n`).
  - Exports imports as descriptive LaTeX comments (`% import "..."`).
  - Supports standalone mode (with `\documentclass{article}`, `amsmath`, `amssymb`, `geometry`) or embeddable snippet mode.

### 7.2 PDF Compiler (`/usr/bin/pdflatex` via `ui.app`)
- In `POST /api/export/pdf`:
  - Runs in a clean `tempfile.TemporaryDirectory`.
  - Executes `pdflatex -interaction=nonstopmode document.tex`.
  - Captures errors and compiles to a valid PDF, returning `application/pdf` binary stream.

---

## 8. Web API Specification (`ui/app.py`)

### Endpoints
- `GET /` — Serves single-page web UI.
- `GET /api/health` — Health check endpoint (`{"status": "ok"}`).
- `GET /api/examples` — Returns list of bundled examples.
- `POST /api/check` — Runs proof verification on source text.
- `POST /api/export/latex` — Returns formatted LaTeX string.
- `POST /api/export/pdf` — Compiles and returns binary PDF file.

### `POST /api/export/latex` Request & Response
```json
// Request
{
  "source": "Theorem: \"Even\"\nProof:\n    Step: 2 * 2 = 4\nQED\n",
  "standalone": true
}

// Response
{
  "latex": "\\documentclass{article}\n\\usepackage{amsmath}\n...\n\\end{document}\n"
}
```

### `POST /api/export/pdf` Request & Response
- **Request:** JSON `{"source": "..."}`
- **Response:** Raw binary PDF stream (`Content-Type: application/pdf`).

---

## 9. AI Proof Generation Rules & Best Practices

When generating synthetic Aether proof scripts, adhere to these rules:

1. **Calculus Notation:** Use `diff(y, x)` or `diff(y, x, order)` for derivatives. Use `integrate(f, x, a, b)` or `\int_{a}^{b} f dx` for integrals. Use `lim(f, x, a)` or `\lim_{x -> a} f` for limits.
2. **Algebraic Structures:** Declare groups with `Assume Group(G, op, e, inv)` and reference elements with `op(a, b)` and `inv(a)`.
3. **Modular Arithmetic:** Write either natural `a = b (mod m)` or LaTeX `a \equiv b \pmod{m}`.
4. **Step Justifications:** Prefer explicit justification annotations where helpful:
   - Algebraic rewrites: `Step: ... [by algebra]`
   - Definition applications: `Step: ... [by definition]`
   - Hypothesis applications: `Step: ... [using h1]`
5. **Multi-File Imports:** Place reusable lemmas in separate `.aether` files and import them using `import "filename.aether"` at the top of the file.
6. **Goal Matching:** Always ensure the final statement or deduction matches the theorem's declared `Claim:` before `QED`.
