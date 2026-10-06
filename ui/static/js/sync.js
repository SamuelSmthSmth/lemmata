// Sync: the student's work, settings and history, kept the same on every
// device they sign in on.
//
// DOM-free, like workspace.js, so the rules below run in Node too
// (ui/verify_frontend.mjs plays two devices against one memory remote).
//
// The browser stays the source of truth while offline: every local change is
// noted in an outbox, and the outbox is pushed when there is a connection.
// Changes from other devices are pulled (and pushed to us live) and written
// quietly, so they are not sent back.  A record is one value in one store:
//
//   {store, key, data, modified, deleted}
//
// where `store` is files, snapshots, meta, packs or prefs, and `modified` is
// the time of the edit.  The remote keeps the newest edit of each record
// (it decides atomically, so two devices cannot race), and so does this
// module when a pull meets an edit it has not pushed yet.  The work that loses
// is never dropped: a proof's losing version is kept as a History snapshot,
// "From your other device" or "Kept from this device".  A deletion is a
// record too (a tombstone), so it reaches every device.
//
// The local adapter (sync-local.js for IndexedDB, or a memory one in tests):
//   all(store)                -> [{key, value}]
//   read(store, key)          -> value | undefined
//   write(store, key, value)  quietly (no outbox entry)
//   remove(store, key)        quietly
//   loadState() / saveState(state)    {owner, cursor, outbox: {"store:key": modified}}
// The remote (remote-supabase.js, or remote-memory.js in tests):
//   push(records)             -> {rejected: ["store:key", ...]}; the server keeps,
//                             per record, the newest `modified`
//   pull(cursor, limit)       -> {records: [...with seq], cursor}
//   subscribe(fn)             -> unsubscribe; fn(record) for each change elsewhere

export const SYNCED = ["files", "snapshots", "meta", "packs", "prefs"];

/** Keys that describe this device, not the student's work: never synced. */
export const DEVICE_ONLY = {
  meta: new Set(["tabs", "active", "migrated-v1", "sync"]),
  prefs: new Set(["aether-desk", "aether-desk-panel", "aether-view", "aether-welcomed"]),
};

export function isSynced(store, key) {
  return SYNCED.includes(store) && !DEVICE_ONLY[store]?.has(key);
}

const id = (store, key) => `${store}:${key}`;

function same(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/** "sheets/week1.aether" taken: "sheets/week1 (2).aether", and so on. */
export function freeCopyPath(path, taken) {
  const dot = path.endsWith(".aether") ? path.length - ".aether".length : path.length;
  const stem = path.slice(0, dot);
  const ext = path.slice(dot);
  for (let n = 2; ; n++) {
    const candidate = `${stem} (${n})${ext}`;
    if (!taken.has(candidate)) return candidate;
  }
}

let seq = 0;
function snapshotId(clock) {
  return `s${clock().toString(36)}${(seq++).toString(36)}sync`;
}

export function createSync({ local, remote, owner, mergeLocal = true, clock = Date.now, onApplied = () => {}, batch = 200 }) {
  let state = null;
  let unsubscribe = null;
  let pushTimer = null;
  let running = false;
  let busy = Promise.resolve();

  async function ensureState() {
    if (state) return state;
    const saved = await local.loadState();
    if (saved && saved.owner === owner) {
      state = { owner, cursor: saved.cursor ?? 0, outbox: { ...(saved.outbox ?? {}) } };
      return state;
    }
    // First sign-in to this account on this device: what is here goes up
    // (unless the student chose to start from the account's work), and the
    // account's records come down.
    state = { owner, cursor: 0, outbox: {} };
    if (mergeLocal) {
      const now = clock();
      for (const store of SYNCED) {
        for (const { key, value } of await local.all(store)) {
          if (isSynced(store, key)) state.outbox[id(store, key)] = modifiedOf(store, value) ?? now;
        }
      }
    }
    await local.saveState(state);
    return state;
  }

  function modifiedOf(store, value) {
    if (!value) return null;
    if (store === "files") return value.updated ?? null;
    if (store === "snapshots") return value.ts ?? null;
    return null;
  }

  /** A local change: note it, and push soon. */
  async function record(store, key, when = clock()) {
    if (!isSynced(store, key)) return;
    const s = await ensureState();
    s.outbox[id(store, key)] = Math.max(when, (s.outbox[id(store, key)] ?? 0) + 1);
    await local.saveState(s);
    schedulePush();
  }

  function schedulePush(delay = 800) {
    if (!running) return;
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => {
      serial(push);
    }, delay);
  }

  function serial(fn) {
    busy = busy.then(fn, fn).catch(() => {});
    return busy;
  }

  async function push() {
    const s = await ensureState();
    const entries = Object.entries(s.outbox);
    for (let i = 0; i < entries.length; i += batch) {
      const slice = entries.slice(i, i + batch);
      const records = [];
      for (const [rid, modified] of slice) {
        const cut = rid.indexOf(":");
        const store = rid.slice(0, cut);
        const key = rid.slice(cut + 1);
        const value = await local.read(store, key);
        records.push(
          value === undefined
            ? { store, key, data: null, modified, deleted: true }
            : { store, key, data: value, modified, deleted: false },
        );
      }
      const { rejected = [] } = (await remote.push(records)) ?? {};
      const refused = new Set(rejected);
      // Only what was sent and kept leaves the outbox: an edit made meanwhile
      // is newer, and one the server refused (it holds a newer edit) stays
      // until the pull meets that edit, which keeps this one as a snapshot.
      for (const [rid, modified] of slice) {
        if (s.outbox[rid] === modified && !refused.has(rid)) delete s.outbox[rid];
      }
      await local.saveState(s);
    }
  }

  async function pull() {
    const s = await ensureState();
    const changed = [];
    for (;;) {
      const { records, cursor } = await remote.pull(s.cursor, 500);
      for (const rec of records) {
        const did = await apply(rec, s);
        if (did) changed.push(...did);
      }
      if (cursor !== undefined && cursor !== null) s.cursor = Math.max(s.cursor, cursor);
      await local.saveState(s);
      if (records.length < 500) break;
    }
    if (changed.length) onApplied(changed);
    return changed;
  }

  /** One record from elsewhere.  Returns what changed here, for the views. */
  async function apply(rec, s) {
    if (!isSynced(rec.store, rec.key)) return null;
    const rid = id(rec.store, rec.key);
    const pending = s.outbox[rid];
    const mine = await local.read(rec.store, rec.key);
    if (pending !== undefined && pending > rec.modified) {
      // This device's edit is newer and not yet pushed: it stays, and goes up
      // next.  The other device's version of a proof is kept as a snapshot.
      if (rec.store === "files" && !rec.deleted && mine && rec.data && rec.data.source !== mine.source) {
        await keepAsSnapshot(rec.data, "From your other device", s);
        return [{ store: "snapshots" }];
      }
      return null;
    }
    if (pending !== undefined) {
      // Theirs is newer: it wins, and this device's unpushed version of a
      // proof is kept as a snapshot rather than lost.
      delete s.outbox[rid];
      if (rec.store === "files" && mine && (rec.deleted || rec.data?.source !== mine.source)) {
        await keepAsSnapshot(mine, "Kept from this device", s);
      }
    }
    if (rec.deleted) {
      if (mine === undefined) return null;
      await local.remove(rec.store, rec.key);
      return [{ store: rec.store, key: rec.key, deleted: true }];
    }
    let data = rec.data;
    if (rec.store === "files" && data) {
      // Two different proofs at one path (two devices' workspaces meeting for
      // the first time): the one with the later id moves aside, so every
      // device makes the same move, and the move syncs.
      const others = (await local.all("files")).filter((f) => f.key !== rec.key);
      const clash = others.find((f) => f.value.path === data.path);
      if (clash) {
        const taken = new Set(others.map((f) => f.value.path));
        if (rec.key > clash.key) {
          data = { ...data, path: freeCopyPath(data.path, taken) };
          await local.write(rec.store, rec.key, data);
          s.outbox[rid] = clock();
          schedulePush();
          return [{ store: rec.store, key: rec.key }];
        }
        taken.add(data.path);
        const moved = { ...clash.value, path: freeCopyPath(data.path, taken) };
        await local.write("files", clash.key, moved);
        await local.write(rec.store, rec.key, data);
        s.outbox[id("files", clash.key)] = clock();
        schedulePush();
        return [{ store: "files", key: clash.key }, { store: rec.store, key: rec.key }];
      }
    }
    if (same(mine, data)) return null;
    await local.write(rec.store, rec.key, data);
    return [{ store: rec.store, key: rec.key }];
  }

  async function keepAsSnapshot(file, name, s) {
    const snap = {
      id: snapshotId(clock),
      fileId: file.id,
      name,
      ts: clock(),
      source: file.source,
      strict: file.strict,
      working: Boolean(file.working),
      level: file.level ?? null,
      auto: true,
    };
    await local.write("snapshots", snap.id, snap);
    s.outbox[id("snapshots", snap.id)] = snap.ts;
  }

  return {
    record,
    /** Push what is pending, then pull what is new. */
    async syncNow() {
      return serial(async () => {
        await push();
        const changed = await pull();
        // What the pull itself produced (a kept snapshot, a file moved aside)
        // goes up now rather than waiting for the next edit.
        if (Object.keys(state.outbox).length) await push();
        return changed;
      });
    },
    pushNow: () => serial(push),
    pullNow: () => serial(pull),
    async start() {
      running = true;
      await ensureState();
      unsubscribe = remote.subscribe?.(() => serial(pull)) ?? null;
      return this.syncNow();
    },
    stop() {
      running = false;
      clearTimeout(pushTimer);
      unsubscribe?.();
      unsubscribe = null;
    },
    async pending() {
      const s = await ensureState();
      return Object.keys(s.outbox).length;
    },
  };
}
