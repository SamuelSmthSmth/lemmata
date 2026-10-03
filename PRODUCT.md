# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Undergraduate pure-mathematics students: anyone, not one cohort. They are working through a module's lecture notes and tutorial sheets (Real Analysis, Abstract Algebra, and similar) and want to know whether a proof they have written down actually holds, and where it breaks if it does not. They use it at a desk, alongside the notes, in sessions of one proof or one sheet at a time.

## Product Purpose

Lemmata checks proofs written in a controlled natural language (`Let`, `Assume`, `Obtain`, `Step:`, `Therefore`, `QED`) step by step. Each step is verified by SymPy (algebra) or Z3 (logic and inequalities), and a failure comes back with the reason and, where one exists, a concrete counterexample. Success is a student who finds the exact step their reasoning slipped on and understands why, without first learning a formal proof assistant.

## Positioning

A "proof intern": it reads proofs written the way the notes write them, `∀ ε > 0, ∃ δ > 0`, `a⁻¹`, `n!` and `∞` included, and audits every line. Formal assistants (Lean, Coq) demand type theory before the first proof, and a CAS checks single calculations, not arguments. Lemmata sits between them: the whole proof, in the notes' own notation, checked line by line with counterexamples.

## Operating Context

- Students write a proof, see a verdict per line, inspect the proof state (declared variables, active hypotheses, scope) at any step, fix it, and export it to LaTeX or PDF for submission or revision.
- Course packs transcribe a module's lecture notes into checkable proofs, keyed to the notes' own numbering ("Example 2.18"). MTH2008 Real Analysis and MTH2010 Algebra are the first two packs. The packs ship Lemmata transcriptions only, never the original notes.
- Packs also carry deliberate blunders ("traps") that students can study as spot-the-error exercises.
- Packs are installable packages (format 1, `aether.packs`): students install, uninstall, update and export them in the browser, install one from a shared `.pack.json`, and make their own from a workspace folder. A course code is optional. The public pack registry (`SamuelSmthSmth/lemmata-packs`) is where anyone publishes packs: pull requests are the moderation, and its CI re-checks every entry with the engine students use. The app searches it and installs from it, offline-tolerant and optional. An institution can point its copy at its own registry through `site.json`.

## Capabilities and Constraints

- Runs locally with `uv run python -m ui`, or as a static site with the checker running in the browser (Pyodide; `ui/build_static.py`), which is how it will be hosted (Vercel), wrapped as a desktop app, and self-hosted by institutions. Every pinned verdict is identical in both.
- A student's work lives in their browser: no accounts or server-side storage in this version, with file import and export as the backup. The storage layer must allow accounts to be added later.
- No build step for development and no runtime network access: vanilla ES modules with vendored CodeMirror 6 and Web Awesome, served by FastAPI. The static build is a distribution step only.
- Every engine call runs under a hard wall-clock budget; a stalled solver query answers TIMEOUT rather than hanging.
- The engine's capability matrix (`USER_GUIDE.md` §8) is the honest statement of what is and is not supported; the product never claims more.

## Brand Commitments

- The working name is **Lemmata**, with the tagline "Proof intern". The preferred name, **Leaner**, waits on written permission from the Lean FRO (its trademark policy covers marks containing "Lean"); until then nothing ships under it.
- The name lives in one place, `ui/site.json`, so a rename (or an institution's own branding) is a config change. The engine package, the CLI, the `.aether` file extension and storage keys keep the old `aether` identifier for compatibility; they are not the brand.
- The existing visual identity is kept and refined, not replaced: the user chose refinement.

## Evidence on Hand

- 19 bundled example proofs (`ui/examples.py`) and standalone proofs in `examples/`.
- The lecture-note corpus: 133 entries across MTH2008, MTH2010 and a notation/soundness set, all verified by the test suite (`tests/lecture_notes/`).
- The capability matrix in `USER_GUIDE.md`, generated from `ui/verify_capabilities.py`.
- No user testimonials, usage numbers or institutional endorsements exist; none may be implied.

## Product Principles

1. **The failing step is the event.** Everything that verifies recedes; the first broken step, its reason and its counterexample are what the interface exists to show.
2. **The notes' notation, not ours.** Students write what their lecturer writes; the tool adapts to the mathematics, never the reverse.
3. **Honest about limits.** When the solver cannot decide something, say so plainly instead of dressing a solver artefact up as a counterexample.
4. **Never lose a student's work.** Every destructive action is snapshotted or undoable, and storage failures are announced, not swallowed.
5. **A study tool, not a grader.** It explains and points; it does not score students.

## Accessibility & Inclusion

The current interface is fully keyboard-operable (roving tabindex in the auditor, arrow-key panel moves) and screen-reader ordered. New views must keep that bar: every view reachable and operable from the keyboard, WCAG 2.2 AA contrast in both themes, and reduced motion respected.
