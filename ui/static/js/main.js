// Entry point: wire the modules together and boot.
//
// The editor is created here rather than inside editor.js so that its
// callbacks can reach the auditor without the two modules importing each
// other.  Everything that needs the editor, the auditor and the workspace at
// once lives here; the individual panes stay independent.

// Side-effect import: defines every <wa-*> custom element. Imported first so
// nothing below can touch an element that has not been upgraded yet.
import "./components.js";
import { checkProof, exportLatex, exportPdf, fetchExamples } from "./api.js";
import { initAuditNav, selectStepForLine } from "./audit.js";
import { renderContext } from "./context.js";
import { dom } from "./dom.js";
import { createEditor, currentSyntax, currentTheme } from "./editor.js";
// Side-effect import: reads the stored panel arrangement and applies it during
// module evaluation, which is still before the first paint.
import "./layout.js";
import {
  ACCEPTED_EXTENSIONS,
  copyText,
  downloadBlob,
  downloadText,
  pdfFilename,
  proofFilename,
  readTextFile,
  setupDropZone,
  texFilename,
} from "./files.js";
import { el } from "./format.js";
import { initHistory, renderHistory, setHistoryOpen } from "./history.js";
import { permalinkFor, readPermalink, writePermalink } from "./permalink.js";
import { applyResponse } from "./render.js";
import { examplesById, state } from "./state.js";
import { addSnapshot, persistWorkspace, recordOutcome, timeline, workspace } from "./store.js";
import { showToast } from "./toast.js";
import { markStale, setPending } from "./verdict.js";

const DEBOUNCE_MS = 300;
// Longer than the check debounce: saving is a side effect, not feedback, so it
// should not race the verification the user is actually watching.
const SAVE_DEBOUNCE_MS = 500;
const THEME_STORAGE_KEY = "aether-theme";
const SYNTAX_STORAGE_KEY = "aether-syntax";
const DEFAULT_EXAMPLE_ID = "even-square";

// Storage warnings are one-shot; repeating them on every keystroke would be
// noise once the user has seen the first one.
let warnedAboutStorage = false;

const currentSource = () => editor.getSource();

// ---------------------------------------------------------------------------
// Workspace persistence
// ---------------------------------------------------------------------------

function scheduleSave() {
  window.clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(saveWorkspace, SAVE_DEBOUNCE_MS);
}

function saveWorkspace() {
  workspace.source = currentSource();
  workspace.strict = dom.strict.checked;
  workspace.exampleId = state.exampleId;
  workspace.saved = true;

  if (!persistWorkspace() && !warnedAboutStorage) {
    warnedAboutStorage = true;
    showToast(
      "This browser refused to store your work (private mode, or storage is full). The proof will not survive a reload — use Download to keep it.",
      { tone: "danger", ms: 8000 },
    );
  }

  writePermalink(workspace.source, workspace.strict);
}

/** Snapshot the buffer before an action is allowed to replace it. */
function snapshotBefore(name) {
  const source = currentSource();
  if (!source.trim()) return;
  addSnapshot({ name, source, strict: dom.strict.checked, auto: true });
}

// ---------------------------------------------------------------------------
// Verification round-trips
// ---------------------------------------------------------------------------

function scheduleCheck() {
  // The pill would otherwise keep advertising a verdict that belongs to the
  // previous buffer for the whole debounce window.
  markStale();
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(runCheck, DEBOUNCE_MS);
}

async function runCheck() {
  window.clearTimeout(state.timer);
  state.timer = null;

  const seq = ++state.seq;
  if (state.controller) state.controller.abort();
  const controller = new AbortController();
  state.controller = controller;

  setPending();

  try {
    const data = await checkProof({
      source: currentSource(),
      strictDomains: dom.strict.checked,
      signal: controller.signal,
    });
    if (seq !== state.seq) return; // superseded by a newer request
    applyResponse(data);
    recordOutcome({
      verdict: data.verdict,
      invalid: data.summary.invalid,
      warnings: data.summary.warnings,
    });
    renderHistory(historyHandlers);
  } catch (error) {
    if (error.name === "AbortError" || seq !== state.seq) return;
    dom.verdict.className = "verdict verdict--invalid";
    dom.verdict.textContent = "Unreachable";
    dom.verdictMeta.textContent = error.message;
    dom.audit.replaceChildren(
      el("p", "empty-state", `Could not reach the Aether backend: ${error.message}`),
    );
  }
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

const editor = createEditor({
  parent: document.getElementById("editor"),
  onDocChanged: () => {
    scheduleCheck();
    scheduleSave();
  },
  onSelectionMoved: selectStepForLine,
});

// ---------------------------------------------------------------------------
// Examples
// ---------------------------------------------------------------------------

function showBlurb(example) {
  dom.blurb.replaceChildren(
    el("strong", null, `${example.name}. `),
    document.createTextNode(`${example.blurb} Expected: ${example.expected}.`),
  );
  dom.blurb.hidden = false;
}

async function loadExamples() {
  try {
    const examples = await fetchExamples();
    for (const example of examples) {
      examplesById.set(example.id, example);
      const option = document.createElement("wa-option");
      option.value = example.id;
      option.textContent = example.name;
      dom.examples.append(option);
    }
    return examples;
  } catch (error) {
    console.warn("Could not load examples:", error);
    return [];
  }
}

/** Replace the buffer with the given text, leaving no trace of the old one. */
function setBuffer(text, { exampleId = null } = {}) {
  editor.setContent(text);
  state.exampleId = exampleId;
  if (!exampleId) dom.blurb.hidden = true;
}

function openExample(example) {
  setBuffer(example.source, { exampleId: example.id });
  showBlurb(example);
}

dom.examples.addEventListener("change", async () => {
  const example = examplesById.get(dom.examples.value);
  dom.examples.value = ""; // behaves as an action menu, so it can be re-picked
  if (!example) return;
  snapshotBefore(`Before opening “${example.name}”`);
  openExample(example);
  saveWorkspace();
  await runCheck(); // act immediately rather than waiting out the debounce
});

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

dom.downloadProof.addEventListener("click", () => {
  const name = state.data?.reports?.[0]?.theorem_name;
  const filename = proofFilename(name);
  downloadText(currentSource(), filename);
  showToast(`Downloaded ${filename}`);
});

setupDropZone({
  onDragState: (active) => {
    dom.dropOverlay.hidden = !active;
  },
  onFile: async (file) => {
    if (!ACCEPTED_EXTENSIONS.test(file.name)) {
      showToast(`“${file.name}” is not a proof file (.aether, .txt, .md)`, { tone: "warning" });
      return;
    }
    try {
      const text = await readTextFile(file);
      snapshotBefore(`Before opening “${file.name}”`);
      setBuffer(text);
      saveWorkspace();
      await runCheck();
      showToast(`Opened ${file.name}`);
    } catch (error) {
      showToast(`Could not open ${file.name}: ${error.message}`, { tone: "danger" });
    }
  },
});

// ---------------------------------------------------------------------------
// LaTeX & PDF Export
// ---------------------------------------------------------------------------

let latexAbortController = null;

/**
 * The workspace panel's timeline and snapshots, for the exported report.
 *
 * The server cannot see either one -- they live in localStorage -- so they are
 * sent along. Only the fields the report renders are included, which keeps the
 * request small and the document's surface predictable.
 */
function exportSession() {
  return {
    timeline: timeline.entries.map(({ verdict, n, ts }) => ({ verdict, n, ts })),
    snapshots: workspace.snapshots.map(({ name, ts, strict, auto }) => ({
      name,
      ts,
      strict: Boolean(strict),
      auto: Boolean(auto),
    })),
  };
}

function exportOptions() {
  return {
    source: currentSource(),
    standalone: dom.latexStandalone.checked,
    breakdown: dom.latexBreakdown.checked,
    strictDomains: dom.strict.checked,
    session: exportSession(),
  };
}

async function refreshLatexExport() {
  if (!dom.latexDialog.open) return;
  if (latexAbortController) latexAbortController.abort();
  latexAbortController = new AbortController();

  dom.latexOutput.value = "% Generating LaTeX...";
  try {
    const data = await exportLatex({
      ...exportOptions(),
      signal: latexAbortController.signal,
    });
    dom.latexOutput.value = data.latex;
  } catch (error) {
    if (error.name === "AbortError") return;
    dom.latexOutput.value = `% Error generating LaTeX: ${error.message}`;
  }
}

function openLatexDialog() {
  dom.latexDialog.open = true;
  refreshLatexExport();
}

dom.exportLatex.addEventListener("click", openLatexDialog);

// <wa-dialog light-dismiss> owns the close button, the backdrop and Escape, so
// there is nothing to wire up for dismissing it. The one thing it cannot know
// is that a LaTeX export may still be in flight, so abandon that once it hides.
dom.latexDialog.addEventListener("wa-after-hide", () => {
  if (latexAbortController) {
    latexAbortController.abort();
    latexAbortController = null;
  }
});

dom.latexStandalone.addEventListener("change", refreshLatexExport);
dom.latexBreakdown.addEventListener("change", refreshLatexExport);

dom.copyLatex.addEventListener("click", async () => {
  const text = dom.latexOutput.value;
  if (!text) return;
  const ok = await copyText(text);
  showToast(ok ? "LaTeX copied to clipboard" : "Could not copy to clipboard", {
    tone: ok ? "info" : "warning",
  });
});

dom.downloadTex.addEventListener("click", () => {
  const text = dom.latexOutput.value;
  if (!text) return;
  const name = state.data?.reports?.[0]?.theorem_name;
  const filename = texFilename(name);
  downloadText(text, filename);
  showToast(`Downloaded ${filename}`);
});

dom.downloadPdf.addEventListener("click", async () => {
  const originalText = dom.downloadPdf.textContent;
  dom.downloadPdf.disabled = true;
  dom.downloadPdf.textContent = "Compiling PDF...";

  try {
    const blob = await exportPdf(exportOptions());
    const name = state.data?.reports?.[0]?.theorem_name;
    const filename = pdfFilename(name);
    downloadBlob(blob, filename);
    showToast(`Downloaded ${filename}`);
  } catch (error) {
    showToast(`PDF generation failed: ${error.message}`, { tone: "danger" });
  } finally {
    dom.downloadPdf.disabled = false;
    dom.downloadPdf.textContent = originalText;
  }
});

// ---------------------------------------------------------------------------
// Workspace panel actions
// ---------------------------------------------------------------------------

function stamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const historyHandlers = {
  onSnapshot() {
    if (!currentSource().trim()) {
      showToast("There is nothing to snapshot yet.", { tone: "warning" });
      return;
    }
    addSnapshot({ name: `Snapshot ${stamp()}`, source: currentSource(), strict: dom.strict.checked });
    showToast("Snapshot saved");
  },

  onRestore(snapshot) {
    snapshotBefore(`Before restoring “${snapshot.name}”`);
    setBuffer(snapshot.source);
    dom.strict.checked = snapshot.strict;
    saveWorkspace();
    runCheck();
    showToast("Snapshot restored");
  },

  onReset() {
    snapshotBefore("Before reset");
    const example = examplesById.get(DEFAULT_EXAMPLE_ID) ?? examplesById.values().next().value;
    if (example) openExample(example);
    else setBuffer("");
    saveWorkspace();
    runCheck();
    showToast("Reset to the starting example");
  },

  async onCopyLink() {
    // Flush first, so the fragment in the address bar is the current proof.
    saveWorkspace();
    const url = permalinkFor(workspace.source, workspace.strict);
    const ok = await copyText(url);
    showToast(
      ok
        ? "Link copied — it reproduces this exact proof"
        : "Could not reach the clipboard; copy the address bar instead",
      { tone: ok ? "info" : "warning" },
    );
  },

  onCleared() {
    showToast("Cleared saved snapshots and history (your proof is untouched)");
  },
};

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

function applyTheme(name, { persist = false } = {}) {
  document.documentElement.dataset.theme = name;
  editor.setTheme(name);
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, name);
    } catch (error) {
      // Storage can be unavailable; the choice simply will not persist.
    }
  }
}

dom.themeToggle.addEventListener("click", () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark", { persist: true });
});

// ---------------------------------------------------------------------------
// Syntax colours
//
// Two schemes, and only the editor is affected: the auditor and the source
// listing colour-code by status, which is a different job from tokenising.
// The colours themselves are CSS (--cm-token-* under [data-syntax]); this only
// flips the attribute and asks the editor to rebuild its highlight style.
// ---------------------------------------------------------------------------

function applySyntax(name, { persist = false } = {}) {
  document.documentElement.dataset.syntax = name;
  dom.syntaxToggle.setAttribute("aria-pressed", String(name === "vivid"));
  editor.setSyntax();
  if (persist) {
    try {
      localStorage.setItem(SYNTAX_STORAGE_KEY, name);
    } catch (error) {
      // Storage can be unavailable; the choice simply will not persist.
    }
  }
}

dom.syntaxToggle.addEventListener("click", () => {
  applySyntax(currentSyntax() === "vivid" ? "mono" : "vivid", { persist: true });
});

dom.strict.addEventListener("change", () => {
  runCheck();
  saveWorkspace();
});

// A reload or a backgrounded tab must not lose the last few hundred ms of
// typing that the debounce has not written out yet.
window.addEventListener("beforeunload", saveWorkspace);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") saveWorkspace();
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function init() {
  // index.html resolved both before first paint so they apply during
  // evaluation; this only brings the controls and the editor in step.
  applySyntax(currentSyntax());
  initAuditNav();
  initHistory(historyHandlers);
  setHistoryOpen(false);

  const examples = await loadExamples();

  // A link wins over saved work: the fragment is what the person clicking it
  // meant to see, and it is kept in sync with the buffer from then on.
  const shared = readPermalink();
  let origin = "default";

  if (shared) {
    setBuffer(shared.source);
    dom.strict.checked = shared.strict;
    origin = "link";
  } else if (workspace.saved) {
    setBuffer(workspace.source);
    dom.strict.checked = workspace.strict;
    origin = "restored";
    const previous = workspace.exampleId ? examplesById.get(workspace.exampleId) : null;
    if (previous && previous.source.trim() === workspace.source.trim()) showBlurb(previous);
  }

  if (origin === "default") {
    const example = examplesById.get(DEFAULT_EXAMPLE_ID) ?? examples[0];
    if (example) openExample(example);
  }

  renderHistory(historyHandlers);
  renderContext();
  saveWorkspace();
  await runCheck();

  if (origin === "link") showToast("Loaded the proof from this link");
  else if (origin === "restored") showToast("Restored your last session");
}

init();
