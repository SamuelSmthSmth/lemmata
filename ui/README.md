# Lemmata UI

A study app for writing proofs and checking them line by line, built on the
Lemmata proof checker:

- a **FastAPI** backend that exposes the engine over a small JSON API, with
  every check run in a worker process under a hard time budget
- a **dependency-free static frontend** (vanilla ES modules, Web Awesome
  components and CodeMirror 6) served by that same process

No `npm`, no build step, and no network access at runtime. The whole thing
starts with one command, and everything a student writes stays in their own
browser.

The UI imports only the public `aether` API (`ProofChecker`, `ParseError`)
described in `AGENTS.md`, plus the course packs in `courses/`.

## Quickstart

```bash
uv run python -m ui
```

Then open <http://127.0.0.1:8000>. A first visit opens the Even-square theorem
with its notes beside it and a short tour, so there is something to look at
immediately; after that it reopens the proofs you had open.

Options:

```bash
uv run python -m ui --host 0.0.0.0 --port 9000
```

For live reload while editing the frontend:

```bash
uv run uvicorn ui.app:app --reload
```

## The shape of the app

A slim **rail** on the left switches between four views; a **status bar**
across the foot carries the verdict, the first problem, the caret position,
the open file and whether work is being kept.

- **Proofs** — the workspace. On the left, the **reading pane** with three
  tabs: *Files* (your proofs and folders), *Notes* (the Library entry you are
  working from, or a pinned Guide page) and *History* (checks and snapshots of
  the open proof). On the right, the open proofs as tabs, a tool strip
  (templates, symbols, strict domains, arrangement, syntax colours, download,
  LaTeX/PDF export), and the editor, auditor and context panes.
- **Library** — course packs: proofs transcribed from MTH2008 (Real Analysis)
  and MTH2010 (Algebra) lecture notes keyed to the notes' own numbering, the
  notes' notation and its traps, and the worked examples of the language.
  Search by reference (`2.18`), title or topic; filter to proofs or traps.
- **Guide** — the handbook, with a *Try it* button on every example and the
  live capability matrix.
- **Settings** — theme, syntax colours, editor text size, line wrap, strict
  domains for new proofs, check debounce, panel arrangement, the reading pane,
  storage use, backup and delete-everything.

`Ctrl/Cmd+K` opens a **command palette** over all of it: commands, your files,
and every Library entry by reference.

## What you can do

| Feature | Where |
| --- | --- |
| Write/edit proofs with line numbers, 4-space Tab, Enter auto-indent | editor |
| Keep many proofs, in folders; new, rename (`F2`), delete with undo, drag to move | Files tab |
| Open several proofs as tabs; middle-click or × closes a tab, not the file | tab strip |
| `import` another proof in the workspace (relative to the importer, then the root) | any proof |
| Open a Library entry as your own copy, with the entry kept beside it | Library → *Open beside the proof* |
| Find the failing step of a trap before the checker tells you | Library → Traps → *Spot the error* |
| Insert a proof shape (ε–δ, induction, cases, contradiction, group, …) | *Insert template*, completion, palette |
| Insert `∀ ∃ ∈ ∉ ⊆ ≤ ≥ ≠ ⇒ ⇔ ε δ ∞ √ ⁻¹ ℝ ℤ ℕ` | symbol strip; or type `\forall`, `<=`, … |
| Completion of keywords, structures, functions and the proof's own names | editor (`Ctrl+Space`) |
| Failing and warning steps marked in the gutter and underlined; hover for why | editor |
| Jump between problems | `F8` / `Shift+F8`, or the status bar |
| Overall verdict, with counts and timing | status bar |
| Toggle strict domain checking (per proof; default in Settings) | tool strip |
| Per-step status, backend, message, counterexample, domain warnings | auditor |
| Move between steps with `↑` `↓` `Home` `End` | auditor |
| Click a proof line, or move the caret with `↑` `↓`, to inspect that step | editor |
| Declared variables, active hypotheses, scope depth for a given step | context pane |
| Rearrange the three panes: four presets, drag-to-swap, arrow keys on a grip | arrangement menu |
| Snapshot a proof, restore an earlier one, reset it to where it started | History tab |
| A link that reproduces the exact proof | History → *Copy link* |
| Back up the whole workspace as a `.zip`, and restore it | Files tab, Settings, or drop it on the window |
| Download one proof, or drop `.aether` files anywhere on the page | tool strip, drag-and-drop |
| Export the proof to LaTeX or PDF, with or without a verification report | tool strip |
| Light / dark theme, mono / vivid syntax (remembered) | rail, tool strip, Settings |

Keys: `Ctrl/Cmd+K` palette · `Alt+1`…`Alt+4` the four views · `Alt+N` new
proof · `Alt+B` show or hide the reading pane · `F8` next problem.

Verification is **debounced by 300 ms** as you type (adjustable in Settings).
Selecting a step — by clicking a proof line, clicking a row in the auditor, or
with the arrow keys — only re-renders the context pane from the already-fetched
report; it never re-runs SymPy or Z3. While a re-check is outstanding the
verdict is dimmed, because until the new answer arrives it describes the
*previous* buffer, not the one on screen. The editor's diagnostics come from
the same response, so there is never a second check.

A few details worth knowing:

- The auditor is a single tab stop with a roving tabindex, and its arrow-key
  listener is scoped to that pane, so the editor keeps normal caret movement.
  The explorer, the tab strip, the reading-pane tabs and the Library filters
  are keyboard-operable the same way.
- The editor drives the panel by **caret position**: clicking a line or moving
  the caret with the arrow keys re-targets it. Caret moves that *edit* the
  document are excluded, so the panel stays put while you type instead of
  churning on every keystroke. Focus never leaves the editor, so you can click
  a line and carry on typing. Lines with no statement (QED, blanks, comments)
  leave the selection alone rather than clearing it.
- The theme, syntax scheme, editor size and reading-pane state are resolved
  before first paint by a small inline script, and the CodeMirror theme and its
  syntax colours are swapped together through a `Compartment` so they can never
  disagree.
- A **trap opened as an exercise** hides every verdict the app would otherwise
  show — the auditor's statuses and messages, its rails, the gutter marks, the
  tab and explorer marks, the status bar — until you commit to a line or ask
  for the answer. The exercise state lives on the file, so it survives a
  reload.

### How your work is kept

Proofs live in **IndexedDB** in your browser (`js/db.js`), in three stores:
`files` (`{id, path, source, strict, created, updated, origin?, exercise?}`),
`snapshots` (per file) and `meta` (folders, open tabs, the active proof, the
verdict timeline, a pinned Guide page). Small preferences — theme, syntax,
editor size, wrap, debounce, arrangement — stay in `localStorage`, because they
have to be read synchronously before first paint. If IndexedDB is unavailable
(some private modes) the same interface runs in memory and mirrors to
`localStorage`, and the status bar says so.

On load, the open proof is chosen like this:

1. a URL fragment (`#p=…`) — reopened if a proof with that exact source is
   already in the workspace, otherwise added as *Shared proof*
2. the proofs you had open last time
3. on a first visit, the starting example from the Library

The fragment is kept in sync with the open proof through `replaceState`, so it
does not fill up the back button. Edits are written 400 ms after typing stops,
and again on `beforeunload` and whenever the tab is hidden. If the browser
refuses to store anything, the UI says so once rather than losing work
silently.

The workspace from the earlier single-buffer UI (`localStorage["aether:workspace"]`
and `["aether:timeline"]`) is migrated once into a file called *My proof*, with
its snapshots and timeline. The old keys are left in place: a migration that
destroys its source cannot be retried.

Resetting, restoring a snapshot, or deleting a proof never destroys work:
reset and restore snapshot the buffer first, and a delete offers *Undo*.
**Export the workspace as a `.zip`** to keep a copy outside the browser; the
archive holds every proof at its path, and dropping it back onto the window
(or importing it from the Files tab) restores them, renaming any that clash.
The zip reader and writer are a few dozen lines in `js/zip.js` (stored entries
out; stored or deflated entries in, via `DecompressionStream`).

### Imports between proofs

Each check sends the open proof's path, and — only when its source contains an
`import` — every proof in the workspace as `files: {path: source}`. The engine
resolves an import against those first (relative to the importing proof, then
the workspace root) and then falls back to the disk search it has always done.
A missing import is named in the auditor rather than ignored.

### Panel arrangements

The three panes live in a CSS grid, and a pane's *position* in it is a
`data-slot` attribute (`a`, `b`, `c`, in reading order). Each arrangement is a
`grid-template-areas` rule keyed off `data-layout` on the grid, so moving a
panel is only ever a swap of two slots.

Four presets are offered from the arrangement menu and from Settings, each
shown as a miniature of itself — **Columns**, **Stack**, **Split** (the
default: the editor across the top, the auditor and context beneath it) and
**Focus**. Two of them deliberately merge panes: in Split and Focus the auditor
and the context pane share a row or column, which is the nearest thing here to
docking one panel inside another. Beyond the presets, panes can be reordered
freely:

- **Drag a grip** — the six dots at the left of a panel head — onto another
  panel to swap the two. The whole panel is the drop target, not just its head,
  which is what makes it feel like docking rather than aiming at a handle.
- **Focus a grip and press an arrow key** to move that panel one slot along the
  order. Movement is clamped at the ends rather than wrapped, and focus stays on
  the grip, so you can keep pressing.

Both are written to `localStorage["aether:layout"]` as `{v, arrangement,
order}`. Nothing read back is trusted: an unknown arrangement falls back to
Split, the order is rebuilt from the panes that actually exist, and a pane
missing from the stored order is appended rather than dropped. The grid is
resolved before the first paint, because the module is deferred and applies the
layout during evaluation. On every change the panes are also reordered *in the
DOM*, which is what keeps tab order and screen-reader order in step with what is
on screen — and what the narrow-screen rule lays out from, since it drops the
slot areas entirely and stacks the panes in a single column.

Below 1100px the reading pane overlays the work instead of squeezing it; below
760px the rail becomes a bar along the foot and the panes stack.

## API

### `POST /api/check`

```json
{
  "source": "import \"lemmas.aether\"\nLet x : Real\nStep: x = x\n",
  "strict_domains": false,
  "path": "sheets/week1.aether",
  "files": { "sheets/lemmas.aether": "…" }
}
```

`path` and `files` are optional. `files` is the browser workspace keyed by
path; `import` resolves against it (relative to `path`, then the root) before
the engine's disk search.

Returns:

```json
{
  "verdict": "VALID | VALID (with domain warnings) | INVALID | PARSE ERROR | TIMEOUT",
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

Every check runs in a **worker process** from a small pool (`ui/checking.py`),
under a hard wall-clock budget: 20 s by default, `AETHER_CHECK_BUDGET` to
change it, `AETHER_CHECK_WORKERS` (2) for the pool size. Z3's own `timeout` is
not enforceable in-process — its quantifier instantiation can run far past it —
so a check that overruns has its worker killed and replaced, and the response
is a `TIMEOUT` verdict whose `parse_error` block says the check was stopped and
what to try (split the step, add the hypothesis it needs) — rather than a
request that never returns. A worker that dies mid-check (out of memory, say)
is reported the same way. LaTeX and PDF export run
their check in the same pool.

### `GET /api/examples`

Returns the bundled examples as `{id, name, blurb, expected, source}`.

### `GET /api/library`

The Library: the bundled examples as a pack, then every pack in `courses/`,
each `{id, code, title, note, chapters: [{id, title}], entries: [{id, chapter,
ref, title, kind: proof|trap, expected, source, blurb?, explanation?}]}`. The
course packs are data shared with the engine's own tests
(`tests/test_lecture_notes.py`), so an entry shown here is one pytest checks.

### `GET /api/capabilities`

The CNL capability matrix that `verify_capabilities.py` pins — area, feature,
snippet, expected verdict and note — for the Guide's *What the checker can
decide* page. Metadata only; nothing is run on request.

### `POST /api/export/latex`, `POST /api/export/pdf`

The proof as LaTeX (two styles, with or without the verification report), or
compiled to PDF when a TeX engine is installed.

### `GET /api/site`

The product's name, tagline and version: `{name, tagline, version}`. The name
and tagline come from `ui/site.json`, the only place the brand is written
down (`ui/site.py` reads it for the server title, the page `<title>` and the
LaTeX/PDF report; `js/site.js` fills `[data-site-name]` in the frontend). The
version is the installed `aether` package's.

### `GET /api/health`

Liveness probe.

## Layout

```
ui/
  app.py                   FastAPI app, pydantic contract, routes
  checking.py              the budgeted worker-process pool every check runs in
  examples.py              the 19 bundled example proofs
  latex_report.py          LaTeX/PDF export: the proof plus its audit
  __main__.py              `python -m ui` entry point
  vendor_codemirror.py     regenerates static/vendor/esm/
  vendor_webawesome.py     regenerates static/vendor/webawesome/
  verify_examples.py       asserts every example matches its blurb
  verify_capabilities.py   pins the documented CNL capability surface
  verify_frontend.mjs      imports resolve, tokenizer, layout rules, zip round trip
  verify_server.py         HTTP: endpoints, MIME types, budget, library, guide examples
  verify_browser.py        headless-Chrome behaviour regression suite
  static/
    index.html             the shell: rail, four views, status bar, dialogs
    styles.css
    aether-language.js     Lemmata syntax mode (DOM-free, testable)
    guide/*.html           the Guide's pages (plain HTML partials)
    js/
      main.js              entry point: wiring, views, check/save flow, boot
      components.js        registers the Web Awesome custom elements
      editor.js            CodeMirror setup, themes, key bindings
      complete.js          completion, proof templates, the symbol strip
      lint.js              check results as editor diagnostics
      api.js               fetch wrappers
      render.js            applying a check response to the panes
      verdict.js           the verdict in the status bar
      audit.js             the auditor, step selection, keyboard nav
      context.js           the context pane
      db.js                IndexedDB (files, snapshots, meta) with a fallback
      workspace.js         the workspace model: paths, files, folders, tabs, history
      explorer.js          the Files tree
      tabs.js              the open-proof tab strip
      notes.js             the Notes tab, including trap exercises
      history.js           the History tab
      library.js           the Library view
      guide.js             the Guide view and its Try-it buttons
      settings.js          the Settings view
      palette.js           the command palette
      prefs.js             small synchronous preferences (localStorage)
      layout.js            panel arrangement: presets, drag-to-swap, keyboard
      permalink.js         URL fragment encode/decode
      files.js             download, clipboard, drag-and-drop
      zip.js               store-only zip writer, zip reader
      toast.js             transient notifications, with Undo
      format.js            DOM-building helpers
      dom.js               element references
      state.js             mutable UI state
    vendor/
      esm/                 generated CodeMirror 6 graph (committed)
      webawesome/          generated Web Awesome components (committed)
courses/                   the course packs (JSON), shared with tests/
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
| Strict toggle hardens the warning | Library → Worked examples → "Unguarded division", flip the switch: `VALID (with domain warnings)` → `INVALID` |
| Arrow keys move the auditor selection | Click a step, then `↑` `↓` `Home` `End` |
| Arrow keys still move the caret in the editor | Focus the editor, press `↓` — the auditor must not move |
| Clicking a line in the proof fills the context panel | Click anywhere on a `Step:` line |
| The panel follows the caret as you arrow up/down | Click a step line, then press `↑` / `↓` |
| The panel does *not* jump around while you type | Type inside a valid line and watch the panel hold still |
| A failing step is marked in the editor | Break a step: a red rule in the gutter, an underline, the reason on hover; `F8` jumps to it |
| Many proofs, kept across reloads | Files → *New proof*, rename with `F2`, reload; DevTools → Application → IndexedDB → `aether` |
| Delete is undoable | Select a proof in Files, press `Delete`, click *Undo* in the toast |
| Imports resolve inside the workspace | Two proofs, one `import "other.aether"`-ing the other; the auditor says *Imported* |
| A Library entry opens beside your copy | Library → MTH2008 → Example 2.18 → *Open beside the proof*; the Notes tab holds the entry |
| A trap hides its answer | Library → Traps → any → *Spot the error*: no verdicts until you choose a line |
| The palette finds anything | `Ctrl+K`, then `2.18`, a file name, or `theme` |
| The workspace round-trips as a .zip | Files → export; *Delete everything* in Settings; drop the .zip back on the window |
| Theme toggle, and it survives a reload | The sun/moon on the rail, or Settings |
| Panels can be swapped by grip | Drag a panel's grip onto another panel, or focus one and press an arrow key |
| A preset rearranges all three panes at once | Arrangement menu in the tool strip; pick Columns or Focus |
| Syntax colours flip between mono and vivid | The three-dot button in the tool strip; the editor repaints |
| The verdict dims while a re-check is pending | Type in a valid proof and watch the status bar |
| Snapshots are taken before anything replaces your proof | Reset it from History, then look at the snapshot list |
| "Copy link" reproduces the proof | Copy it, open it in a private window, note the fragment in the URL |
| The layout holds on a phone | DevTools device toolbar at 390px: the rail moves to the foot |
| Console stays clean | DevTools → Console |

### Automated checks

```bash
uv run python ui/verify_examples.py    # engine: every example matches its blurb
uv run python ui/verify_capabilities.py  # engine: 88 documented snippets still behave
node ui/verify_frontend.mjs            # static: imports resolve, tokenizer correct
uv run python ui/verify_server.py      # HTTP: endpoints, MIME types, both export styles
uv run python ui/verify_browser.py     # real Chrome: editor, workspace, Library, palette, settings
uv run pytest                          # the engine's own suite (untouched)
```

`verify_server.py` and `verify_browser.py` each start and stop their own server
on a free port, so they need nothing running first. `verify_browser.py` uses
`agent-browser` + Chrome and prints `SKIPPED` (exit 0) if either is missing.

Why each one earns its place:

- **`verify_examples.py`** — every example advertises an expected outcome in the
  UI. This fails loudly if an engine change silently turns a blurb into a lie.
- **`verify_capabilities.py`** — the same idea for the *documentation*. What a
  proof may contain, and where the engine stops, is advertised across
  `USER_GUIDE.md` sections 3, 5 and 6 and pinned here as 88 snippets plus the
  verdict each must still produce — including the deliberate refusals
  (`ChainGuard`, `ScopeGuard`, variable capture), the few known gaps, and the
  rejections that are simply correct. It also fails when the table embedded in
  `USER_GUIDE.md` (§8) no longer matches the pins, so a flipped expectation
  cannot stop at the code. `--markdown` prints that table. Each snippet runs in
  a worker process under a wall-clock budget (`--budget`, 10s), because Z3's soft
  `timeout` is not honoured by its model-based quantifier instantiation: one
  query can run from seconds to half an hour, and that must not make this
  worthless as a gate. A snippet that overruns is reported as `TIMEOUT` —
  expected for the one that is documented as such, a failure for anything else.
- **`verify_server.py`** — includes the check that every vendored module is
  served as a JavaScript MIME type. Get that wrong and browsers silently refuse
  to load the editor, with a blank pane as the only symptom. It now covers the
  Web Awesome graph too, and separately that its stylesheets are served as
  `text/css` — a stylesheet served as anything else is ignored outright.
- **`verify_browser.py`** — the only check that can catch a key-binding
  regression. It exists because `Tab` was inserting a literal tab character
  (CodeMirror's `insertTab` ignores `indentUnit`), which no static check noticed.
  It is also where the two pure-logic modules get their wiring tested: the panel
  grips are focused and stepped with real arrow keys, and the syntax button is
  clicked and the editor's *rendered* token colours are compared. And it drives
  the app around the editor end to end: files, folders, rename, delete with
  undo and a reload; imports between workspace files; the migration of the old
  single-buffer storage; gutter marks and `F8`; templates; the palette; a trap
  exercise with its answer hidden; settings that persist; and a workspace
  `.zip` exported, wiped and imported again.
- **`verify_frontend.mjs`** — catches the failure mode where a name is imported
  from the wrong vendored package and silently resolves to `undefined`. It also
  round-trips `zip.js` archives, including through Python's `zipfile`. Web
  Awesome cannot be imported here at all (it needs a DOM), so its tree is
  checked structurally instead: the entry still exports what `components.js`
  imports, and no vendored module imports over the network.

Three things in `verify_browser.py` look odd and are load-bearing. Its
`reset_page` navigates to `/?r=<nonce>#p=…`: a navigation that only changes the
fragment does not reload at all, so the query string varies, and the fragment
is what pins the proof — the app reopens a workspace file with that exact
source rather than adding a copy. When a section needs a true first visit,
`wipe()` deletes the `aether` IndexedDB and clears `localStorage` from a
same-origin page that is *not* the app (`/api/health`), because the app's open
connection would block the delete and its unload flush would rewrite storage
on the way out. And `settle()` waits on the verdict's `stale` flag as well as
on "Checking…" — without that it can read an edit against the previous
buffer's verdict, which looks exactly like a re-check that never happened.

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

## About `static/vendor/webawesome/`

The controls — the strict-domain switch, the template menu, the Library search
field, the icon buttons, tooltips, the arrangement popover, the export dialog,
the setting switches and the toasts — are [Web Awesome](https://webawesome.com)
components, vendored the same way CodeMirror is. The rail, the tabs, the
explorer tree, the segmented controls and the palette are native elements with
the app's own styles: each is simpler than the component it would replace, and
none needs to reach into a shadow root to match the rest of the page.

Web Awesome ships `dist-cdn/`, a pre-bundled build meant to be loaded directly
in the browser with no bundler, and it never bundles a dependency twice: every
file imports its siblings by *relative, content-hashed* path
(`components/switch/switch.js -> ../../chunks/chunk.SVFNJFHB.js`), so a dozen
components converge on one shared chunk and exactly one copy of Lit is ever
loaded. Because those paths are already relative, the graph can be copied
verbatim — no import rewriting, just the tree it lives in.

Only the reachable subgraph is copied. The full `dist-cdn` tree is 13 MB across
~1,200 files (it also carries React wrappers, type declarations and docs); the
12 components this UI uses come to 122 files and about 630 KB. The script
rebuilds the tree from scratch on each run, so a component dropped from its
list takes its chunks with it.
`vendor_webawesome.py` reads the package tarball straight from the npm registry
— so still no `npm` — and walks the imports to work out what is reachable:

```bash
uv run python ui/vendor_webawesome.py
```

### Three things that are easy to get wrong

- **Never use `name` on `<wa-icon>`.** Web Awesome's default icon library is
  Font Awesome, and it fetches each icon from `ka-f.fontawesome.com` at
  runtime; the package ships no SVG assets of its own. Slot an inline `<svg>`
  instead. This was checked with a network probe: a named icon makes a
  cross-origin request, a slotted one makes none. The system icons components
  draw for themselves (the dialog's close button, a dropdown's caret) are safe
  as they are: they are embedded `data:` URIs.
- **Only part of `styles/webawesome.css` is loaded.** That file also pulls in
  `styles/native.css`, a global reset that restyles every native element on the
  page — including `button`, which it gives a fixed
  `height: var(--wa-form-control-height)`. That silently squashed the auditor's
  step rows, which are native `<button>`s (they were 35px tall while their
  content needed 70px, so the text overflowed and collided). `index.html`
  therefore links only the token layer plus the two helpers the components
  rely on, `visually-hidden.css` and `scroll-lock.css`.
- **Component internals cannot be reached from `styles.css`.** They live in
  shadow DOM. Density is expressed through the token layer instead: the theme
  sets the four scale knobs (`--wa-font-size-scale`, `--wa-space-scale`,
  `--wa-border-radius-scale`, `--wa-line-height-normal`) and the semantic
  palette, and the rest of the stylesheet reads its own names as aliases of
  those — so the shell and the components share one palette rather than
  keeping two. `::part()` is used only where a component actually exposes a
  part, and `editor.js` reads the CodeMirror colours from the same tokens
  instead of repeating them as hex.

Because the token layer is what styles everything, `styles.css` is *unlayered*
while Web Awesome's CSS lives in cascade layers — and unlayered CSS outranks
layered CSS, so the app's own rules win wherever the two overlap.

### The visual scheme

The interface is deliberately close to monochrome, and the rules it follows are
worth keeping:

- **A step that held is not news.** Status is set as type, not as a pill, and
  `VALID` is the quietest thing in the row. Colour is reserved for the two
  things that need it: the verdict, and a step that failed.
- **The entailment rail is the signature.** A 2px rule in the margin marks a
  step that did not hold, and every step below it is marked more faintly,
  because everything after a broken step rests on it.
- **The syntax palette is built, not hardcoded.** `aether-language.js` stays
  DOM-free so it can be unit-tested in Node, so it exports
  `makeHighlightStyle(palette)` and `editor.js` passes in the values it resolves
  from the `--cm-token-*` tokens. The CNL keywords take the accent; types are
  inked and separated by weight; operators, glue words, strings and comments
  recede.
- **Two syntax schemes, one vocabulary.** The same thirteen token keys are
  pointed at two different sets of colours by an attribute on `<html>`.
  `[data-syntax="mono"]` (the default) aliases them back to the interface's own
  palette — keywords to the accent, names and numbers to ink, operators, glue
  words and comments to a dim of it — so the editor keeps the page's
  near-monochrome voice, while `[data-syntax="vivid"]` gives each category a hue
  of its own, the way a Python file does. Because the mono scheme is written as
  aliases rather than literals it follows the dark theme for free; only vivid
  needs a second block, since its hues are chosen against one ground apiece. The
  toolbar button flips it, the choice is remembered under
  `localStorage["aether-syntax"]`, and it is resolved before first paint
  alongside the theme. Nothing is re-rendered — the keys are read once and the
  colours are CSS — so every token has to stay legible on its own against both
  grounds.
- **A failure is stated once.** The engine repeats itself — a failing obligation
  arrives as both the message and a warning, and an algebraic failure's message
  ends with the same `Counterexample at x=3: …` sentence the callout shows.
  `splitStepText()` in `format.js` strips from the prose anything a callout is
  about to display, and both panes use it.
- **Two controls are styled through `::part()`** rather than left at their
  defaults: switches are ink toggles (off and on differ by ink, not by hue, so
  the controls that change how a proof is judged cannot outshout the verdict
  they produce), and the Library search is a hairline field rather than a
  boxed control.
- **The rail language carries across the app.** The current view on the rail,
  the active Library pack, the current Guide page and the open proof's tab all
  take a 2px accent rule — the auditor's failure rail, in blue — and the editor
  gutter marks a failing step with the same 2px red rule the auditor uses, not
  CodeMirror's default dot. Everything sits on hairlines; there are no cards,
  and the only shadows are on what floats (the palette, an overlaid reading
  pane).

### LaTeX and PDF export

`aether.export_to_latex` typesets a proof and nothing else — it is handed source
text and never sees a verification result. Everything the auditor and the
Context & State pane show is therefore added by `ui/latex_report.py`, in the UI
layer, rather than by reaching into `aether.core`. The engine proves; the UI
reports.

That module renders the same facts in two presentations, selected by
`export_report_latex(..., style=...)`:

| Style | Used for | Look |
| --- | --- | --- |
| `plain` | the `.tex` a user downloads or copies, and `breakdown=false` | the sober `article` the engine's own exporter has always produced: a title block, then each report section on a fresh page |
| `fancy` | the PDF the server compiles for the user | a site-matched document: topbar opening, journal proof, auditor step list, accent `#0a5fbf` |

Only the PDF is designed. `ui/app.py` passes `style="fancy"` from
`export_pdf` and `style="plain"` from `export_latex`, so the `.tex` stays the
thing you can paste into a paper while the PDF is the thing you would be
pleased to hand in.

The `plain` document is the proof first, then each report section, each starting
on a fresh page under a hairline rule:

| Section | Contents |
| --- | --- |
| Verification Report | the verdict and counts, then a `longtable` of line / status / backend / canonical statement, then a note for every statement that had something to say — so a clean proof says nothing |
| Proof State | what was in scope at each statement: scope depth, declared variables, active hypotheses and derived facts |
| Session | the History tab's verdict timeline and snapshots, which live in the browser and so are sent by the client |
| Original Proof Source | the Lemmata source, verbatim |

The designed document carries exactly the same facts in a different shape. It
opens on a **full-bleed navy cover plate**: brand and kicker, the theorem at
31pt, the verdict at 17pt in the tone it earned, and a mono meta strip giving
the statement counts, the date, how long the check took, and whether domains
were strict. Everything a reader needs before the proof is on that one page.
Then a numbered sequence:

| Section | Contents |
| --- | --- |
| The Proof | an at-a-glance strip of four stat cards over the journal proof |
| Findings | one callout per statement that did not clear, with its counterexample — omitted when nothing failed |
| Auditor | every statement as a step row: rail, line, status chip, statement, backend |
| Proof State | what was in scope at each line |
| Session | the workspace timeline and snapshots — omitted when there is none |
| Source | the buffer, in an editor-window panel |
| About | how to read the document |

The sections are collected and numbered in one pass at the end, so a section
that is left out does not leave a hole in the sequence: a clean proof with no
recorded history numbers them 01 The Proof, 02 Auditor, 03 Proof State, 04
Source, 05 About. Auditor and Source each force a page break — the one is a long
column of rows, the other a wall of monospace that reads badly starting halfway
down a page — while the rest flow. Each opener is a tinted number chip, the
title, and a rule. Colour follows the site light theme (`#0a5fbf` accent; green
/ amber / red only for status, with a light variant of each on the navy cover,
where the dark ones have no contrast at all).

Three consequences worth knowing:

- **Everything is escaped.** A proof is arbitrary text and LaTeX treats `^`,
  `_`, `&` and friends as syntax, so an unescaped `n^2` in a table cell is a
  compile error. Escaping is one regex pass rather than a chain of
  `str.replace` calls, because replacing `\\` first and `{` second would go on
  to escape the braces in the backslash's own replacement text. The engine's own
  exporter needs the same treatment for the free text *it* emits: a theorem name
  like `Divisibility of 3^n - 1 by 2` went into `\begin{theorem}[...]` verbatim,
  where `^` is a math-only token, and pdfTeX stopped with *Missing $ inserted* —
  no PDF at all. `escape_latex_text()` in `aether.core.latex_export` now escapes
  theorem names and labels, and the source listing stays the one deliberate
  exception, since it is quoted verbatim.
- **The PDF is compiled twice.** `longtable` measures its columns on the first
  pass and lays them out on the second; one pass leaves the report's tables
  ragged.
- **The breakdown is optional.** `breakdown=false` returns exactly what the
  engine's exporter produced before any of this existed, which is what the
  engine's own tests and the CLI still see.

Two constraints the designed style has to live with, both recorded in
`_FANCY_PREAMBLE`:

- **No typeface but Computer Modern comes for free.** The `psnfss` packages
  ship `.sty` files far more often than they ship usable metrics, and a
  document that needs Palatino is a document that fails on a minimal TeX
  installation, so the design leans on scale, colour, spacing and rule-work:
  T1 (EC) for text, CM Sans for every label, CM Typewriter for code. A second
  trap follows from the same place — EC has no bold-extended sans below 8pt, so
  a bold sans label at 7.4pt sends pdfTeX after a bitmap that was never
  generated and the run dies outright. Every bold label here is 8pt or larger.
- **The source listing is a `Verbatim`, not a `verbatim`.** A statement can be
  wider than the panel, and `verbatim` cannot break a line: a long `Claim:` ran
  180pt into the margin. `fvextra`'s `Verbatim[breaklines,breakanywhere]` wraps
  it and marks the continuation with a hook, which is also why the designed
  preamble loads `fvextra`. The cover, by contrast, is a `tcolorbox` the size of
  the paper, emitted inside `\newgeometry{margin=0pt}` with the margins restored
  straight afterwards, and the amber bar across its foot is drawn in the shipout
  foreground so that it applies to that page alone.
