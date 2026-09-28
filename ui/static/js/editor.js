// The CodeMirror 6 editor: themes, key bindings, and the Aether syntax mode.
//
// Imports come from the vendored CodeMirror graph (see
// ui/vendor_codemirror.py).  Each symbol is imported from its *owning* package
// rather than the `codemirror` meta-package: that package star-exports all of
// its dependencies, which makes shared names like `EditorView` ambiguous and
// therefore omitted.  All packages resolve to one shared @codemirror/state,
// so facets behave correctly.

import { basicSetup } from "../vendor/esm/codemirror@6.0.2.mjs";
import { EditorView, keymap, placeholder } from "../vendor/esm/@codemirror/view@6.mjs";
import { Compartment } from "../vendor/esm/@codemirror/state@6.mjs";
import { indentLess, indentMore } from "../vendor/esm/@codemirror/commands@6.mjs";
import { indentUnit, syntaxHighlighting } from "../vendor/esm/@codemirror/language@6.mjs";
import { aetherHighlightStyles, aetherLanguage } from "../aether-language.js";

// Mirrors aether.parser.indenter.AetherIndenter.tab_len = 4.
export const INDENT = "    ";

const CM_PALETTES = {
  light: {
    bg: "#ffffff",
    text: "#1f2328",
    caret: "#0969da",
    // Line numbers are secondary, but must stay readable (~3.7:1 on white).
    gutterFg: "#7d858f",
    gutterBorder: "#eaedf1",
    activeGutterBg: "#f2f4f7",
    activeGutterFg: "#5c6570",
    activeLine: "#f7f8fa",
    selection: "#cfe3ff",
    selectionFocused: "#aed2fc",
    placeholder: "#a8b0b9",
    tooltipBg: "#ffffff",
    tooltipBorder: "#dfe3e8",
  },
  dark: {
    bg: "#0f1115",
    text: "#e7e9ee",
    caret: "#7dd3fc",
    // ~3.9:1 on the dark background.
    gutterFg: "#6a737f",
    gutterBorder: "#1e222a",
    activeGutterBg: "#171a21",
    activeGutterFg: "#98a2b1",
    activeLine: "#15181e",
    selection: "#2b4a63",
    selectionFocused: "#2f5b7a",
    placeholder: "#4a515e",
    tooltipBg: "#1b1f26",
    tooltipBorder: "#272c35",
  },
};

function editorTheme(name) {
  const p = CM_PALETTES[name];
  return EditorView.theme(
    {
      "&": { color: p.text, backgroundColor: p.bg, height: "100%" },
      ".cm-content": { caretColor: p.caret, padding: "14px 0" },
      ".cm-gutters": {
        backgroundColor: p.bg,
        color: p.gutterFg,
        border: "none",
        borderRight: `1px solid ${p.gutterBorder}`,
        paddingRight: "6px",
      },
      ".cm-activeLineGutter": { backgroundColor: p.activeGutterBg, color: p.activeGutterFg },
      ".cm-activeLine": { backgroundColor: p.activeLine },
      ".cm-scroller": {
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
        fontSize: "13px",
        lineHeight: "1.6",
      },
      ".cm-selectionBackground": { backgroundColor: p.selection },
      "&.cm-focused .cm-selectionBackground": { backgroundColor: p.selectionFocused },
      ".cm-cursor": { borderLeftColor: p.caret },
      ".cm-placeholder": { color: p.placeholder },
      ".cm-tooltip": {
        backgroundColor: p.tooltipBg,
        border: `1px solid ${p.tooltipBorder}`,
        color: p.text,
      },
    },
    { dark: name === "dark" },
  );
}

// The theme and its syntax colours always travel together, so they can never
// disagree; a Compartment swaps them without rebuilding the whole view.
function themeExtensions(name) {
  return [editorTheme(name), syntaxHighlighting(aetherHighlightStyles[name])];
}

// Resolved before first paint by the inline script in index.html.
export function currentTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

// ---------------------------------------------------------------------------
// Key bindings
//
// basicSetup does NOT bind Tab, and its default indent unit is two spaces.
// Aether's grammar is indentation-sensitive with tab_len = 4, so both are
// overridden here.
// ---------------------------------------------------------------------------

// CodeMirror's own `insertTab` inserts a literal TAB character -- it never
// consults the indentUnit facet.  Aether's grammar is indentation-sensitive and
// every bundled proof uses four spaces, so Tab must emit spaces instead.
function insertAetherTab(view) {
  const { state } = view;
  // With a selection, re-indent the touched lines; indentMore honours the
  // indentUnit facet set below.
  if (state.selection.ranges.some((range) => !range.empty)) return indentMore(view);

  view.dispatch(state.replaceSelection(INDENT), {
    scrollIntoView: true,
    userEvent: "input",
  });
  return true;
}

function insertAetherNewline(view) {
  const { state } = view;
  const range = state.selection.main;
  if (!range.empty) return false;

  const line = state.doc.lineAt(range.head);
  const beforeCursor = line.text.slice(0, range.head - line.from);
  // A trailing ':' opens a block (Proof:, Theorem:, Case:), so indent one more.
  const opensBlock = /:[ \t]*$/.test(beforeCursor);
  const leading = (line.text.match(/^[ \t]*/) || [""])[0];

  view.dispatch(state.replaceSelection(`\n${leading}${opensBlock ? INDENT : ""}`), {
    scrollIntoView: true,
    userEvent: "input",
  });
  return true;
}

const aetherKeymap = keymap.of([
  { key: "Tab", run: insertAetherTab },
  { key: "Shift-Tab", run: indentLess },
  { key: "Enter", run: insertAetherNewline },
]);

// ---------------------------------------------------------------------------
// The view
// ---------------------------------------------------------------------------

/**
 * Build the editor.
 *
 * The two callbacks are injected rather than imported so this module knows
 * nothing about the auditor: `onDocChanged` fires on real edits (never on
 * programmatic ones) and `onSelectionMoved` fires with a 1-based line number
 * when the caret moves without editing -- including a click that lands where
 * the caret already was, which fires no selection change at all.
 */
export function createEditor({ parent, onDocChanged, onSelectionMoved }) {
  const themeCompartment = new Compartment();

  // Declared before the view; the update listener below captures it.
  let programmaticChange = false;

  const view = new EditorView({
    parent,
    doc: "",
    extensions: [
      // Placed first so these win over basicSetup's default keymap.
      aetherKeymap,
      aetherLanguage,
      indentUnit.of(INDENT),
      themeCompartment.of(themeExtensions(currentTheme())),
      basicSetup,
      placeholder("Write an Aether proof here, or load an example above…"),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          if (!programmaticChange) onDocChanged();
          return;
        }
        // Moving the caret without editing (arrow keys, Home/End, PageUp/Down)
        // re-targets the Context panel.  Edits are excluded on purpose, so the
        // panel does not churn on every keystroke while you type.
        if (update.selectionSet) {
          const { state } = update;
          onSelectionMoved(state.doc.lineAt(state.selection.main.head).number);
        }
      }),
      // Clicking a line also drives the panel.  This is separate from the caret
      // listener above because a click landing exactly where the caret already
      // was fires no selection change at all.
      EditorView.domEventHandlers({
        mousedown: (event, v) => {
          const pos = v.posAtCoords({ x: event.clientX, y: event.clientY });
          if (pos != null) onSelectionMoved(v.state.doc.lineAt(pos).number);
          return false; // let CodeMirror place the caret as usual
        },
      }),
    ],
  });

  return {
    view,

    getSource: () => view.state.doc.toString(),

    setContent(text) {
      programmaticChange = true;
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
      programmaticChange = false;
    },

    setTheme(name) {
      view.dispatch({ effects: themeCompartment.reconfigure(themeExtensions(name)) });
    },
  };
}
