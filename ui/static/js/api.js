// Thin wrappers over the engine: the server's endpoints, or -- in the static
// build -- the engine running in this browser (js/backend.js).  Every caller
// goes through here, and both answer with the same shapes.
//
// Nothing here touches the DOM or the editor, so it is safe to import from
// anywhere (and easy to stub).

import { browser, mode } from "./backend.js";

const inBrowser = mode === "browser";

/** Whether this build can compile a PDF (it needs the server's TeX install). */
export const canExportPdf = !inBrowser;

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export const fetchLibrary = () => (inBrowser ? browser.json("library") : getJson("/api/library"));
export const fetchCapabilities = () => (inBrowser ? browser.json("capabilities") : getJson("/api/capabilities"));
export const fetchSite = () => (inBrowser ? browser.json("site") : getJson("/api/site"));

/** Ask the server whether parsed .pack.json contents are a pack: {pack} or {errors}. */
export async function validatePack(data) {
  if (inBrowser) {
    const result = await browser.validatePack(data);
    return { pack: result.pack ?? null, errors: result.errors ?? [] };
  }
  const response = await fetch("/api/packs/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pack: data }),
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  const result = await response.json();
  return { pack: result.pack ?? null, errors: result.errors ?? [] };
}

/**
 * Check a proof.  `files` (workspace path -> source) and `path` (this file's
 * own workspace path) let `import` statements resolve against the browser
 * workspace; they are only sent when the proof imports something.
 */
export async function checkProof({ source, strictDomains, showWorking = false, files = null, path = null, citations = null, signal }) {
  if (inBrowser) return browser.check({ source, strictDomains, showWorking, files, path, citations, signal });
  const response = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, strict_domains: strictDomains, show_working: showWorking, files, path, citations }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

// `breakdown` appends the verification report (audit, proof state, session,
// source listing) to the typeset proof; `session` carries the timeline and
// snapshots, which only the browser knows about.
export async function exportLatex({ source, standalone = true, strictDomains = false, breakdown = true, session = null, signal }) {
  if (inBrowser) return browser.latex({ source, standalone, strictDomains, breakdown, session });
  const response = await fetch("/api/export/latex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, standalone, strict_domains: strictDomains, breakdown, session }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

/**
 * The proof as a Lean 4 + Mathlib skeleton: {lean, rows, untranslated, error?}.
 * Each row is a run of Lean lines and the source line they came from.
 */
export async function exportLean({ source, files = null, path = null, citations = null, signal }) {
  if (inBrowser) return browser.lean({ source, files, path, citations });
  const response = await fetch("/api/export/lean", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, files, path, citations }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export async function exportPdf({ source, strictDomains = false, breakdown = true, session = null, signal }) {
  if (inBrowser) throw new Error("PDF export needs a TeX installation, which this web version does not have");
  const response = await fetch("/api/export/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, strict_domains: strictDomains, breakdown, session }),
    signal,
  });
  if (!response.ok) {
    let errText = `Server error ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.error) errText = errJson.error;
    } catch {
      // ignore
    }
    throw new Error(errText);
  }
  return response.blob();
}
