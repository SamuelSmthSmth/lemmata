// The Library: the student's installed packs, managed like packages.
//
// Packs live in the browser (js/packs.js); the server only offers the bundled
// catalogue.  The rail lists what is installed, then what is available to
// install; a pack's page lists its chapters and entries, with Install,
// Update, Export, Uninstall and "Check all entries" in its head.  An entry
// opens *beside* a fresh copy of its proof; a trap can instead open as an
// exercise, with the verdict hidden until the student says which line fails;
// a proved theorem can be imported into another proof.

import { checkProof } from "./api.js";
import { el } from "./format.js";
import * as packs from "./packs.js";
import * as registry from "./registry.js";

let handlers = {};
let copies = () => new Map(); // entryKey -> {fileId, tone}
let activePack = null;
let filter = "all";
let query = "";
let expanded = null;

// "Check all entries": entryKey -> {state: "running" | "done", verdict}
const checks = new Map();
let checking = null; // name of the pack being checked

export const entryKey = packs.entryKey;

export function initLibrary(actions, copiesFn) {
  handlers = actions;
  copies = copiesFn;
  activePack = packs.findPack("core/mth2008") ? "core/mth2008" : packs.installedPacks()[0]?.name ?? null;

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

/** Show one pack's page (after installing it, or from elsewhere in the app). */
export function showPack(name) {
  activePack = name;
  expanded = null;
  renderLibrary();
}

export const libraryPacks = () => packs.installedPacks();
export const findEntry = packs.findEntry;

function matches(pack, entry) {
  if (filter !== "all" && entry.kind !== filter) return false;
  if (!query) return true;
  const chapter = pack.chapters.find((c) => c.id === entry.chapter)?.title ?? "";
  const haystack = [pack.courses?.join(" "), pack.title, pack.authors?.join(" "), entry.ref, entry.title, chapter, entry.blurb];
  return haystack.filter(Boolean).join(" ").toLowerCase().includes(query);
}

// ---------------------------------------------------------------------------
// The rail
// ---------------------------------------------------------------------------

const entriesText = (n) => `${n} ${n === 1 ? "entry" : "entries"}`;

// A registry pack is listed from the index before its file is fetched.
const entryCount = (pack) => (pack.remote ? pack.remote.count : pack.entries.length);

function packButton(pack, { update = null } = {}) {
  const count = pack.remote ? pack.remote.count : pack.entries.filter((e) => matches(pack, e)).length;
  const button = el("button", "pack-button");
  button.type = "button";
  button.dataset.pack = pack.name;
  button.setAttribute("aria-current", String(pack.name === activePack && !query));
  const meta = el("span", "pack-title", pack.courses?.length ? pack.title : `v${pack.version}`);
  button.append(el("span", "pack-code", packs.packLabel(pack)), meta, el("span", "pack-count", String(count)));
  // "Available" already says these are not installed; only an update is news.
  if (update) button.append(el("span", "pack-flag", "update"));
  button.addEventListener("click", () => {
    showPack(pack.name);
    document.getElementById("library-list").focus({ preventScroll: true });
  });
  return button;
}

function renderRail() {
  const nav = document.getElementById("library-packs");
  nav.replaceChildren();

  const actions = el("div", "packs-actions");
  actions.append(
    textButton("Install from file…", "", () => handlers.onInstallFile?.()),
    textButton("New pack…", "", () => handlers.onNewPack?.()),
  );
  nav.append(actions);

  const updates = packs.updates();
  const updateFor = new Map(updates.map((u) => [u.pack.name, u]));
  const installedHead = el("div", "packs-group-head");
  installedHead.append(el("p", "packs-group", "Installed"));
  if (updates.length) {
    installedHead.append(textButton(updates.length === 1 ? "Update 1" : `Update all ${updates.length}`, "primary", () => handlers.onUpdateAll?.()));
  }
  nav.append(installedHead);
  for (const pack of packs.installedPacks()) nav.append(packButton(pack, { update: updateFor.get(pack.name) }));

  const available = packs.available();
  if (available.length) {
    nav.append(el("p", "packs-group", "Available"));
    for (const pack of available) nav.append(packButton(pack));
  }
  const status = registryStatus();
  if (status) nav.append(status);
}

function clock(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** One quiet line about the registry; nothing when the site has none. */
function registryStatus() {
  const { state, fetched, stubs } = registry.model;
  const text = {
    loading: "Registry · checking for packs…",
    ok: `Registry · ${stubs.length} ${stubs.length === 1 ? "pack" : "packs"}, checked ${clock(fetched)}`,
    offline: `Registry offline · showing what it offered at ${clock(fetched)}`,
    unavailable: "Registry unreachable · installed packs still work",
  }[state];
  return text ? el("p", `packs-registry packs-registry--${state}`, text) : null;
}

// ---------------------------------------------------------------------------
// A pack's page
// ---------------------------------------------------------------------------

function verdictOf(response) {
  if (response.verdict === "VALID (with domain warnings)") return "WARN";
  return response.verdict;
}

async function checkAll(pack) {
  if (checking) return;
  checking = pack.name;
  for (const entry of pack.entries) checks.set(entryKey(pack.name, entry.id), { state: "running" });
  renderLibrary();
  for (const entry of pack.entries) {
    const key = entryKey(pack.name, entry.id);
    let verdict;
    try {
      verdict = verdictOf(await checkProof({ source: entry.source, strictDomains: false }));
    } catch (error) {
      verdict = "UNREACHABLE";
    }
    checks.set(key, { state: "done", verdict });
    if (activePack === pack.name || query) renderLibrary();
  }
  checking = null;
  renderLibrary();
}

function checkSummary(pack) {
  const results = pack.entries.map((e) => ({ entry: e, check: checks.get(entryKey(pack.name, e.id)) }));
  if (!results.some((r) => r.check)) return null;
  const done = results.filter((r) => r.check?.state === "done");
  const differ = done.filter((r) => r.check.verdict !== r.entry.expected);
  const running = checking === pack.name;
  const text = running
    ? `Checked ${done.length} of ${pack.entries.length}${differ.length ? ` · ${differ.length} differ from the pack` : ""}`
    : differ.length
      ? `${differ.length} of ${pack.entries.length} entries no longer give the verdict this pack records.`
      : pack.entries.length === 1
        ? "Its entry gives the verdict this pack records."
        : `All ${pack.entries.length} entries give the verdict this pack records.`;
  return el("p", `pack-check${differ.length ? " is-invalid" : ""}`, text);
}

function packHead(pack, { installed, update }) {
  const head = el("header", "pack-head");
  const label = packs.packLabel(pack);
  head.append(el("h2", null, label === pack.title ? pack.title : `${label} · ${pack.title}`));
  const record = packs.installedRecords().find((r) => r.name === pack.name);
  const count = entryCount(pack);
  const meta = [`v${pack.version}`, pack.authors?.join(", "), pack.license, `${count} ${count === 1 ? "entry" : "entries"}`];
  if (record?.origin === "file") meta.push("installed from a file");
  if (record?.origin === "local") meta.push("made in this browser");
  if (record?.origin === "registry") meta.push("from the registry");
  if (pack.remote) meta.push(`from the registry${pack.remote.engine ? `, verified on engine ${pack.remote.engine}` : ""}`);
  head.append(el("p", "pack-meta", meta.filter(Boolean).join(" · ")));
  head.append(el("p", "pack-note", pack.summary));

  const actions = el("div", "pack-actions");
  if (!installed && pack.remote) {
    actions.append(textButton("Install", "primary", () => handlers.onInstallRemote?.(pack)));
    const preview = registry.model.previews.get(`${pack.name}@${pack.version}`);
    if (!preview) actions.append(textButton("Preview entries", "", () => handlers.onPreview?.(pack)));
  } else if (!installed) {
    actions.append(textButton("Install", "primary", () => handlers.onInstall?.(pack)));
  } else {
    if (update?.pack.remote) {
      actions.append(textButton(`Update to v${update.pack.version}`, "primary", () => handlers.onInstallRemote?.(update.pack)));
    } else if (update) {
      const what = packs.describeDiff(update.diff);
      actions.append(textButton(`Update to v${update.pack.version}${what ? ` (${what})` : ""}`, "primary", () => handlers.onUpdate?.(update.pack)));
    }
    const check = textButton(checking === pack.name ? "Checking…" : "Check all entries", "", () => checkAll(pack));
    check.disabled = Boolean(checking);
    actions.append(check, textButton("Export", "", () => handlers.onExport?.(pack)));
    if (!packs.PINNED.has(pack.name)) actions.append(textButton("Uninstall", "", () => handlers.onUninstall?.(pack)));
    if (record?.origin === "local" && registry.model.contribute) actions.append(textButton(sharing === pack.name ? "Hide sharing steps" : "Share to the registry…", "", () => {
      sharing = sharing === pack.name ? null : pack.name;
      renderLibrary();
    }));
  }
  head.append(actions);
  if (sharing === pack.name && registry.model.contribute) head.append(shareSteps(pack));
  const summary = checkSummary(pack);
  if (summary) head.append(summary);
  return head;
}

let sharing = null; // name of the local pack whose sharing steps are open

/** How a pack made here reaches everyone: export it, add it on GitHub, CI checks it. */
function shareSteps(pack) {
  const [scope] = pack.name.split("/");
  const box = el("ol", "share-steps");
  const one = el("li", null, "Export the pack: ");
  one.append(textButton("Export .pack.json", "", () => handlers.onExport?.(pack)));
  const two = el("li", null, "Add the file to the registry on GitHub, at ");
  two.append(el("code", null, `packs/${pack.name}.pack.json`), document.createTextNode(": "));
  const link = el("a", "share-link", "open the upload page");
  link.href = `${registry.model.contribute}/upload/main/packs/${encodeURIComponent(scope)}`;
  link.target = "_blank";
  link.rel = "noopener";
  two.append(link, document.createTextNode(" (a GitHub account is needed for this step only)."));
  const three = el("li", null, "Open the pull request. The registry's checks run every entry with the engine this app uses; once it is merged, anyone can search for the pack and install it.");
  box.append(one, two, three);
  return box;
}

function checkTag(pack, entry) {
  const result = checks.get(entryKey(pack.name, entry.id));
  if (!result) return null;
  if (result.state === "running") return el("span", "entry-tag", "checking");
  if (result.verdict === entry.expected) return el("span", "entry-tag entry-tag--check is-same", "as recorded");
  return el("span", "entry-tag entry-tag--check is-invalid", `now ${result.verdict.toLowerCase()}, pack says ${entry.expected.toLowerCase()}`);
}

function entryRow(pack, entry, { installed }) {
  const key = entryKey(pack.name, entry.id);
  const copy = installed ? copies().get(key) : null;
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
  const checked = checkTag(pack, entry);
  if (checked) tags.append(checked);
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
    if (!installed) {
      body.append(el("p", "entry-blurb entry-blurb--quiet", "Install this pack to open its proofs."));
    } else if (entry.kind === "trap") {
      actions.append(textButton("Spot the error", "primary", () => handlers.onOpen?.(pack, entry, { exercise: true })));
      actions.append(textButton("Open with answers", "", () => handlers.onOpen?.(pack, entry, { exercise: false })));
    } else {
      actions.append(textButton(copy ? "Open your copy" : "Open beside the proof", "primary", () => handlers.onOpen?.(pack, entry, { exercise: false })));
      if (packs.isImportable(entry)) actions.append(textButton("Use in a proof", "", () => handlers.onUse?.(pack, entry)));
    }
    if (copy) actions.append(textButton("Start a fresh copy", "", () => handlers.onOpen?.(pack, entry, { fresh: true, exercise: entry.kind === "trap" })));
    if (actions.childElementCount) body.append(actions);
    item.append(body);
  }
  return item;
}

function textButton(label, tone, onClick) {
  const b = el("button", `text-button${tone === "primary" ? " text-button--primary" : ""}`, label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

/** Under a search: the registry packs that match and are not installed (or are newer). */
function registryResults(list) {
  const installed = new Map(packs.installedRecords().map((r) => [r.name, r]));
  const hits = registry
    .searchStubs(registry.model.stubs, query)
    .filter((s) => !installed.has(s.name) || packs.compareVersions(s.version, installed.get(s.name).version) > 0);
  if (!hits.length) return 0;
  const section = el("section", "pack registry-results");
  const head = el("header", "pack-head");
  head.append(el("h2", null, "From the registry"));
  head.append(el("p", "pack-note", "Packs anyone can install. Every entry was checked by the engine this app runs before it was listed."));
  section.append(head);
  for (const stub of hits) {
    const row = el("article", "registry-row");
    const text = el("div", "registry-text");
    const label = packs.packLabel(stub);
    text.append(el("p", "registry-title", label === stub.title ? stub.title : `${label} · ${stub.title}`));
    const update = installed.has(stub.name);
    text.append(el("p", "pack-meta", [`v${stub.version}`, stub.authors.join(", "), entriesText(stub.remote.count), update ? `you have v${installed.get(stub.name).version}` : null].filter(Boolean).join(" · ")));
    if (stub.summary) text.append(el("p", "pack-note", stub.summary));
    const actions = el("div", "pack-actions");
    actions.append(
      textButton(update ? `Update to v${stub.version}` : "Install", "primary", () => handlers.onInstallRemote?.(stub)),
      textButton("Details", "", () => {
        clearSearch();
        showPack(stub.name);
      }),
    );
    row.append(text, actions);
    section.append(row);
  }
  list.append(section);
  return hits.length;
}

function clearSearch() {
  const search = document.getElementById("library-search");
  search.value = "";
  query = "";
}

export function renderLibrary() {
  renderRail();
  const list = document.getElementById("library-list");
  list.tabIndex = -1;
  list.replaceChildren();

  const installed = packs.installedPacks();
  const available = packs.available();
  const updateFor = new Map(packs.updates().map((u) => [u.pack.name, u]));
  if (activePack && !packs.findPack(activePack)) activePack = installed[0]?.name ?? null;

  // A search looks across every installed pack; otherwise one pack at a time.
  const shown = query ? installed : [...installed, ...available].filter((p) => p.name === activePack);
  let total = 0;
  for (const listed of shown) {
    const isInstalled = installed.includes(listed);
    // A registry pack shows its entries once previewed (fetched, read-only).
    const pack = listed.remote ? { ...(registry.model.previews.get(`${listed.name}@${listed.version}`) ?? listed), remote: listed.remote } : listed;
    const entries = pack.entries.filter((e) => matches(pack, e));
    if (query && !entries.length) continue;
    total += entries.length;
    const section = el("section", "pack");
    section.dataset.pack = pack.name;
    section.append(packHead(pack, { installed: isInstalled, update: updateFor.get(pack.name) }));
    for (const chapter of pack.chapters) {
      const inChapter = entries.filter((e) => e.chapter === chapter.id);
      if (!inChapter.length) continue;
      const group = el("div", "chapter");
      group.append(el("h3", "chapter-title", /^\d+$/.test(chapter.id) ? `${chapter.id}  ${chapter.title}` : chapter.title));
      for (const entry of inChapter) group.append(entryRow(pack, entry, { installed: isInstalled }));
      section.append(group);
    }
    if (pack.remote && !pack.entries.length) {
      section.append(el("p", "library-empty-sub", `${entriesText(pack.remote.count)}${pack.remote.traps ? `, ${pack.remote.traps} of them traps` : ""}${pack.remote.chapters.length ? ` in ${pack.remote.chapters.join(", ")}` : ""}. Preview them, or install the pack to open them.`));
      total += 1;
    }
    list.append(section);
  }
  if (query) total += registryResults(list);
  if (!shown.length && !query) {
    const empty = el("div", "library-empty");
    empty.append(
      el("p", null, "No packs are installed."),
      el("p", "library-empty-sub", "Install one from the list on the left, or from a .pack.json file someone shared with you."),
    );
    list.append(empty);
  } else if (!total) {
    const empty = el("div", "library-empty");
    empty.append(
      el("p", null, query ? `Nothing matches “${query}”.` : "This pack has no entries of that kind."),
      el("p", "library-empty-sub", "Search by the notes' numbering (2.18), a title word (Lagrange), a course code, or a topic (limit)."),
    );
    list.append(empty);
  }
}
