// Sync's view of this browser: the local adapter js/sync.js expects, over
// IndexedDB (js/db.js) and the settings and panel layout in localStorage.
//
// Records are what a person would call one thing: a proof, a snapshot, one
// meta value (the folders, the check history), an installed pack, one setting
// or the layout.  Writes from sync are quiet (they are not sent back) and
// still update the views: a setting is re-applied through prefs.js's
// listeners, the layout through layoutApi.adopt, and the workspace is told
// through onApplied.

import * as db from "./db.js";
import { onChange } from "./changes.js";
import { PREF_KEYS, adoptPrefKey, readPrefKey } from "./prefs.js";
import { LAYOUT_KEY, layoutApi } from "./layout.js";
import { createSync, isSynced } from "./sync.js";

const STATE_KEY = "aether:sync";

const tables = { files: db.files, snapshots: db.snapshots, packs: db.packs };

function readPrefRecord(key) {
  const raw = readPrefKey(key);
  if (raw === null) return undefined;
  if (key !== LAYOUT_KEY) return raw;
  try {
    return JSON.parse(raw);
  } catch (error) {
    return undefined;
  }
}

export const localAdapter = {
  async all(store) {
    if (store === "prefs") {
      return [...PREF_KEYS, LAYOUT_KEY]
        .map((key) => ({ key, value: readPrefRecord(key) }))
        .filter((row) => row.value !== undefined);
    }
    if (store === "meta") return (await db.metaStore.all()).map((row) => ({ key: row.key, value: row.value }));
    const key = store === "packs" ? "name" : "id";
    return (await tables[store].all()).map((value) => ({ key: value[key], value }));
  },
  async read(store, key) {
    if (store === "prefs") return readPrefRecord(key);
    if (store === "meta") return (await db.metaStore.get(key))?.value;
    return (await tables[store].get(key)) ?? undefined;
  },
  async write(store, key, value) {
    if (store === "prefs") {
      if (key === LAYOUT_KEY) layoutApi.adopt(value);
      else adoptPrefKey(key, value);
      return;
    }
    if (store === "meta") return db.metaStore.putQuiet({ key, value });
    return tables[store].putQuiet(value);
  },
  async remove(store, key) {
    if (store === "prefs") {
      if (key === LAYOUT_KEY) layoutApi.adopt(null);
      else adoptPrefKey(key, null);
      return;
    }
    if (store === "meta") return db.metaStore.deleteQuiet(key);
    return tables[store].deleteQuiet(key);
  },
  async loadState() {
    try {
      return JSON.parse(localStorage.getItem(STATE_KEY) || "null");
    } catch (error) {
      return null;
    }
  },
  async saveState(state) {
    try {
      localStorage.setItem(STATE_KEY, JSON.stringify(state));
    } catch (error) {
      // Quota or private mode: the outbox lives in memory until the next save.
    }
  },
};

/** Forget which account this browser synced with (signing out). */
export function forgetSyncState() {
  try {
    localStorage.removeItem(STATE_KEY);
  } catch (error) {
    // Nothing stored.
  }
}

/** What arrived, for the app (main.js listens and redraws). */
function announce(changes) {
  window.dispatchEvent(new CustomEvent("lemmata:synced", { detail: changes }));
}

/**
 * Start syncing this browser with `remote` as `owner`.  Every kept change goes
 * to the outbox; `onApplied(changes)` hears what arrived from elsewhere.
 * Returns the sync handle, with `disconnect()` to stop.
 */
export function connectSync({ remote, owner, mergeLocal = true, onApplied = announce }) {
  const sync = createSync({ local: localAdapter, remote, owner, mergeLocal, onApplied });
  const off = onChange((store, key) => {
    if (isSynced(store, key)) sync.record(store, key);
  });
  sync.start();
  return {
    ...sync,
    disconnect() {
      off();
      sync.stop();
    },
  };
}
