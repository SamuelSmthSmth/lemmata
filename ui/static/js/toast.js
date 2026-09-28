// Transient notifications: saved, copied, storage full, file rejected.
//
// These are <wa-toast-item>s appended to the single <wa-toast> stack in
// index.html.  The stack owns the layout and the queueing, and each item owns
// its own countdown, so all we do is translate the app's tone into a Web
// Awesome variant.  The item removes itself only after it has finished hiding,
// so the exit animation is never cut off.

import { dom } from "./dom.js";

const VARIANT = { info: "neutral", warning: "warning", danger: "danger" };

export function showToast(text, { tone = "info", ms = 2600 } = {}) {
  const item = document.createElement("wa-toast-item");
  item.variant = VARIANT[tone] ?? "neutral";
  item.duration = ms;
  item.textContent = text;
  item.addEventListener("wa-after-hide", () => item.remove(), { once: true });
  dom.toast.append(item);
}
