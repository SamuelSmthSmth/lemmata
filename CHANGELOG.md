# Changelog

What changed between releases of Lemmata, newest first. The engine is the `aether` Python package; its public API (`ProofChecker`, `ProofReport`, `StepResult`, `StepStatus`, `ParseError`) stays backward compatible within these releases.

## Unreleased

### Proofs you can now write

- **Several names in one quantifier**, as the notes write them: `forall a, b : Int, …`, `∀ a, b ∈ ℤ, …` and `∀ ε, δ > 0, …`. Each name gets the type or bound. The User Guide already used the first form, and it didn't parse.

### The proof kernel, stage 1 (engine only, opt in)

- **`ProofChecker(kernel="exam" | "course" | "scratch")`** checks whether each line *follows*, not only whether it is true. It is the first stage of the design in *A Proof Kernel for Lemmata*.
  - **A line that cites its premises may use only those.** `x² > 25 [using h2]` is refused when h2 doesn't give it, and the message names the fact that does.
  - **Each line is classified by the reasoning that settled it**, and refused as too big a step when the level doesn't allow that: a whole ε–δ statement decided in one line, or a divisibility settled by checking remainders. Under *Exam*, a limit, derivative or series evaluated in one line is refused too.
  - **The audit names the tactic and the premises used**, for example "Kernel: linarith … (from line 5 and line 4)".
  - **Calibrated on the course packs:** at *Course*, all 133 entries give the same verdict as without the kernel.
  - **Without the option, nothing changes.**

### Documentation

- **The README** is a front door: what Lemmata is, a checked example, who it's for, and how to run it.
- **The User Guide** has a new *Proof methods* section: deduction, cases, contradiction (√2), counterexample, and induction from a starting value and with recurrences, each with a proof that checks as written. *Checking options* brings Strict domains and Show your working together, and the app section covers the typeset view. The capability matrix is now §9.
- **The AI reference** matches the 0.2 grammar and engine: the real grammar, the AST as it is, number theory, induction, case coverage, Show your working, and the current HTTP API.

## 0.2.0 (2026-10-06)

The A Level release: induction as it's taught, number theory to go with it, and a mode that asks for the working an exam question wants. Undergraduate proofs keep working as before.

### Proofs you can now write

- **Induction from a starting value:** `forall n : Nat, n >= 5 => P(n)`, with the base case at 5. The inductive step may assume `k >= 5` (or anything that follows from it) alongside the hypothesis, in any order. Induction over the integers works from a starting value too.
- **Recurrences:** a sequence the question defines is declared as a function (`Given u : Nat -> Int`), and its first values and recurrence are its definition. The verdict names them. A recurrence that uses two earlier terms takes two base cases.
- **Matrix powers, De Moivre and factorial sums** by induction.
- **√2 is irrational,** written the classic way: `Rational(x)` is p/q in lowest terms, `Coprime(a, b)`, `Irrational(x)`, and `Obtain p, q : Int such that …` to unpack several witnesses at once.
- **`Prime(p)`:** numbers are settled exactly, `Prime(41)` and `not Prime(1681)`.
- **Divisibility of a polynomial** (`MultipleOf(n^3 - n, 6)`, `Even(n * (n + 1))`) is decided by checking every remainder. A false claim names a remainder as its counterexample.
- **Chained inequalities:** `-2 < k < 2`.
- **The notes' own phrasing:** `Since x > 2, x^2 > 4`, `By Theorem 1.1, …`, `We have`, `Let ε > 0 be given`, `Set δ = ε/3`. Results can be cited by name from installed packs and other files.
- **Show in Lean:** a Lean 4 + Mathlib skeleton of the proof, side by side with it. Every skeleton the repo pins is compiled in CI.

### A study tool that asks for the working

- **Show your working:** a switch beside Strict domains, per proof, with a default in Settings. With it on, a step that skips what a question wants to see gets a warning naming it:
  - the product, quotient or chain rule;
  - integration by parts or substitution;
  - a sum's closed form (prove it by induction or the method of differences);
  - a limit taken straight from 0/0;
  - a divisibility settled only by checking remainders.

  Working written out passes, and so do standard results like sin(3x).
- **Proofs by cases must cover every case.** A missing case is a warning naming a value no case covers, even when the conclusion happens to hold.
- **Hints with one-click fixes** when a step fails: an `Assume` to add, a sign to correct, a hypothesis to cite.

### In the app

- **Typeset the maths** (Settings): the editor shows each expression as it prints (fractions, powers, roots) and opens it as source wherever the caret touches it.
- A calm loading screen while the workspace opens, and no white flash between the site and the app in Firefox.

### Fixed

- **Two soundness bugs in induction.** A base case at 1 "proved" claims false at 0 (Nat includes 0), and induction was accepted over the integers ("every integer is non-negative"). Both are refused now, each with an explanation.
- "Sum to k + 1 = sum to k + the next term" was refused for sums SymPy writes as harmonic numbers.
- A sum's counting variable could appear as a counterexample ("r = 0").
- A guard such as `n >= 1` now discharges a division by n inside its own claim (no spurious domain warning).
- Powers like 3^k are known to be whole numbers, so divisibility inductions close.

## 0.1.0 (2026-10-03)

The first public release: a checker for proofs written the way lecture notes write them.

- Every line checked: algebra by SymPy, logic and inequalities by Z3. A failing step comes with its reason and, where one exists, a counterexample. Domain warnings flag divisions and square roots nothing rules out.
- The proof state at every line: declared variables, hypotheses and scope.
- Course packs: MTH2008 Real Analysis, MTH2010 Algebra and the notation set, and a public registry anyone can publish to.
- A workspace of proofs with imports between them, LaTeX and PDF export, and the Guide.
- In the browser (nothing to install), as a desktop app for Linux, Windows and macOS, or self-hosted.
