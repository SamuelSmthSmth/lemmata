// Installed packs: the browser's own package manager for course packs.
//
// A pack (format 1, see src/aether/packs.py) is installed into IndexedDB and
// read from there; the server's /api/library is only the *catalogue* of
// bundled packs, compared against what is installed to offer Browse and
// Updates.  Installing never touches the student's workspace: copies opened
// from a pack are ordinary files, so uninstalling or updating a pack leaves
// them alone.
//
// Everything above the storage section is pure, so verify_frontend.mjs can
// test it in Node.

import * as db from "./db.js";

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Packs that cannot be uninstalled: the language's own worked examples. */
export const PINNED = new Set(["core/examples"]);

/** The short name a pack goes by: its first course code, or its title. */
export function packLabel(pack) {
  return pack.courses?.length ? pack.courses[0] : pack.title;
}

/** `name/entry` — the key a workspace file's `origin` records. */
export const entryKey = (name, entryId) => `${name}/${entryId}`;

/** Split an entry key on its last slash: pack names contain one themselves. */
export function splitKey(key) {
  const at = String(key).lastIndexOf("/");
  return at < 0 ? null : { name: key.slice(0, at), entryId: key.slice(at + 1) };
}

/**
 * Origins recorded before packs had scoped names (`mth2008/<entry>`) become
 * `core/mth2008/<entry>`; the examples' file entries lost their underscores.
 */
export function migrateOrigin(origin) {
  if (!origin || origin.split("/").length !== 2) return origin;
  const [pack, entry] = origin.split("/");
  return `core/${pack}/${pack === "examples" ? entry.replace(/[^a-z0-9-]+/g, "-") : entry}`;
}

function parts(version) {
  const [core, pre = ""] = String(version).split(/[-+]/, 2);
  return { nums: core.split(".").map((n) => Number.parseInt(n, 10) || 0), pre };
}

/** Compare two semver strings: negative, zero or positive. */
export function compareVersions(a, b) {
  const x = parts(a);
  const y = parts(b);
  for (let i = 0; i < 3; i++) {
    if ((x.nums[i] ?? 0) !== (y.nums[i] ?? 0)) return (x.nums[i] ?? 0) - (y.nums[i] ?? 0);
  }
  if (x.pre === y.pre) return 0;
  if (!x.pre) return 1; // 1.0.0 is after 1.0.0-beta
  if (!y.pre) return -1;
  return x.pre < y.pre ? -1 : 1;
}

const ENTRY_FIELDS = ["ref", "title", "kind", "expected", "source", "chapter", "explanation"];

/** What installing `next` over `prev` would change, entry by entry. */
export function diffPacks(prev, next) {
  const before = new Map((prev?.entries ?? []).map((e) => [e.id, e]));
  const after = new Map((next?.entries ?? []).map((e) => [e.id, e]));
  const added = [...after.keys()].filter((id) => !before.has(id));
  const removed = [...before.keys()].filter((id) => !after.has(id));
  const changed = [...after.keys()].filter(
    (id) => before.has(id) && ENTRY_FIELDS.some((f) => (before.get(id)[f] ?? null) !== (after.get(id)[f] ?? null)),
  );
  return { added, changed, removed, empty: !added.length && !changed.length && !removed.length };
}

/** "3 changed, 1 new" — or null when nothing would change. */
export function describeDiff(diff) {
  const bits = [];
  if (diff.changed.length) bits.push(`${diff.changed.length} changed`);
  if (diff.added.length) bits.push(`${diff.added.length} new`);
  if (diff.removed.length) bits.push(`${diff.removed.length} removed`);
  return bits.length ? bits.join(", ") : null;
}

/**
 * Catalogue packs that would update an installed one: a newer version, or the
 * same version with different contents (a bundled pack edited in place).
 */
export function updatesFor(catalog, installedRecords) {
  const installed = new Map(installedRecords.map((r) => [r.name, r]));
  const out = [];
  for (const pack of catalog) {
    const record = installed.get(pack.name);
    if (!record) continue;
    const order = compareVersions(pack.version, record.version);
    if (order > 0 || (order === 0 && !diffPacks(record.pack, pack).empty)) out.push({ pack, record, diff: diffPacks(record.pack, pack) });
  }
  return out;
}

/** Catalogue packs that are not installed. */
export function browsable(catalog, installedRecords) {
  const names = new Set(installedRecords.map((r) => r.name));
  return catalog.filter((p) => !names.has(p.name));
}

/** Whether an entry proves a named result another proof could import. */
export function isImportable(entry) {
  return entry.kind === "proof" && /^\s*(Theorem|Lemma)\b/m.test(entry.source);
}

/** The path an entry is imported by, without the extension. */
export const importPath = (name, entryId) => `@${name}/${entryId}`;

/** The line that imports an entry into a proof. */
export const importLine = (name, entryId) => `import "${importPath(name, entryId)}"`;

/** Installed proofs keyed by the path `import` resolves them at. Traps never travel. */
export function importSources(packList) {
  const out = {};
  for (const pack of packList) {
    for (const entry of pack.entries) {
      if (entry.kind === "proof") out[`${importPath(pack.name, entry.id)}.aether`] = entry.source;
    }
  }
  return out;
}

/** Whether a proof (or anything it would send along) imports from a pack. */
export const importsFromPacks = (source) => /^\s*import\s+"@/m.test(source);

/** A pack as the file it is shared as. */
export function packToFile(pack) {
  return { filename: `${pack.name.replace("/", "-")}.pack.json`, text: `${JSON.stringify(pack, null, 2)}\n` };
}

/** Parse a .pack.json file's text; the server validates the result. */
export function parsePackFile(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error("the file is not JSON");
  }
}

/** A lower-case slug: "Theorem 1.1 (Triangle)" -> "theorem-1-1-triangle". */
export function slugify(text) {
  return String(text).toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "entry";
}

/** The pack name a new pack in *folder* starts with. */
export const defaultPackName = (folder) => `me/${slugify(folder.split("/").pop())}`;

/** A fresh manifest for a folder being made into a pack. */
export function newManifest(folder) {
  const title = folder.split("/").pop();
  return {
    name: defaultPackName(folder),
    title,
    version: "1.0.0",
    courses: [],
    summary: `Proofs from ${title}.`,
    authors: [],
    license: "CC-BY-SA-4.0",
    entries: {}, // fileId -> {ref, title, kind, chapter, explanation}
  };
}

const stem = (path) => path.split("/").pop().replace(/\.aether$/i, "");

/**
 * The pack a folder exports as.  `files` are the folder's workspace files
 * ({id, path, source}), `verdicts` maps file id to the verdict the file gets
 * when checked on its own (what anyone installing the pack will see).
 * Returns {pack, problems}: problems name the file, not an entries[i] index.
 */
export function buildPack(manifest, files, verdicts) {
  const problems = [];
  if (/^core\//.test(manifest.name)) problems.push("The core/ scope is kept for the packs that ship with the app; choose your own, e.g. yourname/" + slugify(manifest.title));
  const ordered = [...files].sort((a, b) => a.path.localeCompare(b.path));
  const chapterIds = new Map();
  const usedIds = new Set();
  const entries = [];
  for (const file of ordered) {
    const meta = manifest.entries?.[file.id] ?? {};
    const name = stem(file.path);
    const chapterTitle = (meta.chapter || manifest.title || "Proofs").trim();
    if (!chapterIds.has(chapterTitle)) chapterIds.set(chapterTitle, String(chapterIds.size + 1));
    let id = slugify(meta.title || name);
    for (let n = 2; usedIds.has(id); n++) id = `${slugify(meta.title || name)}-${n}`;
    usedIds.add(id);
    const kind = meta.kind === "trap" ? "trap" : "proof";
    const expected = verdicts.get(file.id);
    if (!["VALID", "WARN", "INVALID", "PARSE ERROR"].includes(expected)) {
      problems.push(`${name}: could not be checked (${expected ?? "no verdict"}), so the pack cannot record what it gives`);
    } else if (expected === "PARSE ERROR") {
      problems.push(`${name} does not parse yet; fix it in the editor before it goes into a pack`);
    } else if (kind === "trap" && expected !== "INVALID") {
      problems.push(`${name} is marked as a trap, but it checks (${expected.toLowerCase()}); a trap must fail`);
    }
    if (kind === "trap" && !meta.explanation?.trim()) problems.push(`${name} is a trap, so it needs an explanation of the mistake`);
    if (!file.source.trim()) problems.push(`${name} is empty`);
    const entry = { id, chapter: chapterIds.get(chapterTitle), ref: (meta.ref || name).trim(), title: (meta.title || name).trim(), kind, expected, source: file.source };
    if (kind === "trap") entry.explanation = meta.explanation?.trim() ?? "";
    entries.push(entry);
  }
  if (!entries.length) problems.push("The folder has no proofs in it yet");
  const pack = {
    format: 1,
    name: manifest.name,
    version: manifest.version,
    title: manifest.title,
    ...(manifest.courses?.length ? { courses: manifest.courses } : {}),
    summary: manifest.summary,
    authors: manifest.authors ?? [],
    license: manifest.license,
    engine: ">=0.1",
    depends: {},
    chapters: [...chapterIds].map(([title, id]) => ({ id, title })),
    entries,
  };
  return { pack, problems };
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

export const model = {
  catalog: [], // bundled packs, from /api/library
  registry: [], // stubs of what the pack registry offers (js/registry.js), not yet fetched
  records: new Map(), // name -> {name, version, origin, installed, pack}
};

/** Installed packs, examples first then by name. */
export function installedPacks() {
  return [...model.records.values()]
    .sort((a, b) => (PINNED.has(b.name) - PINNED.has(a.name)) || a.name.localeCompare(b.name))
    .map((r) => r.pack);
}

export const installedRecords = () => [...model.records.values()];

export function findPack(name) {
  return model.records.get(name)?.pack ?? model.catalog.find((p) => p.name === name) ?? model.registry.find((p) => p.name === name) ?? null;
}

/** Find an installed entry by `name/entry` key. */
export function findEntry(key) {
  const split = splitKey(key);
  const pack = split ? model.records.get(split.name)?.pack : null;
  const entry = pack?.entries.find((e) => e.id === split.entryId);
  return pack && entry ? { pack, entry } : null;
}

/**
 * Load what is installed, then install each bundled pack the site preinstalls
 * (site.json `preinstall`; every bundled pack when it does not say) that this
 * browser has never seen.  A pack the student uninstalled stays uninstalled:
 * "seen" is remembered separately from "installed".
 */
export async function load(catalog, preinstall = null) {
  model.catalog = catalog;
  model.records = new Map((await db.packs.all()).map((r) => [r.name, r]));
  const seen = new Set(await db.meta.get("packsSeen", []));
  const wanted = preinstall ? new Set(preinstall) : null;
  for (const pack of catalog) {
    if (seen.has(pack.name)) continue;
    if (!model.records.has(pack.name) && (!wanted || wanted.has(pack.name))) await install(pack, "bundled");
    seen.add(pack.name);
  }
  // The examples always come along, and always as the bundled version.
  for (const name of PINNED) {
    const pack = catalog.find((p) => p.name === name);
    const record = model.records.get(name);
    if (pack && (!record || !diffPacks(record.pack, pack).empty || record.version !== pack.version)) await install(pack, "bundled");
  }
  await db.meta.set("packsSeen", [...seen]);
}

/** Install (or replace) a pack; returns the record it replaced, for undo. */
export async function install(pack, origin) {
  const previous = model.records.get(pack.name) ?? null;
  const record = { name: pack.name, version: pack.version, origin, installed: Date.now(), pack };
  await db.packs.put(record);
  model.records.set(pack.name, record);
  return previous;
}

/** Put back a record exactly as it was (undo of an install or uninstall). */
export async function restore(record) {
  await db.packs.put(record);
  model.records.set(record.name, record);
}

export async function uninstall(name) {
  const previous = model.records.get(name) ?? null;
  if (!previous || PINNED.has(name)) return null;
  await db.packs.delete(name);
  model.records.delete(name);
  return previous;
}

/**
 * Updates: a bundled pack that differs from the installed copy, or a registry
 * pack with a newer version.  A registry update is a stub until it is
 * fetched, so its `diff` is null and the update says what changed afterwards.
 */
export function updates() {
  const records = installedRecords();
  const out = updatesFor(model.catalog, records);
  const listed = new Set(out.map((u) => u.pack.name));
  const installed = new Map(records.map((r) => [r.name, r]));
  for (const stub of model.registry) {
    const record = installed.get(stub.name);
    if (!record || compareVersions(stub.version, record.version) <= 0) continue;
    const bundled = out.findIndex((u) => u.pack.name === stub.name);
    // The registry's version wins over an older bundled one.
    if (bundled >= 0 && compareVersions(stub.version, out[bundled].pack.version) > 0) out.splice(bundled, 1);
    else if (listed.has(stub.name)) continue;
    out.push({ pack: stub, record, diff: null });
  }
  return out;
}

/** Packs to install: bundled ones not installed, then registry ones neither installed nor bundled. */
export function available() {
  const records = installedRecords();
  const bundled = browsable(model.catalog, records);
  const known = new Set([...records.map((r) => r.name), ...model.catalog.map((p) => p.name)]);
  return [...bundled, ...model.registry.filter((s) => !known.has(s.name))];
}
