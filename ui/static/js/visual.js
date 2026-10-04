// Visual mode: the editor typesets each expression in place.
//
// Overleaf's Visual Editor for proofs.  Every span of mathematics that
// visual-math.js can read is replaced by a widget holding its MathML, and the
// span under the caret or a selection is left as source, so moving into an
// expression opens it for editing and moving out sets it again.  Keywords,
// labels and justifications are never touched: the proof still reads as the
// text that is checked.
//
// Nothing here changes the document.  The widgets are decorations, so copy,
// undo, the check and every export see exactly what was typed.

import { Decoration, EditorView, GutterMarker, ViewPlugin, WidgetType, lineNumberMarkers } from "../vendor/esm/@codemirror/view@6.mjs";
import { RangeSet, RangeSetBuilder, StateEffect, StateField } from "../vendor/esm/@codemirror/state@6.mjs";
import { forEachDiagnostic, setDiagnosticsEffect } from "../vendor/esm/@codemirror/lint@6.mjs";
import { mathSpans, renderSpan } from "../visual-math.js";

class MathWidget extends WidgetType {
  constructor(markup, source, severity) {
    super();
    this.markup = markup;
    this.source = source;
    this.severity = severity;
  }

  eq(other) {
    return other.markup === this.markup && other.severity === this.severity;
  }

  toDOM() {
    const span = document.createElement("span");
    // A failing step's squiggle is a mark, and CodeMirror does not wrap a mark
    // round a widget that ends where the mark does -- which an expression at
    // the end of its line always does.  So the widget wears the lint classes
    // itself, and the failure stays underlined all the way along.
    span.className = this.severity ? `cm-math cm-lintRange cm-lintRange-${this.severity}` : "cm-math";
    // The source, for a pointer that rests on it; the MathML itself is what a
    // screen reader reads.
    span.title = this.source;
    span.innerHTML = this.markup;
    return span;
  }

  // Let CodeMirror place the caret from a click, which lands it at the
  // widget's edge and so opens the expression.
  ignoreEvent() {
    return false;
  }
}

// Lines repeat (every `Step: = …` in a chain is short, and re-rendering on
// every caret move re-reads them all), so each line's spans are read once.
const cache = new Map();
const CACHE_LIMIT = 2000;

function spansFor(text) {
  let spans = cache.get(text);
  if (!spans) {
    spans = [];
    for (const s of mathSpans(text)) {
      const markup = renderSpan(s);
      if (markup) spans.push({ from: s.from, to: s.to, markup, source: s.text });
    }
    if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value);
    cache.set(text, spans);
  }
  return spans;
}

// The expression the caret has opened, marked so the unit being edited is
// visible against the typeset lines around it.
const OPENED = Decoration.mark({ class: "cm-math-open" });

const SEVERITY_RANK ={ hint: 1, info: 2, warning: 3, error: 4 };

/** The worst diagnostic over [from, to], or null. */
function severityAt(diagnostics, from, to) {
  let worst = null;
  for (const d of diagnostics) {
    if (d.from > to || d.to < from) continue;
    if (!worst || SEVERITY_RANK[d.severity] > SEVERITY_RANK[worst]) worst = d.severity;
  }
  return worst;
}

function build(view) {
  const builder = new RangeSetBuilder();
  const { state } = view;
  const { doc, selection } = state;
  const diagnostics = [];
  forEachDiagnostic(state, (d, from, to) => diagnostics.push({ from, to, severity: d.severity }));
  // A span the caret touches, even at its edge, stays as source: that is how
  // arrowing into it, clicking it or selecting across it opens it.
  const open = (from, to) => selection.ranges.some((r) => r.from <= to && r.to >= from);
  // MathML does not break across lines.  With wrapping on, a line too long
  // for the editor keeps its source, which wraps; typeset, it would overflow.
  const columns = view.lineWrapping ? Math.floor(view.contentDOM.clientWidth / view.defaultCharacterWidth) - 2 : Infinity;
  let done = 0; // the last line added; two visible ranges can share one
  for (const { from, to } of view.visibleRanges) {
    for (let pos = from; pos <= to; ) {
      const line = doc.lineAt(pos);
      pos = line.to + 1;
      if (line.number <= done) continue;
      done = line.number;
      if (line.length > columns) continue;
      for (const s of spansFor(line.text)) {
        const a = line.from + s.from;
        const b = line.from + s.to;
        if (open(a, b)) {
          builder.add(a, b, OPENED);
          continue;
        }
        const widget = new MathWidget(s.markup, s.source, severityAt(diagnostics, a, b));
        builder.add(a, b, Decoration.replace({ widget }));
      }
    }
  }
  return builder.finish();
}

// ---------------------------------------------------------------------------
// Line numbers on a typeset line
//
// A fraction or a sum's limits make a line taller, and CodeMirror sets the
// line number at the top of the line's box, so it rides above the keyword.
// Centring is only right when the maths reaches as far below the baseline as
// above it.  So the drop is measured after layout -- how far below its usual
// place the line's first text now sits -- and that line's number is supplied
// as a marker padded down by exactly that much.
// ---------------------------------------------------------------------------

class NumberMarker extends GutterMarker {
  constructor(number, drop) {
    super();
    this.number = number;
    this.drop = drop;
  }

  eq(other) {
    return other.number === this.number && other.drop === this.drop;
  }

  toDOM() {
    const span = document.createElement("span");
    span.textContent = String(this.number);
    // Shifted, not padded: padding would make the gutter's own line box taller.
    span.style.position = "relative";
    span.style.top = `${this.drop}px`;
    return span;
  }
}

const setDrops = StateEffect.define();

const dropsField = StateField.define({
  create: () => RangeSet.empty,
  update(markers, tr) {
    for (const e of tr.effects) if (e.is(setDrops)) return e.value;
    return markers.map(tr.changes);
  },
  provide: (field) => lineNumberMarkers.from(field),
});

/** The line's first text outside the maths, as a Range, or null. */
function firstText(line) {
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => (node.parentElement.closest(".cm-math") || !node.textContent.trim() ? NodeFilter.FILTER_SKIP : NodeFilter.FILTER_ACCEPT),
  });
  const node = walker.nextNode();
  if (!node) return null;
  const range = document.createRange();
  range.selectNodeContents(node);
  return range;
}

function measureDrops(view) {
  const drops = [];
  for (const math of view.contentDOM.querySelectorAll(".cm-line .cm-math")) {
    const line = math.closest(".cm-line");
    if (drops.length && drops.at(-1).line === line) continue;
    const text = firstText(line);
    if (!text) continue;
    const box = text.getBoundingClientRect();
    const top = line.getBoundingClientRect().top;
    // Where the text sits in a plain line: centred in the line height.
    const drop = Math.round(box.top - top - (view.defaultLineHeight - box.height) / 2);
    if (drop > 0) drops.push({ line, pos: view.posAtDOM(line), drop });
  }
  return drops;
}

function sameDrops(markers, drops, doc) {
  const old = [];
  markers.between(0, doc.length, (from, _to, m) => {
    old.push(`${from}:${m.drop}`);
  });
  return old.join() === drops.map((d) => `${doc.lineAt(d.pos).from}:${d.drop}`).join();
}

const visualPlugin = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = build(view);
      this.schedule(view);
    }

    update(update) {
      const linted = update.transactions.some((tr) => tr.effects.some((e) => e.is(setDiagnosticsEffect)));
      const changed = update.docChanged || update.selectionSet || update.viewportChanged || update.geometryChanged;
      if (linted || changed) {
        this.decorations = build(update.view);
        this.schedule(update.view);
      }
    }

    schedule(view) {
      view.requestMeasure({
        key: this,
        read: measureDrops,
        write: (drops, v) => {
          const { doc } = v.state;
          if (sameDrops(v.state.field(dropsField), drops, doc)) return;
          const markers = RangeSet.of(drops.map((d) => {
            const line = doc.lineAt(d.pos);
            return new NumberMarker(line.number, d.drop).range(line.from);
          }));
          // Dispatching from a measure write is not allowed; the next frame is.
          requestAnimationFrame(() => v.dispatch({ effects: setDrops.of(markers) }));
        },
      });
    }
  },
  { decorations: (plugin) => plugin.decorations },
);

/** The extensions for visual mode; an empty list turns it off. */
export function visualMath() {
  return [visualPlugin, dropsField, EditorView.editorAttributes.of({ class: "cm-visual" })];
}
