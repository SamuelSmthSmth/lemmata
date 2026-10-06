// The History panel: this proof's checks over time and its snapshots.
//
// Reads from workspace.js; the actions that replace the buffer (restore,
// reset) are injected by main.js, because they need the editor.

import { dom } from "./dom.js";
import { el } from "./format.js";
import { clearTimeline, model, removeSnapshot, snapshotsFor } from "./workspace.js";

const TIMELINE_TONE = {
  VALID: "valid",
  "VALID (with domain warnings)": "warning",
  INVALID: "invalid",
  "PARSE ERROR": "parse",
  TIMEOUT: "parse",
};

let handlers = {};

function clock(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function day(ts) {
  const date = new Date(ts);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? clock(ts)
    : `${date.toLocaleDateString([], { day: "numeric", month: "short" })} ${clock(ts)}`;
}

function renderTimeline() {
  dom.timeline.replaceChildren();
  // Run-length encoded: each segment grows with the number of consecutive
  // checks that produced the same verdict.
  const entries = model.timeline.filter((entry) => !entry.fileId || entry.fileId === model.activeId);
  if (!entries.length) {
    dom.timeline.append(el("p", "ctx-none", "No checks of this proof yet."));
    dom.timelineNote.textContent = "";
    return;
  }
  const strip = el("div", "tl-strip");
  for (const entry of entries) {
    const n = entry.n ?? 1;
    const bar = el("span", `tl-bar tl-bar--${TIMELINE_TONE[entry.verdict] ?? "parse"}`);
    bar.style.flexGrow = String(n);
    bar.title = `${entry.verdict} · ${n} check${n === 1 ? "" : "s"} · last at ${clock(entry.ts)}`;
    strip.append(bar);
  }
  dom.timeline.append(strip);
  const total = entries.reduce((sum, entry) => sum + (entry.n ?? 1), 0);
  const latest = entries[entries.length - 1];
  dom.timelineNote.textContent = `${total} check${total === 1 ? "" : "s"} · latest ${latest.verdict.toLowerCase()}`;
}

async function renderSnapshots() {
  const id = model.activeId;
  const list = id ? await snapshotsFor(id) : [];
  if (id !== model.activeId) return; // switched files while loading
  dom.snapshots.replaceChildren();
  if (!list.length) {
    dom.snapshots.append(
      el("p", "ctx-none", "Nothing saved yet. A snapshot is taken automatically before anything replaces this proof — a reset, a restore, a file dropped onto it."),
    );
    return;
  }
  for (const snapshot of list) {
    const row = el("div", "snapshot");
    const meta = el("div", "snapshot-meta");
    meta.append(el("span", "snapshot-name", snapshot.name));
    meta.append(el("span", "snapshot-sub", `${day(snapshot.ts)}${snapshot.strict ? " · strict" : ""}${snapshot.working ? " · show working" : ""}${snapshot.level && snapshot.level !== "off" ? ` · ${snapshot.level} level` : ""}${snapshot.auto ? " · automatic" : ""}`));
    row.append(meta);
    const actions = el("div", "snapshot-actions");
    const restore = el("button", "text-button", "Restore");
    restore.type = "button";
    restore.addEventListener("click", () => handlers.onRestore?.(snapshot));
    const drop = el("button", "text-button text-button--danger", "Delete");
    drop.type = "button";
    drop.setAttribute("aria-label", `Delete snapshot ${snapshot.name}`);
    drop.addEventListener("click", async () => {
      await removeSnapshot(snapshot.id);
      renderHistory();
    });
    actions.append(restore, drop);
    row.append(actions);
    dom.snapshots.append(row);
  }
}

export function renderHistory() {
  renderTimeline();
  return renderSnapshots();
}

export function initHistory(actions) {
  handlers = actions;
  dom.snapshotNow.addEventListener("click", async () => {
    await handlers.onSnapshot?.();
    renderHistory();
  });
  dom.copyLink.addEventListener("click", () => handlers.onCopyLink?.());
  dom.resetWorkspace.addEventListener("click", async () => {
    await handlers.onReset?.();
    renderHistory();
  });
  dom.clearHistory.addEventListener("click", async () => {
    clearTimeline();
    await handlers.onClearSnapshots?.();
    renderHistory();
    handlers.onCleared?.();
  });
}
