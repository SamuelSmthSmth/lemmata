# Aether Proof Author's Handbook & Cheat Sheet

Welcome to **Aether**, the lightweight, step-by-step mathematical proof intern designed for undergraduate pure mathematics (Real Analysis, Calculus & ODEs, Abstract Algebra, Number Theory, and Linear Algebra).

Instead of requiring you to learn arcane type theory or complex interactive theorem provers (like Lean 4 or Coq), Aether lets you write **Controlled Natural Language (CNL)** proofs using familiar English keywords (`Given`, `Assume`, `Obtain`, `Step:`, `Therefore`, `QED`) paired with standard mathematical notation.

---

## 1. Quick Start: The 30-Second Mental Model

Every Aether proof file contains either:
1. **A Formal Theorem:**
   ```text
   Theorem: "Title of Theorem"
   Claim: <what you promise to prove>
   Proof:
       <indented proof body>
   QED
   ```
2. **Or a Scratchpad Script** (no wrapper needed; statements at the top level are checked sequentially):
   ```text
   Let x : Real
   Assume h: x > 2
   Step: (x^2 - 4) / (x - 2) = x + 2
   Step: > 4
   ```

Indentation is Python-style (4 spaces per level). When you indent, you open a nested subproof or scope.

---

## 2. The Keyword Cheat Sheet (What to Memorize)

Here are the core keywords you will use:

| Keyword | Syntax Example | Meaning |
| :--- | :--- | :--- |
| `import` | `import "lemmas.aether"` | Imports definitions, functions, and proven theorem claims from another file. |
| `Theorem:` / `Lemma:` | `Theorem: "Even square"` | Declares a named theorem or lemma. |
| `Claim:` | `Claim: forall n : Int, Even(n) => Even(n^2)` | Declares the exact goal checked at `QED`. |
| `Proof:` | `Proof:` | Begins the indented proof block. |
| `Given` / `Let` / `Fix` | `Given n : Int`<br>`Let x, y : Real`<br>`Fix \epsilon : Real where \epsilon > 0`<br>`Let \delta = \epsilon / 3` | Introduces new variables, constraints, or variable definitions into scope. |
| `Assume` / `Suppose` | `Assume h1: Even(n)`<br>`Suppose x > 2`<br>`Assume Group(G, op, e, inv)` | Declares a local hypothesis, premise, or algebraic structure. Labels like `h1:` are optional. |
| `Obtain` | `Obtain k : Int such that n = 2 * k from h1` | Unpacks an existential fact or definition (extracts witness `k` from `Even(n)`). |
| `Step:` | `Step: n^2 = (2 * k)^2`<br>`Step: = 4 * k^2 [by algebra]`<br>`Step: < 8 * k^2 [using h1]` | Equational or inequality deduction. Leaving off the LHS chains from previous RHS. Optional `[by ...]` or `[using ...]`. |
| `Therefore` / `Hence` / `Thus` | `Therefore exists m : Int, n^2 = 4 * m [witness: k^2]`<br>`Hence MultipleOf(n^2, 4) [by definition]` | Deduces a new fact. Optional `[witness: ...]` for existential claims and `[by ...]` / `[using ...]`. |
| `Base case` / `Inductive step` | `Base case n = 0:`<br>`Inductive step:` | Opens mathematical induction subproofs. |
| `Case` | `Case x >= 0:`<br>`Case x < 0:` | Splits into exhaustive cases. |
| `Subproof:` | `Subproof:` | Opens a general nested subproof (e.g., for universal generalization or implication). |
| `Define` | `Define CongruentMod(a, b, m) <=> Divides(m, a - b)` | Defines a reusable custom predicate. |
| `QED` | `QED` | Finishes the proof and verifies that the theorem's `Claim:` has been achieved. |

---

## 3. Mathematical Notation & Expressions

### Supported Types
- `Nat` — Natural numbers ($\{0, 1, 2, \dots\}$)
- `Int` — Integers ($\{\dots, -1, 0, 1, \dots\}$)
- `Rat` — Rational numbers
- `Real` — Real numbers
- `Complex` — Complex numbers
- `Bool` — Booleans (`true`, `false`)
- The blackboard letters work too: `Let x : ℝ`, `Let n ∈ ℕ` (also `ℤ`, `ℚ`, `ℂ`).
- **A structure's carrier is a type.** After `Assume Group(G, op, e, inv)`, `Given a, b : G` (or `Let g ∈ G`) declares elements of `G`, and `forall x : G, ...` / `∀ x ∈ G, ...` quantify over it. `Subgroup(H, G, ...)` makes `H` a carrier as well. Any other unknown type name is still refused.

### Greek Letters & Variables
Type standard LaTeX Greek letters:
- `\epsilon`, `\delta`, `\alpha`, `\beta`, `\gamma`, `\theta`, `\lambda`, `\mu`, `\sigma`, `\phi`, `\omega`
- Or type the letter itself: `ε` is the same variable as `\epsilon`, `δ` as `\delta`.
- `\pi` is the number, not a free variable — see **Mathematical Constants** below.

### Mathematical Constants
- `pi` (or `\pi`) is $\pi$ and `e` is Euler's number, available without declaring them: `Step: sin(\pi) = 0` and `Step: ln(e) = 1` both check out.
- Declaring the name takes it back. After `Let pi : Real`, `pi` is your variable again — which is also how the algebra templates keep `e` for the group identity: an `Assume Group(G, op, e, inv)` binds that name.
- `oo` (also `\infty`, `∞`, `infinity`) is $\infty$, with the extended-real arithmetic of the notes: `a + oo = oo`, `a / oo = 0`, `-oo < a < oo` all check out, while the indeterminate `oo - oo` and `0 * oo` are refused. Comparisons against `±oo` are decided exactly; any other arithmetic with it must go through a limit or a sum first.
- Exact identities go to SymPy. The SMT backend carries only loose bounds, so `Step: pi > 3` is proved while `Step: pi > 3.5` is refused rather than mis-answered.

### Arithmetic & Standard Operations
- Operators: `+`, `-`, `*`, `/`, `^` (exponentiation: e.g. `x^2`, `3^(k + 1)`, `x^-1`)
- Factorial: `n!`, `(n - 1)!` or `factorial(n)`
- Square roots: `sqrt(x)` or `√x`
- More functions: `sinh`, `cosh`, `tanh`, `asin`/`arcsin`, `acos`, `atan`, `sec`, `csc`, `cot`, `floor`, `ceil`, `sign`, `binomial(n, k)`, and `gcd(a, b)` / `lcm(a, b)` — the last two are computed for numbers (`gcd(8, 6) = 2`) and left opaque for symbols, since `gcd(n, k)` has no closed form.
- Absolute Value: `|x - a|` or `abs(x - a)`
- Bounds: `min(a, b)`, `max(a, b)`
- Summations:
  - Functional form: `sum(k, 1, n, 2 * k - 1)` (index, lower, upper, summand)
  - LaTeX form: `\sum_{k=1}^{n} (2 * k - 1)`
  - Infinite series: `sum(k, 0, oo, r^k) = 1/(1 - r)` checks once `|r| < 1` is in scope. When SymPy's answer splits into cases (`r = 1` or not, `|r| < 1` or not), the proof's hypotheses pick the case; with nothing in scope to decide it, the step is refused.
  - A division in the summand is checked only over the index range: `sum(k, 1, oo, 1/k^2)` raises no warning about `k = 0`.

### Symbolic Calculus & ODEs
- **Derivatives:**
  - `diff(expr, var)` — First derivative (e.g. `diff(y, x)`)
  - `diff(expr, var, order)` — Higher-order derivative (e.g. `diff(y, t, 2)`)
  - Exponential & Trig: `exp(x)`, `sin(x)`, `cos(x)`, `tan(x)`, `ln(x)`
- **Integrals:**
  - Indefinite: `integrate(expr, var)` or `\int expr dx`
  - Definite: `integrate(expr, var, a, b)` or `\int_{a}^{b} expr dx`
- **Limits:**
  - Two-sided: `lim(expr, var, point)` or `\lim_{x -> a} expr`
  - Directional: `lim(expr, var, point, "+")` / `lim(expr, var, point, "-")` or `\lim_{x -> a^+} expr`
  - At infinity: `lim(1/x, x, oo) = 0`, `\lim_{x \to \infty} (1 - 1/x^2) = 1`; infinite limits: `lim(1/x, x, 0, "+") = oo`
  - A limit that does not exist is refused with the reason: `lim(x/|x|, x, 0)` (the one-sided limits differ), `lim(sin(1/x), x, 0)` (it oscillates), `lim(1/x, x, 0)` (it is `+oo` on one side and `-oo` on the other).
  - The LaTeX form takes one term after the subscript, so write `\lim_{x \to 2} (9 - x^2)` with parentheses; without them `- x^2` is outside the limit.
  - Hypotheses settle parameters: with `0 < \rho < 1` in scope, `lim(\rho^n, n, oo) = 0`.
- **Differential Equations:**
  - Declare function $y(t)$ and verify that derivative combinations satisfy the ODE (e.g. `diff(y, t, 2) + w^2 * y = 0`).

### Abstract Algebra & Group Theory
- **Algebraic Structures:**
  - `Assume Group(G, op, e, inv)` — Groups with operation `op`, identity `e`, and inverse `inv(a)`
  - `Assume AbelianGroup(G, op, e, inv)` — Commutative groups
  - `Assume Ring(R, add, mul, zero, one, neg)` — Rings
  - `Assume Field(F, add, mul, zero, one, neg, inv)` — Fields
- **Subgroups:**
  - `Subgroup(H, G, op, e, inv)`
  - `NormalSubgroup(N, G, op, e, inv)`
- **Group Elements & Operations:**
  - Application: `op(a, b)`, `inv(a)`, `inv(op(a, b))`
  - Inverses: `op(a, inv(a)) = e`, `inv(inv(a)) = a`
  - **The notes' notation:** for elements declared `Given a, b : G`, `a * b` (or `a \cdot b`, `a \circ b`, `a·b`) is `op(a, b)`, `a^-1` (or `a⁻¹`) is `inv(a)`, `a^3` is `a * a * a` and `a^0` is `e`. Variables of a number type keep ordinary, commuting multiplication.
  - An equation built only from the group's operations is checked as an identity of **every** group: `(a * b)^-1 = b^-1 * a^-1` and `a^2 * a^3 = a^5` verify at once, while `a * b = b * a` is refused with the two reduced words (in an `AbelianGroup` it verifies).
- **Modular Arithmetic & Congruence:**
  - Natural syntax: `a = b (mod m)`
  - LaTeX syntax: `a \equiv b \pmod{m}`
  - Predicate form: `Congruent(a, b, m)`

### Relations & Logic
- Comparisons: `=`, `<`, `<=`, `>`, `>=`, `!=` (or `≤`, `≥`, `≠`)
- Boolean Connectives: `and`, `or`, `not`, `=>` (implies), `<=>` (if and only if) — or `∧`, `∨`, `¬`, `⇒`, `⇔`
- Quantifiers:
  - Universal: `forall x : Real, ...` (or `∀ x ∈ ℝ, ...`)
  - Existential: `exists k : Int, ...` (or `∃ k ∈ ℤ, ...`)
  - **Bounded, as the notes write them:** `forall \epsilon > 0, ...` means `forall \epsilon, \epsilon > 0 => ...`, and `exists \delta > 0, ...` means `exists \delta, \delta > 0 and ...`. So Definition 2.6 reads `∀ ε > 0, ∃ δ > 0, ∀ x ∈ ℝ, |x − x0| < δ ⇒ |f(x) − L| < ε`.
- Unicode from typeset notes is accepted throughout: `−` (minus), `·` and `×`, `∈ ∉ ⊂ ⊆ ∪ ∩ ∅`, `≡`, `√`, `∞`, superscripts `x²` and `a⁻¹`.
- Built-in Number Theory Predicates:
  - `Even(x)` $\iff \exists k \in \mathbb{Z}, x = 2k$
  - `Odd(x)` $\iff \exists k \in \mathbb{Z}, x = 2k + 1$
  - `MultipleOf(a, b)` $\iff \exists k \in \mathbb{Z}, a = b \cdot k$
  - `Divides(b, a)` $\iff \exists k \in \mathbb{Z}, a = b \cdot k$
  - `Positive(x)` $\iff x > 0$
  - `NonNegative(x)` $\iff x \ge 0$

---

## 4. Step Justifications & Proof Libraries

### Citing Reasons on Steps
You can explicitly justify your deductions with `[by ...]` or `[using ...]`:
- `Step: 2 * (2 * k^2) = 4 * k^2 [by algebra]` — Direct CAS computation.
- `Step: op(a, e) = a [by definition]` — From active structure definitions.
- `Step: op(a, b) = op(a, c) [using h1]` — Using an active assumption or label.
- `Therefore Congruent(a^2, b^2, m) [using h1]` — Deducing via cited facts.

### Splitting Proofs into Multiple Files
You can organize reusable lemmas across multiple files:
```text
# In file "algebra_lemmas.aether"
Theorem: "Even times even is even"
Claim: forall a, b : Int, Even(a) and Even(b) => Even(a * b)
Proof:
    ...
QED
```

Then import it into your main proof file:
```text
# In file "main_proof.aether"
import "algebra_lemmas.aether"

Theorem: "Even fourth power"
Proof:
    ...
QED
```
Aether automatically resolves the file, verifies that it is valid, imports all definitions and theorem claims, and guards against cyclic dependencies.

---

## 5. Top Proof Templates (Copy & Adapt)

### Template 1: Direct Algebraic Proof (Even Square Theorem)
```text
Theorem: "Even square theorem"
Claim: forall n : Int, Even(n) => MultipleOf(n^2, 4)
Proof:
    Given n : Int
    Assume hn: Even(n)
    Obtain k : Int such that n = 2 * k from hn
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2 [by algebra]
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]
    Hence MultipleOf(n^2, 4)
QED
```

### Template 2: Mathematical Induction ($3^n - 1$ is Divisible by 2)
```text
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: forall n : Nat, MultipleOf(3^n - 1, 2)
Proof:
    Base case n = 0:
        Step: 3^0 - 1 = 0
        Step: = 2 * 0
        Therefore exists m : Int, 3^0 - 1 = 2 * m [witness: 0]
        Hence MultipleOf(3^0 - 1, 2)

    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(3^k - 1, 2)
        Obtain m : Int such that 3^k - 1 = 2 * m from ih
        Step: 3^(k + 1) - 1 = 3 * 3^k - 1
        Step: = 3 * (2 * m + 1) - 1
        Step: = 2 * (3 * m + 1)
        Therefore exists q : Int, 3^(k + 1) - 1 = 2 * q [witness: 3 * m + 1]
        Hence MultipleOf(3^(k + 1) - 1, 2)

    Therefore forall n : Nat, MultipleOf(3^n - 1, 2)
QED
```

### Template 3: Real Analysis $\varepsilon$-$\delta$ Continuity Proof
```text
Theorem: "Continuity of 3x at x=2"
Claim: forall \epsilon : Real, \epsilon > 0 => exists \delta : Real, \delta > 0 and (forall x : Real, |x - 2| < \delta => |3 * x - 6| < \epsilon)
Proof:
    Given \epsilon : Real where \epsilon > 0
    Let \delta = \epsilon / 3
    Step: \delta > 0
    Subproof:
        Given x : Real
        Assume |x - 2| < \delta
        Step: |3 * x - 6| = |3 * (x - 2)|
        Step: = 3 * |x - 2|
        Step: < 3 * \delta
        Step: = \epsilon
    Therefore exists \delta : Real, \delta > 0 and (forall x : Real, |x - 2| < \delta => |3 * x - 6| < \epsilon) [witness: \epsilon / 3]
QED
```

### Template 4: Calculus & Differential Equation Verification
Proving that $y(t) = c_1 \cos(\omega t) + c_2 \sin(\omega t)$ satisfies the harmonic oscillator equation $y''(t) + \omega^2 y(t) = 0$:
```text
Theorem: "Simple harmonic oscillator ODE"
Proof:
    Let c1, c2, w, t : Real
    Let y = c1 * cos(w * t) + c2 * sin(w * t)
    Step: diff(y, t, 1) = -c1 * w * sin(w * t) + c2 * w * cos(w * t)
    Step: diff(y, t, 2) = -c1 * w^2 * cos(w * t) - c2 * w^2 * sin(w * t)
    Step: = -w^2 * y
    Step: diff(y, t, 2) + w^2 * y = 0
QED
```

### Template 5: Abstract Group Theory ("Shoes and Socks" Theorem)
Proving $(a \cdot b)^{-1} = b^{-1} \cdot a^{-1}$ from group axioms:
```text
Theorem: "Inverse of a product in a group"
Proof:
    Assume Group(G, op, e, inv)
    Given a, b : Real
    Step: op(op(a, b), op(inv(b), inv(a))) = e
    Therefore inv(op(a, b)) = op(inv(b), inv(a))
QED
```

### Template 6: Modular Arithmetic & Congruences
```text
Theorem: "Square of congruent integers"
Proof:
    Given a, b, m : Int
    Assume h1: a = b (mod m)
    Obtain k : Int such that a - b = m * k from h1
    Step: a = b + m * k
    Step: a^2 = b^2 (mod m) [by algebra]
    Therefore Congruent(a^2, b^2, m) [using h1]
QED
```

---

## 6. What the Proof Intern Checks (and Common Traps)

1. **Equational & Inequality Chaining Rules:**
   - In a chain (`Step: a <= b`, `Step: = c`, `Step: < d`), directions must remain strictly monotonic.
   - **Trap:** Never mix `<=` and `>=` in the same chain.
2. **Domain Obligations:**
   - Dividing by an expression $B$ requires $B \neq 0$.
   - Square rooting $\sqrt{A}$ requires $A \ge 0$.
   - If not guarded by an active assumption (`Assume x != 2`), Aether emits a domain warning (or a hard error if **Strict Domain Checking** is enabled).
   - Each distinct obligation is reported once, however many times the offending sub-expression occurs.
3. **Implicit Variable Capture Guard:**
   - `Obtain k : Int ...` will be rejected if variable `k` is already in scope. Always pick a fresh witness name!
4. **Illegal Universal Generalization:**
   - Deducing `Therefore forall x : Real, ...` is rejected if `x` is constrained by an undischarged local hypothesis.
5. **Concrete Counterexamples:**
   - When an algebraic or inequality step is wrong, Aether calculates an exact numeric counterexample (e.g. `Counterexample at x=3: LHS = 16, RHS = 10`), displayed in the auditor.
6. **What the Solver Cannot Decide:**
   - The SMT backend has no theory of `exp`, `log`, `sin`, `cos` or `tan`. It is given only true facts about their *ranges* — `-1 <= sin, cos <= 1`, `exp(t) > 0` and `exp(t) >= 1 + t`, `log(t) <= t - 1` for `t > 0`, `cosh >= 1`, `|tanh| < 1` — so `Step: exp(x) > 0` and `Step: |x * sin(1/x)| <= |x|` are proved, but an inequality needing more than that (`exp(x) >= 1 + x + x^2/2`) cannot be decided. The message says as much rather than presenting a misleading counterexample. Equalities (`Step: sin(x)^2 + cos(x)^2 = 1`) are settled by SymPy instead, and do work.
   - A logarithm's argument is **not** subject to a domain obligation, since the check would have to be discharged by that same solver. See §8 for the reasoning.
   - A function name the engine does not know is reported as such — `fact(5)` will suggest `factorial` rather than claiming the arithmetic is wrong.

---

## 7. Web UI & Exporting to LaTeX / PDF

When you open the Aether web interface (`http://localhost:8000`):

1. **Proof Editor & Auditor:**
   - Write or paste your proof on the left.
   - As you type, the auditor on the right checks every step in real time.
   - Click on any statement line to inspect the **Context & State Inspector** (active variables, hypotheses, and scope depth).
2. **Strict Domain Toggle:**
   - Switch the toggle in the header to enforce strict domain checking (where unguarded divisions turn into errors instead of warnings).
3. **Panel Arrangement:**
   - The toolbar's **Panel arrangement** button offers four presets, each drawn as a miniature of itself: **Columns** (the default), **Stack**, **Split** and **Focus**. Split and Focus give the auditor and the context pane one column between them — the nearest thing here to docking one panel inside another.
   - Beyond the presets, **drag a panel's grip** (the dots at the left of a panel head) onto another panel to swap the two, or **focus a grip and press an arrow key** to slide that panel one place along the order.
   - Your arrangement is remembered for the next visit.
4. **Appearance:**
   - The theme button flips light / dark. The **Syntax colours** button flips the editor between near-monochrome (the default) and a colourised scheme, the way a Python file is coloured. Both are remembered.
5. **Exporting to LaTeX & PDF:**
   - Click the **Export to LaTeX / PDF** button in the top menu.
   - **Standalone Switch**: Toggle whether you want a full standalone document (with `\documentclass{article}`, `amsmath`, `amssymb`) or an embeddable snippet.
   - **Verification breakdown Switch**: Appends the audit (line, status, backend, canonical statement), the proof state at each line, the session log, and the source listing. Turn it off to get exactly the proof and nothing else.
   - **Copy LaTeX** / **Download .tex**: Copies or downloads clean, human-readable LaTeX markup, named after the theorem. This is always the sober `article` presentation, so it is the thing to paste into a paper.
   - **Download PDF**: The server compiles the proof in the background and delivers a ready-to-print `.pdf` directly to your browser. The PDF is a **designed** document: a full-bleed cover carrying the verdict, a findings section for every statement that failed (with its counterexample), the auditor as a step list, then the proof state, the session and the source. It is the one you would hand out.
   - The subtlety between the two: only the PDF is designed. The `.tex` you download stays the plain article, so what you edit is never a designed file.

For how each of these is put together — and the checks that keep them honest — see [`ui/README.md`](ui/README.md).

---

## 8. Capability Matrix: What Parses, Verifies, and Refuses

The tables above advertise what an Aether proof may contain, and where the engine stops. This is that surface in one place: every row is a snippet plus the verdict it must still produce. It is generated from the pins themselves —

```bash
uv run python ui/verify_capabilities.py --markdown
```

so it cannot drift from the engine without `uv run python ui/verify_capabilities.py` failing.

A `VALID` row checks out, and still does with **Strict Domain Checking** on. `INVALID` is the engine refusing it, `PARSE_ERROR` the grammar not accepting it at all, `WARN` checking out but leaving a domain obligation unresolved, and `EMPTY` nothing to check. Rows whose note names a component (`Context`, `ChainGuard`, `ScopeGuard`, `QED`) are the *deliberate refusals*; rows with a sentence instead are known *gaps* — things the mathematics would allow but the grammar or a backend does not do yet. No row is expected to hit `TIMEOUT`: the sweep still bounds every snippet, because Z3's soft timeout cannot interrupt a query that has stalled.

| Feature | Verdict | Notes |
| --- | --- | --- |
| types · `Nat / Int / Rat / Real / Complex / Bool` | VALID |  |
| types · `several names at once` | VALID |  |
| types · `Greek names` | VALID |  |
| types · `a value rather than a type` | VALID |  |
| types · `unknown type is refused` | INVALID | Context |
| types · `Nat carries non-negativity` | VALID |  |
| types · `Int does not` | INVALID |  |
| constant · `\pi is the number` | VALID |  |
| constant · `e is the number` | VALID |  |
| constant · `the solver knows a bound` | VALID |  |
| constant · `a looser bound is not known` | INVALID | the SMT backend carries only `3.14159265 < pi < 3.14159266`, so a comparison it cannot settle is refused |
| constant · `a declared name is a variable again` | VALID |  |
| constant · `a structure's e stays its identity` | VALID |  |
| expr · `abs / min / max` | VALID |  |
| expr · `powers` | VALID |  |
| expr · `sqrt` | VALID |  |
| expr · `exp / ln` | VALID |  |
| expr · `trig identity` | VALID |  |
| expr · `derivative` | VALID |  |
| expr · `indefinite integral` | VALID |  |
| expr · `definite integral` | VALID |  |
| expr · `LaTeX integral` | VALID |  |
| expr · `limit` | VALID |  |
| expr · `LaTeX limit` | VALID |  |
| expr · `directional limit` | VALID |  |
| expr · `summation, functional` | VALID |  |
| expr · `summation, LaTeX` | VALID |  |
| expr · `factorial` | VALID |  |
| expr · `a call with the wrong arity is named` | INVALID | the arity is reported; unchecked, `Abs(x, x)` raised a TypeError that escaped `check_source` entirely |
| expr · `ln takes no base` | INVALID | `ln` is the natural log and takes one argument; a second used to be read silently as a base |
| expr · `the solver knows the range of exp / sin / cos` | VALID |  |
| expr · `beyond their ranges, exp / log / trig are opaque` | INVALID | Z3 has no theory of exp/log/trig, only true range facts (sin and cos within [-1, 1], exp > 0, exp(t) >= 1 + t, ...), so an inequality needing more cannot be decided; the message says so instead of presenting a bare counterexample, and equalities still go to SymPy |
| sets · `union / intersect / \emptyset` | VALID |  |
| sets · `subset, infix` | VALID |  |
| sets · `membership` | VALID |  |
| sets · `\varnothing alias` | VALID |  |
| sets · `set literals` | PARSE_ERROR | no {a, b, c} notation; declare and relate instead |
| matrix · `product / det / tr / transpose` | VALID |  |
| matrix · `dot and Orthogonal` | VALID |  |
| matrix · `inverse of a square matrix` | VALID |  |
| matrix · `inverse(A) = the adjugate over the determinant` | VALID |  |
| matrix · `a wrong product is caught` | INVALID |  |
| algebra · `Group identity` | VALID |  |
| algebra · `Group inverse` | VALID |  |
| algebra · `a plain Group is not commutative` | INVALID | a plain Group does not entail commutativity: the two sides reduce to different words in the free group, which is itself a group, so no solver search is needed |
| algebra · `AbelianGroup is` | VALID |  |
| algebra · `Ring distributes` | VALID |  |
| logic · `existential witness` | VALID |  |
| logic · `and / or / not` | VALID |  |
| logic · `nested quantifiers` | VALID |  |
| logic · `forall over a free variable` | VALID |  |
| logic · `biconditional in a hypothesis` | INVALID | a biconditional entails neither side alone -- it also holds when both are false, so a=1 (Even(1) false, Odd(2) false) is a genuine counterexample |
| predicate · `Even / Odd / MultipleOf / Divides` | VALID |  |
| predicate · `Positive implies NonNegative` | VALID |  |
| predicate · `Congruent` | VALID |  |
| predicate · `a = b (mod m)` | VALID |  |
| predicate · `\equiv \pmod` | VALID |  |
| predicate · `Define, then use both ways` | VALID |  |
| predicate · `an undefined predicate proves nothing` | INVALID | unknown predicates are uninterpreted and unrelated to = |
| structure · `sections of a proof` | VALID |  |
| structure · `scratchpad, no Theorem` | VALID |  |
| structure · `cases` | VALID |  |
| structure · `induction` | VALID |  |
| structure · `Subproof` | VALID |  |
| structure · `justification [by ...]` | VALID |  |
| structure · `justification [using ...]` | VALID |  |
| structure · `Claim is discharged by QED` | VALID |  |
| structure · `a Claim that is not established` | INVALID | QED |
| structure · `restating the forall yourself` | INVALID | prove the body under Given/Assume and let QED discharge it |
| structure · `import` | INVALID | Library |
| guard · `chain continues a strict inequality` | VALID |  |
| guard · `chain mixes directions` | INVALID | ChainGuard |
| guard · `chained step with no anchor` | INVALID | ChainGuard |
| guard · `witness would shadow a variable` | INVALID | Context |
| guard · `generalising a constrained variable` | INVALID | ScopeGuard |
| guard · `unresolved domain obligation` | WARN | unresolved obligation is an error under strict checking |
| guard · `an assumption can discharge it` | VALID |  |
| guard · `sqrt needs its radicand bounded` | VALID |  |
| guard · `a logarithm's argument is not obliged positive` | VALID | positivity of `ln`'s argument is not extracted, so `ln(x)` needs no `x > 0` in scope; the solver now discharges `exp(x) > 0`, so `ln(exp(x)) = x` would survive the check |
| grammar · `hash comments` | VALID |  |
| grammar · `slash slash comments` | PARSE_ERROR | `#` and `--` each start a comment; `//` does not |
| grammar · `CRLF line endings` | VALID |  |
| grammar · `unicode quantifier` | VALID |  |
| grammar · `unicode comparison` | VALID |  |
| grammar · `reason: instead of by:` | PARSE_ERROR | the bracket takes [by ...] or [using ...] |
| grammar · `indentation is load-bearing` | PARSE_ERROR |  |
| grammar · `unknown keyword` | PARSE_ERROR |  |
| grammar · `empty source` | EMPTY |  |
