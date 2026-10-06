// One bus for "the student changed something that is kept": a file, a
// snapshot, a setting, the panel layout.  db.js, prefs.js and layout.js tell
// it; sync (js/sync.js) listens and notes the change in its outbox.  Writes
// that come *from* sync use the quiet paths, so they are not sent back.
//
// DOM-free, so the modules that tell it stay importable in Node.

const listeners = new Set();

/** fn(store, key) after each kept change.  Returns an unsubscribe. */
export function onChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function changed(store, key) {
  for (const fn of listeners) {
    try {
      fn(store, key);
    } catch (error) {
      // A listener's failure must not fail the write that told it.
    }
  }
}
