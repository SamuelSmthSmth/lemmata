# AGENTS.md — Lemmata Project Guide for UI Development

## ⚠️ Critical Rules for Agents

1. **Separation of Concerns (Engine vs. UI):**
   - **When working on the UI (`ui/`):** Do **not** edit, move, or delete any files inside `src/aether/core/`, `src/aether/parser/`, `src/aether/engine/`, or `tests/`. All UI code, assets, and entry points must live in the dedicated top-level `ui/` directory.
   - **When working on the Engine (`src/aether/`, `tests/`):** You **may** edit and add files in `src/aether/` and `tests/`. Do **not** modify `ui/`, and always preserve backwards compatibility with the public Python API (`ProofChecker`, `ProofReport`, `StepResult`, `StepStatus`, `ParseError`) verified by `uv run python ui/verify_examples.py`.
2. **Use `uv` for Python environment management.**
   Run commands and scripts via `uv run ...` (the virtual environment is already configured in `.venv` with Python 3.12, `lark`, `sympy`, and `z3-solver`).

---

## 1. What Lemmata Is

> **Naming.** Lemmata is the working product name (from `ui/site.json`; "Leaner" is pending permission from the Lean FRO). The engine is still the `aether` Python package, with the `aether` CLI and `.aether` files, and the public API below is unchanged. Never hard-code the product name in the UI: read it from `site.json` (Python: `ui/site.py`; frontend: `js/site.js` or `[data-site-name]`).

**Lemmata** is a lightweight, Controlled Natural Language (CNL) "Proof Intern" / step-by-step mathematical proof checker designed for undergraduate pure mathematics (such as Real Analysis and Abstract Algebra).

Instead of requiring users to learn complex formal type-theory compilers (like Lean 4), Lemmata lets users write structured, human-readable mathematical proofs using natural deduction keywords (`Let`, `Given`, `Assume`, `Obtain`, `Step:`, `Therefore`, `Hence`, `QED`) combined with standard mathematical expressions.

### How the Engine Works Under the Hood
- **Parser (`aether.parser`)**: Uses a Lark LALR grammar with Python-style indentation tracking (`AetherIndenter`) to parse proof documents into typed AST nodes (`DocumentNode`, `TheoremNode`, `VarDeclNode`, `AssumeNode`, `ObtainNode`, `StepNode`, `DeduceNode`, `SubProofNode`).
- **Scope & Context Manager (`aether.engine.context`)**: Tracks nested proof scopes, variable types (`Nat`, `Int`, `Rat`, `Real`, `Complex`, `Bool`), active hypotheses, and equational/inequality chains. Enforces guardrails against:
  - **Strict Monotonicity Violations**: Rejecting conflicting inequality directions in a chain (e.g., mixing `<=` and `>=`).
  - **Implicit Variable Capture**: Preventing existential witnesses (`Obtain k ...`) from shadowing variables already in scope.
  - **Illegal Universal Generalization**: Preventing `forall x` conclusions while `x` is constrained by an undischarged assumption.
- **SymPy Algebraic Backend (`aether.engine.algebra`)**:
  - Verifies algebraic rewrite steps (`lhs = rhs`) by checking whether `lhs - rhs` simplifies to `0` (including substituting active context equalities like `n = 2 * k`).
  - Extracts **Domain Obligations** prior to simplification (e.g., non-zero denominators `B != 0` in `A / B`, and non-negative radicands `A >= 0` in `sqrt(A)`).
  - Generates **concrete numeric counterexamples** when an algebraic step is false (e.g., `Counterexample at x=3: LHS = 24, RHS = 23`).
- **Z3 SMT & Logic Backend (`aether.engine.logic`)**:
  - Verifies inequalities (`<`, `<=`, `>`, `>=`, `!=`), logical deductions, quantifiers (`exists`, `forall`), existential witnesses (`[witness: ...]`), and built-in prelude predicates (`Even(x)`, `Odd(x)`, `MultipleOf(a, b)`, `Divides(a, b)`, `Positive(x)`, `NonNegative(x)`).
  - Checks whether extracted domain obligations are guaranteed by active assumptions, and extracts counterexample assignments when obligations or deductions fail.

---

## 2. Example Lemmata Proof Syntax

```text
Theorem: "Even square theorem"
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]
    Hence MultipleOf(n^2, 4)
QED
```

Top-level scratchpad scripts (without a `Theorem:` / `Proof:` wrapper) are also valid:

```text
Let x, y : Real
Assume x > 2
Step: (x^2 - 4) / (x - 2) = x + 2
Step: > 4
```

---

## 3. Engine Python API Reference (How the UI Calls the Backend)

Import `ProofChecker`, `StepStatus`, and `ParseError` directly from `aether`:

```python
from aether import ProofChecker, ProofReport, StepResult, StepStatus, ParseError

# strict_domains=False (default): unguarded domain obligations produce StepStatus.WARNING
# strict_domains=True: unguarded domain obligations produce StepStatus.INVALID
checker = ProofChecker(strict_domains=False)

try:
    reports: list[ProofReport] = checker.check_source(source_text)
except ParseError as err:
    # err.message: str
    # err.line: int | None
    # err.col: int | None
    ...
```

`check_source` also takes three optional keyword arguments, all backward
compatible: `file_path` (the checked file's path, for relative imports),
`sources` (a `Mapping[str, str]` of other files by path), and `citations` (the
names a step may cite with `by …`, each mapped to the `sources` key that proves
it, or to `[[label, key], …]` when it names more than one; see
`aether.engine.citations`). `import` resolves
against `sources` first — relative to `file_path`, then the root — and then
falls back to the disk search. The web app passes its browser workspace this
way.

### Data Structures Returned by `checker.check_source(source_text)`

#### `ProofReport`
- `theorem_name: str | None` — Name of the theorem (or `None` for top-level scratchpad statements).
- `results: list[StepResult]` — Ordered list of verification results for each statement in the proof.
- `is_valid: bool` — `True` if no step has `StepStatus.INVALID`.
- `has_warnings: bool` — `True` if any step has `StepStatus.WARNING` or unresolved `domain_warnings`.
- `format_report() -> str` — Returns a plain-text formatted audit log.

#### `StepResult`
Each item in `report.results` corresponds to one parsed statement and contains:
- `statement: StatementNode` — The AST node (`str(step.statement)` gives the canonical readable statement).
- `line: int | None` — 1-based source line number in the input document.
- `status: StepStatus` — Enum value:
  - `StepStatus.VALID` (`"VALID"`)
  - `StepStatus.WARNING` (`"WARNING"`)
  - `StepStatus.INVALID` (`"INVALID"`)
- `message: str` — Human-readable explanation of the verification result or failure reason.
- `backend: str` — Which engine component verified or rejected the step (e.g., `"Context"`, `"SymPy"`, `"SymPy (Witness)"`, `"SymPy+Logic"`, `"Z3"`, `"Definition+Z3"`, `"ChainGuard"`, `"ScopeGuard"`, `"SubProof"`).
- `scope_depth: int` — Nesting depth of the statement (`0` for top-level, `1+` for subproofs).
- `active_variables: dict[str, str]` — Snapshot of declared variables and their canonical types at this point in the proof (e.g., `{"n": "Int", "k": "Int"}`).
- `active_hypotheses: list[str]` — Snapshot of active assumptions and derived facts in scope at this point (e.g., `["h1: Even(n)", "n = (2 * k)"]`).
- `domain_warnings: list[str]` — List of unresolved domain obligation messages triggered on this line (e.g., `["Unresolved domain obligation: requires non-zero denominator ((x - 2) != 0) in (((x ^ 2) - 4) / (x - 2)) (violated at x=2)."]`).
- `citation: dict | None` — The result a `by …` citation used: `{"cited", "label", "key", "claim"}`.
- `hints: list[dict]` — What to do about a step that did not check, in the student's notation: `{"message", "fix"?}`, where a fix is `{"line", "insert_before", "label"}` or `{"line", "col_start", "col_end", "text", "was", "label"}` (1-based; see `aether.engine.hints`). Empty for a step that checks.
- `counterexample: str | None` — Concrete counterexample assignment if the step failed and one was found (e.g., `"Counterexample at x=3: LHS = 24, RHS = 23"` or `"x=1"`).

---

## 4. What Needs to Be Present in the UI

The UI should expose the full capabilities of the Lemmata engine to the user. It must include the following functional elements and information readouts:

1. **Proof Input / Editor Area**
   - Multi-line text input where the user writes or edits Lemmata CNL proof scripts.
   - Support for loading pre-built example proofs (e.g., valid Even Square theorem, Odd Square theorem, an algebraic blunder with a counterexample, an unguarded division-by-zero example, and a guarded domain example) so users can test features immediately. In the current app these live in the **Library** (`GET /api/library`), alongside the course packs.

2. **Overall Proof Verdict & Controls**
   - Overall proof status readout (`VALID`, `VALID (with domain warnings)`, `INVALID`, or `PARSE ERROR`; the server adds `TIMEOUT` when a check overruns its budget).
   - A toggle for **Strict Domain Checking** (`strict_domains=True` vs `strict_domains=False`), controlling whether unguarded divisions/square roots are treated as warnings or hard errors.
   - Parse error display showing line number, column number, and error message whenever `ParseError` is raised.

3. **Step-by-Step Auditor Readout**
   For each statement (`StepResult`) in the proof, display:
   - **Line number** (`result.line`) and **statement text** (`str(result.statement)`).
   - **Verification status** (`VALID`, `WARNING`, `INVALID`).
   - **Backend badge / label** (`result.backend`, e.g., `SymPy`, `Z3`, `Context`, `Definition+Z3`, `ChainGuard`, `ScopeGuard`).
   - **Verification message** (`result.message`).
   - **Concrete counterexample** (`result.counterexample`), highlighted clearly whenever a step fails.
   - **Domain obligation warnings** (`result.domain_warnings`), whenever division by zero or negative square-root radicands are not ruled out by the context.

4. **Context & State Inspector**
   Allow the user to see what the "Proof Intern" knows (either for the selected step or at the current point in the proof):
   - **Declared Variables & Types** (`result.active_variables`, e.g., `n : Int`, `x : Real`).
   - **Active Hypotheses & Derived Facts** (`result.active_hypotheses`, e.g., `h1: Even(n)`, `n = (2 * k)`).
   - **Scope Depth** (`result.scope_depth`).

The app around these four — the workspace of many proofs, the Library, the
Guide, Settings and the command palette — is described in `ui/README.md`, and
its design context in `PRODUCT.md` and `DESIGN.md`.

### Course packs

`courses/*.json` holds the MTH2008, MTH2010 and Notation packs: transcriptions
of lecture-note results keyed to the notes' numbering, each with the verdict it
must produce (`kind: proof | trap`; a trap carries an `explanation`). They are
in **pack format 1**, defined and validated by `src/aether/packs.py`
(`validate_pack`, `load_packs`), which is the one authority on what a pack is;
`courses/pack.schema.json` is a JSON Schema copy for authors, and
`tests/test_packs.py` keeps the two in step. A pack has a scoped `name`
(`core/mth2008`), a semver `version`, a `license`, and an **optional**
`courses` list, so a pack can be a topic rather than a module.

They are data shared by both sides: `tests/test_lecture_notes.py` checks every
entry, and the UI serves them as the bundled catalogue the browser installs
from. Neither side imports the other's code, so the engine/UI separation above
still holds; changing an entry's `expected` is an engine-side change. **Raise a
pack's `version` when you change it**, so browsers that installed it are
offered the update (a same-version edit is still offered, but a version says
what changed).

**The pack registry** ([`SamuelSmthSmth/lemmata-packs`](https://github.com/SamuelSmthSmth/lemmata-packs), public) publishes packs anyone can install. Its CI checks every entry with the engine the app publishes (`static/engine/`), so a change to the engine that alters a published verdict will fail the registry's weekly run. Publish a changed core pack with `uv run python ui/publish_packs.py ../lemmata-packs` after raising its version.

A proved theorem in an installed pack can be imported into a student's proof:
`import "@core/mth2010/<entry-id>"`. The browser sends installed packs' proof
entries as `sources` keyed `@<name>/<entry-id>.aether`, and the engine finds
them because the `.aether` extension may be left off an import.

---

## 5. Verification & Tooling

Every claim this repo makes is checked by a script you can run yourself:

| Command | What it guards |
| :--- | :--- |
| `uv run pytest -q` | the engine (never imports `ui/`) |
| `uv run python tests/lecture_notes/run_corpus.py [filter] [-v]` | the MTH2008 / MTH2010 lecture-note corpora (also part of `pytest`), one process per entry under a wall-clock budget, with full reports for anything off |
| `uv run python ui/verify_examples.py` | each bundled example still produces the verdict its blurb advertises |
| `uv run python ui/verify_capabilities.py` | the CNL capability matrix listed in `USER_GUIDE.md` — and that the table published there still matches the pins; `--markdown` prints it as the doc table, and every snippet runs under a wall-clock budget (`--budget`, 10s) because Z3's soft `timeout` is not enforceable in-process |
| `uv run python ui/verify_server.py` | the HTTP API (check budget and `TIMEOUT`, workspace imports, library, capabilities), both export styles, the vendored asset graph, and every *Try it* example in the Guide |
| `node ui/verify_frontend.mjs` | the CodeMirror tokenizer, the frontend module graph, layout rules and the `.zip` reader/writer |
| `node ui/verify_wasm.mjs` | every pinned verdict (course packs, examples, capability probes) gives the same answer inside Pyodide — the browser's Python — as natively, with timings; needs `uv run python ui/vendor_pyodide.py` once |
| `uv run python ui/verify_browser.py --static` | the static build (`uv run python ui/build_static.py` → `dist/`): checking, imports, packs, LaTeX and the budget with the engine in the browser and no server |
| `uv run python web/verify_web.py` | the public site (`web/`, built by `ui/build_site.py` with the app at `/app/`): every link and asset, the landing page's audits against the engine, the Vercel rules, the installer, and in a browser the old-permalink redirect, the storage notice, the scrub and phone widths |
| `uv run python desktop/verify_desktop.py` | the desktop app (`desktop/`, Tauri): the real app driven over WebDriver on its own webview (WebKitGTK), checking under its CSP, the registry, exports into Downloads, links to the system browser, and storage across a restart; needs Rust, Node and `tauri-driver` |
| `uv run python ui/verify_browser.py` | real-browser behaviour: editor keys and round-trip, panels, theme, the workspace (files, tabs, IndexedDB, migration, imports, `.zip`), diagnostics, templates, palette, Library exercises, settings |

For ad-hoc browser work — screenshots, accessibility audits, HARs, layout diffs —
see `TOOLING.md`: what the `agent-browser` CLI can do, its argument-order and
session footguns, and the recipes this repo uses to verify the UI.
