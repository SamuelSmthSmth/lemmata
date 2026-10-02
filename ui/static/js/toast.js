// Transient notifications: saved, copied, deleted (with undo), file rejected.
//
// These are <wa-toast-item>s appended to the single <wa-toast> stack in
// index.html.  The stack owns the layout and the queueing, and each item owns
// its own countdown, so all we do is translate the app's tone into a Web
// Awesome variant.  The item removes itself only after it has finished hiding,
// so the exit animation is never cut off.
//
// A toast with an `action` (Undo) stays twice as long, and its button runs the
// action once and closes the toast.

import { dom } from "./dom.js";

const VARIANT = { info: "neutral", warning: "warning", danger: "danger" };

export function showToast(text, { tone = "info", ms = 2600, action = null, onAction = null } = {}) {
  const item = document.createElement("wa-toast-item");
  item.variant = VARIANT[tone] ?? "neutral";
  item.duration = action ? Math.max(ms, 6000) : ms;
  item.append(document.createTextNode(text));
  if (action && onAction) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action;
    let used = false;
    button.addEventListener("click", () => {
      if (used) return;
      used = true;
      onAction();
      item.hide?.();
    });
    item.append(button);
  }
  item.addEventListener("wa-after-hide", () => item.remove(), { once: true });
  dom.toast.append(item);
}
