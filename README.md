# Lemmata

**A proof intern.** Write a proof the way your lecture notes write it, and Lemmata checks every line. When a step fails, it says why, and where it can, gives a counterexample.

[Open it in your browser](https://lemmata.sous.systems/app/) · [Download for Linux, Windows or macOS](https://lemmata.sous.systems/download/) · [What's new](CHANGELOG.md)

```text
Theorem: "A slip in the algebra"
Proof:
    Let x : Real
    Step: (x + 1)^2 = x^2 + 2*x + 1
    Step: (x + 3)^2 = x^2 + 6*x + 6
QED
```

```text
  L3   ✓ Let x : Real  [Context]
  L4   ✓ Step: ((x + 1) ^ 2) = (((x ^ 2) + (2 * x)) + 1)  [SymPy]
  L5   ❌ Step: ((x + 3) ^ 2) = (((x ^ 2) + (6 * x)) + 6)  [SymPy]
         ↳ Counterexample at x=3: LHS = 36, RHS = 33
Result: INVALID
```

## Who it's for

Students writing proofs, from A Level and Further Maths to undergraduate pure mathematics (Real Analysis, Algebra, number theory). You write in plain proof language, with the notes' own symbols:

- **Structure:** `Let`, `Given`, `Assume`, `Obtain`, `Step:`, `Since`, `By`, `Therefore`, `Base case`, `Inductive step`, `Case`, `QED`.
- **Notation:** `∀ ε > 0, ∃ δ > 0`, `|x − 2|`, `n!`, `a⁻¹`, `-2 < k < 2`.

There's no type theory to learn first, unlike Lean or Coq. When you're ready for those, *Show in Lean* turns your proof into a Lean 4 skeleton.

## What it checks

- **Algebra** with SymPy, and **logic and inequalities** with Z3. A failing step comes back with its reason and, where one exists, a concrete counterexample.
- **Every proof method A Level and the notes use:** deduction, cases (it checks they cover everything), contradiction (√2 is irrational, as the textbook writes it), counterexample, and induction. Induction works from any starting value, and with recurrences that use several earlier terms.
- **Domains:** a division or square root that nothing rules out is flagged.
- **Whether each line follows, not just whether it's true.** At the *Course* level (the default), a true line that skips the argument is refused as too big a step: a whole ε–δ statement at once, or a divisibility settled by checking remainders. The message says what to write instead. *Exam* also wants a derivative, limit or sum worked; *Off* checks only truth.
- **Show your working (optional):** a step that skips what an exam question wants to see, like the product rule or a sum's closed form, gets a warning naming it.
- **What each line used, and what the checker did:** arcs in the auditor from each line to the lines it rests on, and a Trace tab with every question put to SymPy and Z3 (`lemmata --trace` on the command line).
- **The proof state at every line:** the variables, the hypotheses, and what each step relied on.

What it can and can't do is listed exactly, and checked on every change, in the [capability matrix](USER_GUIDE.md#9-capability-matrix-what-parses-verifies-and-refuses).

## The app

- **Proofs:** a workspace of proofs, kept in your browser, with `import` between them. The editor has completion, templates, a symbol strip, and an optional typeset view of the maths.
- **Library:** course packs (MTH2008 Real Analysis, MTH2010 Algebra, the notation set), installed and updated like packages. Anyone can publish one to the [pack registry](https://samuelsmthsmth.github.io/lemmata-packs/).
- **Guide:** the handbook, with a *Try it* button on every example.
- **Export** to LaTeX, PDF or Lean.

It runs in the browser with nothing to install, as a desktop app that works offline, or self-hosted. No account is needed and your work stays on your machine; an optional account syncs it between your devices.

## Documentation

| For | Read |
| --- | --- |
| Writing proofs | [`USER_GUIDE.md`](USER_GUIDE.md): the language, proof methods, templates and the capability matrix. The same material is in the app's Guide. |
| What changed | [`CHANGELOG.md`](CHANGELOG.md) |
| The engine's internals | [`AI_REFERENCE.md`](AI_REFERENCE.md): grammar, AST, how each kind of step is verified, the Python and HTTP APIs |
| Contributing | [`AGENTS.md`](AGENTS.md): the rules, the API contract and every verification script. [`ui/README.md`](ui/README.md): how the app is built. [`desktop/README.md`](desktop/README.md): the desktop app. [`TOOLING.md`](TOOLING.md): driving a browser in tests. |
| Design | [`PRODUCT.md`](PRODUCT.md) and [`DESIGN.md`](DESIGN.md) |

## Running it from source

Lemmata uses [`uv`](https://docs.astral.sh/uv/) and Python 3.12.

```bash
git clone https://github.com/SamuelSmthSmth/lemmata.git
cd lemmata
uv sync
```

Check a proof from the command line (`aether` and `lemmata` are the same command):

```bash
uv run lemmata examples/sequence_bounds.aether
uv run lemmata --help
```

Run the app locally, at <http://127.0.0.1:8000>:

```bash
uv run python -m ui
```

Every check runs in a worker process under a time budget. A step the solver cannot settle reports `TIMEOUT` instead of hanging.

Build the static site, with the checker running in the browser via Pyodide, to host anywhere:

```bash
uv run python ui/vendor_pyodide.py && uv run python ui/build_static.py
python -m http.server --directory dist
```

The public site is `uv run python ui/build_site.py`: the app at `/app/` inside the landing, download and legal pages from `web/`. The desktop app is the same build in a Tauri window. See [`desktop/README.md`](desktop/README.md).

## Checks

Every claim the repo makes is checked by a script. The main ones:

```bash
uv run pytest -q                         # the engine and the lecture-note corpora
uv run python ui/verify_examples.py      # each bundled example gives its advertised verdict
uv run python ui/verify_capabilities.py  # the capability matrix, and that USER_GUIDE.md's copy matches it
uv run python ui/verify_server.py        # the HTTP API, exports and the Guide's examples
node ui/verify_frontend.mjs              # the editor's tokenizer, module graph and frontend rules
uv run python ui/verify_browser.py       # the app in a real browser
```

The full table, including the static build, the public site, the desktop app and Pyodide, is in [`AGENTS.md`](AGENTS.md#5-verification--tooling). CI also compiles every Lean skeleton the repo pins.

## Licence

The code is [Apache-2.0](LICENSE). The course packs in `courses/` are CC BY-SA 4.0 (see [`courses/LICENSE.md`](courses/LICENSE.md)). They are our own transcriptions; the original lecture notes are not distributed.

The engine is the `aether` Python package and proofs are `.aether` files. Those names are kept for compatibility; *Lemmata* is the product name.
