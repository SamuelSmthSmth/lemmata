# Lemmata Proof Author's Handbook & Cheat Sheet

Welcome to **Lemmata**, a step-by-step proof checker for students writing proofs: from A Level Maths and Further Maths (proof by deduction, contradiction, counterexample and induction) to undergraduate pure mathematics (Real Analysis, Calculus & ODEs, Abstract Algebra, Number Theory, and Linear Algebra).

You don't need to learn type theory or an interactive theorem prover like Lean 4 or Coq first. You write the proof in **Controlled Natural Language (CNL)**: familiar English keywords (`Given`, `Assume`, `Obtain`, `Step:`, `Therefore`, `QED`) with ordinary mathematical notation. Lemmata checks every line, and says why a line fails.

**Contents:**
1. Quick Start
2. The Keyword Cheat Sheet
3. Mathematical Notation
4. Step Justifications & Proof Libraries
5. Proof Methods: deduction, cases, contradiction, counterexample, induction
6. Proof Templates
7. What It Checks, Checking Options, and Common Traps
8. The App, and Exporting to LaTeX / PDF and Lean
9. Capability Matrix

---

## 1. Quick Start: The 30-Second Mental Model

Every Lemmata proof file contains either:
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
| `Given` / `Let` / `Fix` | `Given n : Int`<br>`Let x, y : Real`<br>`Fix \epsilon : Real where \epsilon > 0`<br>`Let ε > 0 be given`<br>`Let \delta = \epsilon / 3` | Introduces new variables, constraints, or variable definitions into scope. `Let ε > 0` alone declares a real `ε` with that condition. |
| `Take` / `Set` / `Put` | `Take δ = ε / 3`<br>`Set δ = ε / 3` | Names a value, exactly as `Let δ = …` does. |
| `Assume` / `Suppose` | `Assume h1: Even(n)`<br>`Suppose x > 2`<br>`Assume Group(G, op, e, inv)` | Declares a local hypothesis, premise, or algebraic structure. Labels like `h1:` are optional. |
| `Obtain` | `Obtain k : Int such that n = 2 * k from h1` | Unpacks an existential fact or definition (extracts witness `k` from `Even(n)`). |
| `Step:` | `Step: n^2 = (2 * k)^2`<br>`Step: = 4 * k^2 [by algebra]`<br>`Step: < 8 * k^2 [using h1]` | Equational or inequality deduction. Leaving off the LHS chains from previous RHS. Optional `[by ...]` or `[using ...]`. |
| `Therefore` / `Hence` / `Thus` | `Therefore exists m : Int, n^2 = 4 * m [witness: k^2]`<br>`Hence MultipleOf(n^2, 4) [by definition]` | Deduces a new fact. Optional `[witness: ...]` for existential claims and `[by ...]` / `[using ...]`. `So`, `Then`, `We have`, `We get`, `Note that`, `Now`, `Clearly` and `It follows that` say the same. |
| `Since … , …` | `Since x > 2, x^2 > 4`<br>`Since h1, x + 1 > 3` | The first part must already hold (it is checked); the second follows using it. A label (`h1`) is used as it stands. |
| `By … , …` | `By h1, x^2 > 4`<br>`By Theorem 1.1, abs(a - b) <= abs(a) + abs(-b)` | The second part follows using what is named: a label, or a result cited by name (§4). |
| `Base case` / `Inductive step` | `Base case n = 0:`<br>`Inductive step:` | Opens mathematical induction subproofs. |
| `Case` | `Case x >= 0:`<br>`Case x < 0:` | Splits into exhaustive cases. |
| `Subproof:` | `Subproof:` | Opens a general nested subproof (e.g., for universal generalization or implication). |
| `Define` / `Definition:` | `Define CongruentMod(a, b, m) <=> Divides(m, a - b)`<br>`Definition 2.6 (Continuity): Continuous(f, a) <=> ∀ ε > 0, ∃ δ > 0, ∀ x ∈ ℝ, abs(x - a) < δ => abs(f(x) - f(a)) < ε` | Defines a reusable predicate or function. The notes' own heading works, with or without its number and name. A definition may take a function as an argument (§3). |
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
- **Functions are a type too.** `Given f : Real -> Real` (or `ℝ → ℝ`, `Int -> Int`, `Real -> Real -> Real` for two arguments) declares an abstract function: nothing is known about it but what you assume, so `Assume ∀ x ∈ ℝ, f(x) > 0` then `Therefore f(2) > 0` checks, and `Therefore f(2) > 0` alone does not. A definition can take one as an argument: with `Continuous(f, a)` defined as above, `Assume Continuous(h, 0)` is usable, `Let g(x) = 3 * x` then `Therefore Continuous(g, 2)` checks, and a theorem whose `Claim:` is `Continuous(g, 2)` is proved by its definition: `Given ε`, `Assume ε > 0`, then the `∃ δ`.
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
  - Several names at once: `forall a, b : Int, ...` (or `∀ a, b ∈ ℤ, ...`) means `forall a : Int, forall b : Int, ...`
  - **Bounded, as the notes write them:** `forall \epsilon > 0, ...` means `forall \epsilon, \epsilon > 0 => ...`, and `exists \delta > 0, ...` means `exists \delta, \delta > 0 and ...`. So Definition 2.6 reads `∀ ε > 0, ∃ δ > 0, ∀ x ∈ ℝ, |x − x0| < δ ⇒ |f(x) − L| < ε`. A bound after several names bounds each: `∀ ε, δ > 0, ...`.
- Unicode from typeset notes is accepted throughout: `−` (minus), `·` and `×`, `∈ ∉ ⊂ ⊆ ∪ ∩ ∅`, `≡`, `√`, `∞`, superscripts `x²` and `a⁻¹`.
- Built-in Number Theory Predicates:
  - `Even(x)` $\iff \exists k \in \mathbb{Z}, x = 2k$
  - `Odd(x)` $\iff \exists k \in \mathbb{Z}, x = 2k + 1$
  - `MultipleOf(a, b)` $\iff \exists k \in \mathbb{Z}, a = b \cdot k$
  - `Divides(b, a)` $\iff \exists k \in \mathbb{Z}, a = b \cdot k$
  - `Positive(x)` $\iff x > 0$
  - `NonNegative(x)` $\iff x \ge 0$
  - `Prime(p)` $\iff p > 1$ and no $d$ with $1 < d < p$ divides $p$ (a number is settled exactly: `Prime(41)`, `not Prime(1681)`)
  - `Coprime(a, b)` $\iff$ every common divisor of $a$ and $b$ is $\pm 1$; to show `not Coprime(a, b)`, show some $d > 1$ divides both
  - `Rational(x)` $\iff \exists p, q \in \mathbb{Z}, q > 0, \operatorname{Coprime}(p, q), x = p/q$ (lowest terms, the form a proof by contradiction uses); `Irrational(x)` $\iff$ `not Rational(x)`
- A polynomial's divisibility by a number (`MultipleOf(n^3 - n, 6)`, `Even(n * (n + 1))`) is decided outright, by checking every remainder.
- `Obtain p, q : Int such that … from h` unpacks several witnesses at once.

---

## 4. Step Justifications & Proof Libraries

### Citing Reasons on Steps
You can explicitly justify your deductions with `[by ...]` or `[using ...]`:
- `Step: 2 * (2 * k^2) = 4 * k^2 [by algebra]` — Direct CAS computation.
- `Step: op(a, e) = a [by definition]` — From active structure definitions.
- `Step: op(a, b) = op(a, c) [using h1]` — Using an active assumption or label.
- `Therefore Congruent(a^2, b^2, m) [using h1]` — Deducing via cited facts.

### Citing a Result by Name
A step can lean on a proved result without an `import` line: name it, as the notes do.
- `Step: abs(a - b) <= abs(a) + abs(-b) by Theorem 1.1`
- `By the triangle inequality, abs(a - b) <= abs(a) + abs(-b)`
- `… [by MTH2008 Theorem 1.1]`

In the app a result can be cited by its reference when that has a number (`Theorem 1.1`, and `MTH2008 Theorem 1.1` with the course), by its title, or by the title's first part (`The triangle inequality` for "The triangle inequality, by the four cases"); a theorem in your workspace by its name. Typing after `by` offers what is installed.
- The cited result is used **for that step only**, and the audit says which one it was. Context & state shows its statement, with a link back to it.
- A name that could mean two results is refused with both named ("cite it by its full name"); an unknown name is refused with the nearest names.
- Only results that state something can be cited: a pack's worked calculations, with no `Claim:` or conclusion, have nothing to lend.

From Python, pass the names with `check_source(source, sources=..., citations={"Theorem 1.1": "path/of/its.aether"})`.

### When a Step Fails: Hints
A step that does not check comes back with what to try, in your own notation, and a one-click fix when there is exactly one edit that would mend it:
- **An unguarded division or root:** "This step needs x − 1 ≠ 0 …" with **Add Assume x − 1 ≠ 0**.
- **Algebra off by a term:** "The two sides differ by ε/2."
- **A strict inequality that holds non-strictly:** "This holds with ≥, not >" with **Use ≥**.
- **A label that is out of scope or mistyped:** where it was introduced, or **Use h1**.
- **A mistyped predicate:** "Did you mean Even?" with **Use Even**.
- **A chain that changes direction:** how to split it.

Fixes are in Context & state and in the editor's tooltip on the marked line; each is one ordinary edit, so Ctrl+Z takes it back, and the check that follows says whether it worked.

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
Lemmata automatically resolves the file, verifies that it is valid, imports all definitions and theorem claims, and guards against cyclic dependencies.

A theorem is lent out with the hypotheses it was proved under. If its proof declares `Let x : Real` and assumes `x > 2` before concluding `x > 1`, what other proofs receive is `forall x : Real, x > 2 => x > 1`, not a bare `x > 1` about anybody's `x`. So an imported result applies exactly where its assumptions hold. A conclusion about an `Obtain` witness exists only inside its proof, so it is not lent out. If you want a result to travel, state it with `Claim:`.

The `.aether` extension may be left off: `import "algebra_lemmas"` finds `algebra_lemmas.aether`.

Where the file is looked for: in the web app, first among the proofs in your workspace — relative to the importing proof's folder, then from the top of the workspace — and then on disk. On the command line, beside the importing file, then a `base_dir` if one was given, then the working directory. An import that cannot be found is reported by name.

---

## 5. Proof Methods

These are the methods A Level and Further Maths name, and that undergraduate proofs are built from. Each example here checks as written; paste it into the app and change a line to see what a mistake looks like.

### Proof by deduction

Start from what you are given and work forward to the claim. Name the general objects with `Given`, state what you know with `Assume`, unpack a definition with `Obtain`, and do the algebra in `Step:` lines:

```text
Theorem: "The sum of two odd numbers is even"
Claim: forall m, n : Int, Odd(m) and Odd(n) => Even(m + n)
Proof:
    Given m, n : Int
    Assume hm: Odd(m)
    Assume hn: Odd(n)
    Obtain a : Int such that m = 2 * a + 1 from hm
    Obtain b : Int such that n = 2 * b + 1 from hn
    Step: m + n = (2 * a + 1) + (2 * b + 1)
    Step: = 2 * (a + b + 1)
    Therefore Even(m + n)
QED
```

`QED` checks that what you reached is the `Claim:`. Here, the `Given` and `Assume` lines discharge the `forall` and the `=>`.

### Proof by exhaustion (cases)

Split with `Case`, one indented block per case, and draw the conclusion after the last one. The cases must cover every possibility between them: `Even(n)` and `Odd(n)`, `x >= 0` and `x < 0`, or `n = 0`, `n = 1` and `n >= 2` for a natural number.

```text
Theorem: "n^2 + n is even"
Claim: forall n : Int, Even(n^2 + n)
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 2 * (2 * k^2 + k)
        Therefore Even(n^2 + n)
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 2 * (2 * k^2 + 3 * k + 1)
        Therefore Even(n^2 + n)
    Therefore Even(n^2 + n)
QED
```

Leave out the odd case and the conclusion is a **warning**, even though it is true: "the cases (Even(n)) do not cover every possibility (n=3 is in none of them) … Add the missing case." A mark scheme would mark that proof down, so the checker does too.

### Proof by contradiction

Open a `Subproof:`, assume the opposite, and reach `Contradiction`. Afterwards, the negation of what you assumed holds. Here is the textbook proof that √2 is irrational, written as the textbook writes it:

```text
Theorem: "The square root of 2 is irrational"
Claim: Irrational(sqrt(2))
Proof:
    Subproof:
        Assume h: Rational(sqrt(2))
        Obtain p, q : Int such that q > 0 and Coprime(p, q) and sqrt(2) = p / q from h
        Step: p^2 = 2 * q^2
        Therefore Even(p^2)
        Therefore Even(p)
        Obtain k : Int such that p = 2 * k
        Step: 4 * k^2 = 2 * q^2
        Step: q^2 = 2 * k^2
        Therefore Even(q^2)
        Therefore Even(q)
        Therefore not Coprime(p, q)
        Therefore Contradiction
    Therefore not Rational(sqrt(2))
    Hence Irrational(sqrt(2))
QED
```

`Rational(x)` means $x = p/q$ in lowest terms (`Coprime(p, q)`, $q > 0$), which is exactly what the argument contradicts. Every step is still checked. Skip straight to `Therefore Contradiction` and the proof is refused. Run the same argument for √4 and it fails at the line that is false ($q^2 = 2k^2$).

### Disproof by counterexample

To show a statement is false, exhibit one case where it fails. Name the value with `Let`, and show it breaks the claim:

```text
Theorem: "n^2 + n + 41 is not always prime"
Proof:
    Let n = 40
    Step: n^2 + n + 41 = 41 * 41
    Therefore Divides(41, n^2 + n + 41)
    Hence not Prime(n^2 + n + 41)
QED
```

Lemmata finds counterexamples itself as well. A false `Step:` or `Therefore` comes back with values that break it (`Counterexample at x=3: LHS = 36, RHS = 33`), so trying to *prove* a false claim is often the quickest way to find the case that disproves it.

### Proof by induction

`Base case n = …:` and `Inductive step:` each open a block. The inductive step introduces `k`, assumes the claim for `k` (the inductive hypothesis), and proves it for `k + 1`. The conclusion after both is the `forall`. [Template 2](#template-2-mathematical-induction-3n---1-is-divisible-by-2) is a complete divisibility proof.

#### Induction from a starting value, and recurrences

A claim for "every positive integer" or "every $n \ge 5$" puts the start in the claim, as a guard: `forall n : Nat, n >= 5 => P(n)`. The base case is then `n = 5`. The inductive step may assume anything that follows from $k \ge 5$ (`Assume hk: k >= 5`, or `Given k : Nat where k >= 5`) alongside the hypothesis, in any order. Over the integers, induction needs a starting value (`forall n : Int, n >= -2 => …`). Without one, the base case and the step say nothing about the numbers below it.

A sequence the question defines is declared as a function. Its first values and recurrence are its definition, and the verdict names them. Here the recurrence uses one earlier term, so one base case does; a recurrence that uses two earlier terms (`u(n + 2) = u(n + 1) + u(n)`) needs two base cases, and an inductive step that assumes the claim for both `k` and `k + 1`.

```text
Theorem: "A recurrence"
Claim: forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
Proof:
    Given u : Nat -> Int
    Assume u1: u(1) = 2
    Assume rec: forall n : Nat, n >= 1 => u(n + 1) = 2 * u(n) - 1
    Base case n = 1:
        Step: u(1) = 2^0 + 1
    Inductive step:
        Given k : Nat
        Assume hk: k >= 1
        Assume ih: u(k) = 2^(k - 1) + 1
        Step: u(k + 1) = 2 * u(k) - 1
        Step: = 2 * (2^(k - 1) + 1) - 1
        Step: = 2^k + 1
    Therefore forall n : Nat, n >= 1 => u(n) = 2^(n - 1) + 1
QED
```

State a recurrence from where the sequence starts (`n >= 1` above). Stated for every natural number, it also applies at $n = 0$, where $u(1) = 2u(0) - 1$ forces $u(0) = \tfrac32$. Definitions that contradict each other are refused.

---

## 6. Proof Templates (Copy & Adapt)

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

## 7. What It Checks, Checking Options, and Common Traps

1. **Equational & Inequality Chaining Rules:**
   - In a chain (`Step: a <= b`, `Step: = c`, `Step: < d`), directions must remain strictly monotonic.
   - **Trap:** Never mix `<=` and `>=` in the same chain.
2. **Domain Obligations:**
   - Dividing by an expression $B$ requires $B \neq 0$.
   - Square rooting $\sqrt{A}$ requires $A \ge 0$.
   - If not guarded by an active assumption (`Assume x != 2`), Lemmata emits a domain warning (or a hard error with [Strict domains](#checking-options) on).
   - Each distinct obligation is reported once, however many times the offending sub-expression occurs.
3. **Implicit Variable Capture Guard:**
   - `Obtain k : Int ...` will be rejected if variable `k` is already in scope. Always pick a fresh witness name!
4. **Illegal Universal Generalization:**
   - Deducing `Therefore forall x : Real, ...` is rejected if `x` is constrained by an undischarged local hypothesis.
5. **Concrete Counterexamples:**
   - When an algebraic or inequality step is wrong, Lemmata calculates an exact numeric counterexample (e.g. `Counterexample at x=3: LHS = 16, RHS = 10`), displayed in the auditor.
6. **What the Solver Cannot Decide:**
   - The SMT backend has no theory of `exp`, `log`, `sin`, `cos` or `tan`. It is given only true facts about their *ranges* — `-1 <= sin, cos <= 1`, `exp(t) > 0` and `exp(t) >= 1 + t`, `log(t) <= t - 1` for `t > 0`, `cosh >= 1`, `|tanh| < 1` — so `Step: exp(x) > 0` and `Step: |x * sin(1/x)| <= |x|` are proved, but an inequality needing more than that (`exp(x) >= 1 + x + x^2/2`) cannot be decided. The message says as much rather than presenting a misleading counterexample. Equalities (`Step: sin(x)^2 + cos(x)^2 = 1`) are settled by SymPy instead, and do work.
   - A logarithm's argument is **not** subject to a domain obligation, since the check would have to be discharged by that same solver. See §9 for the reasoning.
   - A function name the engine does not know is reported as such — `fact(5)` will suggest `factorial` rather than claiming the arithmetic is wrong.
7. **Cases Must Cover Everything:**
   - A conclusion drawn after `Case` blocks is a warning when the cases leave a possibility out, with a value that is in none of them. See [Proof by exhaustion](#proof-by-exhaustion-cases).
8. **Induction Is Checked as Induction:**
   - The base case must be the claim's starting value, the inductive step must reach `k + 1` (or `k + 2`, … for a recurrence) from what it assumed, and a claim over `Int` needs a starting value. A proof that only *looks* like induction is refused.

### Checking options

Three settings change how strict the checking is. Each proof keeps its own, and all three travel with the proof's link.

**The checking level** decides how big a step one line may take. With the level *Off*, every true line passes, however big the leap; the other levels are the proof kernel's:

| Level | A line may | Refused as too big a step |
| --- | --- | --- |
| **Exam** | use algebra, linear and non-linear arithmetic, and the facts it cites | a whole quantified statement in one line, a divisibility settled by checking remainders, a derivative, limit or sum written down without the working |
| **Course** (the default for new proofs) | all of that, and write a standard result down (a limit, a derivative, the geometric series), as lecture notes do | a whole quantified statement in one line, a divisibility settled by checking remainders |
| **Scratch** | anything the solvers can decide | nothing for being big |

At every level but Off, a line that cites its premises (`[using h1]`, `Since …`, `By …`) may use only those, and is told which fact it needed if it cited the wrong one. A refused line says what to write instead ("introduce each variable with Given, … choose any witness with [witness: …]"), and its conclusion still counts, so one leap is one finding. `QED` closes only a claim the proof reached. The level is in the tool strip (*Level: Course*), in the command palette (*Checking level: …*), and its default in Settings; a link made before levels existed opens at Off, as it was checked. From Python: `ProofChecker(kernel="course")`.

**Strict domains** (`ProofChecker(strict_domains=True)`) makes an unguarded division or square root an error instead of a warning. Turn it on when the proof should rule out every `x - 2 = 0` itself.

**Show your working** (`ProofChecker(show_working=True)`) is for practising exam-style answers. The checker can do a lot in one line: `diff(x^2 * sin(x), x) = 2*x*sin(x) + x^2*cos(x)` checks, and so do a series in closed form and `MultipleOf(n^3 - n, 6)`. That is right, but an exam question wants the working. With this on, such a step is a warning that says what is expected:

- a derivative or integral that needs the product, quotient or chain rule, or integration by parts or substitution, done in one step;
- a sum to a variable bound written in closed form, which needs induction or the method of differences;
- a limit evaluated straight from an indeterminate form, which needs the algebra first;
- a divisibility settled only by checking every remainder, which needs the cases.

Writing the working out passes: `diff(x^2 * sin(x), x) = diff(x^2, x) * sin(x) + x^2 * diff(sin(x), x)`, then `= 2*x*sin(x) + x^2*cos(x)`. Standard results, including linear insides like `sin(3x)` and `e^(2x)`, may be written straight down. With the option off, nothing changes.

---

## 8. The App, and Exporting to LaTeX / PDF and Lean

Run `uv run python -m ui` and open `http://localhost:8000`. The rail on the left switches between four views — **Proofs**, **Library**, **Guide** and **Settings** — and the status bar at the foot always shows the verdict for the open proof. `Ctrl/Cmd+K` opens a command palette that finds commands, your files, and any Library entry by its reference (`2.18`).

1. **Proof Editor & Auditor:**
   - Write or paste your proof in the editor. As you type, the auditor beneath it checks every step.
   - A failing step is marked in the editor too: a red rule in the gutter, an underline, and the reason when you hover. `F8` jumps to the next problem, and so does the problem count in the status bar.
   - Click on any statement line to inspect the **Context & State** pane (active variables, hypotheses, and scope depth).
   - **Insert template** offers whole proof shapes (theorem with a claim, ε–δ limit, induction, cases, contradiction, a group-theory proof, unpacking an existential); the symbol strip inserts `∀ ∃ ∈ ≤ ≠ ⇒ ε δ ∞ ℝ` and friends; `Ctrl+Space` completes keywords, structures, functions and the names your proof has declared.
2. **Your workspace:**
   - The **Files** tab of the reading pane holds every proof you have, in folders. New proof, new folder, rename (`F2`), delete (with *Undo*), and drag a proof onto a folder to move it. Open proofs sit in tabs above the editor.
   - Everything is kept **in this browser**. Export the whole workspace as a `.zip` from the Files tab or Settings to keep a copy; drop the `.zip` (or any `.aether` file) on the window to bring it back.
   - A proof can `import` another proof in the workspace by its path — relative to the importing proof, then from the top of the workspace (see §4).
   - The **History** tab shows the checks of the open proof and its snapshots: snapshot it, restore an earlier version, reset it to where it started, or copy a link that reproduces it exactly.
   - **What each line used.** Select a step and the auditor draws arcs from it to the lines it was proved from, with their line numbers lit; the lines that rest on it are drawn in grey. Context & state lists both as *Used* and *Used by*, each a link to that line, and says when the engine could not recover everything a line used. The button at the right of the auditor's head draws every line's arcs at once.
   - The **Trace** tab is the checker's log: for each line, every question it asked SymPy and Z3, the answer, and how long it took, with a case's or subproof's own lines nested under it. It is what `lemmata --trace FILE` prints on the command line (and `--used` lists what each line used).
   - Both come from one switch in Settings, *What each line used*, which is on by default; with it off, checking is about a tenth quicker.
3. **Library:**
   - Course packs for **MTH2008** (Real Analysis) and **MTH2010** (Algebra), keyed to the notes' own numbering, plus **Notation** (the notes' symbols and the traps around them) and the **Worked examples** of the language. Search by reference, title or topic.
   - **Open beside the proof** gives you your own copy of the entry's proof, with the entry kept in the **Notes** tab while you work.
   - **Traps** are deliberate mistakes. **Spot the error** opens one as an exercise: no verdicts are shown until you pick the line you think fails (or ask for the answer), and then the Notes explain why it fails.
   - The Library is a **pack manager**. Packs are installed in your browser: **Uninstall** one you don't need (your copies of its proofs stay in your workspace; *Undo* puts it back), **Install** it again from *Available*, and take an **Update** when one is offered. **Install from file…** (or dropping a `.pack.json` on the window) installs a pack someone shared with you. A pack doesn't need a course code; it can be a topic.
   - **Search the registry.** The Library's search also looks through the public pack registry, where anyone can publish a pack. Matching packs appear under *From the registry*: **Install** one, or open it to preview its entries first. Every entry in the registry was checked before it was listed. When a pack you installed gets a new version there, it appears as an update. Without a connection, the Library shows what the registry last offered, and your installed packs work as always.
   - **Check all entries** re-checks every entry of a pack and flags any that no longer gives the verdict the pack records.
   - **Use in a proof** puts `import "@core/mth2010/<entry>"` at the top of the open proof, so you can cite that theorem. It arrives with its assumptions: it applies where they hold (see §4).
   - **Make your own pack.** *New pack…* (or the pack button on a folder in the Files tab) turns a folder of your proofs into a pack. Give it a name, a version and, if you like, a course code; give each proof a reference, title and chapter, and mark traps with what is wrong. **Export .pack.json** checks every proof on its own and records the verdict it gives, so anyone who installs your pack sees exactly what you saw. **Share to the registry…** shows how to publish it for everyone: upload the file to the registry on GitHub and open a pull request, and its checks run every entry again.
4. **Checking Options, Arrangement and Appearance:**
   - The **Level** menu and the **Strict domains** and **Show working** switches in the tool strip are the [checking options](#checking-options). Each proof keeps its own settings, its link and History snapshots carry them, and Settings chooses the defaults for new proofs.
   - **Typeset the maths** (in Settings, or *Toggle typeset maths* in the command palette) shows each expression as it would print: fractions, powers and roots. The keywords stay as you wrote them. Move the caret into an expression to edit its source.
   - The **Panel arrangement** button offers four presets, each drawn as a miniature of itself: **Columns**, **Stack**, **Split** (the default) and **Focus**. Drag a panel's grip onto another panel to swap the two, or focus a grip and press an arrow key.
   - The sun/moon on the rail flips light / dark; the three-dot button flips the editor between near-monochrome and colourised syntax. **Settings** also holds the editor text size, line wrapping, how long to wait after typing before checking, and storage use. All of it is remembered.
5. **Exporting to LaTeX & PDF:**
   - Click the **Export to LaTeX / PDF** button at the end of the tool strip.
   - **Standalone Switch**: Toggle whether you want a full standalone document (with `\documentclass{article}`, `amsmath`, `amssymb`) or an embeddable snippet.
   - **Verification breakdown Switch**: Appends the audit (line, status, backend, canonical statement), the proof state at each line, the session log, and the source listing. Turn it off to get exactly the proof and nothing else.
   - **Copy LaTeX** / **Download .tex**: Copies or downloads clean, human-readable LaTeX markup, named after the theorem. This is always the sober `article` presentation, so it is the thing to paste into a paper.
   - **Download PDF**: The server compiles the proof in the background and delivers a ready-to-print `.pdf` directly to your browser. The PDF is a **designed** document: a full-bleed cover carrying the verdict, a findings section for every statement that failed (with its counterexample), the auditor as a step list, then the proof state, the session and the source. It is the one you would hand out.
   - The subtlety between the two: only the PDF is designed. The `.tex` you download stays the plain article, so what you edit is never a designed file.

6. **Show in Lean:**
   - The **Show in Lean** button at the end of the tool strip (or *Show in Lean* in the command palette) states your proof in **Lean 4 with Mathlib**, side by side with your own lines, each step beside the Lean it became.
   - `Given` and `Assume` become `intro`, a `Step:` chain a `calc`, `Therefore` a `have`, `Obtain` an `obtain`, cases a split with one bullet each, and induction Lean's `induction`. Your definitions become Lean `def`s, a function argument typed `ℝ → ℝ`; a group becomes Mathlib's `Group` with `*`, `1` and `⁻¹`; limits, derivatives, integrals and matrices use Mathlib's `Filter.Tendsto`, `deriv`, `intervalIntegral` and `!![…]`.
   - **Nothing is proved for you.** Each step's proof is `sorry`, a gap for Lean's tactics to fill; the comment beside it says how Lemmata checked the step and the tactic most likely to do the same (`ring`, `linarith`, `nlinarith`, `omega`, `group`). A step that did not check keeps its red rail and says so.
   - What has no faithful Lean (arithmetic with `∞`, an indefinite integral, an unknown type) is left as `sorry` and named above the table, rather than guessed.
   - **Copy Lean**, **Download .lean**, or **Open in Lean's web editor**, which has Mathlib, to start filling the gaps. Every example, pack entry and Guide example is compiled against Mathlib whenever the engine changes, so the skeleton you get compiles.

For how each of these is put together — and the checks that keep them honest — see [`ui/README.md`](ui/README.md).

---

## 9. Capability Matrix: What Parses, Verifies, and Refuses

The tables above advertise what an Lemmata proof may contain, and where the engine stops. This is that surface in one place: every row is a snippet plus the verdict it must still produce. It is generated from the pins themselves —

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
| expr · `chained inequality` | VALID |  |
| expr · `a sum to k + 1 is the sum to k plus a term` | VALID |  |
| expr · `polynomial divisibility, by remainders` | VALID |  |
| expr · `a false divisibility names a remainder` | INVALID | n^2 + 1 at n = 0 is 1: a polynomial's divisibility by a number depends only on the remainders, so they decide it |
| structure · `a missing case is flagged` | WARN | the conclusion holds, but Case Even(n) alone does not cover every n, so it is not proved by this case analysis |
| logic · `√2 is irrational, by contradiction` | VALID |  |
| logic · `a contradiction needs its argument` | INVALID | that √2 is irrational is not taken as known: the contradiction has to be derived |
| expr · `Prime` | VALID |  |
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
| structure · `induction from n = 1, when the claim holds at 0 too` | VALID |  |
| structure · `induction from n = 1 does not cover n = 0` | INVALID | Nat starts at 0: a base case at 1 needs P(0) too, and 2^0 >= 2 is false |
| structure · `induction over the integers is refused` | INVALID | a base case and a step say nothing below the base, so induction is accepted over Nat only |
| structure · `induction from a starting value` | VALID |  |
| structure · `a step may assume only what follows from the start` | INVALID | the step assumes k >= 5 but the claim starts at 1, so it says nothing about 2, 3 and 4 |
| structure · `a recurrence defined in the proof, two base cases` | VALID |  |
| structure · `a two-step recurrence needs two base cases` | INVALID | a step that uses n = k and n = k + 1 needs base cases at both 1 and 2 |
| structure · `contradictory definitions are refused` | INVALID | u(1) = 1 and u(1) = 2 contradict each other, and anything would follow from them |
| structure · `matrix-power induction` | VALID |  |
| structure · `divisibility induction with powers` | VALID |  |
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
| phrasing · `Let ε > 0 be given` | VALID |  |
| phrasing · `Fix ε > 0` | VALID |  |
| phrasing · `Set / Take / Put δ = …` | VALID |  |
| phrasing · `Since A, B` | VALID |  |
| phrasing · `Since checks its premise` | INVALID | the premise does not follow, so it cannot be used |
| phrasing · `By h1, B` | VALID |  |
| phrasing · `We have / Note that / Now / Clearly` | VALID |  |
| phrasing · `It follows that / We get` | VALID |  |
| function · `Given f : Real -> Real` | VALID |  |
| function · `ℝ → ℝ, and other number types` | VALID |  |
| function · `nothing is known about f unassumed` | INVALID | an abstract function is any function, so f(2) could be anything |
| function · `Definition 2.6 (Name): heading` | VALID |  |
| function · `a definition about a function, assumed` | VALID |  |
| function · `a defined function as the argument` | VALID |  |
| function · `Claim: a defined property, proved by its definition` | VALID |  |
| grammar · `hash comments` | VALID |  |
| grammar · `slash slash comments` | PARSE_ERROR | `#` and `--` each start a comment; `//` does not |
| grammar · `CRLF line endings` | VALID |  |
| grammar · `unicode quantifier` | VALID |  |
| grammar · `several names in one quantifier` | VALID |  |
| grammar · `several names under one bound` | VALID |  |
| grammar · `unicode comparison` | VALID |  |
| grammar · `reason: instead of by:` | PARSE_ERROR | the bracket takes [by ...] or [using ...] |
| grammar · `indentation is load-bearing` | PARSE_ERROR |  |
| grammar · `unknown keyword` | PARSE_ERROR |  |
| grammar · `empty source` | EMPTY |  |
