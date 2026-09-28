// The workspace panel: this session's verdict timeline, saved snapshots, and
// the destructive actions (reset, clear).
//
// All four actions are injected as callbacks rather than imported, so this
// module never reaches into the editor or the checker.

import { dom } from "./dom.js";
import { el } from "./format.js";
import { clearSnapshots, clearTimeline, removeSnapshot, timeline, workspace } from "./store.js";

const TIMELINE_TONE = {
  VALID: "valid",
  "VALID (with domain warnings)": "warning",
  INVALID: "invalid",
  "PARSE ERROR": "parse",
};

function clock(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderTimeline() {
  dom.timeline.replaceChildren();

  const entries = timeline.entries;
  if (!entries.length) {
    dom.timeline.append(el("p", "ctx-none", "No checks yet this session."));
    dom.timelineNote.textContent = "";
    return;
  }

  // Run-length encoded: each segment grows with the number of consecutive
  // checks that produced the same verdict.
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

function renderSnapshots({ onRestore }) {
  dom.snapshots.replaceChildren();

  if (!workspace.snapshots.length) {
    dom.snapshots.append(
      el(
        "p",
        "ctx-none",
        "Nothing saved yet. Snapshots are taken automatically before an example, reset or restore replaces your buffer.",
      ),
    );
    return;
  }

  for (const snapshot of workspace.snapshots) {
    const row = el("div", "snapshot");

    const meta = el("div", "snapshot-meta");
    meta.append(el("span", "snapshot-name", snapshot.name));
    meta.append(
      el(
        "span",
        "snapshot-sub",
        `${clock(snapshot.ts)}${snapshot.strict ? " · strict" : ""}${snapshot.auto ? " · automatic" : ""}`,
      ),
    );
    row.append(meta);

    const actions = el("div", "snapshot-actions");

    const restore = el("button", "mini", "Restore");
    restore.type = "button";
    restore.addEventListener("click", () => onRestore(snapshot));
    actions.append(restore);

    const drop = el("button", "mini mini--danger", "Delete");
    drop.type = "button";
    drop.setAttribute("aria-label", `Delete snapshot ${snapshot.name}`);
    drop.addEventListener("click", () => {
      removeSnapshot(snapshot.id);
      renderSnapshots({ onRestore });
    });
    actions.append(drop);

    row.append(actions);
    dom.snapshots.append(row);
  }
}

export function renderHistory(handlers) {
  renderTimeline();
  renderSnapshots(handlers);
}

export function setHistoryOpen(open) {
  dom.historyPanel.hidden = !open;
  dom.historyToggle.setAttribute("aria-expanded", open ? "true" : "false");
}

export function isHistoryOpen() {
  return !dom.historyPanel.hidden;
}

export function initHistory(handlers) {
  dom.historyToggle.addEventListener("click", () => setHistoryOpen(!isHistoryOpen()));
  dom.historyClose.addEventListener("click", () => setHistoryOpen(false));

  dom.snapshotNow.addEventListener("click", () => {
    handlers.onSnapshot();
    renderHistory(handlers);
  });

  dom.copyLink.addEventListener("click", () => handlers.onCopyLink());

  dom.resetWorkspace.addEventListener("click", () => {
    handlers.onReset();
    renderHistory(handlers);
  });

  dom.clearHistory.addEventListener("click", () => {
    clearTimeline();
    clearSnapshots();
    renderHistory(handlers);
    handlers.onCleared?.();
  });

  // Escape closes the panel, matching the usual behaviour of a popover.
  dom.historyPanel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setHistoryOpen(false);
      dom.historyToggle.focus();
    }
  });
}
