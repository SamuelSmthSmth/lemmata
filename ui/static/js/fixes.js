// Applying a hint's fix to the proof: the engine says what to change, the
// editor makes the change, and the check that follows says whether it worked.
//
// A fix is one of (aether.engine.hints):
//   {line, insert_before, label}                  a new line above `line`
//   {line, col_start, col_end, text, was, label}  replace `was` on `line`
// with 1-based lines and columns.  It goes through the editor as one ordinary
// edit, so Ctrl+Z takes it back.  If the line no longer holds what the check
// saw, the fix is refused rather than applied to the wrong text.
//
// `fixChange` is pure, so verify_frontend.mjs tests it in Node.

/**
 * The change a fix makes to *doc* (a CodeMirror Text), or null when it no
 * longer applies.  `doc.line(n)` gives `{from, to, text}`.
 */
export function fixChange(doc, fix) {
  if (!fix || !Number.isInteger(fix.line) || fix.line < 1 || fix.line > doc.lines) return null;
  const line = doc.line(fix.line);
  if (typeof fix.insert_before === "string") {
    const indent = line.text.slice(0, line.text.length - line.text.trimStart().length);
    return { from: line.from, to: line.from, insert: `${indent}${fix.insert_before}\n` };
  }
  if (Number.isInteger(fix.col_start) && Number.isInteger(fix.col_end) && typeof fix.text === "string") {
    const from = line.from + fix.col_start - 1;
    const to = line.from + fix.col_end - 1;
    if (to > line.to || from > to) return null;
    if (typeof fix.was === "string" && doc.sliceString(from, to) !== fix.was) return null;
    return { from, to, insert: fix.text };
  }
  return null;
}

/** Apply *fix* in *view*; returns whether it applied. */
export function applyFix(view, fix) {
  const change = fixChange(view.state.doc, fix);
  if (!change) return false;
  view.dispatch({
    changes: change,
    selection: { anchor: change.from + change.insert.length },
    scrollIntoView: true,
    userEvent: "input.fix",
  });
  view.focus();
  return true;
}
