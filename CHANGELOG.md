# Changelog

What changed between releases of Lemmata, newest first. The engine is the `aether` Python package; its public API (`ProofChecker`, `ProofReport`, `StepResult`, `StepStatus`, `ParseError`) stays backward compatible within these releases.

## Unreleased

### The kernel decides

- **At the Exam, Course and Scratch levels, a line passes because a named rule proved it,** not because the solver agreed. The badge names the rule (`Kernel: ring`, `linarith`, `nlinarith`, …), and the solver now checks the rule's answer: any refusal it makes still stands.
- **A true line no rule can show is passed with a warning,** "Checked by the solver only", with advice to split it or cite what it uses. No pinned proof has one.
- **Square roots are understood:** `√a·√b = √(ab)` for a, b ≥ 0, the root of a difference written as a quotient, and bounds such as `√2 > 1` are now proved by the rules, so the lecture notes' density and continuity proofs are checked step by step.
- A line resting on facts the rules cannot read (a group's axioms, `Bounded(h)`) keeps the solver's verdict, and says so.
- *Off* is unchanged.

### Calculus by named rules

- **At a level, a derivative or a definite integral is checked by the kernel's own rules,** and the badge names them: `Kernel: power rule`, `product rule`, `quotient rule`, `chain rule`, `FTC`. The kernel differentiates by those rules itself, never by asking SymPy. For an integral, SymPy may *propose* an antiderivative, but the kernel checks it (its derivative is the integrand, and the integrand is continuous on the interval) before using F(b) − F(a). 37 of the course packs' derivative and integral lines are now checked this way.
- **Limits and finite sums too.**
  - **Limits:** a limit goes by substitution, by cancelling a common factor, by the algebra of limits, by L'Hôpital's rule (with the kernel's own derivatives), by dominant terms at infinity, or by the squeeze.
  - **Finite sums:** a sum is added up, telescoped, has its last term peeled off, or is replaced by a closed form that SymPy proposes and the kernel checks by induction.
  - **The traps stay refused:** the packs' limit traps, the two-sided `1/x → ∞` and `sin(1/x) → 0`, are still refused.
  - **Coverage:** 63 of the packs' and tests' limit and sum lines are now checked this way.
  - **Still the solver's:** infinite series and `ρⁿ → 0` need a convergence or |ρ| < 1 premise, so they stay with the solver.
- A line the rules do not reach (an integral up to a symbolic bound of a function like log) keeps the solver's verdict, as before. No verdict changes.

### Show in Lean proves steps

- **Each step now tries the Lean tactic for the rule Lemmata's kernel checked it by,** falling back to `sorry` only where that tactic can't finish it: `first | (ring; done) | … | sorry  -- Kernel: ring`.
- **On every pinned proof, Lean itself proves 320 of the 440 steps it is asked to try. A step about absolute values splits each `|t|` into its two cases first, as Lemmata's solver does.** The rest stay `sorry`, as before.
- **Every skeleton still compiles** against the pinned Mathlib.
- **Stays `sorry`:** calculus steps (Lean's `deriv` and `Tendsto` goals need lemmas, not one tactic) and steps that did not check.

### Quantified statements by natural deduction

- **A quantified line is taken apart as a written proof would:** ∧-introduction (each part), ∀-introduction (a fresh variable), ⇒-introduction (assume the left, prove the right). Each leaf goes to a core tactic.
- **The badge shows the whole argument,** for example `Kernel: ∀-intro, ⇒-intro, nlinarith`.
- **An `exists` without a witness is left to the proof,** since choosing one isn't a rule's job.
- **Levels behave as before:** at *Course* a whole ∀-statement in one line is still refused as too big a step.

### Groups, subgroups and rings by named rules

- **Group identities by word reduction:** `Kernel: group axioms`.
  - An element built from `op`, `inv` and the identity, in either notation (`op(a, b)` or `a * b`, `a^-1`), is reduced the way the group axioms allow. Two sides that reduce to the same word are equal in every group.
  - No solver is asked.
- **Hypotheses join in:** `Kernel: group axioms and hypotheses`.
  - Equations, and ∀-statements such as a homomorphism's `f(op(x, y)) = star(f(x), f(y))`, count only at elements known to lie in the group.
  - This covers cancellation, uniqueness of the identity, and the image-and-kernel proofs.
- **Subgroup membership:** `Kernel: subgroup closure` or `normal subgroup`. A product of members, an inverse, the identity, or a conjugate in a normal subgroup.
- **Rings and fields:** `Kernel: ring axioms` or `field axioms`. A field's `inv(x)` counts only where `x ≠ zero` is assumed.
- **Traps stay refused:** "a group is abelian", `(ab)⁻¹ = a⁻¹b⁻¹` and `a²b² = (ab)²`, outside an abelian group.

### Honest counterexamples

- **A counterexample is shown only when it is one.** The solver knows only what it is told about functions like `sin` or `arctan`, so it could call x = 2 a counterexample to `sin²x + cos²x ≥ 1`. Now the line is checked at those values with each function's real meaning first; if it holds there, the step says it could not be verified and that the solver's values are not a counterexample.
- **Two more true lines are proved:** `3ⁿ ≥ 3` from `n ≥ 1` (a claim about powers gets a second try with the fact that a base of at least 1 only grows), and `∀x, x ≥ 0 ⇒ sqrt(x)² = x`, which was refused with the false counterexample x = 0.
- **`floor`, `ceiling` and `n!` are understood:** `floor(x) ≤ x`, `ceiling(x) ≥ x`, `n! ≥ 1` and `n! ≥ n` are proved, where before they were refused with counterexamples that were wrong (x = −1, n = 0).

## 0.3.0 (2026-10-06)

The proof kernel release. Lemmata used to check whether each line was true; now it can check whether each line *follows*. A line that is true but skips the argument is refused as too big a step, with what to write instead. Underneath, a typed core and named tactics say what each line needed. You can also see what each line was proved from, as a graph, and what the checker did, as a log.

### Checking levels

- **A *Level* menu in the tool strip:**
  - *Off* checks as before: every true line passes.
  - *Course*, the default for new proofs, refuses a line that is true but skips the argument (a whole ε–δ statement at once, a divisibility settled by checking remainders) and says what to write instead.
  - *Exam* also wants a derivative, limit or sum worked, not written down. At *Exam*, the *Show working* switch stands aside, because the level already asks for it.
  - *Scratch* accepts anything the solvers decide.
- **A line that cites its premises may use only those.** `x² > 25 [using h2]` is refused when `h2` doesn't give it, and the message names the fact that does.
- **`QED` closes only a claim the proof reached.** `Given n : Int` followed by `QED` no longer proves a divisibility for you.
- **A conclusion after a complete case split is accepted by the case rule:** "By cases: … holds in each case …".
- **Your existing work is safe.** Each proof keeps its own level, carried by its link and its History snapshots. A proof or link from before levels opens at *Off*, as it was checked.
- **On the course packs, *Course* changes no verdict:** all 133 entries agree.

### What each line used, and what the checker did

- **The proof graph:** select a step and the auditor draws arcs to the lines it was proved from, with their line numbers lit, and to the lines that use it. *Used* and *Used by* in Context & state list the same facts as links. A button in the auditor's head shows the whole graph.
- **The Trace tab:** the checker's log, line by line. Each line shows what SymPy and Z3 were asked, the answer and the time, with a block's own lines nested under it.
- **Both can be turned off** in Settings (*What each line used*), which makes checking about a tenth quicker.

### Proofs you can now write

- **Several names in one quantifier**, as the notes write them: `forall a, b : Int, …`, `∀ a, b ∈ ℤ, …`, `∀ ε, δ > 0, …`.

### Packs

- **A pack, or one entry, can record its checking level** (`"level": "course"`), and its verdicts then hold at that level. A pack without one means what it always meant.
- **The app and the registry use the level everywhere:** checking a pack, making one (each proof is recorded at its own level), and opening an entry or an exercise, so an exercise's answer is the line that fails at the pack's level.
- **The core packs (1.0.1) are recorded at *Course*.**

### On the command line

- **`lemmata --used FILE`** lists what each line was proved from, and **`--trace`** lists the calls made to SymPy and Z3: the same log as the Trace tab.

### For developers

- **`ProofChecker(kernel="exam" | "course" | "scratch")`:** the proof kernel (`aether.kernel`). It has a typed core and the tactics `ring`, `field`, `subst`, `simp`, `linarith` (products of unknowns as atoms), `nlinarith` and `residues`, which label each line with the weakest one that proves it.
- **Shadow mode** (`tests/lecture_notes/kernel_shadow.py`) compares the tactics with the engine on every line of the packs and tests. A test runs every pack trap and fails if a tactic proves its false line.
- **`ProofChecker(dependencies=True, trace=True)`** fills `StepResult.premises` and `StepResult.trace` without changing a verdict or a message.
- **Without these options, the engine checks exactly as 0.2 did.**
- **Documentation:**
  - the README is now a proper front page;
  - the User Guide has a *Proof methods* section and documents the levels;
  - *A Proof Kernel for Lemmata* describes the design.

### Fixed

- **With the kernel on, a hard induction step could come back "inconclusive"** ("7ⁿ − 3ⁿ is divisible by 4"). The kernel's own solver questions now run apart from the check's.
- **Shadow mode caught three false proofs in the new tactics before release:** `gcd(n, k) = 1`, `lcm(n, k) = nk` and `√(x − 1) ≥ 0`. All three are refused, and tested.
- **The tool strip no longer pushes the export and Lean buttons off screen** at 1440px.

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
