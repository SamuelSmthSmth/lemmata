// A sync remote in memory: the server's rules, without a server.
//
// It does what the Supabase function does (supabase/migrations/): per
// (store, key) it keeps the record with the newest `modified`, and numbers
// every accepted write with a rising `seq`, so a pull from a cursor sees each
// change once.  Used by the frontend checks to play several devices against
// one account, and by the app when site.json asks for a demo remote.

// Postgres's jsonb does not keep object key order (shorter keys first, then
// by bytes), so neither does this: sync must not mistake a reordered record
// for a changed one.
function jsonbOrder(value) {
  if (Array.isArray(value)) return value.map(jsonbOrder);
  if (!value || typeof value !== "object") return value;
  const keys = Object.keys(value).sort((a, b) => a.length - b.length || (a < b ? -1 : a > b ? 1 : 0));
  return Object.fromEntries(keys.map((k) => [k, jsonbOrder(value[k])]));
}

export function createMemoryRemote() {
  const rows = new Map(); // "store:key" -> record with seq
  const subscribers = new Set();
  let seq = 0;

  return {
    rows,
    async push(records) {
      const accepted = [];
      const rejected = [];
      for (const rec of records) {
        const key = `${rec.store}:${rec.key}`;
        const current = rows.get(key);
        if (current && current.modified > rec.modified) {
          rejected.push(key); // a newer edit is already here
          continue;
        }
        const row = { ...structuredClone(rec), data: rec.deleted ? null : jsonbOrder(structuredClone(rec.data)), seq: ++seq };
        rows.set(key, row);
        accepted.push(row);
      }
      for (const fn of subscribers) for (const row of accepted) fn(row);
      return { accepted: accepted.length, rejected };
    },
    async pull(cursor = 0, limit = 500) {
      const records = [...rows.values()]
        .filter((r) => r.seq > cursor)
        .sort((a, b) => a.seq - b.seq)
        .slice(0, limit)
        .map((r) => structuredClone(r));
      return { records, cursor: records.length ? records[records.length - 1].seq : cursor };
    },
    subscribe(fn) {
      subscribers.add(fn);
      return () => subscribers.delete(fn);
    },
  };
}
