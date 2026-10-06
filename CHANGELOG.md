# Changelog

What changed between releases of Lemmata, newest first. The engine is the `aether` Python package; its public API (`ProofChecker`, `ProofReport`, `StepResult`, `StepStatus`, `ParseError`) stays backward compatible within these releases.

## Unreleased

### Proofs you can now write

- **Several names in one quantifier**, as the notes write them: `forall a, b : Int, …`, `∀ a, b ∈ ℤ, …` and `∀ ε, δ > 0, …`. Each name gets the type or bound. The User Guide already used the first form, and it didn't parse.

### In the app

- **What each line used.** Select a step and the auditor draws arcs to the lines it was proved from, with their line numbers lit, and to the lines that use it. Context & state lists both as *Used* and *Used by*, each a link to its line. A button in the auditor's head draws the whole proof's graph.
- **The Trace tab:** the checker's log in the reading pane. For each line it shows what was asked of SymPy and Z3, the answer and the time, with a block's own lines nested under it.
- Both can be turned off in Settings (*What each line used*), which makes checking about a tenth quicker.

### On the command line

- **`lemmata --used FILE`** lists what each line was proved from, and **`--trace`** lists the calls made to SymPy and Z3 per line: the same log as the Trace tab.

### The proof kernel, stage 1 (engine only, opt in)

- **`ProofChecker(kernel="exam" | "course" | "scratch")`** checks whether each line *follows*, not only whether it is true. It is the first stage of the design in *A Proof Kernel for Lemmata*.
  - **A line that cites its premises may use only those.** `x² > 25 [using h2]` is refused when h2 doesn't give it, and the message names the fact that does.
  - **Each line is classified by the reasoning that settled it**, and refused as too big a step when the level doesn't allow that: a whole ε–δ statement decided in one line, or a divisibility settled by checking remainders. Under *Exam*, a limit, derivative or series evaluated in one line is refused too.
  - **The audit names the tactic and the premises used**, for example "Kernel: linarith … (from line 5 and line 4)".
  - **Calibrated on the course packs:** at *Course*, all 133 entries give the same verdict as without the kernel.
  - **Without the option, nothing changes.**
- **Stage 2, the structural rules:**
  - **`QED` is goal closure.** It no longer proves the claim for you: a proof that is only `Given n : Int`, then `QED`, is refused for a divisibility or a quantified claim, and the message names what the proof never showed.
  - **A conclusion after a complete case split is by the case rule** ("By cases: … holds in each case …"), not decided by a solver.
  - **Induction on a sum is recognised as working at *Exam*:** peeling off the last term and using the inductive hypothesis.
  - **A line that follows from the line above is classified by that argument**, even when the engine reached it another way. This fixes stage 1 refusing the User Guide's own proof by cases.
- **The typed core and its tactics:**
  - **One typed form for the maths** (`aether.kernel.core`). A line's maths is translated once into typed terms: naturals, integers, rationals, reals, with division's side conditions recorded.
  - **Separate tactics on those terms** (`aether.kernel.tactics`): `ring`, `field`, `subst`, `linarith` and `nlinarith`. The audit now names the weakest one that proves a line, rather than guessing from which solver answered.
  - **`linarith` treats products of unknowns as atoms**, so the Archimedean step (`nε ≤ β − ε` from `(n+1)ε ≤ β`) is linear, as it should be.
  - **The tactics label lines; they don't decide them.** All 133 course-pack entries still agree at *Course*.
  - **Fixed:** with the kernel on, a hard induction step ("7ⁿ − 3ⁿ is divisible by 4") could come back "inconclusive". The kernel's own solver questions now run apart from the check's, so they can't change its answer.

### What each line used, and what was computed (engine only, opt in)

- **`ProofChecker(dependencies=True)`** names the premises each line that checked was proved from (`StepResult.premises`): the equalities SymPy substituted, the unsat core of Z3's proof, the line a chain continues, the source of an `Obtain … from`, an induction's base case and step, a result cited by name. When the engine can't say everything a line used, `premises_complete` is False rather than a guess. This is what a proof graph needs.
- **`ProofChecker(trace=True)`** lists the backend calls made checking each line (`StepResult.trace`): what Z3 or SymPy was asked, the answer, how long it took, nested under the call that made it.
- **Neither changes a verdict or a message.** The audit's unsat cores run on a Z3 context of their own, so they can't steer the check. `tests/lecture_notes/dependency_parity.py` checks this on every pack entry, with and without the kernel. On the packs, 98% of the lines that check have a complete list of premises, at no measurable cost.

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
