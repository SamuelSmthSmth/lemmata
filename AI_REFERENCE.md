# Lemmata System Architecture & AI Agent Reference Manual

This document is the comprehensive technical reference for AI assistants, autonomous coding agents, and compiler/tooling engineers working with the **Lemmata** Controlled Natural Language (CNL) mathematical proof-checking engine.

It covers the formal grammar, AST node specifications, scope management algorithms, CAS and SMT verification backends, guardrails, API schemas, and generation rules for synthetic proof authoring.

---

## 1. System Architecture Pipeline

The Lemmata verification engine operates as a sequential pipeline with no circular dependencies:

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

Lemmata uses Lark with a Python-style indentation tracking indenter (`AetherIndenter`).

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

### 5.2 Matrix Operations
Matrices are literal (`[[1, 2], [3, 4]]`) and compared elementwise, so an equality step passes when every entry matches (`_is_zero` recurses into `sp.MatrixBase`).
- `det(A)` / `determinant(A)` → `A.det()`
- `tr(A)` / `trace(A)` → `A.trace()`
- `transpose(A)` → `A.T`
- `dot(u, v)` → `u.dot(v)`
- `inverse(A)` / `inv(A)` → `A.inv()`, **for a square matrix only**. A non-square or non-matrix argument falls back to an uninterpreted `inv`, which is what the abstract-algebra templates rely on when they write `inv(a)` for a group element.

### 5.3 Pre-simplification Domain Extraction
`extract_domain_obligations(expr)` walks the un-simplified AST:
- $A / B \implies B \neq 0$
- $\sqrt{A} \implies A \ge 0$

- Inside `sum(k, lo, hi, body)`, an obligation that mentions the index is
  quantified over the range: `forall k : Int, lo <= k <= hi => B != 0`. So
  `sum(k, 1, oo, 1/k^2)` owes nothing, while `sum(k, -1, 1, 1/k)` is refused.
- An obligation between closed terms (`gcd(8, 2) != 0`) is evaluated by SymPy
  before the solver is asked (`_evaluate_constant_relation` in `logic`).

**Not extracted: $\ln(A) \implies A > 0$.** Positivity of a logarithm's argument is
not checked. This was forced while Z3 could not prove $e^x > 0$; it now can (see
§6.3), so the obligation could be added -- at the price of turning every `ln(x)`
without `x > 0` in scope into a warning. (Unresolved obligations are reported as
warnings, or as errors under `strict_domains=True`.)

### 5.4 Mathematical Constants
`pi` (and `\pi`) and `e` convert to `sp.pi` / `sp.E`, so `sin(\pi) = 0` is settled by SymPy rather than reported as `Counterexample at pi=3`. Both a `SymbolNode` named `pi`/`e` and the `GreekSymbolNode` for `\pi` are mapped; `i`/`I` → `sp.I` works the same way and predates this.

Two guards keep the names usable as variables, and both are needed:
- **Declared wins.** `ctx.get_var(name) is not None` leaves the name alone, so `Let pi : Real` restores the old behaviour.
- **A structure's names are reserved.** `ProofContext.structure_names()` collects the symbols an active `Group`/`AbelianGroup`/`Ring`/`Field`/`Subgroup`/`NormalSubgroup` assumption binds. Without it, `e` — the identity in `Assume Group(G, op, e, inv)`, which the templates and five tests rely on — would silently become 2.718 in every algebraic step.

In `logic`, the constants are real constants carrying true, if loose, bounds (`3.14159265 < pi < 3.14159266`, `2.718281828 < e < 2.718281829`) fed through `extra_constraints`. They are facts about the numbers, so adding them only narrows the models; without them `pi > 3` was answered by an arbitrary real.

### 5.5 Infinity, Limits and Case Splits
- `oo` (the grammar's `\infty`, `∞`, `infinity` all become `SymbolNode("oo")`)
  converts to `sp.oo` unless declared. An equation with an infinite side is not
  checked as `lhs - rhs == 0` (that is `oo - oo = nan`); the two sides must
  agree outright, so `a + oo = oo` holds and `oo - oo = 0` does not.
- `sp.limit` is wrapped: a two-sided limit whose sides differ (SymPy raises
  `ValueError`), an oscillating one (`AccumBounds`), `zoo`, or an unevaluated
  `Limit` becomes an `AlgebraConversionError` -- a refused step with the
  reason, never an exception out of `check_source`. A limit at `+-oo` takes no
  direction.
- `Piecewise` and `sign(...)` in a sum or limit result are resolved by
  `logic.refine_with_context`, which asks Z3 whether the proof's hypotheses
  entail a branch condition (`Abs(r) < 1`, `Ne(r, 1)`, `log(rho) < 0`). A
  branch is taken only when entailed, so an undecided split leaves the step
  unproved.

### 5.6 Group Elements and the Notes' Notation
- `Given a : G` resolves through `ProofContext.resolve_type`: a number type as
  before, or -- when `G` is a structure's carrier or a declared set -- the
  `Element` type with `VarInfo.carrier = "G"` and the fact `a in G`.
- `ProofContext.elaborate_group_notation` (applied by `expand_user_functions`,
  so every backend sees it) rewrites `a * b`, `a \cdot b`, `a \circ b` to the
  group's `op`, `a^-1` to `inv(a)`, literal powers to products, and `a^0` to the
  identity -- only for operands recognisably in a group, so real arithmetic is
  untouched.
- `_verify_group_identity` (algebra) checks an equation built only from one
  group's `op`/`inv`/identity as words over non-commuting SymPy symbols
  (commuting for `AbelianGroup`). Equal reduced words are equal in the free
  group, hence in every group. Different words are only a diagnosis -- unless
  every fact in scope is a structure assumption or carrier membership, in which
  case the free group is a counter-model and the result is `decisive`, which
  stops the slow non-commutative model search in Z3.

### 5.7 Unknown Calls and Wrong Arity Are Named
A `f(...)` name no backend interprets becomes an uninterpreted function, which used to surface as a maths error: `fact(5) = 120` reported only that `fact(5) - 120 != 0`. Both backends now append a diagnosis to a failure — a near miss is offered (`fact` → did you mean `factorial`?), and an unrelated name is reported as uninterpreted. The hints never change a verdict, they only explain a rejection; `unknown_call_hints(expr, ctx)` in `algebra` is the shared implementation, and user-declared functions (`Define`) are excluded.

A call whose *name* the backend knows but whose *argument list* it does not
(`det(A, A)`, `sum(k, 1, n)`, `integrate(x)`) is refused with the count, rather
than falling through to that same uninterpreted branch. Unchecked, `Abs(x, x)`
raised a TypeError that escaped `check_source` altogether — a 500 from the API —
while `log(x, 2)` silently became a base-2 logarithm, so `ln(x, 2)` quietly
stopped meaning the natural log. The counts live in `_SYMPY_FUNC_ARITY` (the
prelude group) and `_ALGEBRA_CALLS` (everything else) in `algebra`, and in
`_LOGIC_CALL_ARITY` in `logic`.

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
- `a = b (mod m)` is encoded as $\exists k \in \mathbb{Z}, a - b = m \cdot k$; in Z3 as `If(m == 0, a == b, (a - b) % m == 0)` -- Z3 leaves `x % 0` unconstrained, so the plain remainder made congruences modulo a symbolic `m` unprovable. `MultipleOf` and `Divides` get the same guard.
- With a symbolic modulus the question is non-linear, so the SymPy route rewrites the goal with the divisibility facts in scope (`_eliminate_divisibility_witnesses`: `i = k (mod n)` gives `i = k + n*t` for a fresh integer `t`) and checks that the difference over the modulus is an integer polynomial. A quotient that is `zoo` (modulus 0) is not.
- Proves modular addition, multiplication, and power identities via Z3 integer arithmetic.

### 6.3 What the Solver Cannot Decide
Z3 has no theory of `exp`, `log`, `sin`, `cos` or `tan`: `ast_to_z3` makes them
uninterpreted functions. Each application is given true facts about its range
(`_range_facts`: `-1 <= sin, cos <= 1`, `exp(t) > 0` and `exp(t) >= 1 + t`,
`log(t) <= t - 1` for `t > 0`, `cosh >= 1`, `-1 < tanh < 1`), which hold for every
argument and so cannot make a false claim provable -- `exp(x) > 0` and
`|x sin(1/x)| <= |x|` now go through. An inequality needing more than the range
is still `sat` in some model, and that model is *not* a counterexample; a failed
query whose claim mentions one of `_SYMPY_ONLY_CALLS` says so instead of
leaving that to be read as a maths error.

Comparisons with `+-oo` are decided outright (`-oo < a < oo` for any finite
`a`); any other use of `oo` raises `LogicConversionError`, since a real-valued
solver has no infinite element. Equalities about these functions never reach Z3 at all:
`verify_entailment` tries `verify_algebraic_equality` first, so
`sin(x)^2 + cos(x)^2 = 1` is settled by SymPy and does hold.

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

When generating synthetic Lemmata proof scripts, adhere to these rules:

1. **Calculus Notation:** Use `diff(y, x)` or `diff(y, x, order)` for derivatives. Use `integrate(f, x, a, b)` or `\int_{a}^{b} f dx` for integrals. Use `lim(f, x, a)` or `\lim_{x -> a} f` for limits.
2. **Algebraic Structures:** Declare groups with `Assume Group(G, op, e, inv)` and reference elements with `op(a, b)` and `inv(a)`.
3. **Modular Arithmetic:** Write either natural `a = b (mod m)` or LaTeX `a \equiv b \pmod{m}`.
4. **Step Justifications:** Prefer explicit justification annotations where helpful:
   - Algebraic rewrites: `Step: ... [by algebra]`
   - Definition applications: `Step: ... [by definition]`
   - Hypothesis applications: `Step: ... [using h1]`
5. **Multi-File Imports:** Place reusable lemmas in separate `.aether` files and import them using `import "filename.aether"` at the top of the file.
6. **Goal Matching:** Always ensure the final statement or deduction matches the theorem's declared `Claim:` before `QED`.
