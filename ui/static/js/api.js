// Thin wrappers over the backend endpoints.
//
// Nothing here touches the DOM or the editor, so it is safe to import from
// anywhere (and easy to stub).

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export const fetchExamples = () => getJson("/api/examples");
export const fetchLibrary = () => getJson("/api/library");
export const fetchCapabilities = () => getJson("/api/capabilities");

/**
 * Check a proof.  `files` (workspace path -> source) and `path` (this file's
 * own workspace path) let `import` statements resolve against the browser
 * workspace; they are only sent when the proof imports something.
 */
export async function checkProof({ source, strictDomains, files = null, path = null, signal }) {
  const response = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, strict_domains: strictDomains, files, path }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

// `breakdown` appends the verification report (audit, proof state, session,
// source listing) to the typeset proof; `session` carries the timeline and
// snapshots, which only the browser knows about.
export async function exportLatex({ source, standalone = true, strictDomains = false, breakdown = true, session = null, signal }) {
  const response = await fetch("/api/export/latex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, standalone, strict_domains: strictDomains, breakdown, session }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export async function exportPdf({ source, strictDomains = false, breakdown = true, session = null, signal }) {
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
