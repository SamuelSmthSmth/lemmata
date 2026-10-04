// Check results as editor diagnostics: squiggles, gutter marks and hovers.
//
// Push-based on purpose.  The check that fills the auditor already carries a
// status per line, so the editor is told about it with `setDiagnostics` rather
// than asking a linter to run a second check.  What a diagnostic says is the
// same text the auditor shows, built by the same helper (`splitStepText`), so
// the two can never disagree about why a step failed.

import { lintGutter, nextDiagnostic, previousDiagnostic, setDiagnostics } from "../vendor/esm/@codemirror/lint@6.mjs";
import { splitStepText } from "./format.js";
import { applyFix } from "./fixes.js";

// What a fix in the tooltip does: main.js routes it through the same path as
// Context & state's button, which warns when the proof has changed.
let onFix = (view, fix) => applyFix(view, fix);
export function setLintFixHandler(fn) {
  onFix = fn;
}

/** The extensions to add to the editor once. */
export function lintExtensions() {
  return [
    // Gutter marks only for what needs attention; valid lines stay unmarked,
    // the editor's counterpart of the auditor's "a step that held is not news".
    lintGutter({ hoverTime: 250 }),
  ];
}

export const lintCommands = { nextDiagnostic, previousDiagnostic };

/** The range of line *n* without its indentation, so the squiggle sits under the statement. */
function lineRange(doc, n) {
  if (n == null || n < 1 || n > doc.lines) return null;
  const line = doc.line(n);
  const indent = line.text.length - line.text.trimStart().length;
  const from = line.from + indent;
  return { from, to: Math.max(from, line.to) };
}

function stepDiagnostic(doc, result) {
  if (result.status === "VALID" && !result.domain_warnings?.length) return null;
  const range = lineRange(doc, result.line);
  if (!range) return null;
  const { message, callouts } = splitStepText(result);
  const hints = result.hints ?? [];
  const parts = [message, ...callouts.map((c) => c.text), ...hints.map((h) => h.message)].filter(Boolean);
  return {
    from: range.from,
    to: range.to,
    severity: result.status === "INVALID" ? "error" : "warning",
    source: result.backend,
    message: parts.join("\n"),
    // A hint's fix, one click from the squiggle's tooltip.
    actions: hints.filter((h) => h.fix).map((h) => ({ name: h.fix.label, apply: (view) => onFix(view, h.fix) })),
  };
}

/** Diagnostics for a check response, against the document it describes. */
export function diagnosticsFor(doc, data) {
  if (!data) return [];
  if (data.parse_error) {
    const err = data.parse_error;
    if (err.line == null) {
      // No location (a timeout, an engine fault): flag the first line, so the
      // gutter still shows that something needs reading.
      const range = lineRange(doc, 1);
      return range ? [{ ...range, severity: data.verdict === "TIMEOUT" ? "warning" : "error", message: `${err.headline}\n${err.message}` }] : [];
    }
    const line = doc.line(Math.min(Math.max(err.line, 1), doc.lines));
    const from = Math.min(line.from + Math.max((err.col ?? 1) - 1, 0), line.to);
    return [{ from, to: Math.max(from + 1, line.to), severity: "error", source: "Parser", message: err.headline }];
  }
  const out = [];
  const seen = new Set();
  for (const report of data.reports) {
    for (const result of report.results) {
      const diagnostic = stepDiagnostic(doc, result);
      // A line can carry several results (a subproof header and its QED); one mark each.
      const key = diagnostic && `${diagnostic.from}:${diagnostic.severity}`;
      if (diagnostic && !seen.has(key)) {
        seen.add(key);
        out.push(diagnostic);
      }
      for (const sub of result.sub_results ?? []) {
        const inner = stepDiagnostic(doc, sub);
        const innerKey = inner && `${inner.from}:${inner.severity}`;
        if (inner && !seen.has(innerKey)) {
          seen.add(innerKey);
          out.push(inner);
        }
      }
    }
  }
  return out.sort((a, b) => a.from - b.from);
}

/** Show *data*'s diagnostics in *view*; pass null to clear them. */
export function showDiagnostics(view, data) {
  view.dispatch(setDiagnostics(view.state, diagnosticsFor(view.state.doc, data)));
}
