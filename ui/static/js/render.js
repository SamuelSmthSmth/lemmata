// Applying a check response to the whole UI.
//
// Lives apart from main.js so that the wiring there (event listeners, boot
// order) and the rendering here stay separately readable.

import { state, flatten } from "./state.js";
import { renderVerdict } from "./verdict.js";
import { renderAudit } from "./audit.js";
import { renderContext } from "./context.js";

export function applyResponse(data) {
  const previous =
    state.selected !== null && state.steps[state.selected] ? state.steps[state.selected] : null;
  const previousLine = previous ? previous.result.line : null;
  const previousStatement = previous ? previous.result.statement : null;

  state.data = data;
  state.steps = flatten(data);

  // Re-anchor the selection so a re-check never yanks it away.  Matching on the
  // statement text as well as the line keeps the anchor correct when an edit
  // shifts the lines below it, e.g. pressing Enter part-way through a proof.
  const find = (predicate) => state.steps.findIndex(predicate);
  let next = null;
  if (previousLine !== null && previousStatement !== null) {
    const both = find(
      (entry) => entry.result.line === previousLine && entry.result.statement === previousStatement,
    );
    if (both !== -1) next = both;
  }
  if (next === null && previousStatement !== null) {
    const byStatement = find((entry) => entry.result.statement === previousStatement);
    if (byStatement !== -1) next = byStatement;
  }
  if (next === null && previousLine !== null) {
    const byLine = find((entry) => entry.result.line === previousLine);
    if (byLine !== -1) next = byLine;
  }
  if (next === null && state.selected !== null && state.selected < state.steps.length) {
    next = state.selected;
  }
  state.selected = next;

  renderVerdict(data);
  renderAudit(data);
  renderContext();
}
