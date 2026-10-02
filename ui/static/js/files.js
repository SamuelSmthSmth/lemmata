// Getting proofs in and out of the browser: download, clipboard, drag-and-drop.

const MAX_BYTES = 2 * 1024 * 1024;

export const ACCEPTED_EXTENSIONS = /\.(aether|txt|md|proof)$/i;

/** Turn a theorem name into a safe, readable filename. */
export function proofFilename(name) {
  const slug = String(name ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "aether-proof"}.aether`;
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  // Give the browser a tick to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadText(text, filename) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  downloadBlob(blob, filename);
}


export function texFilename(name) {
  const slug = String(name ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "aether-proof"}.tex`;
}

export function pdfFilename(name) {
  const slug = String(name ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "aether-proof"}.pdf`;
}


export async function readTextFile(file) {
  if (file.size > MAX_BYTES) throw new Error(`${file.name} is larger than 2 MB`);
  return await file.text();
}

/**
 * Copy to the clipboard, falling back to a hidden textarea.
 *
 * navigator.clipboard is unavailable on insecure origins (plain http:// on a
 * non-localhost host is a realistic way to run this), and there it fails rather
 * than throwing loudly, so the fallback matters.
 */
export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    // Fall through to the legacy path.
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch (error) {
    return false;
  }
}

/**
 * Accept dropped proof files anywhere on the page.
 *
 * Listening on window rather than the editor keeps the whole surface a drop
 * target, and the dragenter/dragleave depth counter stops a drag passing over
 * child elements from flickering the overlay off.
 */
export function setupDropZone({ onFiles, onDragState }) {
  let depth = 0;
  const carriesFiles = (event) => Array.from(event.dataTransfer?.types ?? []).includes("Files");

  window.addEventListener("dragenter", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    depth += 1;
    onDragState(true);
  });

  window.addEventListener("dragover", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });

  window.addEventListener("dragleave", (event) => {
    if (!carriesFiles(event)) return;
    depth -= 1;
    if (depth <= 0) {
      depth = 0;
      onDragState(false);
    }
  });

  window.addEventListener("drop", (event) => {
    if (!carriesFiles(event)) return;
    // Without preventDefault the browser navigates away and opens the file.
    event.preventDefault();
    depth = 0;
    onDragState(false);
    const files = [...(event.dataTransfer?.files ?? [])];
    if (files.length) onFiles(files);
  });
}
