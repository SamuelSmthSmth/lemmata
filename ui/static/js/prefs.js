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
  desk: { key: "aether-desk", allowed: ["open", "closed"], fallback: "open" },
  deskPanel: { key: "aether-desk-panel", allowed: ["files", "notes", "history"], fallback: "files" },
  view: { key: "aether-view", allowed: ["workspace", "library", "guide", "settings"], fallback: "workspace" },
  welcomed: { key: "aether-welcomed", allowed: ["yes", "no"], fallback: "no" },
};

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
  const spec = SPEC[name];
  if (!spec.allowed.includes(String(value))) return;
  try {
    localStorage.setItem(spec.key, String(value));
  } catch (error) {
    // Storage can be unavailable; the choice simply will not persist.
  }
  for (const fn of listeners) fn(name, String(value));
}

export function onPrefChange(fn) {
  listeners.add(fn);
}

export const PREF_OPTIONS = Object.fromEntries(Object.entries(SPEC).map(([k, v]) => [k, v.allowed]));
