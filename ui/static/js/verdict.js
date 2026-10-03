// The verdict pill in the topbar.

import { dom } from "./dom.js";
import { el, verdictClass } from "./format.js";

// The pill keeps showing the previous verdict for the length of the debounce,
// which for 300 ms is actively misleading: the proof on screen is no longer the
// one that verdict describes.  `is-stale` dims it and the data attribute makes
// "no longer describes the buffer" observable from outside.
function clearStale() {
  delete dom.verdict.dataset.stale;
}

export function markStale() {
  dom.verdict.dataset.stale = "1";
  dom.verdict.classList.add("is-stale");
}

export function renderVerdict(data) {
  clearStale();
  dom.verdict.className = `verdict ${verdictClass(data.verdict, data.parse_error)}`;
  dom.verdict.textContent = data.verdict;

  const bits = [];
  if (data.verdict === "TIMEOUT") {
    bits.push(data.parse_error?.headline ?? "stopped");
  } else if (data.parse_error) {
    bits.push(
      data.parse_error.line != null
        ? `line ${data.parse_error.line}, col ${data.parse_error.col ?? "?"}`
        : "location unknown",
    );
  } else {
    const s = data.summary;
    bits.push(`${s.total} statement${s.total === 1 ? "" : "s"}`);
    bits.push(`${s.valid} valid`);
    if (s.warnings) bits.push(`${s.warnings} warning${s.warnings === 1 ? "" : "s"}`);
    if (s.invalid) bits.push(`${s.invalid} invalid`);
  }
  bits.push(`${data.duration_ms.toFixed(0)} ms`);
  bits.push(data.strict_domains ? "strict domains" : "lenient domains");
  dom.verdictMeta.textContent = bits.join(" · ");
}

export function setPending() {
  clearStale();
  dom.verdict.className = "verdict verdict--pending";
  // renderVerdict() writes textContent, which clears the spinner again.
  dom.verdict.replaceChildren(el("wa-spinner"), document.createTextNode(engineLoading ? "Loading…" : "Checking…"));
  dom.verdictMeta.textContent = engineLoading ?? "";
}

// In the static build the checker itself loads in this browser first (about
// 25 MB the first time, then from the cache); while it does, a pending check
// says what it is waiting for rather than just "Checking…".
let engineLoading = null;

export function setEngineLoading(detail) {
  engineLoading = detail;
  if (dom.verdict.classList.contains("verdict--pending")) setPending();
}
