// The pack registry: a public index of packs, searched and installed from here.
//
// The registry is a Git repository (github.com/SamuelSmthSmth/lemmata-packs)
// whose CI re-checks every entry with the engine this app runs and publishes
// `index.json` beside the pack files (site.json `registry` says where).  The
// index carries each pack's metadata, a search text and the sha256 of its
// file; the file itself is fetched only to preview or install it, checked
// against that sha256, then validated like any .pack.json.
//
// Fetched at most every 10 minutes and cached in IndexedDB, so the Library
// still lists what the registry offered when it is offline.  The registry is
// optional: without it (site.json `"registry": ""`, or unreachable) every
// installed pack works exactly as before.
//
// The parts above the storage section are pure, so verify_frontend.mjs tests
// them in Node.

import * as db from "./db.js";
import { compareVersions } from "./packs.js";

export const INDEX_FORMAT = 1;
export const STALE_MS = 10 * 60 * 1000;

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

const isStr = (v) => typeof v === "string" && v.trim() !== "";

/**
 * The packs an index offers, as stubs the Library can list before a pack is
 * fetched: the pack's own fields, no entries yet, and `remote` holding what
 * the index says about it.  Malformed rows are dropped, not trusted.
 */
export function indexStubs(doc) {
  if (!doc || doc.format !== INDEX_FORMAT || !Array.isArray(doc.packs)) return [];
  const out = [];
  for (const row of doc.packs) {
    if (!row || !/^[a-z0-9][a-z0-9-]*\/[a-z0-9][a-z0-9-]*$/.test(row.name) || !isStr(row.version) || !isStr(row.url) || !/^[0-9a-f]{64}$/.test(row.sha256 ?? "")) continue;
    out.push({
      format: 1,
      name: row.name,
      version: row.version,
      title: isStr(row.title) ? row.title : row.name,
      courses: Array.isArray(row.courses) ? row.courses.filter(isStr) : [],
      summary: isStr(row.summary) ? row.summary : "",
      authors: Array.isArray(row.authors) ? row.authors.filter(isStr) : [],
      license: isStr(row.license) ? row.license : "",
      chapters: [],
      entries: [],
      remote: {
        url: row.url,
        sha256: row.sha256,
        count: Number.isInteger(row.entries) ? row.entries : 0,
        traps: Number.isInteger(row.traps) ? row.traps : 0,
        chapters: Array.isArray(row.chapters) ? row.chapters.filter(isStr) : [],
        search: isStr(row.search) ? row.search : "",
        engine: isStr(doc.engine) ? doc.engine : "",
      },
    });
  }
  return out;
}

const tokens = (text) => String(text).toLowerCase().normalize("NFKD").split(/[^a-z0-9.]+/).filter(Boolean);

/**
 * Registry packs matching *query*, best first.  Every word of the query must
 * appear somewhere; a course code outranks the title, which outranks the
 * summary and authors, which outrank the theorems inside.
 */
export function searchStubs(stubs, query) {
  const words = tokens(query);
  if (!words.length) return [];
  const scored = [];
  for (const stub of stubs) {
    const fields = [
      [4, tokens(stub.courses.join(" "))],
      [3, tokens(`${stub.title} ${stub.name}`)],
      [2, tokens(`${stub.summary} ${stub.authors.join(" ")}`)],
      [1, tokens(`${stub.remote.search} ${stub.remote.chapters.join(" ")}`)],
    ];
    let score = 0;
    let all = true;
    for (const word of words) {
      const hit = fields.find(([, list]) => list.some((t) => t === word || t.startsWith(word)));
      if (!hit) {
        all = false;
        break;
      }
      score += hit[0];
    }
    if (all) scored.push({ stub, score });
  }
  return scored.sort((a, b) => b.score - a.score || a.stub.name.localeCompare(b.stub.name)).map((s) => s.stub);
}

/** Registry packs worth offering beside the bundled catalogue: newer than what ships, or not shipped. */
export function offered(stubs, bundled) {
  const shipped = new Map(bundled.map((p) => [p.name, p]));
  return stubs.filter((s) => !shipped.has(s.name) || compareVersions(s.version, shipped.get(s.name).version) > 0);
}

export async function sha256Hex(bytes) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** The pack file's text, if its bytes are the ones the index vouches for. */
export async function verifiedText(bytes, sha256) {
  const actual = await sha256Hex(bytes);
  if (actual !== sha256) throw new Error("the file does not match the registry's checksum, so it was not installed");
  return new TextDecoder().decode(bytes);
}

// ---------------------------------------------------------------------------
// Fetching and caching
// ---------------------------------------------------------------------------

export const model = {
  base: "", // site.json `registry`; "" means no registry
  stubs: [],
  contribute: "",
  fetched: 0, // when the cached index was fetched
  state: "off", // off | loading | ok | offline | unavailable
  previews: new Map(), // name@version -> full pack, fetched to preview
};

const CACHE_KEY = "registryIndex";

function adopt(doc, fetched) {
  model.stubs = indexStubs(doc);
  model.contribute = isStr(doc?.contribute) ? doc.contribute : "";
  model.fetched = fetched;
}

/**
 * Bring the index up to date (at most every STALE_MS unless *force*).
 * Offline, the cached copy stands in and the state says so.
 */
export async function refresh(base, { force = false } = {}) {
  model.base = base ?? "";
  if (!model.base) {
    model.state = "off";
    model.stubs = [];
    return model;
  }
  const cached = await db.meta.get(CACHE_KEY, null);
  if (cached?.base === model.base && !model.stubs.length) adopt(cached.doc, cached.fetched);
  if (!force && cached?.base === model.base && Date.now() - cached.fetched < STALE_MS) {
    model.state = "ok";
    return model;
  }
  model.state = "loading";
  try {
    const response = await fetch(new URL("index.json", model.base), { cache: "no-cache" });
    if (!response.ok) throw new Error(`the registry answered ${response.status}`);
    const doc = await response.json();
    if (doc?.format !== INDEX_FORMAT) throw new Error("the registry's index is in a format this app does not read");
    const fetched = Date.now();
    adopt(doc, fetched);
    await db.meta.set(CACHE_KEY, { base: model.base, doc, fetched });
    model.state = "ok";
  } catch (error) {
    model.state = cached?.base === model.base ? "offline" : "unavailable";
    model.error = error.message;
  }
  return model;
}

/** Download a registry pack's file and check it against the index. */
export async function fetchPack(stub) {
  const response = await fetch(new URL(stub.remote.url, model.base));
  if (!response.ok) throw new Error(`the registry answered ${response.status}`);
  const text = await verifiedText(await response.arrayBuffer(), stub.remote.sha256);
  return JSON.parse(text);
}

export function findStub(name) {
  return model.stubs.find((s) => s.name === name) ?? null;
}
