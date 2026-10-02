# Aether UI

A dual-purpose web front end for the Aether proof checker:

- a **FastAPI** backend that exposes the engine over a small JSON API
- a **dependency-free static frontend** (vanilla JS, Web Awesome components
  and CodeMirror 6) served by that same process

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
| Load any of 19 worked examples | "Load an example…" menu |
| Overall verdict | pill in the header |
| Toggle strict domain checking | switch in the header |
| Rearrange the three panels: four presets, drag-to-swap, arrow keys on a grip | layout menu in the toolbar |
| Colourised syntax, or keep the editor near-monochrome (remembered) | button in the toolbar |
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
| Export the proof to LaTeX or PDF, with or without a verification report | export button in the toolbar |

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

### Panel arrangements

The three panes live in a CSS grid, and a pane's *position* in it is a
`data-slot` attribute (`a`, `b`, `c`, in reading order). Each arrangement is a
`grid-template-areas` rule keyed off `data-layout` on the grid, so moving a
panel is only ever a swap of two slots.

Four presets are offered from the toolbar menu, each shown as a miniature of
itself — **Columns** (the default), **Stack**, **Split** and **Focus**. Two of
them deliberately merge panes: in Split and Focus the auditor and the context
pane share a column, which is the nearest thing here to docking one panel
inside another. Beyond the presets, panes can be reordered freely:

- **Drag a grip** — the six dots at the left of a panel head — onto another
  panel to swap the two. The whole panel is the drop target, not just its head,
  which is what makes it feel like docking rather than aiming at a handle.
- **Focus a grip and press an arrow key** to move that panel one slot along the
  order. Movement is clamped at the ends rather than wrapped, and focus stays on
  the grip, so you can keep pressing.

Both are written to `localStorage["aether:layout"]` as `{v, arrangement,
order}`. Nothing read back is trusted: an unknown arrangement falls back to
Columns, the order is rebuilt from the panes that actually exist, and a pane
missing from the stored order is appended rather than dropped. The grid is
resolved before the first paint, because the module is deferred and applies the
layout during evaluation. On every change the panes are also reordered *in the
DOM*, which is what keeps tab order and screen-reader order in step with what is
on screen — and what the narrow-screen rule lays out from, since it drops the
slot areas entirely and stacks the panes in a single column.

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
  examples.py              the 19 bundled example proofs
  __main__.py              `python -m ui` entry point
  vendor_codemirror.py     regenerates static/vendor/esm/
  vendor_webawesome.py     regenerates static/vendor/webawesome/
  verify_examples.py       asserts every example matches its blurb
  verify_capabilities.py   pins the documented CNL capability surface
  verify_frontend.mjs      asserts imports resolve + tokenizer + layout rules
  verify_server.py         HTTP smoke test (endpoints, MIME types)
  verify_browser.py        headless-Chrome behaviour regression suite
  static/
    index.html
    styles.css
    aether-language.js     Aether syntax mode (DOM-free, testable)
    js/
      main.js              entry point: wiring, debounce, boot
      components.js        registers the Web Awesome custom elements
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
      layout.js            panel arrangement: presets, drag-to-swap, keyboard
      permalink.js         URL fragment encode/decode
      files.js             download, clipboard, drag-and-drop
      history.js           the workspace panel
      toast.js             transient notifications
  latex_report.py          LaTeX/PDF export: the proof plus its audit
    vendor/
      esm/                 generated CodeMirror 6 graph (committed)
      webawesome/          generated Web Awesome components (committed)
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
| Panels can be swapped by grip | Drag a panel's grip onto another panel, or focus one and press an arrow key |
| A preset rearranges all three panes at once | Layout menu in the toolbar; pick Split or Focus |
| Syntax colours flip between mono and vivid | The three-dot button in the toolbar; the editor repaints |
| A reload restores what you were typing | Type an edit, reload, watch it come back |
| The verdict dims while a re-check is pending | Type in a valid proof and watch the pill |
| Snapshots are taken before anything replaces your buffer | Load an example, then open the workspace panel |
| "Copy link" reproduces the proof | Copy it, open it in a private window, note the fragment in the URL |
| Dropping a file loads it | Drag any `.aether` file onto the page |
| Console stays clean | DevTools → Console |

### Automated checks

```bash
uv run python ui/verify_examples.py    # engine: every example matches its blurb
uv run python ui/verify_capabilities.py  # engine: 87 documented snippets still behave
node ui/verify_frontend.mjs            # static: imports resolve, tokenizer correct
uv run python ui/verify_server.py      # HTTP: endpoints, MIME types, both export styles
uv run python ui/verify_browser.py     # real Chrome: key bindings, debounce, workspace
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
  `USER_GUIDE.md` sections 3, 5 and 6 and pinned here as 87 snippets plus the
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
  clicked and the editor's *rendered* token colours are compared.
- **`verify_frontend.mjs`** — catches the failure mode where a name is imported
  from the wrong vendored package and silently resolves to `undefined`. Web
  Awesome cannot be imported here at all (it needs a DOM), so its tree is
  checked structurally instead: the entry still exports what `components.js`
  imports, and no vendored module imports over the network.

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

## About `static/vendor/webawesome/`

The controls — the strict-domain switch, the example menu, the icon buttons,
tooltips, the workspace popover, the export dialog, the toasts and the status
badges — are [Web Awesome](https://webawesome.com) components, vendored the
same way CodeMirror is.

Web Awesome ships `dist-cdn/`, a pre-bundled build meant to be loaded directly
in the browser with no bundler, and it never bundles a dependency twice: every
file imports its siblings by *relative, content-hashed* path
(`components/switch/switch.js -> ../../chunks/chunk.SVFNJFHB.js`), so a dozen
components converge on one shared chunk and exactly one copy of Lit is ever
loaded. Because those paths are already relative, the graph can be copied
verbatim — no import rewriting, just the tree it lives in.

Only the reachable subgraph is copied. The full `dist-cdn` tree is 13 MB across
~1,200 files (it also carries React wrappers, type declarations and docs); the
12 components this UI uses come to 138 files and about 1 MB.
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
  cross-origin request, a slotted one makes none. `<wa-select>` and
  `<wa-option>` are safe as they are — their internal caret and checkmark are
  embedded `data:` URIs.
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
  they produce), and the example picker is an inline hairline field rather than
  a boxed control.

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
| Session | the workspace panel's verdict timeline and snapshots, which live in `localStorage` and so are sent by the client |
| Original Proof Source | the Aether source, verbatim |

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
