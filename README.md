# Aether — The Mathematical Proof Intern

**Aether** is a lightweight, Controlled Natural Language (CNL) step-by-step mathematical proof checker designed for undergraduate pure mathematics (Real Analysis, Abstract Algebra, Number Theory, and Combinatorics).

Instead of requiring formal type-theory compilers (like Lean 4 or Coq), Aether lets users write structured, human-readable mathematical proofs using natural deduction keywords (`Let`, `Given`, `Assume`, `Obtain`, `Step:`, `Therefore`, `Hence`, `Base case:`, `Inductive step:`, `QED`) paired with standard algebraic and logic expressions.

Behind the scenes, Aether orchestrates:
- **SymPy**: Algebraic equivalence verification, pre-simplification domain obligation extraction (denominators $\neq 0$, radicands $\ge 0$), and concrete numeric counterexample search.
- **Z3 SMT Solver**: Inequality verification, propositional and predicate logic, existential witness checks, exhaustiveness of case splits, and refutation models.
- **Scope & Context Guardrails**: Enforcing strict monotonicity in inequality chains, preventing implicit existential variable capture, and forbidding illegal universal generalization over undischarged hypotheses.

---

## 📚 Documentation

Guides for different audiences:

1. **[User Guide & Cheat Sheet (`USER_GUIDE.md`)](USER_GUIDE.md)**
   - **For Humans**: Designed for students and mathematicians writing proofs.
   - Contains the 30-second mental model, keyword cheat sheet, notation reference, top 6 copy-paste proof templates (direct proof, mathematical induction, $\varepsilon$-$\delta$ continuity, proof by contradiction, cases, custom predicates), and common gotchas.

2. **[AI & System Architecture Reference (`AI_REFERENCE.md`)](AI_REFERENCE.md)**
   - **For AI & Engine Developers**: Exhaustive technical documentation.
   - Complete formal grammar (Lark EBNF), AST dataclass taxonomy, scope manager mechanics, SymPy & Z3 solver algorithms, error taxonomy, Python public API, and REST API JSON schemas.

3. **[Browser Tooling (`TOOLING.md`)](TOOLING.md)**
   - **For Contributors**: What the `agent-browser` CLI can and cannot do, established by sweeping it, plus the recipes used to verify this UI (screenshots, axe-core audits, HARs, layout diffs).

---

## 🚀 Quick Start

### Installation & Environment Setup
Aether uses `uv` for Python virtual environment management:

```bash
# Clone the repository
git clone https://github.com/username/aether.git
cd aether

# Verify dependencies (Python 3.12, lark, sympy, z3-solver, fastapi, uvicorn)
uv sync
```

### Running the CLI
Verify a `.aether` proof file directly:

```bash
uv run aether examples/sequence_bounds.aether
```

Or pass a proof via standard input:

```bash
uv run aether << 'EOF'
Let x : Real
Assume h: x > 2
Step: (x^2 - 4) / (x - 2) = x + 2
Step: > 4
EOF
```

### Running the Web UI
Aether includes a study app that runs locally in your browser:

```bash
uv run python -m ui
```
Open your browser at `http://127.0.0.1:8000`.

- **Proofs** — a workspace of many proofs in folders and tabs, kept in your browser (IndexedDB), with `import` between them. A CodeMirror 6 editor with completion, proof templates, a symbol strip, and failing steps marked in the gutter; the step auditor and the context inspector beside it.
- **Library** — course packs transcribed from the MTH2008 (Real Analysis) and MTH2010 (Algebra) lecture notes, keyed to the notes' own numbering, plus the notes' notation and its traps and the worked examples. Open an entry beside your own copy of its proof, or open a trap as an exercise and find the failing line.
- **Guide** — the handbook in the app, with a *Try it* button on every example and the live capability matrix.
- **Settings**, a command palette (`Ctrl/Cmd+K`), LaTeX/PDF export, and a `.zip` backup of the whole workspace.

Every check runs in a worker process under a hard time budget, so a step the solver cannot settle reports `TIMEOUT` instead of hanging. Nothing leaves your machine. See [`ui/README.md`](ui/README.md) for how it is built.

---

## 🧪 Verification & Testing

Run all automated test suites:

```bash
# Run engine unit and integration tests, including the lecture-note corpora
uv run pytest -v

# Verify bundled UI examples match engine verdicts (19 examples)
uv run python ui/verify_examples.py

# Verify the documented CNL capability matrix (88 claims)
uv run python ui/verify_capabilities.py

# Verify FastAPI server and export endpoints (including PDF compilation)
uv run python ui/verify_server.py

# Verify CodeMirror tokenizer and frontend assets
node ui/verify_frontend.mjs

# Verify real-browser behaviour (editor, workspace, Library, palette, settings)
uv run python ui/verify_browser.py
```
