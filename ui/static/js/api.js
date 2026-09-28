// Thin wrappers over the backend endpoints.
//
// Nothing here touches the DOM or the editor, so it is safe to import from
// anywhere (and easy to stub).

export async function fetchExamples() {
  const response = await fetch("/api/examples");
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export async function checkProof({ source, strictDomains, signal }) {
  const response = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, strict_domains: strictDomains }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export async function exportLatex({ source, standalone = true, signal }) {
  const response = await fetch("/api/export/latex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, standalone }),
    signal,
  });
  if (!response.ok) throw new Error(`server returned ${response.status}`);
  return response.json();
}

export async function exportPdf({ source, signal }) {
  const response = await fetch("/api/export/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
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
