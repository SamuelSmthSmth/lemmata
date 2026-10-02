// The Library: course packs and worked examples.
//
// Packs come from /api/library (courses/*.json plus the bundled examples).
// Every entry is verified by the test suite, so the list never advertises a
// proof the engine does not check.  An entry opens *beside* a fresh copy of its
// proof; a trap can instead open as an exercise, with the verdict hidden until
// the student says which line fails.

import { el } from "./format.js";

let packs = [];
let handlers = {};
let copies = () => new Map(); // entryKey -> {fileId, tone}
let activePack = null;
let filter = "all";
let query = "";
let expanded = null;

export const entryKey = (packId, entryId) => `${packId}/${entryId}`;

export function initLibrary(data, actions, copiesFn) {
  packs = data;
  handlers = actions;
  copies = copiesFn;
  activePack = packs.find((p) => p.id === "mth2008")?.id ?? packs[0]?.id ?? null;

  const search = document.getElementById("library-search");
  search.addEventListener("input", () => {
    query = (search.value ?? "").trim().toLowerCase();
    renderLibrary();
  });
  search.addEventListener("wa-clear", () => {
    query = "";
    renderLibrary();
  });

  const filters = document.getElementById("library-filters");
  filters.addEventListener("click", (event) => {
    const button = event.target.closest(".filter");
    if (!button) return;
    filter = button.dataset.filter;
    for (const b of filters.querySelectorAll(".filter")) b.setAttribute("aria-checked", String(b === button));
    renderLibrary();
  });
  filters.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const buttons = [...filters.querySelectorAll(".filter")];
    const i = buttons.indexOf(document.activeElement);
    const next = buttons[(i + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    next.focus();
    next.click();
    event.preventDefault();
  });
  renderLibrary();
}

export function libraryPacks() {
  return packs;
}

/** Find an entry by `pack/entry` key. */
export function findEntry(key) {
  const [packId, entryId] = key.split("/");
  const pack = packs.find((p) => p.id === packId);
  const entry = pack?.entries.find((e) => e.id === entryId);
  return pack && entry ? { pack, entry } : null;
}

function matches(pack, entry) {
  if (filter !== "all" && entry.kind !== filter) return false;
  if (!query) return true;
  const chapter = pack.chapters.find((c) => c.id === entry.chapter)?.title ?? "";
  return `${pack.code} ${entry.ref} ${entry.title} ${chapter} ${entry.blurb ?? ""}`.toLowerCase().includes(query);
}

function renderPacks() {
  const nav = document.getElementById("library-packs");
  nav.replaceChildren();
  for (const pack of packs) {
    const count = pack.entries.filter((e) => matches(pack, e)).length;
    const button = el("button", "pack-button");
    button.type = "button";
    button.dataset.pack = pack.id;
    button.setAttribute("aria-current", String(pack.id === activePack && !query));
    button.append(el("span", "pack-code", pack.code), el("span", "pack-title", pack.title), el("span", "pack-count", String(count)));
    button.addEventListener("click", () => {
      activePack = pack.id;
      expanded = null;
      renderLibrary();
      document.getElementById("library-list").focus({ preventScroll: true });
    });
    nav.append(button);
  }
}

function entryRow(pack, entry) {
  const key = entryKey(pack.id, entry.id);
  const copy = copies().get(key);
  const isOpen = expanded === key;

  const item = el("article", `entry${entry.kind === "trap" ? " entry--trap" : ""}${isOpen ? " is-open" : ""}`);
  item.dataset.entry = key;

  const head = el("button", "entry-head");
  head.type = "button";
  head.setAttribute("aria-expanded", String(isOpen));
  head.append(el("span", "entry-ref", entry.ref));
  head.append(el("span", "entry-title", entry.title));
  const tags = el("span", "entry-tags");
  if (entry.kind === "trap") tags.append(el("span", "entry-tag entry-tag--trap", "Trap"));
  if (copy) {
    const word = { valid: "your copy checks", warning: "your copy: warnings", invalid: "your copy fails" }[copy.tone] ?? "opened";
    tags.append(el("span", `entry-tag entry-tag--copy${copy.tone ? ` is-${copy.tone}` : ""}`, word));
  }
  head.append(tags);
  head.addEventListener("click", () => {
    expanded = isOpen ? null : key;
    renderLibrary();
    document.querySelector(`.entry[data-entry="${CSS.escape(key)}"] .entry-head`)?.focus();
  });
  item.append(head);

  if (isOpen) {
    const body = el("div", "entry-body");
    if (entry.blurb) body.append(el("p", "entry-blurb", entry.blurb));
    if (entry.kind === "trap") {
      body.append(el("p", "entry-blurb", "One step of this proof does not hold. Open it as an exercise to find the line before the checker tells you."));
    }
    body.append(el("pre", "entry-source", entry.source));
    const actions = el("div", "entry-actions");
    if (entry.kind === "trap") {
      actions.append(button("Spot the error", "primary", () => handlers.onOpen?.(pack, entry, { exercise: true })));
      actions.append(button("Open with answers", "", () => handlers.onOpen?.(pack, entry, { exercise: false })));
    } else {
      actions.append(button(copy ? "Open your copy" : "Open beside the proof", "primary", () => handlers.onOpen?.(pack, entry, { exercise: false })));
    }
    if (copy) actions.append(button("Start a fresh copy", "", () => handlers.onOpen?.(pack, entry, { fresh: true, exercise: entry.kind === "trap" })));
    body.append(actions);
    item.append(body);
  }
  return item;
}

function button(label, tone, onClick) {
  const b = el("button", `text-button${tone === "primary" ? " text-button--primary" : ""}`, label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

export function renderLibrary() {
  if (!packs.length) return;
  renderPacks();
  const list = document.getElementById("library-list");
  list.tabIndex = -1;
  list.replaceChildren();

  // A search looks across every pack; otherwise one pack at a time.
  const shown = query ? packs : packs.filter((p) => p.id === activePack);
  let total = 0;
  for (const pack of shown) {
    const entries = pack.entries.filter((e) => matches(pack, e));
    if (!entries.length) continue;
    total += entries.length;
    const section = el("section", "pack");
    const head = el("header", "pack-head");
    head.append(el("h2", null, `${pack.code} · ${pack.title}`), el("p", "pack-note", pack.note));
    section.append(head);
    for (const chapter of pack.chapters) {
      const inChapter = entries.filter((e) => e.chapter === chapter.id);
      if (!inChapter.length) continue;
      const group = el("div", "chapter");
      group.append(el("h3", "chapter-title", /^\d+$/.test(chapter.id) ? `${chapter.id}  ${chapter.title}` : chapter.title));
      for (const entry of inChapter) group.append(entryRow(pack, entry));
      section.append(group);
    }
    list.append(section);
  }
  if (!total) {
    const empty = el("div", "library-empty");
    empty.append(
      el("p", null, query ? `Nothing matches “${query}”.` : "This pack has no entries of that kind."),
      el("p", "library-empty-sub", "Search by the notes' numbering (2.18), a title word (Lagrange), or a topic (limit)."),
    );
    list.append(empty);
  }
}
