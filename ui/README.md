# Aether UI

A dual-purpose web front end for the Aether proof checker:

- a **FastAPI** backend that exposes the engine over a small JSON API
- a **dependency-free static frontend** (vanilla JS + CodeMirror 6) served by
  that same process

No `npm`, no build step, and no network access at runtime. The whole thing
starts with one command.

The engine itself is untouched — this package only imports the public
`aether` API (`ProofChecker`, `ParseError`) described in `AGENTS.md`.

## Quickstart

```bash
uv run python -m ui
```

Then open <http://127.0.0.1:8000>. A first visit loads the Even-square theorem,
so there is something to look at immediately; after that it reopens whatever
you were last working on.

Options:

```bash
uv run python -m ui --host 0.0.0.0 --port 9000
```

For live reload while editing the frontend:

```bash
uv run uvicorn ui.app:app --reload
```

## What you can do

| Feature | Where |
| --- | --- |
| Write/edit proofs with line numbers, 4-space Tab, Enter auto-indent | left pane |
| Load any of 8 worked examples | "Load an example…" menu |
| Overall verdict | pill in the header |
| Toggle strict domain checking | switch in the header |
| Parse errors with line + column | auditor pane |
| Per-step status, backend badge, message, counterexample, domain warnings | auditor pane |
| Move between steps with `↑` `↓` `Home` `End` | auditor pane |
| Click a proof line, or move the caret with `↑` `↓`, to inspect that step | left pane |
| Light / dark theme (remembered) | button in the header |
| Declared variables, active hypotheses, scope depth for a given step | context pane |
| Work saved as you type, restored on the next visit | automatic |
| Download a proof, or drop a `.aether` file anywhere on the page | download button, drag-and-drop |
| Snapshot the buffer, restore an earlier one, reset to the starting example | workspace panel |
| A link that reproduces the exact proof | "Copy link" in the workspace panel |
| Session verdict timeline | workspace panel |

Verification is **debounced by 300 ms** as you type. Selecting a step — by
clicking a proof line, clicking a row in the auditor, or with the arrow keys —
only re-renders the context pane from the already-fetched report; it never
re-runs SymPy or Z3. While a re-check is outstanding the verdict pill is dimmed,
because until the new answer arrives the pill is describing the *previous*
buffer, not the one on screen.

A few details worth knowing:

- The auditor is a single tab stop with a roving tabindex, and its arrow-key
  listener is scoped to that pane, so the editor keeps normal caret movement.
- The editor drives the panel by **caret position**: clicking a line or moving
  the caret with the arrow keys re-targets it. Caret moves that *edit* the
  document are excluded, so the panel stays put while you type instead of
  churning on every keystroke. Focus never leaves the editor, so you can click
  a line and carry on typing. Lines with no statement (QED, blanks, comments)
  leave the selection alone rather than clearing it.
- The theme is resolved before first paint by a small inline script, and the
  CodeMirror theme and its syntax colours are swapped together through a
  `Compartment` so they can never disagree.

### How your work is kept

On load, the buffer comes from the first of these that exists:

1. the URL fragment (`#p=…`)
2. `localStorage["aether:workspace"]`
3. the starting example

The fragment wins because it is what someone opening a link meant to see, and it
is kept in sync with the buffer afterwards — through `replaceState`, so it does
not fill up the back button. The verdict timeline lives under
`localStorage["aether:timeline"]` instead, so that a check does not rewrite every
saved snapshot alongside it. Snapshots are capped at 20 and the timeline at 120
entries.

Storage is written 500 ms after typing stops, and again on `beforeunload` and
whenever the tab is hidden, so a reload cannot lose the last few hundred
milliseconds of typing. If the browser refuses to store anything — private mode,
or the quota is full — the UI says so once rather than losing work silently.

Loading an example, resetting, restoring a snapshot or opening a dropped file
all snapshot the buffer they are about to replace first, so none of them can
destroy something you meant to keep.

## API

### `POST /api/check`

```json
{ "source": "Let x : Real\nStep: x = x\n", "strict_domains": false }
```

Returns:

```json
{
  "verdict": "VALID | VALID (with domain warnings) | INVALID | PARSE ERROR",
  "reports": [
    {
      "theorem_name": "Even square theorem",
      "is_valid": true,
      "has_warnings": false,
      "verdict": "VALID",
      "results": [
        {
          "line": 5,
          "statement": "Obtain k : Int such that n = (2 * k) from h1",
          "source_line": "    Obtain k : Int such that n = 2 * k from h1",
          "status": "VALID",
          "message": "Obtained fresh witness k with n = (2 * k).",
          "backend": "Definition+Z3",
          "scope_depth": 0,
          "active_variables": { "n": "Int", "k": "Int" },
          "active_hypotheses": ["h1: Even(n)", "n = (2 * k)"],
          "domain_warnings": [],
          "counterexample": null
        }
      ]
    }
  ],
  "parse_error": { "message": "…", "headline": "…", "line": 3, "col": 1 },
  "summary": { "total": 8, "valid": 8, "warnings": 0, "invalid": 0 },
  "strict_domains": false,
  "duration_ms": 12.4
}
```

`parse_error` is `null` unless the document failed to parse, in which case
`reports` is empty and `verdict` is `PARSE ERROR`.

The handler is a plain `def`, so FastAPI runs it on a worker thread — SymPy
and Z3 are blocking and would otherwise stall the event loop.

### `GET /api/examples`

Returns the bundled examples as `{id, name, blurb, expected, source}`.

### `GET /api/health`

Liveness probe.

## Layout

```
ui/
  app.py                   FastAPI app, pydantic contract, routes
  examples.py              the 8 bundled example proofs
  __main__.py              `python -m ui` entry point
  vendor_codemirror.py     regenerates static/vendor/
  verify_examples.py       asserts every example matches its blurb
  verify_frontend.mjs      asserts imports resolve + tokenizer output
  verify_server.py         HTTP smoke test (endpoints, MIME types)
  verify_browser.py        headless-Chrome behaviour regression suite
  static/
    index.html
    styles.css
    aether-language.js     Aether syntax mode (DOM-free, testable)
    js/
      main.js              entry point: wiring, debounce, boot
      editor.js            CodeMirror setup, themes, key bindings
      api.js               fetch wrappers
      render.js            applying a check response to all three panes
      verdict.js           the topbar pill
      audit.js             the auditor, step selection, keyboard nav
      context.js           the context pane
      format.js            DOM-building helpers
      dom.js               element references
      state.js             mutable UI state
      store.js             localStorage: buffer, snapshots, timeline
      permalink.js         URL fragment encode/decode
      files.js             download, clipboard, drag-and-drop
      history.js           the workspace panel
      toast.js             transient notifications
    vendor/                generated CodeMirror 6 graph (committed)
```

## Testing it yourself

### Poke at it by hand

```bash
uv run python -m ui      # then open http://127.0.0.1:8000
```

Two things make manual testing much easier:

- **Interactive API docs at <http://127.0.0.1:8000/docs>** (Swagger UI). You can
  `POST /api/check` straight from the page and read the whole JSON response —
  the fastest way to see exactly what the engine hands back.
- **`GET /api/examples`** in the browser lists the bundled proofs and the
  outcome each one advertises.

Worth eyeballing, and where to look:

| What to check | How |
| --- | --- |
| Tab inserts 4 spaces, *not* a tab | Click the editor, press Tab, watch the gutter shift |
| Enter after `Proof:` indents one level | Click the `Proof:` line, press End then Enter |
| Clicking a step re-runs nothing | DevTools → Network: no `POST /api/check` appears |
| Verdict refreshes ~300 ms after you stop typing | DevTools → Network timing |
| Strict toggle hardens the warning | Load "Unguarded division", flip the switch: `VALID (with domain warnings)` → `INVALID` |
| Arrow keys move the auditor selection | Click a step, then `↑` `↓` `Home` `End` |
| Arrow keys still move the caret in the editor | Focus the editor, press `↓` — the auditor must not move |
| Clicking a line in the proof fills the context panel | Click anywhere on a `Step:` line |
| The panel follows the caret as you arrow up/down | Click a step line, then press `↑` / `↓` |
| The panel does *not* jump around while you type | Type inside a valid line and watch the panel hold still |
| Theme toggle, and it survives a reload | Header button; check DevTools → Application → Local Storage |
| A reload restores what you were typing | Type an edit, reload, watch it come back |
| The verdict dims while a re-check is pending | Type in a valid proof and watch the pill |
| Snapshots are taken before anything replaces your buffer | Load an example, then open the workspace panel |
| "Copy link" reproduces the proof | Copy it, open it in a private window, note the fragment in the URL |
| Dropping a file loads it | Drag any `.aether` file onto the page |
| Console stays clean | DevTools → Console |

### Automated checks

```bash
uv run python ui/verify_examples.py   # engine: every example matches its blurb
node ui/verify_frontend.mjs           # static: imports resolve, tokenizer correct
uv run python ui/verify_server.py     # HTTP: endpoints, and MIME types for all 44 modules
uv run python ui/verify_browser.py    # real Chrome: key bindings, debounce, workspace
uv run pytest                         # the engine's own suite (untouched)
```

`verify_server.py` and `verify_browser.py` each start and stop their own server
on a free port, so they need nothing running first. `verify_browser.py` uses
`agent-browser` + Chrome and prints `SKIPPED` (exit 0) if either is missing.

Why each one earns its place:

- **`verify_examples.py`** — every example advertises an expected outcome in the
  UI. This fails loudly if an engine change silently turns a blurb into a lie.
- **`verify_server.py`** — includes the check that every vendored module is
  served as a JavaScript MIME type. Get that wrong and browsers silently refuse
  to load the editor, with a blank pane as the only symptom.
- **`verify_browser.py`** — the only check that can catch a key-binding
  regression. It exists because `Tab` was inserting a literal tab character
  (CodeMirror's `insertTab` ignores `indentUnit`), which no static check noticed.
- **`verify_frontend.mjs`** — catches the failure mode where a name is imported
  from the wrong vendored package and silently resolves to `undefined`.

Two things in `verify_browser.py` look odd and are load-bearing. Its
`reset_page` navigates to `/?r=<nonce>#p=…`: a navigation that only changes the
fragment does not reload at all, and clearing `localStorage` cannot be relied on
either, because the app's own unload flush rewrites it during the navigation. So
the fragment is what pins the starting point. And its `settle()` waits on the
pill's `stale` flag as well as on "Checking…" — without that it can read an edit
against the previous buffer's verdict, which looks exactly like a re-check that
never happened.

## About `static/vendor/`

CodeMirror 6 is a graph of packages that share singleton state — facets like
`indentUnit` only work if every package sees the *same* copy of
`@codemirror/state`. Bundling each package separately would inline duplicate
copies and silently break that.

`vendor_codemirror.py` mirrors esm.sh's dependency graph to disk instead,
preserving its canonical version-pinned paths and rewriting absolute imports
to relative ones. Every importer converges on one file, so dedup is intact and
nothing is fetched at runtime. To refresh:

```bash
uv run python ui/vendor_codemirror.py
```

Note that `static/js/editor.js` imports each symbol from its *owning* package,
not from the `codemirror` meta-package. That package star-exports all of its dependencies,
which makes shared names like `EditorView` ambiguous across star-exports and
therefore omitted.
