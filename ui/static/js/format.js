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

export function note(label, text, className) {
  const box = el("div", `note ${className}`);
  box.append(el("span", "note-label", label), document.createTextNode(text));
  return box;
}

// Status and backend markers are Web Awesome badges. The variant carries the
// meaning; the tinted `accent` appearance keeps them from shouting on a screen
// that has eight of them at once.
const STATUS_VARIANT = { VALID: "success", WARNING: "warning", INVALID: "danger" };

export function badge(status) {
  const node = document.createElement("wa-badge");
  node.className = "badge";
  node.variant = STATUS_VARIANT[status] ?? "neutral";
  node.appearance = "accent";
  node.textContent = status;
  return node;
}

/** The engine component that verified a step (SymPy, Z3, ChainGuard, ...). */
export function backendBadge(name) {
  const node = document.createElement("wa-badge");
  node.className = "backend";
  node.variant = "neutral";
  node.appearance = "outlined";
  node.textContent = name;
  return node;
}

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
