// The Guide: the handbook, in the app.
//
// Pages are static HTML partials under /static/guide/.  Every runnable example
// is a <pre class="try" data-expect="..."> block -- ui/verify_server.py checks
// each one against the engine -- and gets a "Try it" button here that opens it
// in a scratch proof.  A page can be pinned beside the proof in the Notes tab.

import { fetchCapabilities } from "./api.js";
import { el } from "./format.js";

export const GUIDE_PAGES = [
  { id: "start", title: "Getting started" },
  { id: "language", title: "Writing a proof" },
  { id: "notation", title: "Notation" },
  { id: "analysis", title: "Real analysis" },
  { id: "algebra", title: "Algebra" },
  { id: "limits", title: "What the checker can decide" },
  { id: "keys", title: "Keyboard" },
];

const cache = new Map();
let handlers = {};
let current = null;

export function initGuide(actions) {
  handlers = actions;
  const toc = document.getElementById("guide-toc");
  const list = el("ol", "guide-toc-list");
  for (const page of GUIDE_PAGES) {
    const item = el("li");
    const link = el("a", "guide-toc-link", page.title);
    link.href = `?view=guide&page=${page.id}`;
    link.dataset.page = page.id;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openGuidePage(page.id);
    });
    item.append(link);
    list.append(item);
  }
  toc.replaceChildren(el("p", "guide-toc-head", "Guide"), list);
}

async function pageHtml(id) {
  if (!cache.has(id)) {
    const response = await fetch(`/static/guide/${id}.html`);
    if (!response.ok) throw new Error(`the page could not be loaded (${response.status})`);
    cache.set(id, await response.text());
  }
  return cache.get(id);
}

/** Decorate a page's DOM: Try-it buttons, and the capability matrix where it lives. */
function decorate(root, { compact = false } = {}) {
  for (const pre of root.querySelectorAll("pre.try")) {
    const wrap = el("div", "try-block");
    pre.replaceWith(wrap);
    wrap.append(pre);
    const bar = el("div", "try-bar");
    const expect = pre.dataset.expect;
    if (expect) bar.append(el("span", `try-expect try-expect--${expect.toLowerCase().replace(/\s+/g, "-")}`, expect === "WARN" ? "warns" : expect === "VALID" ? "checks" : "fails"));
    const button = el("button", "text-button", "Try it");
    button.type = "button";
    button.addEventListener("click", () => handlers.onTry?.(pre.textContent, root.dataset.title ?? "Guide example"));
    bar.append(button);
    wrap.append(bar);
  }
  const matrix = root.querySelector("#capability-matrix");
  if (matrix && !compact) renderMatrix(matrix);
}

async function renderMatrix(container) {
  try {
    const rows = await fetchCapabilities();
    const table = el("table", "guide-table capability-table");
    const head = el("thead");
    const headRow = el("tr");
    for (const label of ["Feature", "Verdict", "Note"]) headRow.append(el("th", null, label));
    head.append(headRow);
    const body = el("tbody");
    let area = null;
    for (const row of rows) {
      if (row.area !== area) {
        area = row.area;
        const tr = el("tr", "capability-area");
        const td = el("td", null, area);
        td.colSpan = 3;
        tr.append(td);
        body.append(tr);
      }
      const tr = el("tr");
      const name = el("td");
      name.append(el("span", "capability-name", row.name));
      const source = el("code", "capability-source", row.source.split("\n").pop());
      source.title = row.source;
      name.append(source);
      tr.append(name, el("td", `capability-verdict is-${row.expect.toLowerCase().replace(/_/g, "-")}`, row.expect.replace("_", " ")), el("td", "capability-note", row.note || ""));
      body.append(tr);
    }
    table.append(head, body);
    container.replaceChildren(table);
  } catch (error) {
    container.replaceChildren(el("p", "guide-error", `The capability matrix could not be loaded: ${error.message}`));
  }
}

export async function openGuidePage(id, { push = true } = {}) {
  const page = GUIDE_PAGES.find((p) => p.id === id) ?? GUIDE_PAGES[0];
  current = page.id;
  for (const link of document.querySelectorAll(".guide-toc-link")) {
    if (link.dataset.page === page.id) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const article = document.getElementById("guide-article");
  article.replaceChildren(el("p", "guide-loading", "Loading…"));
  try {
    const html = await pageHtml(page.id);
    if (current !== page.id) return;
    const body = el("div", "guide-body");
    body.innerHTML = html;
    body.dataset.title = page.title;
    const tools = el("div", "guide-tools");
    const pin = el("button", "text-button", "Pin beside the proof");
    pin.type = "button";
    pin.addEventListener("click", () => handlers.onPin?.(page.id));
    tools.append(pin);
    decorate(body);
    article.replaceChildren(tools, body);
    article.scrollTop = 0;
    handlers.onNavigate?.(page.id, push);
  } catch (error) {
    article.replaceChildren(el("p", "guide-error", `This page could not be loaded: ${error.message}`));
  }
}

export function currentGuidePage() {
  return current;
}

/** A guide page's content for the Notes tab, with working Try-it buttons. */
export async function guideNode(id) {
  const page = GUIDE_PAGES.find((p) => p.id === id);
  if (!page) return null;
  const body = el("div", "guide-body guide-body--pinned");
  body.innerHTML = await pageHtml(page.id);
  body.dataset.title = page.title;
  decorate(body, { compact: true });
  body.querySelector("#capability-matrix")?.remove();
  return { title: page.title, node: body };
}
