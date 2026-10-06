// The auditor pane: the per-statement readout, selection, and keyboard nav.
//
// Selection is purely client-side.  Moving between steps re-renders the
// context pane from the report already in memory; it never calls the backend.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { el, note, splitStepText, verdictLabel } from "./format.js";
import { renderContext } from "./context.js";
import { drawGraph } from "./graph.js";
import { followSelection } from "./trace.js";

function reportHeader(report) {
  const header = el("div", "report-header");
  if (report.theorem_name) {
    header.append(
      el("span", null, "Theorem"),
      el("span", "report-name", `"${report.theorem_name}"`),
    );
  } else {
    header.append(el("span", null, "Scratchpad"));
  }
  header.append(el("span", "report-verdict", verdictLabel(report.verdict, [report])));
  return header;
}

function parseErrorCard(error) {
  const card = el("div", "parse-error");
  card.append(el("h3", null, "Parse error"));
  card.append(
    el(
      "div",
      "location",
      error.line != null
        ? `Line ${error.line}, column ${error.col ?? "?"}`
        : "Location unavailable",
    ),
  );
  card.append(el("pre", null, error.message));
  return card;
}

/** Status and provenance, set as type rather than as a row of pills.
 *
 * A pill per row made eight passing steps as loud as the one that failed, which
 * is backwards -- a valid step is the unremarkable case.  The word is always
 * present (it has to be; the audit contract requires the status), but only a
 * warning or a failure earns colour.
 */
function stepMeta(result) {
  const meta = el("span", "step-meta");
  meta.append(el("span", `status status--${result.status.toLowerCase()}`, result.status));
  if (result.backend) {
    meta.append(el("span", "meta-sep", "·"), el("span", "backend", result.backend));
  }
  if (result.scope_depth > 0) {
    meta.append(el("span", "meta-sep", "·"), el("span", "depth", `depth ${result.scope_depth}`));
  }
  return meta;
}

function stepRow(entry, index) {
  const { result } = entry;
  const row = el("button", `step step--${result.status.toLowerCase()}`);
  row.type = "button";
  row.dataset.index = String(index);
  const selected = state.selected === index;
  if (selected) row.classList.add("is-selected");
  row.setAttribute("aria-pressed", selected ? "true" : "false");
  // Roving tabindex: the whole auditor is one tab stop and the arrow keys move
  // within it, instead of every step being its own tab stop.
  row.tabIndex = selected || (state.selected === null && index === 0) ? 0 : -1;

  // The margin holds the source line and nothing else.
  row.append(el("span", "step-line", `${result.line ?? "?"}`));

  const body = el("div", "step-body");
  const head = el("div", "step-head");
  head.append(el("code", "step-statement", result.statement));
  head.append(stepMeta(result));
  body.append(head);

  const { message, callouts } = splitStepText(result);
  if (message) body.append(el("p", "step-message", message));
  // No labels: each engine sentence already names itself.
  for (const { text, className } of callouts) body.append(note(null, text, className));
  // What to try, in prose; the fixes themselves are buttons in Context & state
  // and in the editor's diagnostic, since this row is itself a button.
  for (const hint of result.hints ?? []) body.append(el("p", "step-hint", hint.message));
  row.append(body);

  row.addEventListener("click", () => selectStep(index, { focus: true }));
  return row;
}

export function renderAudit(data) {
  renderRows(data);
  // The arcs are measured from the rows, so they are drawn once the rows are in.
  drawGraph();
}

function renderRows(data) {
  dom.audit.replaceChildren();

  if (data.parse_error) {
    dom.audit.append(parseErrorCard(data.parse_error));
    return;
  }

  if (!state.steps.length) {
    dom.audit.append(
      el(
        "p",
        "empty-state",
        "No statements to audit yet. Write a proof, or load an example from the menu above.",
      ),
    );
    return;
  }

  // The entailment rule.  A failed step invalidates everything that rests on
  // it, so the margin rule turns red at the break and stays red to the end of
  // the proof rather than marking one isolated row.  This is the one thing the
  // layout knows that a flat list of results does not.
  const firstInvalid = state.steps.findIndex((entry) => entry.result.status === "INVALID");

  let flatIndex = 0;
  for (const report of data.reports) {
    const group = el("div", "report-group");
    if (data.reports.length > 1 || report.theorem_name) group.append(reportHeader(report));
    for (const result of report.results) {
      const row = stepRow(state.steps[flatIndex], flatIndex);
      if (firstInvalid !== -1 && flatIndex === firstInvalid) row.classList.add("is-break");
      if (firstInvalid !== -1 && flatIndex > firstInvalid) row.classList.add("is-downstream");
      group.append(row);
      flatIndex += 1;
    }
    dom.audit.append(group);
  }
}

export function selectStep(index, { focus = false } = {}) {
  if (index < 0 || index >= state.steps.length) return;
  state.selected = index;
  for (const node of dom.audit.querySelectorAll(".step")) {
    const isSelected = Number(node.dataset.index) === index;
    node.classList.toggle("is-selected", isSelected);
    node.setAttribute("aria-pressed", isSelected ? "true" : "false");
    node.tabIndex = isSelected ? 0 : -1;
  }
  if (focus) focusStepRow(index);
  drawGraph({ animate: true });
  followSelection(index);
  renderContext();
}

export function focusStepRow(index) {
  const row = dom.audit.querySelector(`.step[data-index="${index}"]`);
  if (!row) return;
  row.focus();
  // Keep the row visible inside the scrolling auditor without scrolling the page.
  row.scrollIntoView({ block: "nearest" });
}

// Selecting by line never takes focus: focus and the caret must stay in the
// editor so typing continues to work.  Lines with no statement (QED, blank
// lines, comments) leave the current selection alone rather than clearing it.
export function selectStepForLine(line) {
  const index = state.steps.findIndex((entry) => entry.result.line === line);
  if (index === -1 || index === state.selected) return;
  selectStep(index);
  dom.audit.querySelector(`.step[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
}

// Arrow-key navigation. The listener sits on the auditor pane rather than the
// document, so CodeMirror keeps normal caret movement while typing.
const AUDIT_NAV_KEYS = new Set(["ArrowDown", "ArrowUp", "Home", "End"]);

function onAuditKeydown(event) {
  if (!AUDIT_NAV_KEYS.has(event.key) || !state.steps.length) return;
  const row = event.target instanceof Element ? event.target.closest(".step") : null;
  if (!row) return;

  const current = Number(row.dataset.index);
  const last = state.steps.length - 1;
  let next;
  if (event.key === "ArrowDown") next = Math.min(current + 1, last);
  else if (event.key === "ArrowUp") next = Math.max(current - 1, 0);
  else if (event.key === "Home") next = 0;
  else next = last;

  // Without this the arrow keys would also scroll the auditor pane.
  event.preventDefault();
  selectStep(next);
  focusStepRow(next);
}

export function initAuditNav() {
  dom.audit.addEventListener("keydown", onAuditKeydown);
}
