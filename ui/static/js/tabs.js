// The tab strip: the open proofs, in order.
//
// A WAI-ARIA tablist: Left/Right move between tabs, Enter or Space activates,
// Delete closes.  Each tab carries the file's last verdict as a small mark,
// so a failing proof in a background tab is visible without opening it.

import { el } from "./format.js";
import { basename, model } from "./workspace.js";

let handlers = {};
let verdicts = new Map();

export function initTabs(actions, verdictMap) {
  handlers = actions;
  verdicts = verdictMap;
  const strip = document.getElementById("tabs");
  strip.addEventListener("keydown", (event) => {
    const tabs = [...strip.querySelectorAll(".tab")];
    const current = event.target.closest?.(".tab");
    if (!current) return;
    const index = tabs.indexOf(current);
    let next = null;
    if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
    else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs[tabs.length - 1];
    else if (event.key === "Delete") {
      event.preventDefault();
      handlers.onClose?.(current.dataset.file);
      return;
    } else return;
    event.preventDefault();
    next?.focus();
  });
}

export function renderTabs() {
  const strip = document.getElementById("tabs");
  const hadFocus = strip.contains(document.activeElement);
  strip.replaceChildren();
  for (const id of model.tabs) {
    const file = model.files.get(id);
    if (!file) continue;
    const active = id === model.activeId;
    const tab = el("div", `tab${active ? " is-active" : ""}`);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(active));
    tab.setAttribute("aria-controls", "editor");
    tab.tabIndex = active ? 0 : -1;
    tab.dataset.file = id;
    tab.title = file.path;
    tab.draggable = true;

    const tone = verdicts.get(id);
    const mark = el("span", `tab-mark${tone ? ` tab-mark--${tone}` : ""}`);
    mark.setAttribute("aria-hidden", "true");
    tab.append(mark, el("span", "tab-label", basename(file.path).replace(/\.aether$/, "")));

    const close = el("button", "tab-close");
    close.type = "button";
    close.tabIndex = -1;
    close.setAttribute("aria-label", `Close ${basename(file.path)}`);
    close.innerHTML =
      '<svg class="icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>';
    close.addEventListener("click", (event) => {
      event.stopPropagation();
      handlers.onClose?.(id);
    });
    tab.append(close);

    tab.addEventListener("click", () => handlers.onActivate?.(id));
    tab.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handlers.onActivate?.(id);
      }
    });
    // Middle-click closes, as in every browser tab strip.
    tab.addEventListener("auxclick", (event) => {
      if (event.button === 1) handlers.onClose?.(id);
    });
    tab.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-aether-tab", id);
      event.dataTransfer.effectAllowed = "move";
    });
    tab.addEventListener("dragover", (event) => {
      if (event.dataTransfer.types.includes("application/x-aether-tab")) event.preventDefault();
    });
    tab.addEventListener("drop", (event) => {
      const moved = event.dataTransfer.getData("application/x-aether-tab");
      if (!moved || moved === id) return;
      event.preventDefault();
      handlers.onMove?.(moved, model.tabs.indexOf(id));
    });
    strip.append(tab);
  }
  if (!model.tabs.length) {
    strip.append(el("span", "tabs-empty", "No proof open"));
  }
  if (hadFocus) strip.querySelector(".tab.is-active")?.focus();
}
