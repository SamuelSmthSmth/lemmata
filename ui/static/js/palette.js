// The command palette (Ctrl/Cmd+K).
//
// One list, three kinds of row: commands, open-able files, and Library
// entries -- so "2.18" finds Example 2.18 and "week" finds week1.aether.
// Rows come from a provider function main.js hands in, so this module knows
// nothing about what the commands do.

import { el } from "./format.js";

let provider = () => [];
let selected = 0;
let rows = [];
let returnFocus = null;

function score(item, terms) {
  const hay = `${item.label} ${item.detail ?? ""} ${item.keywords ?? ""}`.toLowerCase();
  let total = 0;
  for (const term of terms) {
    const at = hay.indexOf(term);
    if (at === -1) return -1;
    total += at === 0 ? 3 : hay[at - 1] === " " ? 2 : 1;
  }
  return total + (item.boost ?? 0);
}

function render() {
  const dialog = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  const list = document.getElementById("palette-list");
  const terms = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const all = provider();
  rows = terms.length
    ? all
        .map((item) => ({ item, s: score(item, terms) }))
        .filter((r) => r.s >= 0)
        .sort((a, b) => b.s - a.s)
        .map((r) => r.item)
    : all.filter((item) => item.kind === "command");
  rows = rows.slice(0, 40);
  selected = Math.min(selected, Math.max(0, rows.length - 1));
  list.replaceChildren();
  rows.forEach((item, index) => {
    const li = el("li", `palette-row${index === selected ? " is-selected" : ""}`);
    li.id = `palette-row-${index}`;
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(index === selected));
    li.append(el("span", `palette-kind palette-kind--${item.kind}`, { command: "Command", file: "Proof", entry: "Library" }[item.kind] ?? ""));
    li.append(el("span", "palette-label", item.label));
    if (item.detail) li.append(el("span", "palette-detail", item.detail));
    if (item.shortcut) li.append(el("kbd", "palette-shortcut", item.shortcut));
    li.addEventListener("mousedown", (event) => event.preventDefault());
    li.addEventListener("click", () => run(index));
    list.append(li);
  });
  if (!rows.length) list.append(el("li", "palette-empty", "Nothing matches."));
  input.setAttribute("aria-activedescendant", rows.length ? `palette-row-${selected}` : "");
  list.querySelector(".is-selected")?.scrollIntoView({ block: "nearest" });
  dialog.dataset.count = String(rows.length);
}

function run(index) {
  const item = rows[index];
  if (!item) return;
  closePalette();
  item.run();
}

export function openPalette(initial = "") {
  const dialog = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  if (dialog.open) return;
  returnFocus = document.activeElement;
  input.value = initial;
  selected = 0;
  render();
  dialog.showModal();
  input.focus();
  input.select();
}

export function closePalette() {
  const dialog = document.getElementById("palette");
  if (!dialog.open) return;
  dialog.close();
}

export function initPalette(itemsProvider) {
  provider = itemsProvider;
  const dialog = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  input.addEventListener("input", () => {
    selected = 0;
    render();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") selected = Math.min(selected + 1, rows.length - 1);
    else if (event.key === "ArrowUp") selected = Math.max(selected - 1, 0);
    else if (event.key === "Enter") return void (event.preventDefault(), run(selected));
    else return;
    event.preventDefault();
    render();
  });
  // A click on the backdrop (the dialog element itself, outside the box) closes it.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closePalette();
  });
  dialog.addEventListener("close", () => {
    if (returnFocus && document.contains(returnFocus)) returnFocus.focus();
  });
}
