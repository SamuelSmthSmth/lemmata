// Transient notifications: saved, copied, storage full, file rejected.
//
// The live region is in index.html and stays put; only its text and tone
// change, so screen readers announce each message without re-announcing the
// region itself.

import { dom } from "./dom.js";

let timer = null;

export function showToast(text, { tone = "info", ms = 2600 } = {}) {
  dom.toast.textContent = text;
  dom.toast.className = `toast toast--${tone}`;
  dom.toast.hidden = false;

  window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    dom.toast.hidden = true;
  }, ms);
}
