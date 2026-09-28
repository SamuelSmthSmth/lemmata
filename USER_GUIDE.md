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

### Greek Letters & Variables
Type standard LaTeX Greek letters:
- `\epsilon`, `\delta`, `\alpha`, `\beta`, `\gamma`, `\theta`, `\lambda`, `\mu`, `\pi`, `\sigma`, `\phi`, `\omega`

### Arithmetic & Standard Operations
- Operators: `+`, `-`, `*`, `/`, `^` (exponentiation: e.g. `x^2`, `3^(k + 1)`)
- Absolute Value: `|x - a|` or `abs(x - a)`
- Bounds: `min(a, b)`, `max(a, b)`
- Summations:
  - Functional form: `sum(k, 1, n, 2 * k - 1)` (index, lower, upper, summand)
  - LaTeX form: `\sum_{k=1}^{n} (2 * k - 1)`

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
- **Modular Arithmetic & Congruence:**
  - Natural syntax: `a = b (mod m)`
  - LaTeX syntax: `a \equiv b \pmod{m}`
  - Predicate form: `Congruent(a, b, m)`

### Relations & Logic
- Comparisons: `=`, `<`, `<=`, `>`, `>=`, `!=`
- Boolean Connectives: `and`, `or`, `not`, `=>` (implies), `<=>` (if and only if)
- Quantifiers:
  - Universal: `forall x : Real, ...`
  - Existential: `exists k : Int, ...`
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
3. **Implicit Variable Capture Guard:**
   - `Obtain k : Int ...` will be rejected if variable `k` is already in scope. Always pick a fresh witness name!
4. **Illegal Universal Generalization:**
   - Deducing `Therefore forall x : Real, ...` is rejected if `x` is constrained by an undischarged local hypothesis.
5. **Concrete Counterexamples:**
   - When an algebraic or inequality step is wrong, Aether calculates an exact numeric counterexample (e.g. `Counterexample at x=3: LHS = 16, RHS = 10`), displayed in the auditor.

---

## 7. Web UI & Exporting to LaTeX / PDF

When you open the Aether web interface (`http://localhost:8000`):

1. **Proof Editor & Auditor:**
   - Write or paste your proof on the left.
   - As you type, the auditor on the right checks every step in real time.
   - Click on any statement line to inspect the **Context & State Inspector** (active variables, hypotheses, and scope depth).
2. **Strict Domain Toggle:**
   - Switch the toggle in the header to enforce strict domain checking (where unguarded divisions turn into errors instead of warnings).
3. **Exporting to LaTeX & PDF:**
   - Click the **Export to LaTeX / PDF** button in the top menu.
   - **Standalone Switch**: Toggle whether you want a full standalone document (with `\documentclass{article}`, `amsmath`, `amssymb`) or an embeddable snippet.
   - **Copy LaTeX**: Copies clean, human-readable LaTeX markup to your clipboard.
   - **Download .tex**: Downloads the proof as a `.tex` file named after the theorem.
   - **Download PDF**: The server compiles the proof using LaTeX in the background and delivers a ready-to-print `.pdf` file directly to your browser!
