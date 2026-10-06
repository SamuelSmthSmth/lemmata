// The proof graph: what each line was proved from, drawn as arcs in the
// auditor's gutter.
//
// The proof's lines are already its nodes, in the order a reader takes them,
// so the graph needs no layout of its own: an arc runs from a line up (or, for
// QED, down) to each line it rests on.  With a step selected, its premises are
// drawn in the accent and their line numbers lit, the lines that use it in
// quiet ink; the pane head's toggle adds every other arc, faintly.  The arcs
// are a picture of what Context & state lists as "Used" and "Used by", which
// is where a screen reader and the keyboard get the same facts.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { getPref, setPref } from "./prefs.js";

const SVG = "http://www.w3.org/2000/svg";

/** Whether the last check carried the audit (premises and trace). */
export function hasGraph() {
  return state.steps.some((entry) => entry.result.premises?.length || entry.result.trace?.length);
}

/** The auditor row a premise on source line *line* belongs to: the row on that
 *  line, or the block (a subproof, a case) whose lines contain it. */
function rowForLine(line) {
  let best = -1;
  state.steps.forEach((entry, i) => {
    const at = entry.result.line;
    if (at == null || at > line) return;
    if (best === -1 || at >= state.steps[best].result.line) best = i;
  });
  return best;
}

/** What step *index* was proved from: `{index, premise}` for each premise on a
 *  line of this proof (an earlier theorem or a cited result has no row). */
export function premisesOf(index) {
  const result = state.steps[index]?.result;
  if (!result) return [];
  const out = [];
  for (const premise of result.premises ?? []) {
    if (premise.line == null) {
      out.push({ index: -1, premise });
      continue;
    }
    const row = rowForLine(premise.line);
    out.push({ index: row === index ? -1 : row, premise });
  }
  return out;
}

/** The steps that used step *index*, in order. */
export function dependentsOf(index) {
  const out = [];
  state.steps.forEach((_, i) => {
    if (i !== index && premisesOf(i).some((p) => p.index === index)) out.push(i);
  });
  return out;
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

let svg = null;
let observer = null;

function anchor(row) {
  // The middle of the statement's first line: the row's top padding plus half
  // a 13px line at 1.45.
  return row.offsetTop + 8 + 9.5;
}

function arcPath(x, y1, y2, reach) {
  const span = Math.abs(y2 - y1);
  const bulge = Math.min(reach, 5 + Math.sqrt(span) * 1.6);
  return `M ${x} ${y1} C ${x - bulge} ${y1}, ${x - bulge} ${y2}, ${x} ${y2}`;
}

function node(tag, attrs) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
}

/** Draw the arcs.  *animate* (a new selection) lets the premises draw in; a
 *  re-check while typing, or a resize, redraws them still. */
export function drawGraph({ animate = false } = {}) {
  const audit = dom.audit;
  const on = hasGraph() && document.body.dataset.exercise !== "hidden";
  audit.classList.toggle("has-graph", on);
  dom.graphToggle.hidden = !on;
  for (const row of audit.querySelectorAll(".step.is-premise, .step.is-dependent")) {
    row.classList.remove("is-premise", "is-dependent");
  }
  if (!on) {
    svg?.remove();
    svg = null;
    return;
  }

  const rows = [...audit.querySelectorAll(".step")];
  const first = rows[0];
  if (!first) return;
  // The gutter is the column gap between the line number and the statement.
  const line = first.querySelector(".step-line");
  const body = first.querySelector(".step-body");
  const x = body.offsetLeft - 7;
  const reach = Math.max(8, x - (line.offsetLeft + line.offsetWidth) - 4);

  if (!svg) {
    svg = node("svg", { class: "arcs", "aria-hidden": "true", focusable: "false" });
  }
  audit.append(svg);
  svg.setAttribute("width", String(x + 2));
  svg.setAttribute("height", String(audit.scrollHeight));
  svg.replaceChildren();

  const rowAt = (i) => rows.find((r) => Number(r.dataset.index) === i);
  const selected = state.selected;

  if (getPref("graph") === "all") {
    const quiet = node("g", { class: "arcs-all" });
    state.steps.forEach((_, i) => {
      if (i === selected) return;
      const from = rowAt(i);
      for (const { index, premise } of premisesOf(i)) {
        if (index < 0 || index === selected) continue;
        const to = rowAt(index);
        if (!from || !to) continue;
        const path = node("path", { d: arcPath(x, anchor(from), anchor(to), reach) });
        if (premise.kind === "chain") path.setAttribute("class", "arc-chain");
        quiet.append(path);
      }
    });
    svg.append(quiet);
  }

  if (selected === null || !rowAt(selected)) return;
  const here = rowAt(selected);
  const y0 = anchor(here);

  const used = node("g", { class: "arcs-dependents" });
  for (const i of dependentsOf(selected)) {
    const row = rowAt(i);
    if (!row) continue;
    row.classList.add("is-dependent");
    used.append(node("path", { d: arcPath(x, y0, anchor(row), reach) }));
    used.append(node("circle", { cx: x, cy: anchor(row), r: 1.75 }));
  }
  svg.append(used);

  const premises = node("g", { class: "arcs-premises" });
  for (const { index, premise } of premisesOf(selected)) {
    const row = index >= 0 ? rowAt(index) : null;
    if (!row) continue;
    row.classList.add("is-premise");
    const path = node("path", { d: arcPath(x, y0, anchor(row), reach) });
    if (premise.kind === "chain") {
      path.setAttribute("class", "arc-chain");
    } else if (animate) {
      // Drawn in from the selected step: the dash runs the path's length.
      path.setAttribute("pathLength", "1");
      path.setAttribute("class", "arc-draw");
    }
    premises.append(path);
    premises.append(node("circle", { cx: x, cy: anchor(row), r: 2 }));
  }
  if (premises.childNodes.length) premises.append(node("circle", { cx: x, cy: y0, r: 2.25, class: "arc-here" }));
  svg.append(premises);
}

function syncToggle() {
  const all = getPref("graph") === "all";
  dom.graphToggle.setAttribute("aria-pressed", String(all));
  dom.graphToggle.setAttribute("aria-label", all ? "Show only the selected line's arcs" : "Show what every line used");
}

export function initGraph() {
  syncToggle();
  dom.graphToggle.addEventListener("click", () => {
    setPref("graph", getPref("graph") === "all" ? "selected" : "all");
    syncToggle();
    drawGraph();
  });
  // Rows reflow when the pane is resized or text wraps differently; the arcs
  // follow the rows.
  observer = new ResizeObserver(() => {
    if (svg) drawGraph();
  });
  observer.observe(dom.audit);
}
