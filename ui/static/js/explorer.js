// The Files panel: the workspace as a tree.
//
// role="tree" with one roving tab stop.  Keys: Up/Down move, Right/Left open
// and close folders (or step in and out), Enter opens a file, F2 renames,
// Delete deletes (with undo).  Files can be dragged onto a folder, or onto the
// tree's own background to move them to the top level.
//
// What the tree shows comes from workspace.js; what an action *does* is handed
// in by main.js, so this module only draws and dispatches.

import { el } from "./format.js";
import { allFolders, basename, dirname, filesSorted, model } from "./workspace.js";

const collapsed = new Set();
let handlers = {};
let verdicts = new Map(); // fileId -> "valid" | "warning" | "invalid"
let focusKey = null;

/** Hand in the actions and the per-file verdict map. */
export function initExplorer(actions, verdictMap) {
  handlers = actions;
  verdicts = verdictMap;
  const root = document.getElementById("explorer");
  root.addEventListener("keydown", onKeydown);
  // Dropping on the background moves a file to the top level.
  root.addEventListener("dragover", (event) => {
    if (!event.dataTransfer.types.includes("application/x-aether-file")) return;
    event.preventDefault();
  });
  root.addEventListener("drop", (event) => {
    const id = event.dataTransfer.getData("application/x-aether-file");
    if (!id || event.target.closest(".tree-row--folder")) return;
    event.preventDefault();
    handlers.onMove?.(id, "");
  });
}

function icon(kind) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("class", "icon tree-icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.3");
  svg.setAttribute("stroke-linejoin", "round");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute(
    "d",
    kind === "folder-open"
      ? "M2 4.5h4l1.2 1.3H14V12a.8.8 0 0 1-.8.8H2.8A.8.8 0 0 1 2 12z M2 7.5h12"
      : kind === "folder"
        ? "M2 4.5h4l1.2 1.3H14V12a.8.8 0 0 1-.8.8H2.8A.8.8 0 0 1 2 12z"
        : "M4 2h5.5L12.5 5v8.2a.8.8 0 0 1-.8.8H4.3a.8.8 0 0 1-.8-.8V2.8A.8.8 0 0 1 4.3 2z M9.5 2v3h3",
  );
  svg.append(path);
  return svg;
}

function actionButton(label, onClick) {
  const button = el("button", "tree-action", null);
  button.type = "button";
  button.tabIndex = -1;
  button.setAttribute("aria-label", label);
  button.title = label;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.4");
  svg.setAttribute("stroke-linecap", "round");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute(
    "d",
    label.startsWith("Rename") ? "M3 13l1-3.5L10.5 3 13 5.5 6.5 12zM9.5 4l2.5 2.5" : "M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.6 8.5h4.8l.6-8.5",
  );
  svg.append(path);
  button.append(svg);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick();
  });
  return button;
}

function row({ key, depth, label, kind, fileId = null, folder = null, expanded = null }) {
  const item = el("div", `tree-row tree-row--${kind}`);
  item.setAttribute("role", "treeitem");
  item.dataset.key = key;
  item.style.setProperty("--depth", String(depth));
  item.setAttribute("aria-level", String(depth + 1));
  if (expanded !== null) item.setAttribute("aria-expanded", String(expanded));
  if (fileId) {
    item.dataset.file = fileId;
    const active = fileId === model.activeId;
    item.setAttribute("aria-selected", String(active));
    if (active) item.classList.add("is-active");
    item.draggable = true;
    item.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-aether-file", fileId);
      event.dataTransfer.effectAllowed = "move";
    });
  }
  if (folder !== null) {
    item.dataset.folder = folder;
    item.addEventListener("dragover", (event) => {
      if (!event.dataTransfer.types.includes("application/x-aether-file")) return;
      event.preventDefault();
      item.dataset.dropTarget = "true";
    });
    item.addEventListener("dragleave", () => delete item.dataset.dropTarget);
    item.addEventListener("drop", (event) => {
      delete item.dataset.dropTarget;
      const id = event.dataTransfer.getData("application/x-aether-file");
      if (!id) return;
      event.preventDefault();
      handlers.onMove?.(id, folder);
    });
  }

  item.append(icon(kind === "folder" ? (expanded ? "folder-open" : "folder") : "file"));
  item.append(el("span", "tree-label", label));
  if (fileId) {
    const tone = verdicts.get(fileId);
    const mark = el("span", `tree-mark${tone ? ` tree-mark--${tone}` : ""}`);
    mark.setAttribute("aria-hidden", "true");
    item.append(mark);
    if (tone && tone !== "valid") item.setAttribute("aria-description", tone === "invalid" ? "does not check" : "checks with warnings");
  }
  const actions = el("span", "tree-actions");
  if (fileId) {
    actions.append(
      actionButton(`Rename ${label}`, () => startRename(item)),
      actionButton(`Delete ${label}`, () => handlers.onDelete?.(fileId)),
    );
  } else {
    actions.append(
      actionButton(`Rename folder ${label}`, () => startRename(item)),
      actionButton(`Delete folder ${label}`, () => handlers.onDeleteFolder?.(folder)),
    );
  }
  item.append(actions);

  item.addEventListener("click", () => {
    focusKey = key;
    if (fileId) handlers.onOpen?.(fileId);
    else toggle(folder);
  });
  return item;
}

function toggle(folder) {
  if (collapsed.has(folder)) collapsed.delete(folder);
  else collapsed.add(folder);
  renderExplorer();
}

/** Redraw the tree from the model, keeping focus on the same row. */
export function renderExplorer() {
  const root = document.getElementById("explorer");
  const hadFocus = root.contains(document.activeElement);
  root.replaceChildren();

  const files = filesSorted();
  if (!files.length && !model.folders.size) {
    const empty = el("div", "tree-empty");
    empty.append(
      el("p", null, "No proofs yet."),
      el("p", "tree-empty-sub", "Start a new proof, open one from the Library, or drop .aether files here."),
    );
    root.append(empty);
    return;
  }

  const folders = allFolders();
  const childrenOf = (parent) => ({
    folders: folders.filter((f) => dirname(f) === parent),
    files: files.filter((f) => dirname(f.path) === parent),
  });

  const walk = (parent, depth) => {
    const { folders: subFolders, files: subFiles } = childrenOf(parent);
    for (const folder of subFolders) {
      const expanded = !collapsed.has(folder);
      root.append(row({ key: `d:${folder}`, depth, label: basename(folder), kind: "folder", folder, expanded }));
      if (expanded) walk(folder, depth + 1);
    }
    for (const file of subFiles) {
      root.append(row({ key: `f:${file.id}`, depth, label: basename(file.path), kind: "file", fileId: file.id }));
    }
  };
  walk("", 0);

  const rows = [...root.querySelectorAll(".tree-row")];
  const target =
    rows.find((r) => r.dataset.key === focusKey) ?? rows.find((r) => r.classList.contains("is-active")) ?? rows[0];
  for (const r of rows) r.tabIndex = r === target ? 0 : -1;
  if (hadFocus && target) target.focus();
}

/** Expand the folders above *fileId* so the active file is always visible. */
export function revealFile(fileId) {
  const file = model.files.get(fileId);
  if (!file) return;
  let dir = dirname(file.path);
  while (dir) {
    collapsed.delete(dir);
    dir = dirname(dir);
  }
  focusKey = `f:${fileId}`;
}

function startRename(item) {
  const label = item.querySelector(".tree-label");
  const current = label.textContent;
  const input = el("input", "tree-rename");
  input.value = current;
  input.setAttribute("aria-label", "New name");
  label.replaceWith(input);
  input.focus();
  // Select the stem, not the extension: that is the part people rename.
  input.setSelectionRange(0, current.endsWith(".aether") ? current.length - 7 : current.length);
  let done = false;
  const finish = (commit) => {
    if (done) return;
    done = true;
    const value = input.value.trim();
    if (commit && value && value !== current) {
      if (item.dataset.file) handlers.onRename?.(item.dataset.file, value);
      else handlers.onRenameFolder?.(item.dataset.folder, value);
    } else {
      renderExplorer();
    }
  };
  input.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (event) => event.stopPropagation());
}

function onKeydown(event) {
  const rows = [...event.currentTarget.querySelectorAll(".tree-row")];
  const current = event.target.closest?.(".tree-row");
  if (!current || event.target.tagName === "INPUT") return;
  const index = rows.indexOf(current);
  const move = (to) => {
    const next = rows[Math.max(0, Math.min(rows.length - 1, to))];
    if (!next) return;
    for (const r of rows) r.tabIndex = r === next ? 0 : -1;
    focusKey = next.dataset.key;
    next.focus();
  };
  const folder = current.dataset.folder;
  switch (event.key) {
    case "ArrowDown":
      move(index + 1);
      break;
    case "ArrowUp":
      move(index - 1);
      break;
    case "Home":
      move(0);
      break;
    case "End":
      move(rows.length - 1);
      break;
    case "ArrowRight":
      if (folder !== undefined && collapsed.has(folder)) toggle(folder);
      else move(index + 1);
      break;
    case "ArrowLeft":
      if (folder !== undefined && !collapsed.has(folder)) toggle(folder);
      else {
        const parentKey = `d:${dirname(folder ?? model.files.get(current.dataset.file)?.path ?? "")}`;
        const parent = rows.findIndex((r) => r.dataset.key === parentKey);
        if (parent !== -1) move(parent);
      }
      break;
    case "Enter":
    case " ":
      current.click();
      break;
    case "F2":
      startRename(current);
      break;
    case "Delete":
      if (current.dataset.file) handlers.onDelete?.(current.dataset.file);
      else handlers.onDeleteFolder?.(folder);
      break;
    default:
      return;
  }
  event.preventDefault();
}
