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
3. AST Transformer (`AetherASTTransformer`)
      │  Transforms parse tree into typed immutable AST nodes (`DocumentNode`)
      ▼
4. Proof Orchestrator (`ProofChecker`)
      │
      ├──> Import & Library Resolver (`ProofChecker._process_import`)
      │      - Resolves relative file paths
      │      - Detects cyclic dependencies (`A -> B -> A`)
      │      - Caches parsed ASTs & verification results
      │      - Transitively registers imported functions & verified theorem claims
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
      ├──> Show your working (`aether.engine.working`, opt-in)
      │      - Warns on a valid step that skips a rule an exam wants shown
      │
      ├──> Hints & citations (`aether.engine.hints`, `aether.engine.citations`)
      │      - What to try for a failing step, with one-edit fixes
      │      - Results cited by name (`by Theorem 1.1`)
      │
      └──> SMT Solver (`Z3` Backend)
             - Inequalities, propositional logic, boolean connectives
             - Quantifiers (`exists`, `forall`) and witness validation
             - Prelude predicates (`Even`, `Odd`, `MultipleOf`, `Divides`, `Positive`, `Prime`, `Coprime`, `Rational`)
             - Symbolic powers and the residue decision for polynomial divisibility
             - Abstract algebra: Group axioms (identity, inverse, cancellation, shoes-and-socks), rings, fields
             - Subgroups and normal subgroup conjugation properties
             - Modular arithmetic & congruences (`a = b (mod m)`)
             - Domain obligation discharge via refutation (`UNSAT`)
             - Counterexample model extraction (`extract_z3_model_dict`)
             - Case split exhaustiveness verification
             - Induction schema: starting values, recurrences, sequence definitions
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

### 2.1 Grammar Rules (Summary)

`src/aether/parser/grammar.lark` is the authority; this is its shape, abridged. Lark runs LALR(1) with the **contextual** lexer, so a terminal like `QUANT_NAMES` is only offered where the parser can accept it.

```lark
start: (_NL | item)*
item: theorem_stmt | proof_stmt | line_stmt

theorem_stmt: THEOREM_KW (CNAME | STRING)? ":" (CNAME | STRING)? _NL claim_stmt? proof_stmt?
claim_stmt:   CLAIM_KW ":" expr _NL
proof_stmt:   PROOF_KW ":"? _NL _INDENT line_stmt+ _DEDENT (QED_KW _NL)?

line_stmt:  simple_stmt _NL | block_stmt
block_stmt: CASE_KW expr ":" block            -> case_block
          | BASE_CASE_KW expr? ":" block      -> base_case_block
          | IND_STEP_KW expr? ":" block       -> ind_step_block
          | CNAME ":" block                   -> named_block      // Subproof:, Claim 1:, …

simple_stmt: var_decl | assume_stmt | obtain_stmt | step_stmt | deduce_stmt
           | since_stmt | by_stmt | import_stmt | QED_KW

var_decl: VAR_INTRO var_list ":" decl_type (("with" | SUCH_THAT) expr)?             -> var_decl_typed
        | (VAR_INTRO | DEFINE_KW | DEFINITION_HEAD) CNAME "(" var_list ")" (REL_OP | IFF_OP) expr -> func_def
        | VAR_INTRO var_ident REL_OP arith_expr BE_GIVEN?                         -> var_decl_cond
decl_type: type_name | type_name ((IMPL_OP | TO_OP) type_name)+                     // Nat -> Int

assume_stmt: ASSUME_KW (CNAME ":")? expr
obtain_stmt: OBTAIN_KW var_ident ("," var_ident)* (":" type_name)? SUCH_THAT expr ("from" CNAME)?
step_stmt:   STEP_KW ":" REL_OP arith_expr justification?   -> step_chained
           | STEP_KW ":" expr justification?               -> step_single
deduce_stmt: DEDUCE_KW REL_OP arith_expr justification?     -> deduce_chained
           | DEDUCE_KW expr justification? witness_clause?  -> deduce_expr
since_stmt:  SINCE_KW expr "," expr justification? witness_clause?
by_stmt:     BY_KW CITE_TEXT "," expr witness_clause?
justification:  "[" JUST_TEXT "]" | ("using" | "by") JUST_TEXT
witness_clause: "[" "witness" ":" expr "]"

expr: quant_expr
quant_expr: QUANT var_ident (":" type_name)? "," quant_expr          // forall x : Real, …
          | QUANT QUANT_NAMES ":" type_name "," quant_expr           // forall a, b : Int, …
          | QUANT QUANT_NAMES REL_OP arith_expr "," quant_expr       // ∀ a, b ∈ ℤ, … / ∀ ε, δ > 0, …
          | QUANT var_ident REL_OP arith_expr "," quant_expr         // ∀ ε > 0, … / ∃ x ∈ S, …
          | iff_expr
iff_expr: impl_expr (IFF_OP quant_expr)?
impl_expr: or_expr (IMPL_OP quant_expr)?
or_expr: and_expr (OR_OP and_expr)*
and_expr: not_expr (AND_OP not_expr)*
not_expr: NOT_OP not_expr | rel_expr
rel_expr: arith_expr REL_OP arith_expr mod_spec?                    // a = b (mod m)
        | arith_expr REL_OP arith_expr (REL_OP arith_expr)+          // -2 < k < 2: a conjunction
        | arith_expr
```

Keyword sets, each a terminal: `VAR_INTRO` (`Let`, `Given`, `Fix`, `Take`, and `Set` or `Put` before `name =`), `ASSUME_KW` (`Assume`, `Suppose`, `Hypothesize`), `OBTAIN_KW` (`Obtain`, `Choose`, `Pick`), `DEDUCE_KW` (`Therefore`, `Thus`, `Hence`, `So`, `Then`, `Conclude`, `It follows that`, `We have`, `We get`, `Note that`, …), `THEOREM_KW` (`Theorem`, `Lemma`, `Proposition`).

Desugaring done by the transformer (`aether.parser.transformer`), so the checker never sees the surface form:

- `Obtain p, q : Int such that …` becomes one `ObtainNode` per name.
- `forall a, b : Int, P` becomes `forall a : Int, forall b : Int, P`. A bound applies to each name: `∀ ε, δ > 0, P` is `∀ ε, ε > 0 ⇒ ∀ δ, δ > 0 ⇒ P`.
- `∀ ε > 0, P` is `∀ ε, ε > 0 ⇒ P`; `∃ δ > 0, P` is `∃ δ, δ > 0 ∧ P`; a membership bound that is a bare name (`∈ ℝ`, `in G`) becomes the variable's type.
- `-2 < k < 2` becomes `-2 < k and k < 2`.
- `Since A, B` is a `DeduceNode` with `premise=A`.
- Unicode (`∀ ∃ ∈ ≤ ≠ ⇒ ℝ ε x² a⁻¹ −`) is mapped to the ASCII forms.

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

Every AST node inherits from `ExprNode` or `StatementNode` and tracks `line: Optional[int]` and `col: Optional[int]`. `str(node)` gives the canonical readable form the audit shows.

### Expression Nodes (`ExprNode`)
- `SymbolNode(name: str)`: an identifier (`x`, `k`, `n`). `oo` is infinity.
- `GreekSymbolNode(name: str)`: a Greek letter, by its word (`epsilon`, from `\epsilon` or `ε`).
- `NumberNode(value: str)`: a numeric literal, kept as written (`"2"`, `"3.14"`).
- `BinaryOpNode(op: str, left, right)`: `+`, `-`, `*`, `/`, `^`, `and`, `or`, `=>`, `<=>`.
- `UnaryOpNode(op: str, operand)`: `-` or `not`.
- `FunctionCallNode(func: str, args: list[ExprNode])`: a user function, a built-in (`abs`, `sqrt`, `factorial`, `diff`, `integrate`, `lim`, `sum`, `det`, …) or a prelude predicate (`Even`, `Odd`, `MultipleOf`, `Divides`, `Positive`, `NonNegative`, `Prime`, `Coprime`, `Rational`, `Irrational`, `Congruent`, `Group`, `AbelianGroup`, `Ring`, `Field`, `Subgroup`, `NormalSubgroup`). Sums are `sum(k, lo, hi, body)` calls; `\sum_{k=a}^{b}` parses to the same.
- `IntegralNode(body, var: str, lower, upper)`: a definite or indefinite integral.
- `LimitNode(body, var: str, target, direction: str)`: `"+-"`, `"+"` or `"-"`.
- `RelationNode(op: str, left, right)`: `=`, `<`, `<=`, `>`, `>=`, `!=`, `in`, `notin`, `subset`, `mod`.
- `QuantifierNode(quantifier: str, var: str, var_type: Optional[str], formula)`: `exists` or `forall`, one variable each.
- `VectorNode(elements)`, `MatrixNode(rows)`: `[1, 2, 3]`, `[[1, 0], [0, 1]]`.
- `EmptySetNode()`, `StringLiteralNode(value: str)`, `RawMathNode(raw_text: str)` (`$ … $` the grammar keeps as written).

### Statement Nodes (`StatementNode`)
- `ImportNode(path: str)`: `import "lemmas"` (the `.aether` may be left off).
- `VarDeclNode(variables: list[str], type_name: str, condition: Optional[ExprNode])`: `type_name` may be a function type (`Nat -> Int`), which declares a sequence.
- `AssumeNode(label: Optional[str], proposition)`.
- `ObtainNode(variable: str, type_name: Optional[str], condition, source_label: Optional[str])`: one per witness.
- `StepNode(relation: str, lhs: Optional[ExprNode], rhs, justification: Optional[str])`: `lhs=None` chains from the previous step.
- `DeduceNode(claim, justification, witness, premise)`: `premise` is set by `Since …, …`.
- `SubProofNode(statements, case_condition: Optional[ExprNode], label: Optional[str])`: `label` is `"Case"`, `"Base case"`, `"Inductive step"`, or the block's own name (`Subproof:`); `case_condition` holds the case's condition, or the base case's `n = a`.
- `FuncDefNode(name: str, params: list[str], body)`: `Let f(x) = …` and `Define P(x) <=> …` alike.
- `QEDNode(claim: Optional[ExprNode])`.
- `ProofNode(statements)`, `TheoremNode(name, claim, proof)`, `DocumentNode(theorems, statements, imports)`.

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
- **Case Coverage:** a conclusion after `Case` blocks that do not cover every possibility is a WARNING (§6.6).
- **Induction:** a `forall` concluded after `Base case` / `Inductive step` is checked as an induction, or refused (§6.5).

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

### 5.8 Show Your Working (`aether.engine.working`)
`ProofChecker(show_working=True)` reviews each step that is already VALID. The review never refuses a step: the mathematics is right, so the verdict is a **WARNING** with backend `Working` and a message naming the rule ("Show your working: … The step itself is correct.").
- `working_gap(lhs, rhs, ctx)` looks at operators (`diff`, `integrate`, `lim`, `sum`) that are on the left and gone from the right. One rewritten into the same operator on its parts, like `diff(u*v, x) = diff(u, x)*v + u*diff(v, x)`, is the working itself and passes.
  - A derivative or integral needs a rule when the expression is a product, a quotient, or a composition with a non-linear inside. That means the product, quotient or chain rule, or integration by parts or substitution. Standard results with a linear inside (`sin(3x)`, `e^(2x)`) may be written down.
  - A sum to a symbolic bound in closed form needs induction or the method of differences.
  - A limit taken straight from an indeterminate form needs the algebra first.
- `ProofChecker._review_shortcut`: a conclusion settled by the residue decision (§6.4, backend `Residues`) asks for the cases instead. With the option on, the residue shortcut runs *after* Z3, so an argument the student did write is credited first.
- With the option off (the default), nothing changes. The flag is `show_working` on `/api/check`, and the app's **Show working** switch; the CLI has no flag for it.

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

### 6.4 Number Theory: Primes, Rationals, Powers and Remainders
- **Prelude predicates** are expanded by `expand_prelude_predicate` before Z3 sees them. `Even`/`Odd`/`MultipleOf`/`Divides` become `z3.IsInt(a / b)` (guarded for `b = 0`), not an existential witness, so a divisibility fact is usable without `Obtain`.
  - `Prime(p)` is `p > 1` with no `d` such that `1 < d < p` divides `p`. For a number this is decided outright (`Prime(41)`, `not Prime(1681)`).
  - `Coprime(a, b)`: every common divisor is ±1.
  - `Rational(x)`: `∃ p, q ∈ ℤ, q > 0 ∧ Coprime(p, q) ∧ x = p/q`, lowest terms, which is the form the √2 contradiction argues against.
  - `Irrational(x)` is `not Rational(x)`.
- **Symbolic powers** (`_symbolic_power`): `b^k` with a symbolic whole-number exponent becomes one real constant per `(base, exponent)` pair (`pow!b!k`, `_power_atom`). It carries guarded facts:
  - an integer base to a non-negative power is an integer;
  - `b^0 = 1`, `b^1 = b`, and `b ≥ 1 ⇒ b^k ≥ 1`;
  - `b^(k + c) = b^c · b^k` for a constant shift (|c| ≤ 6), which is the step an induction takes.

  Every fact is conditional on the exponent being non-negative, so `2^(k − 1)` at `k = 0` claims nothing.
- **Residue decision** (`_try_residue_divisibility`): "`m` divides `P(n)`", for an integer polynomial `P` and a number `m ≤ 1000`, is decided by checking every remainder of each variable. Fractional coefficients are handled as `Q/d` with period `m·d`, capped at 20 000 combinations.
  - True at every remainder: valid, whatever else is assumed.
  - False at some remainder: a counterexample, but only when no hypothesis mentions those variables, because an `Assume Even(n)` could rule the remainder out. Otherwise Z3 decides.
- **Opaque binding calls** (`_opaque_binding_call`): Z3 has no theory of a sum, definite integral or limit, so the call becomes an uninterpreted real function of the variables free in it, never of the variable it binds. It is named by the call's shape (`sum[sum(r, 1, _a0, r^2)]`), so `sum(r, 1, k, r^2)` and `sum(r, 1, n, r^2)` are one function at `k` and at `n`. That is what lets a fact about one be used for the other, and why a sum's own index is never offered as a counterexample.

### 6.5 Induction and Sequence Definitions
`verify_induction_schema(claim, ctx)` runs at a `forall` conclusion that follows `Base case` / `Inductive step` blocks. Its docstring is the full contract; in short:
- **Claims it reads:**
  - `forall n : Nat, P(n)`, from 0;
  - `forall n : Nat, n >= a => P(n)` (or `n > a`, `a <= n`), from `a`;
  - `forall n : Int, n >= a => P(n)`.
- **Base cases:** `P(a)`, `P(a + 1)`, … as the base-case blocks export them. An unguarded `Nat` claim with a base case above 0 must also establish each `P(j)` below it, or have it provable directly.
- **The step:** `forall k, H => P(k + d)` for `d ∈ {1, 2, 3}`. Each conjunct of `H` is one of `P(k)`, …, `P(k + d − 1)`, or a side condition that follows from `k >= a`. A recurrence using two earlier terms is `d = 2` and needs two base cases.
- **Refused:** an `Int` claim with no starting value, any claim over `Real`, a side condition stronger than `k >= a`, and a step that does not reach `P(k + d)` from what it assumed. The result is `None` when the proof is not an induction at all, so other routes still apply.

**Sequence definitions.** A top-level `Assume` about a function-typed variable the proof declared (`Given u : Nat -> Int`, then `Assume u1: u(1) = 2`, `Assume rec: forall n …`) is a definition, not a hypothesis. `ProofChecker._defines_declared_function` recognises it. The definitions are checked for consistency (if together they entail `false`, they are refused), and the QED message names them ("… where u(1) = 2 and …"), so a claim is never proved from an assumption the student did not mean to make.

### 6.6 Case Coverage
After a `Case` block, `ProofContext` frames carry `cases_exhaustive` and `cases_reviewed`. The first conclusion drawn after a run of cases asks `verify_case_exhaustiveness` whether the disjunction of the case conditions holds under the hypotheses in scope. If it doesn't, that conclusion is a **WARNING**, even when it is true by another route: the message names the cases and a value in none of them (`n=3`). Later conclusions in the same frame are not re-warned.

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

FastAPI, served by `uv run python -m ui`. Each check runs in a worker process under a wall-clock budget; one that overruns answers with verdict `TIMEOUT` instead of hanging. The static build (`ui/build_static.py`) runs the same engine in the browser through Pyodide and answers the same shapes without a server. `ui/README.md` documents both in full.

### Endpoints
- `GET /`: the app.
- `GET /api/site`: the product name and links from `ui/site.json`.
- `GET /api/health`: `{"status": "ok"}`.
- `GET /api/examples`: the bundled examples, each with the verdict it must produce.
- `GET /api/library`: the bundled course packs (pack format 1, see `aether.packs`).
- `POST /api/packs/validate`: validates a pack someone wants to install.
- `GET /api/capabilities`: the capability matrix (`ui/verify_capabilities.py` pins).
- `POST /api/check`: checks a proof.
- `POST /api/export/latex`, `POST /api/export/pdf`, `POST /api/export/lean`: exports.

### `POST /api/check`
```json
// Request: every field but source is optional
{
  "source": "Let x : Real\nAssume h: x > 2\nStep: (x^2 - 4) / (x - 2) = x + 2\n",
  "strict_domains": false,
  "show_working": false,
  "files": {"lemmas.aether": "…"},       // the workspace, for `import`
  "path": "main.aether",                 // this file's path, for relative imports
  "citations": {"Theorem 1.1": [["MTH2008 Theorem 1.1 · …", "@core/mth2008/1-1.aether"]]}
}

// Response
{
  "verdict": "VALID",                    // VALID | VALID (with domain warnings) | INVALID | PARSE ERROR | TIMEOUT
  "reports": [{"theorem_name": null, "is_valid": true, "has_warnings": false, "verdict": "VALID",
               "results": [{"line": 3, "statement": "…", "status": "VALID", "backend": "SymPy", "message": "…",
                            "counterexample": null, "domain_warnings": [], "hints": [], "citation": null,
                            "active_variables": {"x": "Real"}, "active_hypotheses": ["h: x > 2"], "scope_depth": 0}]}],
  "parse_error": null,                   // {message, headline, line, col} on a syntax error
  "summary": {"total": 3, "valid": 3, "warnings": 0, "invalid": 0},
  "strict_domains": false,
  "duration_ms": 41.2
}
```

### `POST /api/export/latex`
- **Request:** `{"source", "standalone": true, "strict_domains": false, "breakdown": true}`. `breakdown` appends the audit, the proof state and the source listing.
- **Response:** `{"latex": "…", "error": null}`.

### `POST /api/export/pdf`
- **Request:** as for LaTeX.
- **Response:** the PDF (`application/pdf`), compiled with `pdflatex` in a temporary directory.

### `POST /api/export/lean`
- **Request:** `{"source", "files", "path", "citations"}`, as for `/api/check`.
- **Response:** `{"lean", "rows", "untranslated", "error"}`. `lean` is the Lean 4 + Mathlib skeleton, with each step a `sorry` and a suggested tactic. `rows` pairs each source line with the Lean it became. `untranslated` names what has no faithful Lean.

A step result also carries `source_line`, `counterexample_dict`, `diagnostic_range` (for the editor's underline) and `subproof_metadata`.

---

## 9. AI Proof Generation Rules & Best Practices

When generating Lemmata proofs, follow these rules. Check every proof you generate with `uv run lemmata file.aether`; a proof that only *looks* right is the failure this tool exists to catch.

1. **State the claim.** Give every theorem a `Claim:`. `QED` checks the conclusion against it, and the claim is exactly what an `import` or a citation lends to other proofs.
2. **Introduce, then assume.** Discharge `forall x : T, A => B` with `Given x : T`, then `Assume h: A`, then reach `B`. Use fresh names for `Obtain` witnesses; reusing a name in scope is refused.
3. **Proof methods:**
   - Cases: one `Case cond:` block per case, covering everything between them, with the conclusion drawn after the last block.
   - Contradiction: a `Subproof:` that assumes the negation and ends `Therefore Contradiction`, followed by the negation as a conclusion.
   - Induction: `Base case n = a:`, then `Inductive step:` with `Given k : Nat`, a side condition `k >= a` if the claim starts at `a`, and the hypothesis `Assume ih: P(k)`; then conclude the `forall`. Put the starting value in the claim as a guard (`n >= a => …`).
   - Sequences: declare them as functions (`Given u : Nat -> Int`), with their values and recurrence as top-level `Assume`s.
   - Counterexample: `Let n = 40`, then show that the claim fails at that value.
4. **Calculus notation:** `diff(y, x)` or `diff(y, x, order)` for derivatives; `integrate(f, x, a, b)` or `\int_{a}^{b} f dx` for integrals; `lim(f, x, a)` or `\lim_{x -> a} f` for limits; `sum(k, 1, n, f)` or `\sum_{k=1}^{n} f` for sums.
5. **Algebraic structures:** `Assume Group(G, op, e, inv)`, then `Given a, b : G`. Write `op(a, b)` and `inv(a)`, or the notes' `a * b` and `a^-1`, which are elaborated to the group's operation.
6. **Modular arithmetic:** `a = b (mod m)` or `a \equiv b \pmod{m}`.
7. **Guard domains.** Before dividing by `B` or taking `sqrt(A)`, have `B != 0` or `A >= 0` in scope, or the step warns (and fails under `strict_domains`).
8. **Justifications:** `[by algebra]`, `[by definition]`, `[using h1]`, or a named result (`by Theorem 1.1`). A label must be in scope.
9. **Imports:** put reusable lemmas in their own files and `import "lemmas"`. An imported theorem arrives with the hypotheses it was proved under.
10. **What isn't supported:** the capability matrix in `USER_GUIDE.md` §9 lists every known gap. Don't generate syntax it marks `PARSE_ERROR` (for example `//` comments, or `[reason: …]`).
