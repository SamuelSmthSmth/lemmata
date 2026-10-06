// The Trace tab: what the checker did, as a terminal would print it.
//
// One block per line of the proof: a head (the line, its statement, its status
// and the time its calls took) that selects the step, then each backend call
// made checking it (SymPy and Z3, the call, the query in the proof's notation,
// the answer and its milliseconds), indented under the call that made it.  It
// reads from the report already in memory (StepResult.trace, from a check made
// with the audit on), and follows the auditor's selection.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { el } from "./format.js";
import { getPref } from "./prefs.js";
import { selectStep } from "./audit.js";

/** Calls shown per line before "N more" is offered. */
const SHOWN = 40;

const expanded = new Set();

function answerClass(answer) {
  const a = String(answer).toLowerCase();
  if (/^(holds|unsat|proved|valid|true|identity)/.test(a)) return "trace-answer is-yes";
  if (/(unknown|timeout|budget|gave up)/.test(a)) return "trace-answer is-unknown";
  return "trace-answer";
}

function ms(value) {
  if (value == null) return "";
  return value >= 100 ? `${Math.round(value)}` : value.toFixed(1);
}

function eventRow(event) {
  const row = el("div", "trace-event");
  row.style.setProperty("--depth", String(event.depth ?? 0));
  row.append(el("span", "trace-ms", ms(event.ms)));
  const body = el("span", "trace-call");
  body.append(
    el("span", "trace-backend", event.backend),
    el("span", "trace-kind", event.call),
    el("code", "trace-query", event.query),
    el("span", "trace-arrow", "→"),
    el("span", answerClass(event.result), event.result),
  );
  row.append(body);
  return row;
}

function total(events) {
  return (events ?? []).filter((e) => (e.depth ?? 0) === 0).reduce((sum, e) => sum + (e.ms ?? 0), 0);
}

/** A block's own lines (a case, a subproof, an inductive step): each with its
 *  calls, stepped in under the block, as the proof indents them. */
function innerLines(lines, level) {
  const out = [];
  for (const line of lines) {
    const wrap = el("div", "trace-inner");
    wrap.style.setProperty("--level", String(level));
    const head = el("div", "trace-subhead");
    head.append(el("span", "trace-line", line.line != null ? `L${line.line}` : ""));
    head.append(el("code", "trace-statement", line.statement));
    const meta = el("span", "trace-meta");
    meta.append(el("span", `status status--${String(line.status).toLowerCase()}`, line.status));
    if (line.trace?.length) meta.append(el("span", "trace-total", `${ms(total(line.trace))} ms`));
    head.append(meta);
    wrap.append(head);
    if (line.trace?.length) {
      const list = el("div", "trace-events");
      for (const event of line.trace) list.append(eventRow(event));
      wrap.append(list);
    }
    out.push(wrap, ...innerLines(line.inner ?? [], level + 1));
  }
  return out;
}

function stepBlock(entry, index) {
  const { result } = entry;
  const block = el("section", "trace-block");
  block.dataset.index = String(index);
  if (state.selected === index) block.classList.add("is-selected");

  const head = el("button", "trace-head");
  head.type = "button";
  head.append(el("span", "trace-line", result.line != null ? `L${result.line}` : ""));
  head.append(el("code", "trace-statement", result.statement));
  const meta = el("span", "trace-meta");
  meta.append(el("span", `status status--${result.status.toLowerCase()}`, result.status));
  if (result.trace?.length) meta.append(el("span", "trace-total", `${ms(total(result.trace))} ms`));
  head.append(meta);
  head.addEventListener("click", () => selectStep(index, { focus: true }));
  block.append(head);

  const events = result.trace ?? [];
  const inner = innerLines(result.inner ?? [], 1);
  if (!events.length) {
    block.append(...(inner.length ? inner : [el("p", "trace-quiet", "No solver calls.")]));
    return block;
  }
  const open = expanded.has(index);
  const shown = open ? events : events.slice(0, SHOWN);
  const list = el("div", "trace-events");
  for (const event of shown) list.append(eventRow(event));
  block.append(list);
  if (events.length > shown.length) {
    const more = el("button", "text-button trace-more", `${events.length - shown.length} more calls`);
    more.type = "button";
    more.addEventListener("click", () => {
      expanded.add(index);
      renderTrace();
    });
    block.append(more);
  }
  block.append(...inner);
  return block;
}

function empty(text) {
  dom.trace.replaceChildren(el("p", "trace-empty", text));
}

export function renderTrace() {
  if (!dom.trace) return;
  if (getPref("audit") !== "on") {
    empty("The trace is off. Turn on “What each line used” in Settings, and each check records what it asked SymPy and Z3.");
    return;
  }
  if (document.body.dataset.exercise === "hidden") {
    empty("The trace is hidden until you choose the line you think fails: its answers would give the exercise away.");
    return;
  }
  const data = state.data;
  if (!data) {
    empty("Check a proof to see what the checker asked, and what it was told.");
    return;
  }
  if (data.parse_error) {
    empty("The proof does not parse, so nothing was checked.");
    return;
  }
  if (!state.steps.some((entry) => entry.result.trace?.length || entry.result.inner?.length)) {
    empty("This check recorded no trace. It will appear after the next check.");
    return;
  }

  const count = (lines) => lines.reduce((n, l) => n + (l.trace?.length ?? 0) + count(l.inner ?? []), 0);
  const calls = count(state.steps.map((entry) => entry.result));
  const head = el("p", "trace-command");
  // The same log the command line prints with --trace (`lemmata --trace FILE`).
  head.append(el("span", "trace-prompt", "$"), el("span", null, ` lemmata --trace ${dom.editorPath?.textContent || "proof.aether"}`));
  const nodes = [head];
  state.steps.forEach((entry, i) => nodes.push(stepBlock(entry, i)));
  const summary = el("p", "trace-summary", `${calls} call${calls === 1 ? "" : "s"} · ${Math.round(data.duration_ms ?? 0)} ms · ${data.verdict}`);
  nodes.push(summary);
  dom.trace.replaceChildren(...nodes);
}

/** Follow the auditor: mark the selected line's block and bring it into view. */
export function followSelection(index) {
  if (!dom.trace) return;
  for (const block of dom.trace.querySelectorAll(".trace-block")) {
    block.classList.toggle("is-selected", Number(block.dataset.index) === index);
  }
  if (!dom.trace.closest("[hidden]")) {
    dom.trace.querySelector(`.trace-block[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }
}

/** A new check: forget which lines were expanded. */
export function resetTrace() {
  expanded.clear();
}
