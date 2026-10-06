// Small per-browser preferences, in localStorage.
//
// These are read before first paint by the inline script in index.html (theme,
// syntax, editor size, reading pane), so they stay in localStorage rather than
// IndexedDB, which cannot be read synchronously.  Every value is validated on
// the way out: storage is user-editable and outlives upgrades.

const SPEC = {
  theme: { key: "aether-theme", allowed: ["light", "dark"], fallback: null },
  syntax: { key: "aether-syntax", allowed: ["mono", "vivid"], fallback: "mono" },
  editorSize: { key: "aether-editor-size", allowed: ["12", "13", "14", "15", "16"], fallback: "13" },
  wrap: { key: "aether-wrap", allowed: ["on", "off"], fallback: "off" },
  visual: { key: "aether-visual", allowed: ["on", "off"], fallback: "off" },
  debounce: { key: "aether-debounce", allowed: ["150", "300", "600", "1000"], fallback: "300" },
  strictDefault: { key: "aether-strict-default", allowed: ["on", "off"], fallback: "off" },
  workingDefault: { key: "aether-working-default", allowed: ["on", "off"], fallback: "off" },
  // The checking level of new proofs (js/level.js; the proof kernel's levels).
  levelDefault: { key: "aether-level-default", allowed: ["off", "exam", "course", "scratch"], fallback: "course" },
  // What each line used and the checker's trace: the proof graph and the Trace tab.
  audit: { key: "aether-audit", allowed: ["on", "off"], fallback: "on" },
  // The auditor's arcs: the selected line's only, or the whole graph.
  graph: { key: "aether-graph", allowed: ["selected", "all"], fallback: "selected" },
  desk: { key: "aether-desk", allowed: ["open", "closed"], fallback: "open" },
  deskPanel: { key: "aether-desk-panel", allowed: ["files", "notes", "history", "trace"], fallback: "files" },
  view: { key: "aether-view", allowed: ["workspace", "library", "guide", "settings"], fallback: "workspace" },
  welcomed: { key: "aether-welcomed", allowed: ["yes", "no"], fallback: "no" },
};

import { changed } from "./changes.js";

const listeners = new Set();

export function getPref(name) {
  const spec = SPEC[name];
  try {
    const value = localStorage.getItem(spec.key);
    return spec.allowed.includes(value) ? value : spec.fallback;
  } catch (error) {
    return spec.fallback;
  }
}

export function setPref(name, value) {
  if (store(name, value)) changed("prefs", SPEC[name].key);
}

// Listeners hear fn(name, value, {remote}); remote is true for a setting that
// arrived from another device, which the app re-applies on screen.
function store(name, value, origin = { remote: false }) {
  const spec = SPEC[name];
  if (!spec.allowed.includes(String(value))) return false;
  try {
    localStorage.setItem(spec.key, String(value));
  } catch (error) {
    // Storage can be unavailable; the choice simply will not persist.
  }
  for (const fn of listeners) fn(name, String(value), origin);
  return true;
}

/** The storage keys of every preference, for sync. */
export const PREF_KEYS = Object.values(SPEC).map((spec) => spec.key);

/** A preference by storage key, as stored (null when unset). */
export function readPrefKey(key) {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

/** A preference from another device: applied, but not sent back. */
export function adoptPrefKey(key, value) {
  const name = Object.keys(SPEC).find((n) => SPEC[n].key === key);
  if (!name) return;
  if (value === null || value === undefined) {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      // Nothing to remove.
    }
    for (const fn of listeners) fn(name, getPref(name), { remote: true });
    return;
  }
  store(name, value, { remote: true });
}

export function onPrefChange(fn) {
  listeners.add(fn);
}

export const PREF_OPTIONS = Object.fromEntries(Object.entries(SPEC).map(([k, v]) => [k, v.allowed]));
