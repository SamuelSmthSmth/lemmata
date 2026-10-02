// Panel arrangement: four presets, plus drag-to-swap and keyboard reordering.
//
// The three panes live in a CSS grid.  Their *position* is expressed by a
// `data-slot` attribute ("a", "b", "c") -- slot 1, 2, 3 in reading order --
// and each arrangement says where those three slots sit.  Because the slot
// names are what the template areas reference, moving a pane is only ever a
// matter of swapping two slots; the arrangements themselves need no knowledge
// of which pane is where.
//
// That is also why the grid areas are set through an attribute rather than an
// inline style: the narrow-screen rule in styles.css has to be able to drop
// them again and fall back to a single stacked column, and an inline style
// would outrank it.
//
// The geometry itself is CSS (see the [data-layout] blocks in styles.css).
// This module owns only the state and the interactions: the preset menu, the
// grips, the swap.

const LAYOUT_KEY = "aether:layout";
const VERSION = 1;

// ---------------------------------------------------------------------------
// Pure logic -- no DOM, no storage.  Importable in Node: see
// ui/verify_frontend.mjs.
// ---------------------------------------------------------------------------

// Slot names, in reading order, as they appear in styles.css.
export const SLOTS = ["a", "b", "c"];

/** Left to right on load.  The editor is the thing you came for. */
export const DEFAULT_ORDER = ["editor", "audit", "context"];

/**
 * The four arrangements.  `id` doubles as the value of `data-layout` on the
 * grid and as the label of the corresponding `grid-template-areas` rule.
 *
 * "Split" and "Focus" are the two that deliberately *merge* panes: the auditor
 * and the context share a column, which is the nearest thing to docking one
 * panel inside another.
 */
export const ARRANGEMENTS = [
  { id: "columns", label: "Columns", hint: "Three panels across" },
  { id: "stack", label: "Stack", hint: "Three panels in one column" },
  { id: "split", label: "Split", hint: "Editor above, auditor and context beneath" },
  { id: "focus", label: "Focus", hint: "Editor beside a stacked auditor and context" },
];

const ARRANGEMENT_IDS = ARRANGEMENTS.map((arrangement) => arrangement.id);

/**
 * Editor above, auditor and context beneath: the working half of the
 * "notes beside the proof" desk, where the reading pane already takes a column.
 */
export const DEFAULT_ARRANGEMENT = "split";

export function isArrangement(id) {
  return ARRANGEMENT_IDS.includes(id);
}

/**
 * Coerce whatever is in storage into a usable layout.
 *
 * Storage is user-editable and survives upgrades, so nothing here is trusted:
 * an unknown arrangement falls back to the default, and the order is rebuilt
 * from the panes that actually exist rather than from the stored list.  A pane
 * missing from the stored order is appended; an id that no longer exists is
 * dropped.  This is the only place that has to know the two can disagree.
 */
export function normalizeLayout(stored, available = DEFAULT_ORDER) {
  const arrangement =
    stored && typeof stored.arrangement === "string" && isArrangement(stored.arrangement)
      ? stored.arrangement
      : DEFAULT_ARRANGEMENT;

  const order = [];
  if (stored && Array.isArray(stored.order)) {
    for (const id of stored.order) {
      if (available.includes(id) && !order.includes(id)) order.push(id);
    }
  }
  for (const id of available) {
    if (!order.includes(id)) order.push(id);
  }

  return { v: VERSION, arrangement, order };
}

/** Swap two panes' slots.  Returns a new order, or the same one if no-op. */
export function swapInOrder(order, idA, idB) {
  const a = order.indexOf(idA);
  const b = order.indexOf(idB);
  if (a === -1 || b === -1 || a === b) return order;
  const next = order.slice();
  next[a] = idB;
  next[b] = idA;
  return next;
}

/**
 * Move one pane `delta` slots along the order, clamped at the ends rather than
 * wrapped: wrapping is a surprising thing for an arrow key to do to a layout.
 */
export function moveInOrder(order, id, delta) {
  const from = order.indexOf(id);
  if (from === -1 || !delta) return order;
  const to = Math.max(0, Math.min(order.length - 1, from + delta));
  if (to === from) return order;
  const next = order.slice();
  next.splice(from, 1);
  next.splice(to, 0, id);
  return next;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

function readStored() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    // Private mode, quota, or a hand-edited value.  The default layout is
    // always a valid answer.
    return null;
  }
}

function persist() {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
    return true;
  } catch (error) {
    return false;
  }
}

const hasDom = typeof document !== "undefined" && typeof localStorage !== "undefined";

// Read at import time, so the arrangement is in place before the first paint:
// main.js is a deferred module, and applying the layout during evaluation
// still happens before the first frame is drawn.
export const layout = normalizeLayout(hasDom ? readStored() : null);

/**
 * The handle callers use.  `setArrangement` and `setOrder` are filled in by
 * the DOM section; in Node they are absent and `reset()` degrades to changing
 * the state object only.
 */
export const layoutApi = {
  arrangements: ARRANGEMENTS,
  get current() {
    return { arrangement: layout.arrangement, order: layout.order.slice() };
  },
  reset() {
    layout.arrangement = DEFAULT_ARRANGEMENT;
    layout.order = [...DEFAULT_ORDER];
    layoutApi.setArrangement?.(layout.arrangement);
    layoutApi.setOrder?.(layout.order);
    persist();
  },
};

// ---------------------------------------------------------------------------
// DOM wiring
//
// Skipped entirely when there is no document, so the pure functions above can
// be imported and exercised in Node.
// ---------------------------------------------------------------------------

if (hasDom) boot();

// Elements are looked up here rather than through js/dom.js, which is the app's
// usual registry: dom.js cannot be evaluated in Node, and this module has to be
// importable there for its pure half to be testable.
function boot() {
  const grid = document.querySelector("main.layout");
  const toggle = document.getElementById("layout-toggle");
  const popup = document.getElementById("layout-popup");
  const options = document.getElementById("layout-options");
  if (!grid || !toggle || !popup || !options) return;

  // Pane elements keyed by the id their class carries.  The order attribute is
  // not read back from here -- it is the source of truth, and apply() writes
  // the DOM from it.
  const panes = new Map();
  for (const pane of grid.querySelectorAll(".pane")) {
    for (const id of DEFAULT_ORDER) {
      if (pane.classList.contains(`pane--${id}`)) panes.set(id, pane);
    }
  }
  if (panes.size !== DEFAULT_ORDER.length) return;

  // Rebuild the order against the panes that were actually found, so a
  // mismatch cannot leave a pane unplaced.
  layout.order = normalizeLayout(layout, [...panes.keys()]).order;

  // --- Preset menu ---------------------------------------------------------

  const buttons = new Map();
  for (const arrangement of ARRANGEMENTS) {
    const button = el("button", "layout-option");
    button.type = "button";
    button.dataset.arrangement = arrangement.id;
    button.setAttribute("role", "menuitemradio");
    button.append(
      el("span", "layout-option-label", arrangement.label),
      el("span", "layout-option-hint", arrangement.hint),
      preview(arrangement.id),
    );
    button.addEventListener("click", () => {
      setArrangement(arrangement.id);
      closePopup();
    });
    buttons.set(arrangement.id, button);
    options.append(button);
  }

  function syncButtons() {
    for (const [id, button] of buttons) {
      const active = id === layout.arrangement;
      button.setAttribute("aria-checked", String(active));
      button.dataset.active = active ? "true" : "false";
    }
  }

  // --- Popup --------------------------------------------------------------

  function closePopup() {
    popup.active = false;
    toggle.setAttribute("aria-expanded", "false");
    toggle.focus();
  }

  toggle.addEventListener("click", () => {
    if (popup.active) {
      closePopup();
      return;
    }
    popup.active = true;
    toggle.setAttribute("aria-expanded", "true");
  });

  // <wa-popup> knows about the dismissals this module cannot see -- a click
  // outside, and Escape.
  popup.addEventListener("wa-hide", () => {
    toggle.setAttribute("aria-expanded", "false");
    toggle.focus();
  });

  // --- Grips --------------------------------------------------------------

  for (const [id, pane] of panes) {
    const head = pane.querySelector(".pane-head");
    if (!head) continue;

    const grip = el("button", "pane-grip");
    grip.type = "button";
    grip.draggable = true;
    grip.dataset.pane = id;
    grip.setAttribute("aria-label", `Move the ${id} panel`);
    grip.title = "Drag to swap panels, or press an arrow key to move this panel";
    grip.append(gripIcon());
    head.prepend(grip);

    grip.addEventListener("dragstart", (event) => {
      event.dataTransfer.effectAllowed = "move";
      // Some browsers cancel a drag with no payload set.
      event.dataTransfer.setData("text/plain", id);
      pane.dataset.dragging = "true";
      grid.dataset.dragging = id;
    });

    grip.addEventListener("dragend", () => {
      delete pane.dataset.dragging;
      delete grid.dataset.dragging;
      for (const other of panes.values()) delete other.dataset.dropTarget;
    });

    grip.addEventListener("keydown", (event) => {
      const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[event.key];
      if (step === undefined) return;
      event.preventDefault();
      setOrder(moveInOrder(layout.order, id, step), { focus: grip });
    });
  }

  // Drop targets are the panes, not the grips: the whole panel is the target,
  // which is what makes this feel like docking rather than aiming at a handle.
  for (const [id, pane] of panes) {
    pane.addEventListener("dragover", (event) => {
      const dragging = grid.dataset.dragging;
      if (!dragging || dragging === id) return;
      event.preventDefault(); // required, or no drop fires
      event.dataTransfer.dropEffect = "move";
      pane.dataset.dropTarget = "true";
    });

    pane.addEventListener("dragleave", () => {
      delete pane.dataset.dropTarget;
    });

    pane.addEventListener("drop", (event) => {
      delete pane.dataset.dropTarget;
      const source = event.dataTransfer.getData("text/plain") || grid.dataset.dragging;
      if (!source || source === id) return;
      event.preventDefault();
      setOrder(swapInOrder(layout.order, source, id));
    });
  }

  // --- Applying -----------------------------------------------------------

  function apply() {
    grid.dataset.layout = layout.arrangement;
    for (const [index, id] of layout.order.entries()) {
      const pane = panes.get(id);
      if (pane) pane.dataset.slot = SLOTS[index] ?? SLOTS[SLOTS.length - 1];
    }
    // Slot names are assigned by position, so reordering the nodes is not
    // strictly necessary for the grid -- but it is what keeps tab order and
    // screen-reader order in step with what is on screen, and it is what the
    // narrow-screen fallback (which ignores the slots) lays out from.
    for (const pane of layout.order.map((id) => panes.get(id)).filter(Boolean)) {
      grid.append(pane);
    }
    syncButtons();
  }

  function setArrangement(id) {
    if (!isArrangement(id) || id === layout.arrangement) return;
    layout.arrangement = id;
    apply();
    persist();
  }

  function setOrder(order, { focus = null } = {}) {
    if (order === layout.order) return;
    layout.order = order;
    apply();
    persist();
    if (focus && document.contains(focus)) focus.focus();
  }

  apply();
  Object.assign(layoutApi, { setArrangement, setOrder, apply, panes, grid });
}

// ---------------------------------------------------------------------------
// Small DOM helpers
//
// Not from format.js: this module has to stay importable in Node, and
// format.js reaches for the document.
// ---------------------------------------------------------------------------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function svgIcon(viewBox) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

/**
 * A miniature of the arrangement, drawn from the same slot grid the CSS uses.
 * Slot a is wide in "split", tall in "focus", and so on -- a picture of the
 * preset rather than a name for it.
 */
function preview(id) {
  const svg = svgIcon("0 0 34 22");
  svg.classList.add("layout-preview");
  const boxes = {
    columns: [
      [1, 1, 10, 20],
      [12, 1, 10, 20],
      [23, 1, 10, 20],
    ],
    stack: [
      [1, 1, 32, 6],
      [1, 8, 32, 6],
      [1, 15, 32, 6],
    ],
    split: [
      [1, 1, 32, 12],
      [1, 14, 15, 7],
      [17, 14, 16, 7],
    ],
    focus: [
      [1, 1, 20, 20],
      [22, 1, 11, 9],
      [22, 11, 11, 10],
    ],
  }[id] ?? [];

  boxes.forEach(([x, y, width, height], index) => {
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", width);
    rect.setAttribute("height", height);
    rect.setAttribute("rx", "1.5");
    // The first slot is the one the presets differ on, so it carries the
    // accent in the miniature.
    if (index === 0) rect.setAttribute("data-accent", "true");
    svg.append(rect);
  });
  return svg;
}

function gripIcon() {
  const svg = svgIcon("0 0 16 16");
  svg.setAttribute("fill", "currentColor");
  for (const y of [4, 8, 12]) {
    for (const x of [5.5, 10.5]) {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x);
      dot.setAttribute("cy", y);
      dot.setAttribute("r", "1.2");
      svg.append(dot);
    }
  }
  return svg;
}
