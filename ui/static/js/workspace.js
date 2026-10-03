// The workspace model: files, folders, open tabs and snapshots.
//
// DOM-free on purpose.  Views (the explorer, the tab strip, the editor) read
// from here and listen for "change" events; nothing in this module knows how
// it is drawn.  Persistence goes through db.js.
//
// Paths are POSIX-style and relative ("sheets/week1.aether").  A folder exists
// when a file lives under it or when it was created empty (kept in meta).

import * as db from "./db.js";

const EXTENSION = ".aether";
const MAX_SNAPSHOTS_PER_FILE = 20;
const MAX_TIMELINE = 120;

const events = new EventTarget();

export const model = {
  ready: false,
  files: new Map(), // id -> file
  folders: new Set(), // explicitly created folders (paths)
  tabs: [], // open file ids, in strip order
  activeId: null,
  timeline: [],
  persistent: true,
};

function emit(kind, detail = {}) {
  events.dispatchEvent(new CustomEvent("change", { detail: { kind, ...detail } }));
}

export function onChange(handler) {
  events.addEventListener("change", (event) => handler(event.detail));
}

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

export function normalizePath(raw) {
  const parts = [];
  for (const part of String(raw).replace(/\\/g, "/").split("/")) {
    const clean = part.trim();
    if (!clean || clean === ".") continue;
    if (clean === "..") parts.pop();
    else parts.push(clean);
  }
  return parts.join("/");
}

export function withExtension(path) {
  return path.endsWith(EXTENSION) ? path : `${path}${EXTENSION}`;
}

export function basename(path) {
  return path.split("/").pop();
}

export function dirname(path) {
  const parts = path.split("/");
  parts.pop();
  return parts.join("/");
}

/** Why *path* cannot be used for a new or renamed file, or null when it can. */
export function pathProblem(path, ignoreId = null) {
  if (!path || !basename(path).replace(EXTENSION, "")) return "A file needs a name.";
  if (/[<>:"|?*\u0000-\u001f]/.test(path)) return "Names cannot contain < > : \" | ? or *.";
  // "@…" is where installed packs live for `import "@scope/pack/entry"`.
  if (path.startsWith("@")) return "Names cannot start with @; that is how proofs import from packs.";
  for (const file of model.files.values()) {
    if (file.id !== ignoreId && file.path.toLowerCase() === path.toLowerCase()) {
      return `${path} already exists.`;
    }
  }
  return null;
}

/** A free path like "Untitled 2.aether" in *folder*. */
export function freePath(stem = "Untitled", folder = "") {
  const prefix = folder ? `${folder}/` : "";
  for (let n = 1; n < 1000; n++) {
    const candidate = `${prefix}${stem}${n === 1 ? "" : ` ${n}`}${EXTENSION}`;
    if (!pathProblem(candidate)) return candidate;
  }
  return `${prefix}${stem} ${Date.now()}${EXTENSION}`;
}

/** Every folder: explicit ones and the parents of every file, sorted. */
export function allFolders() {
  const out = new Set(model.folders);
  for (const file of model.files.values()) {
    let dir = dirname(file.path);
    while (dir) {
      out.add(dir);
      dir = dirname(dir);
    }
  }
  return [...out].sort((a, b) => a.localeCompare(b));
}

export function filesSorted() {
  return [...model.files.values()].sort((a, b) => a.path.localeCompare(b.path));
}

export function activeFile() {
  return model.activeId ? model.files.get(model.activeId) ?? null : null;
}

// ---------------------------------------------------------------------------
// Boot and migration
// ---------------------------------------------------------------------------

/**
 * Bring the pre-workspace single buffer across, exactly once.
 *
 * The old UI kept one buffer and its snapshots under `aether:workspace` and
 * the verdict history under `aether:timeline`.  Both become a file (with its
 * snapshots) and the timeline here.  The old keys are left in place: a
 * migration that destroys its source cannot be retried.
 */
async function migrateLegacy() {
  if (await db.meta.get("migrated-v1", false)) return;
  let legacy = null;
  let legacyTimeline = null;
  try {
    legacy = JSON.parse(localStorage.getItem("aether:workspace") || "null");
    legacyTimeline = JSON.parse(localStorage.getItem("aether:timeline") || "null");
  } catch (error) {
    // Unreadable: nothing to migrate.
  }
  if (legacy && typeof legacy.source === "string" && legacy.source.trim()) {
    const id = db.newId();
    const now = Date.now();
    const file = { id, path: "My proof.aether", source: legacy.source, strict: Boolean(legacy.strict), created: now, updated: now };
    await db.files.put(file);
    for (const snap of Array.isArray(legacy.snapshots) ? legacy.snapshots : []) {
      if (typeof snap.source !== "string") continue;
      await db.snapshots.put({
        id: db.newId("s"),
        fileId: id,
        name: snap.name ?? "Snapshot",
        ts: snap.ts ?? now,
        source: snap.source,
        strict: Boolean(snap.strict),
        auto: Boolean(snap.auto),
      });
    }
    await db.meta.set("tabs", [id]);
    await db.meta.set("active", id);
  }
  if (legacyTimeline && Array.isArray(legacyTimeline.entries)) {
    await db.meta.set("timeline", legacyTimeline.entries.slice(-MAX_TIMELINE));
  }
  await db.meta.set("migrated-v1", true);
}

export async function load() {
  await migrateLegacy();
  const [files, folders, tabs, active, timeline, persistent] = await Promise.all([
    db.files.all(),
    db.meta.get("folders", []),
    db.meta.get("tabs", []),
    db.meta.get("active", null),
    db.meta.get("timeline", []),
    db.persistent(),
  ]);
  model.files = new Map(files.map((f) => [f.id, f]));
  model.folders = new Set(folders);
  model.tabs = tabs.filter((id) => model.files.has(id));
  model.activeId = model.files.has(active) ? active : model.tabs[0] ?? null;
  model.timeline = Array.isArray(timeline) ? timeline : [];
  model.persistent = persistent;
  model.ready = true;
  db.requestPersistence();
  emit("load");
}

function saveTabs() {
  db.meta.set("tabs", model.tabs);
  db.meta.set("active", model.activeId);
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

export async function createFile({ path, source = "", strict = false, open = true } = {}) {
  const finalPath = withExtension(normalizePath(path || freePath()));
  const problem = pathProblem(finalPath);
  if (problem) throw new Error(problem);
  const now = Date.now();
  const file = { id: db.newId(), path: finalPath, source, strict, created: now, updated: now };
  model.files.set(file.id, file);
  await db.files.put(file);
  emit("files", { id: file.id });
  if (open) openFile(file.id);
  return file;
}

/** Save *changes* to a file; source edits are the hot path and skip the event storm. */
export async function updateFile(id, changes) {
  const file = model.files.get(id);
  if (!file) return null;
  Object.assign(file, changes, { updated: Date.now() });
  await db.files.put(file);
  emit("file", { id, fields: Object.keys(changes) });
  return file;
}

export async function renameFile(id, newPath) {
  const file = model.files.get(id);
  if (!file) return null;
  const finalPath = withExtension(normalizePath(newPath));
  const problem = pathProblem(finalPath, id);
  if (problem) throw new Error(problem);
  file.path = finalPath;
  file.updated = Date.now();
  await db.files.put(file);
  emit("files", { id });
  return file;
}

export async function duplicateFile(id) {
  const file = model.files.get(id);
  if (!file) return null;
  const stem = basename(file.path).replace(EXTENSION, "");
  return createFile({ path: freePath(`${stem} copy`, dirname(file.path)), source: file.source, strict: file.strict });
}

/**
 * Delete a file, returning everything needed to put it back.
 *
 * The caller offers undo; `restoreFile(bundle)` reverses this exactly.
 */
export async function deleteFile(id) {
  const file = model.files.get(id);
  if (!file) return null;
  const snaps = await db.snapshotsFor(id);
  const tabIndex = model.tabs.indexOf(id);
  model.files.delete(id);
  await db.files.delete(id);
  for (const snap of snaps) await db.snapshots.delete(snap.id);
  if (tabIndex !== -1) closeTab(id);
  emit("files", { id, deleted: true });
  return { file, snaps, tabIndex };
}

export async function restoreFile(bundle) {
  const { file, snaps, tabIndex } = bundle;
  model.files.set(file.id, file);
  await db.files.put(file);
  for (const snap of snaps) await db.snapshots.put(snap);
  if (tabIndex !== -1) {
    model.tabs.splice(Math.min(tabIndex, model.tabs.length), 0, file.id);
    model.activeId = file.id;
    saveTabs();
    emit("tabs");
  }
  emit("files", { id: file.id });
}

// ---------------------------------------------------------------------------
// Folders
// ---------------------------------------------------------------------------

export async function createFolder(path) {
  const clean = normalizePath(path);
  if (!clean) throw new Error("A folder needs a name.");
  if (allFolders().some((f) => f.toLowerCase() === clean.toLowerCase())) throw new Error(`${clean} already exists.`);
  model.folders.add(clean);
  await db.meta.set("folders", [...model.folders]);
  emit("files");
  return clean;
}

/** Move a file into *folder* ("" is the root), keeping its name. */
export async function moveFile(id, folder) {
  const file = model.files.get(id);
  if (!file) return null;
  const target = normalizePath(folder);
  return renameFile(id, target ? `${target}/${basename(file.path)}` : basename(file.path));
}

export async function renameFolder(oldPath, newPath) {
  const from = normalizePath(oldPath);
  const to = normalizePath(newPath);
  if (!to) throw new Error("A folder needs a name.");
  for (const file of model.files.values()) {
    if (file.path.startsWith(`${from}/`)) {
      const moved = `${to}/${file.path.slice(from.length + 1)}`;
      const problem = pathProblem(moved, file.id);
      if (problem) throw new Error(problem);
    }
  }
  for (const file of model.files.values()) {
    if (file.path.startsWith(`${from}/`)) {
      file.path = `${to}/${file.path.slice(from.length + 1)}`;
      await db.files.put(file);
    }
  }
  model.folders = new Set([...model.folders].map((f) => (f === from || f.startsWith(`${from}/`) ? to + f.slice(from.length) : f)));
  await db.meta.set("folders", [...model.folders]);
  emit("files");
}

/** Delete a folder and everything in it; returns the bundles for undo. */
export async function deleteFolder(path) {
  const clean = normalizePath(path);
  const bundles = [];
  for (const file of [...model.files.values()]) {
    if (file.path.startsWith(`${clean}/`)) bundles.push(await deleteFile(file.id));
  }
  const removedFolders = [...model.folders].filter((f) => f === clean || f.startsWith(`${clean}/`));
  for (const f of removedFolders) model.folders.delete(f);
  await db.meta.set("folders", [...model.folders]);
  emit("files");
  return { bundles, removedFolders };
}

export async function restoreFolder({ bundles, removedFolders }) {
  for (const f of removedFolders) model.folders.add(f);
  await db.meta.set("folders", [...model.folders]);
  for (const bundle of bundles) await restoreFile(bundle);
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

export function openFile(id) {
  if (!model.files.has(id)) return;
  if (!model.tabs.includes(id)) {
    const at = model.activeId ? model.tabs.indexOf(model.activeId) + 1 : model.tabs.length;
    model.tabs.splice(at, 0, id);
  }
  model.activeId = id;
  saveTabs();
  emit("tabs");
}

export function closeTab(id) {
  const index = model.tabs.indexOf(id);
  if (index === -1) return;
  model.tabs.splice(index, 1);
  if (model.activeId === id) model.activeId = model.tabs[index] ?? model.tabs[index - 1] ?? null;
  saveTabs();
  emit("tabs");
}

export function moveTab(id, toIndex) {
  const from = model.tabs.indexOf(id);
  if (from === -1) return;
  model.tabs.splice(from, 1);
  model.tabs.splice(Math.max(0, Math.min(toIndex, model.tabs.length)), 0, id);
  saveTabs();
  emit("tabs");
}

// ---------------------------------------------------------------------------
// Snapshots and the verdict timeline
// ---------------------------------------------------------------------------

export async function addSnapshot(fileId, { name, auto = false } = {}) {
  const file = model.files.get(fileId);
  if (!file || !file.source.trim()) return null;
  const snap = {
    id: db.newId("s"),
    fileId,
    name: name ?? "Snapshot",
    ts: Date.now(),
    source: file.source,
    strict: file.strict,
    auto,
  };
  await db.snapshots.put(snap);
  const all = await db.snapshotsFor(fileId);
  for (const old of all.slice(MAX_SNAPSHOTS_PER_FILE)) await db.snapshots.delete(old.id);
  emit("snapshots", { id: fileId });
  return snap;
}

export const snapshotsFor = db.snapshotsFor;

export async function removeSnapshot(id) {
  await db.snapshots.delete(id);
  emit("snapshots");
}

/** Run-length history of verdicts, as the old workspace panel showed it. */
export function recordOutcome({ verdict, invalid = 0, warnings = 0, fileId = null }) {
  const entries = model.timeline;
  const last = entries[entries.length - 1];
  if (last && last.verdict === verdict && last.fileId === fileId) {
    Object.assign(last, { ts: Date.now(), invalid, warnings, n: (last.n ?? 1) + 1 });
  } else {
    entries.push({ verdict, invalid, warnings, fileId, ts: Date.now(), n: 1 });
  }
  if (entries.length > MAX_TIMELINE) entries.splice(0, entries.length - MAX_TIMELINE);
  db.meta.set("timeline", entries);
  emit("timeline");
}

export function clearTimeline() {
  model.timeline.length = 0;
  db.meta.set("timeline", []);
  emit("timeline");
}

// ---------------------------------------------------------------------------
// Imports between files
// ---------------------------------------------------------------------------

/** Every file's source keyed by path: what /api/check resolves `import` against. */
export function sourcesByPath() {
  const out = {};
  for (const file of model.files.values()) out[file.path] = file.source;
  return out;
}

/** Whether *source* imports anything, so the workspace only travels when it is needed. */
export function hasImports(source) {
  return /^\s*import\s+"/m.test(source);
}
