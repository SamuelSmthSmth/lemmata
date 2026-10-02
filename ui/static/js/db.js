// The workspace's storage: IndexedDB, behind one small async interface.
//
// Everything a student writes lives in their browser.  This module is the only
// place that knows *how*, so a future account-backed store replaces this file
// and nothing else.  Three stores:
//
//   files      {id, path, source, strict, created, updated}
//   snapshots  {id, fileId, name, ts, source, strict, auto}     index: fileId
//   meta       {key, value}   settings, folders, tabs, timeline, migration flag
//
// When IndexedDB is unavailable (some private modes) or refuses to open, the
// same interface runs over memory and mirrors into localStorage, so the app
// keeps working and `persistent()` says whether work will survive a reload.

const DB_NAME = "aether";
const DB_VERSION = 1;
const FALLBACK_KEY = "aether:db-fallback";

let dbPromise = null;
let fallback = null; // {files: Map, snapshots: Map, meta: Map} when IndexedDB is out

function request(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    let req;
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION);
    } catch (error) {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("files")) db.createObjectStore("files", { keyPath: "id" });
      if (!db.objectStoreNames.contains("snapshots")) {
        const snaps = db.createObjectStore("snapshots", { keyPath: "id" });
        snaps.createIndex("fileId", "fileId");
      }
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
    req.onblocked = () => resolve(null);
  }).then((db) => {
    if (!db) startFallback();
    return db;
  });
  return dbPromise;
}

function startFallback() {
  if (fallback) return;
  fallback = { files: new Map(), snapshots: new Map(), meta: new Map() };
  try {
    const raw = JSON.parse(localStorage.getItem(FALLBACK_KEY) || "null");
    if (raw) {
      for (const name of ["files", "snapshots", "meta"]) {
        for (const [k, v] of raw[name] ?? []) fallback[name].set(k, v);
      }
    }
  } catch (error) {
    // Nothing readable: start empty.
  }
}

let fallbackTimer = null;
function saveFallback() {
  window.clearTimeout(fallbackTimer);
  fallbackTimer = window.setTimeout(() => {
    try {
      const dump = {};
      for (const name of ["files", "snapshots", "meta"]) dump[name] = [...fallback[name].entries()];
      localStorage.setItem(FALLBACK_KEY, JSON.stringify(dump));
    } catch (error) {
      // Quota or private mode: work stays in memory for this session.
    }
  }, 200);
}

async function tx(storeName, mode, fn) {
  const db = await openDb();
  if (!db) return fn(null);
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const store = transaction.objectStore(storeName);
    let result;
    Promise.resolve(fn(store)).then((value) => {
      result = value;
    }, reject);
    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

function keyFor(storeName, value) {
  return storeName === "meta" ? value.key : value.id;
}

const store = (name) => ({
  async all() {
    return tx(name, "readonly", (s) => (s ? request(s.getAll()) : [...fallback[name].values()]));
  },
  async get(key) {
    return tx(name, "readonly", (s) => (s ? request(s.get(key)) : fallback[name].get(key)));
  },
  async put(value) {
    return tx(name, "readwrite", (s) => {
      if (s) return request(s.put(value));
      fallback[name].set(keyFor(name, value), value);
      saveFallback();
      return keyFor(name, value);
    });
  },
  async delete(key) {
    return tx(name, "readwrite", (s) => {
      if (s) return request(s.delete(key));
      fallback[name].delete(key);
      saveFallback();
      return undefined;
    });
  },
  async clear() {
    return tx(name, "readwrite", (s) => {
      if (s) return request(s.clear());
      fallback[name].clear();
      saveFallback();
      return undefined;
    });
  },
});

export const files = store("files");
export const snapshots = store("snapshots");
const metaStore = store("meta");

export const meta = {
  async get(key, fallbackValue = null) {
    const row = await metaStore.get(key);
    return row === undefined || row === null ? fallbackValue : row.value;
  },
  async set(key, value) {
    return metaStore.put({ key, value });
  },
};

/** Snapshots of one file, newest first. */
export async function snapshotsFor(fileId) {
  const all = await snapshots.all();
  return all.filter((s) => s.fileId === fileId).sort((a, b) => b.ts - a.ts);
}

/** Whether work written now survives a reload (false on the in-memory fallback without storage). */
export async function persistent() {
  const db = await openDb();
  if (db) return true;
  try {
    localStorage.setItem(`${FALLBACK_KEY}:probe`, "1");
    localStorage.removeItem(`${FALLBACK_KEY}:probe`);
    return true;
  } catch (error) {
    return false;
  }
}

/** Bytes used and available, when the browser will say. */
export async function usage() {
  try {
    const estimate = await navigator.storage?.estimate?.();
    return estimate ? { used: estimate.usage ?? 0, quota: estimate.quota ?? 0 } : null;
  } catch (error) {
    return null;
  }
}

/** Ask the browser not to evict the workspace under storage pressure. */
export async function requestPersistence() {
  try {
    return (await navigator.storage?.persist?.()) ?? false;
  } catch (error) {
    return false;
  }
}

/** Delete everything: files, snapshots and settings. */
export async function wipe() {
  await Promise.all([files.clear(), snapshots.clear(), metaStore.clear()]);
}

let idSeq = 0;
export function newId(prefix = "f") {
  return `${prefix}${Date.now().toString(36)}${(idSeq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
