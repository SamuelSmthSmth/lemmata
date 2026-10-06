# Changelog

What changed between releases of Lemmata, newest first. The engine is the `aether` Python package; its public API (`ProofChecker`, `ProofReport`, `StepResult`, `StepStatus`, `ParseError`) stays backward compatible within these releases.

## Unreleased

### Accounts and sync

- **An optional account keeps your work the same on every device.** Settings → Account: sign in with an emailed link, Microsoft, GitHub or Discord (Google when it is turned on). Your proofs, their History, folders, the check history, installed packs, settings and panel layout all sync; which tabs are open stays with each device.
- **Nothing is lost when two devices disagree.** The newer edit wins everywhere, and the other is kept in the proof's History ("From your other device" or "Kept from this device"). Offline, changes wait and go up when you are back.
- **Signing in on a second device merges, not duplicates.** The same proof at the same path is kept once; two different proofs at one path are both kept, one renamed "(2)".
- **Download my data** and **Delete account** in Settings. Signing out, or deleting the account, leaves this browser's copy where it is.
- Not in the desktop app yet.

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
