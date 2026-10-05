// Small DOM-building helpers shared by the panes.
//
// Everything here is pure: no module state, no fetching.  That keeps the
// panes (audit.js / context.js / verdict.js) free to import these without
// creating any dependency between each other.

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/**
 * A callout attached to a step.
 *
 * The engine's own sentences already name themselves -- "Counterexample at
 * x=3: …", "Unresolved domain obligation: …" -- so a label above one of those
 * just repeats its first two words in caps.  Pass a label only when the value
 * is a bare expression and needs one.
 */
export function note(label, text, className) {
  const box = el("div", `note ${className}`);
  if (label) box.append(el("span", "note-label", label));
  box.append(document.createTextNode(text));
  return box;
}

/**
 * Separate a step result into the prose worth printing quietly and the failures
 * worth printing loudly.
 *
 * The engine repeats itself, which is fine for a machine and tiresome to read:
 * a failing obligation arrives as the message *and* as a warning, and an
 * algebraic failure's message ends with the same "Counterexample at x=3: …"
 * sentence the callout shows.  Rendering both states every failure twice, so
 * any sentence a callout is about to display is stripped out of the prose and
 * the caller drops the prose if nothing is left.
 */
export function splitStepText(result) {
  const callouts = [];
  if (result.counterexample) {
    callouts.push({ text: result.counterexample, className: "note--counterexample" });
  }
  for (const warning of result.domain_warnings) {
    callouts.push({ text: warning, className: "note--domain" });
  }

  let message = result.message ?? "";
  for (const { text } of callouts) message = message.split(text).join("");

  return { message: message.replace(/\s+/g, " ").trim(), callouts };
}

// Status and backend markers are plain spans, styled by styles.css.  They were
// Web Awesome badges until the auditor stopped rendering a pill per row: eight
// passing rows should not look as loud as the one that failed.

export function chipList(pairs, emptyText) {
  if (!pairs.length) return el("p", "ctx-none", emptyText);
  const wrap = el("div", "chips");
  for (const [name, type] of pairs) {
    const chip = el("span", "chip");
    chip.append(
      el("span", "chip-name", name),
      document.createTextNode(" : "),
      el("span", "chip-type", type),
    );
    wrap.append(chip);
  }
  return wrap;
}

export function bulletList(items, emptyText) {
  if (!items.length) return el("p", "ctx-none", emptyText);
  const list = el("ul", "ctx-list");
  for (const item of items) list.append(el("li", null, item));
  return list;
}

export function section(title, nodes) {
  const wrap = el("div", "ctx-section");
  wrap.append(el("h3", null, title));
  for (const node of nodes) wrap.append(node);
  return wrap;
}

export function verdictClass(verdict, parseError) {
  if (parseError) return "verdict--parse-error";
  if (verdict === "VALID") return "verdict--valid";
  if (verdict === "VALID (with domain warnings)") return "verdict--warning";
  return "verdict--invalid";
}

/**
 * The verdict as shown.  The API calls every warned verdict "VALID (with
 * domain warnings)", a name it keeps for compatibility; a warning about
 * skipped working or an incomplete case split is not about domains, so what
 * the student reads says only what is true of *reports*.
 */
export function verdictLabel(verdict, reports) {
  if (verdict !== "VALID (with domain warnings)") return verdict;
  const domains = (reports ?? []).some((report) => report.results.some((r) => r.domain_warnings?.length));
  return domains ? verdict : "VALID (with warnings)";
}
