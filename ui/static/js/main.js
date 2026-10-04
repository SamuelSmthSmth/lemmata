// Entry point: wire the views to the workspace and the checker, and boot.
//
// Modules own their own piece of screen (explorer, tabs, auditor, notes,
// library, guide, settings, palette) and are handed callbacks; this file is
// where those callbacks meet the editor, the workspace model and the server.

// Side-effect import: defines every <wa-*> custom element. Imported first so
// nothing below can touch an element that has not been upgraded yet.
import "./components.js";
import { canExportPdf, checkProof, exportLatex, exportLean, exportPdf, fetchLibrary, validatePack } from "./api.js";
import { leanEditorUrl, leanFilename, renderLeanMessage, renderLeanRows, untranslatedNote } from "./lean.js";
import { onEngineStatus, warmUp } from "./backend.js";
import { initAuditNav, selectStepForLine } from "./audit.js";
import { insertSymbol, insertTemplate, setCitationSource, setScopeSource, SYMBOLS, TEMPLATES } from "./complete.js";
import { renderContext, setContextHandlers } from "./context.js";
import { applyFix } from "./fixes.js";
import * as db from "./db.js";
import { dom } from "./dom.js";
import { createEditor, currentSyntax, currentTheme } from "./editor.js";
import { initExplorer, renderExplorer, revealFile } from "./explorer.js";
import { ACCEPTED_EXTENSIONS, copyText, downloadBlob, downloadText, pdfFilename, readTextFile, setupDropZone, texFilename } from "./files.js";
import { el } from "./format.js";
import { currentGuidePage, GUIDE_PAGES, guideNode, initGuide, openGuidePage } from "./guide.js";
import { initHistory, renderHistory } from "./history.js";
// Side-effect import: reads the stored panel arrangement and applies it during
// module evaluation, which is still before the first paint.
import { layoutApi } from "./layout.js";
import { entryKey, findEntry, initLibrary, libraryPacks, renderLibrary, showEntry, showPack } from "./library.js";
import { setLintFixHandler, showDiagnostics } from "./lint.js";
import { initNotes, renderNotes } from "./notes.js";
import { allManifests, initPackAuthor, isPackFolder, openPackDialog, renameManifestFolder, restoreManifests } from "./pack-author.js";
import * as packs from "./packs.js";
import * as registry from "./registry.js";
import { initPalette, openPalette } from "./palette.js";
import { permalinkFor, readPermalink, writePermalink } from "./permalink.js";
import { getPref, setPref } from "./prefs.js";
import { applyResponse } from "./render.js";
import { initSettings, renderSettings } from "./settings.js";
import { holder, kept, loadSite, site } from "./site.js";
import { state } from "./state.js";
import { initTabs, renderTabs } from "./tabs.js";
import { showToast } from "./toast.js";
import { markStale, setEngineLoading, setPending } from "./verdict.js";
import * as ws from "./workspace.js";
import { readZip, writeZip } from "./zip.js";

const SAVE_DEBOUNCE_MS = 400;
const STARTING_ENTRY = "core/examples/even-square";

// fileId -> "valid" | "warning" | "invalid": the last verdict of every file
// checked this session, shown in the tabs and the explorer.
const verdicts = new Map();
// fileId -> the last check response, so switching back to a tab is instant.
const lastResponse = new Map();

let pinnedGuide = null; // guide page id pinned beside the proof
let warnedAboutStorage = false;

const editor = createEditor({
  parent: dom.editor,
  wrap: getPref("wrap") === "on",
  visual: getPref("visual") === "on",
  onDocChanged: () => {
    scheduleCheck();
    scheduleSave();
  },
  onSelectionMoved: selectStepForLine,
  onCaret: ({ line, col }) => {
    dom.statusPos.textContent = `Ln ${line}, Col ${col}`;
  },
});

// Completion offers the variables the last check saw in scope at the caret.
setCitationSource(() => packs.citationIndex(packs.installedPacks(), ws.sourcesByPath()));

// Context & state's buttons: a hint's fix goes through the editor (so Ctrl+Z
// takes it back, and the check that follows says whether it worked); a cited
// result opens where it lives, a pack's entry in the Library or a workspace file.
function useFix(fix) {
  if (!applyFix(editor.view, fix)) showToast("The proof has changed since it was checked, so that fix no longer applies.", { tone: "warning" });
}
setLintFixHandler((_view, fix) => useFix(fix));
setContextHandlers({
  onFix: useFix,
  async onOpenCited(citation) {
    const match = /^@([^/]+\/[^/]+)\/(.+)\.aether$/.exec(citation.key);
    if (match) {
      setView("library");
      showEntry(match[1], match[2]);
      return;
    }
    const file = ws.filesSorted().find((f) => f.path === citation.key);
    if (file) {
      setView("workspace");
      await activate(file.id);
    }
  },
});
setScopeSource((lineNumber) => {
  let best = null;
  for (const entry of state.steps) {
    if (entry.result.line != null && entry.result.line <= lineNumber) best = entry.result;
  }
  return best?.active_variables ?? {};
});

const currentSource = () => editor.getSource();
const active = () => ws.activeFile();

function toneOf(data) {
  if (!data) return null;
  if (data.verdict === "VALID") return "valid";
  if (data.verdict === "VALID (with domain warnings)" || data.verdict === "TIMEOUT") return "warning";
  return "invalid";
}

// ---------------------------------------------------------------------------
// Saving
// ---------------------------------------------------------------------------

function scheduleSave() {
  window.clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(saveActive, SAVE_DEBOUNCE_MS);
}

async function saveActive() {
  window.clearTimeout(state.saveTimer);
  const file = active();
  if (!file) return;
  const source = currentSource();
  const strict = dom.strict.checked;
  if (file.source !== source || file.strict !== strict) {
    try {
      await ws.updateFile(file.id, { source, strict });
    } catch (error) {
      if (!warnedAboutStorage) {
        warnedAboutStorage = true;
        showToast(`${holder[0].toUpperCase()}${holder.slice(1)} refused to store your work. Export the workspace to keep it.`, { tone: "danger", ms: 8000 });
      }
    }
  }
  writePermalink(source, strict);
}

/** Snapshot the active proof before an action is allowed to replace it. */
async function snapshotBefore(name) {
  const file = active();
  if (!file) return;
  await saveActive();
  await ws.addSnapshot(file.id, { name, auto: true });
}

// ---------------------------------------------------------------------------
// Checking
// ---------------------------------------------------------------------------

function exerciseHidden(file = active()) {
  return Boolean(file?.exercise && !file.exercise.revealed);
}

function scheduleCheck() {
  // The verdict would otherwise keep describing the previous buffer for the
  // whole debounce window.
  markStale();
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(runCheck, Number(getPref("debounce")));
}

/** What `import` may resolve against: the workspace, and installed packs when asked for. */
function importableFiles(path, source) {
  const files = { ...ws.sourcesByPath(), [path]: source };
  if (Object.values(files).some(packs.importsFromPacks)) Object.assign(files, packs.importSources(packs.installedPacks()));
  return files;
}

/**
 * What the engine needs beside the source: the workspace, only when this proof
 * imports from it, and the installed packs and the names they answer to when
 * it may cite a result.
 */
function engineContext(file, source) {
  let files = ws.hasImports(source) ? importableFiles(file.path, source) : null;
  let citations = null;
  if (packs.mayCite(source)) {
    const workspace = { ...ws.sourcesByPath(), [file.path]: source };
    files = { ...workspace, ...packs.importSources(packs.installedPacks()), ...(files ?? {}) };
    citations = packs.citationIndex(packs.installedPacks(), workspace);
  }
  return { files, citations };
}

async function runCheck() {
  window.clearTimeout(state.timer);
  state.timer = null;
  const file = active();
  if (!file) return;

  const seq = ++state.seq;
  if (state.controller) state.controller.abort();
  const controller = new AbortController();
  state.controller = controller;
  setPending();

  const source = currentSource();
  try {
    const { files, citations } = engineContext(file, source);
    const data = await checkProof({
      source,
      strictDomains: dom.strict.checked,
      files,
      path: file.path,
      citations,
      signal: controller.signal,
    });
    if (seq !== state.seq) return; // superseded by a newer request
    lastResponse.set(file.id, data);
    showResponse(file, data);
    ws.recordOutcome({ verdict: data.verdict, invalid: data.summary.invalid, warnings: data.summary.warnings, fileId: file.id });
    renderHistory();
  } catch (error) {
    if (error.name === "AbortError" || seq !== state.seq) return;
    dom.verdict.className = "verdict verdict--invalid";
    dom.verdict.textContent = "Unreachable";
    dom.verdictMeta.textContent = error.message;
    dom.audit.replaceChildren(el("p", "empty-state", `Could not reach the ${site.name} server: ${error.message}. Your work is still saved in this browser.`));
  }
}

function firstProblem(data) {
  const problems = [];
  for (const report of data.reports ?? []) {
    for (const r of report.results) if (r.status !== "VALID" && r.line != null) problems.push(r);
  }
  if (data.parse_error?.line != null) problems.push({ line: data.parse_error.line, status: "INVALID" });
  return problems;
}

function showResponse(file, data) {
  const hidden = exerciseHidden(file);
  document.body.dataset.exercise = hidden ? "hidden" : file.exercise ? "revealed" : "none";
  applyResponse(data);
  showDiagnostics(editor.view, hidden ? null : data);

  const tone = toneOf(data);
  if (verdicts.get(file.id) !== tone) {
    verdicts.set(file.id, tone);
    renderTabs();
    renderExplorer();
  }

  const problems = firstProblem(data);
  if (hidden) {
    dom.verdict.className = "verdict verdict--exercise";
    dom.verdict.textContent = "Exercise";
    dom.verdictMeta.textContent = "find the step that fails";
    dom.statusProblem.hidden = true;
  } else if (problems.length) {
    dom.statusProblem.hidden = false;
    dom.statusProblem.textContent = `${problems.length} problem${problems.length === 1 ? "" : "s"} · first on line ${problems[0].line}`;
    dom.statusProblem.onclick = () => editor.goToLine(problems[0].line);
  } else {
    dom.statusProblem.hidden = true;
  }
  if (file.exercise && !file.exercise.revealed) {
    // Remember the answer for the reveal, without showing it.
    const answer = problems.find((p) => p.status === "INVALID")?.line ?? null;
    if (file.exercise.answer !== answer) ws.updateFile(file.id, { exercise: { ...file.exercise, answer } });
  }
}

// ---------------------------------------------------------------------------
// The active file
// ---------------------------------------------------------------------------

async function showActive({ check = true } = {}) {
  const file = active();
  renderTabs();
  if (file) revealFile(file.id);
  renderExplorer();
  dom.welcome.hidden = Boolean(file);
  dom.editor.hidden = !file;
  if (!file) {
    renderWelcome();
    editor.setContent("");
    dom.editorPath.textContent = "";
    dom.statusFile.textContent = "";
    dom.verdict.className = "verdict verdict--idle";
    dom.verdict.textContent = "Ready";
    dom.verdictMeta.textContent = "";
    dom.audit.replaceChildren(el("p", "empty-state", "Open a proof to see its audit here."));
    state.steps = [];
    state.data = null;
    renderContext();
    renderNotesPanel();
    return;
  }
  if (editor.getSource() !== file.source) editor.setContent(file.source);
  dom.strict.checked = file.strict;
  dom.editorPath.textContent = file.path;
  dom.statusFile.textContent = file.path;
  writePermalink(file.source, file.strict);
  renderNotesPanel();
  renderHistory();
  const cached = lastResponse.get(file.id);
  if (cached) showResponse(file, cached);
  if (check) await runCheck();
}

async function activate(id) {
  if (id === ws.model.activeId) return;
  await saveActive();
  ws.openFile(id);
  await showActive();
}

// ---------------------------------------------------------------------------
// Notes (the reading pane's middle tab)
// ---------------------------------------------------------------------------

async function renderNotesPanel() {
  const file = active();
  const found = file?.origin ? findEntry(file.origin) : null;
  const pinned = pinnedGuide ? await guideNode(pinnedGuide) : null;
  renderNotes({ found, file, pinned });
  if (!getPref("welcomed") || getPref("welcomed") === "no") prependWelcomeCard();
}

function prependWelcomeCard() {
  const card = el("section", "welcome-card");
  card.append(el("h2", null, `Welcome to ${site.name}`));
  card.append(el("p", null, "A proof checker that reads the notation in your notes. A short tour of the desk:"));
  const steps = [
    ["Write the proof here.", ".pane--editor"],
    ["Every statement is audited here; a failing step gets a red rule in the margin.", ".pane--audit"],
    ["Click any line to see what is known at that point.", ".pane--context"],
    ["The verdict for the whole proof lives in the status bar.", ".statusbar"],
    ["Course packs and examples are in the Library.", '.rail-button[data-view="library"]'],
  ];
  const list = el("ol", "welcome-steps");
  for (const [text, selector] of steps) {
    const item = el("li", null, text);
    item.tabIndex = 0;
    const on = () => document.querySelector(selector)?.setAttribute("data-tour", "on");
    const off = () => document.querySelector(selector)?.removeAttribute("data-tour");
    item.addEventListener("mouseenter", on);
    item.addEventListener("mouseleave", off);
    item.addEventListener("focus", on);
    item.addEventListener("blur", off);
    list.append(item);
  }
  card.append(list);
  // The storage notice, said once: there is nothing to consent to.
  const storage = el("p", "welcome-storage", `No cookies, no tracking: your work is kept ${kept}. `);
  const how = el("a", null, "How storage works");
  how.href = "https://lemmata.sous.systems/cookies/";
  how.target = "_blank";
  how.rel = "noopener";
  storage.append(how);
  card.append(storage);
  const done = el("button", "text-button text-button--primary", "Got it");
  done.type = "button";
  done.addEventListener("click", () => {
    setPref("welcomed", "yes");
    for (const node of document.querySelectorAll("[data-tour]")) node.removeAttribute("data-tour");
    card.remove();
  });
  card.append(done);
  dom.notes.prepend(card);
}

function renderWelcome() {
  dom.welcome.replaceChildren();
  const box = el("div", "welcome-box");
  box.append(el("h2", null, "No proof open"));
  box.append(el("p", null, "Start a new proof, open one from the Library, or pick up where you left off in Files."));
  const actions = el("div", "welcome-actions");
  const make = (label, fn, primary = false) => {
    const b = el("button", `text-button${primary ? " text-button--primary" : ""}`, label);
    b.type = "button";
    b.addEventListener("click", fn);
    actions.append(b);
  };
  make("New proof", () => newProof(), true);
  make("Open the Library", () => setView("library"));
  make("Read the Guide", () => setView("guide"));
  box.append(actions);
  dom.welcome.append(box);
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

function strictDefault() {
  return getPref("strictDefault") === "on";
}

async function newProof({ path = null, source = null, origin = null, exercise = null, open = true } = {}) {
  await saveActive();
  const folder = active() ? ws.dirname(active().path) : "";
  const finalPath = path ?? ws.freePath("Untitled", folder);
  const text = source ?? 'Theorem: "Untitled"\nProof:\n    \nQED\n';
  const file = await ws.createFile({ path: finalPath, source: text, strict: strictDefault(), open });
  // `initial` is what "Reset to its start" goes back to.
  await ws.updateFile(file.id, { initial: text, ...(origin ? { origin } : {}), ...(exercise ? { exercise } : {}) });
  setView("workspace");
  await showActive();
  if (!source) editor.goToLine(3);
  return file;
}

function safeName(text) {
  return text.replace(/[<>:"|?*\\/]/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
}

async function openLibraryEntry(pack, entry, { exercise = false, fresh = false } = {}) {
  const key = entryKey(pack.name, entry.id);
  if (!fresh) {
    const existing = [...ws.model.files.values()].find((f) => f.origin === key);
    if (existing) {
      setView("workspace");
      await activate(existing.id);
      showDesk("notes");
      return existing;
    }
  }
  const examples = pack.name === "core/examples";
  const folder = examples ? "Examples" : safeName(packs.packLabel(pack));
  const stem = examples ? entry.title : `${entry.ref} ${entry.title}`;
  let path = `${folder}/${safeName(stem)}.aether`;
  if (ws.pathProblem(path)) path = ws.freePath(safeName(stem), folder);
  const file = await newProof({
    path,
    source: entry.source,
    origin: key,
    exercise: exercise && entry.kind === "trap" ? { revealed: false, guess: null, answer: null } : null,
  });
  showDesk("notes");
  return file;
}

// ---------------------------------------------------------------------------
// Packs: install, uninstall, update, export, and importing from them
// ---------------------------------------------------------------------------

function refreshPacks() {
  renderLibrary();
  renderNotesPanel();
}

/** Install a pack, offering to undo; an install over an older copy reports what changed. */
async function installPack(pack, origin) {
  const before = packs.installedRecords().find((r) => r.name === pack.name)?.pack ?? null;
  const previous = await packs.install(pack, origin);
  showPack(pack.name);
  refreshPacks();
  const what = before ? packs.describeDiff(packs.diffPacks(before, pack)) : null;
  const label = packs.packLabel(pack);
  const text = previous
    ? `Updated ${label} to v${pack.version}${what ? ` — ${what}` : ""}`
    : `Installed ${label} (${pack.entries.length} ${pack.entries.length === 1 ? "entry" : "entries"})`;
  showToast(text, {
    action: "Undo",
    onAction: async () => {
      if (previous) await packs.restore(previous);
      else await packs.uninstall(pack.name);
      refreshPacks();
    },
  });
}

async function uninstallPack(pack) {
  const previous = await packs.uninstall(pack.name);
  if (!previous) return;
  refreshPacks();
  showToast(`Uninstalled ${packs.packLabel(pack)}. Your copies of its proofs are still in your workspace.`, {
    action: "Undo",
    onAction: async () => {
      await packs.restore(previous);
      showPack(pack.name);
      refreshPacks();
    },
  });
}

async function updateAllPacks() {
  const pending = packs.updates();
  let done = 0;
  for (const { pack } of pending) {
    try {
      if (pack.remote) await packs.install(await registryPack(pack), "registry");
      else await packs.install(pack, "bundled");
      done += 1;
    } catch (error) {
      showToast(`${packs.packLabel(pack)} was not updated: ${error.message}`, { tone: "danger", ms: 8000 });
    }
  }
  refreshPacks();
  if (done) showToast(done === 1 ? `Updated ${packs.packLabel(pending[0].pack)}` : `Updated ${done} packs`);
}

// ---------------------------------------------------------------------------
// The pack registry
// ---------------------------------------------------------------------------

/** Re-read the registry's index (if stale), then let the Library show what it offers. */
async function refreshRegistry({ force = false } = {}) {
  await registry.refresh(site.registry, { force });
  packs.model.registry = registry.offered(registry.model.stubs, packs.model.catalog);
  if (document.body.dataset.view === "library") renderLibrary();
}

/** A registry pack's file: fetched, checked against the index's sha256, validated. */
async function registryPack(stub) {
  const data = await registry.fetchPack(stub);
  const { pack, errors } = await validatePack(data);
  if (!pack) throw new Error(`it is not a valid pack (${errors[0]})`);
  if (pack.name !== stub.name || pack.version !== stub.version) throw new Error("the file is not the pack the registry lists");
  return pack;
}

async function installFromRegistry(stub) {
  try {
    await installPack(await registryPack(stub), "registry");
  } catch (error) {
    showToast(`${packs.packLabel(stub)} was not installed: ${error.message}`, { tone: "danger", ms: 8000 });
  }
}

async function previewRegistryPack(stub) {
  try {
    registry.model.previews.set(`${stub.name}@${stub.version}`, await registryPack(stub));
    renderLibrary();
  } catch (error) {
    showToast(`Could not preview ${packs.packLabel(stub)}: ${error.message}`, { tone: "danger", ms: 8000 });
  }
}

/**
 * `?install=<scope/name>`: the registry site's "Open in Lemmata" link.  Opens
 * the Library on that pack: an installed one as it is, a registry one previewed
 * with its Install button, so nothing is installed without the student's click.
 */
async function openPackLink(name) {
  const params = new URLSearchParams(location.search);
  params.delete("install");
  params.set("view", "library");
  history.replaceState({ view: "library" }, "", `${location.pathname}?${params}${location.hash}`);
  setView("library", { push: false });
  if (!packs.model.records.has(name)) await refreshRegistry();
  const pack = packs.findPack(name);
  if (!pack) {
    showToast(`There is no pack called ${name} in the registry.`, { tone: "danger", ms: 8000 });
    return;
  }
  showPack(name);
  const stub = registry.findStub(name);
  if (!packs.model.records.has(name) && stub) await previewRegistryPack(stub);
}

function exportPack(pack) {
  const { filename, text } = packs.packToFile(pack);
  downloadBlob(new Blob([text], { type: "application/json" }), filename);
  showToast(`Saved ${filename}`);
}

/** Read .pack.json files, have the server validate them, and install the good ones. */
async function installPackFiles(fileList) {
  for (const file of fileList) {
    try {
      const data = packs.parsePackFile(await readTextFile(file));
      const { pack, errors } = await validatePack(data);
      if (!pack) {
        const more = errors.length > 1 ? ` (and ${errors.length - 1} more)` : "";
        showToast(`${file.name} is not a pack: ${errors[0]}${more}`, { tone: "danger", ms: 8000 });
        continue;
      }
      await installPack(pack, "file");
    } catch (error) {
      showToast(`Could not install ${file.name}: ${error.message}`, { tone: "danger" });
    }
  }
}

function choosePackFile() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.multiple = true;
  input.addEventListener("change", () => {
    if (input.files?.length) installPackFiles([...input.files]);
  });
  input.click();
}

/** Put `import "@pack/entry"` at the top of the proof in front of the student. */
async function useInProof(pack, entry) {
  const line = packs.importLine(pack.name, entry.id);
  let file = active();
  if (!file) file = await newProof({ source: `${line}\n\n` });
  else {
    await saveActive();
    const source = currentSource();
    if (!source.includes(line)) {
      const lines = source.split("\n");
      let at = 0;
      while (at < lines.length && /^\s*import\s+"/.test(lines[at])) at++;
      lines.splice(at, 0, line);
      editor.setContent(lines.join("\n"));
      await saveActive();
    }
  }
  setView("workspace");
  await showActive();
  showToast(`Imported ${entry.ref} into ${ws.basename(active().path)}; its theorem holds wherever its assumptions do`);
}

/** The proofs a pack folder holds, its subfolders included. */
function filesIn(folder) {
  return ws.filesSorted().filter((f) => f.path.startsWith(`${folder}/`));
}

/** "New pack…": a fresh folder with one proof in it, and the pack's details open. */
async function newPackFromWorkspace() {
  const folders = new Set(ws.allFolders().map((f) => f.toLowerCase()));
  let folder = "New pack";
  for (let n = 2; folders.has(folder.toLowerCase()); n++) folder = `New pack ${n}`;
  await ws.createFolder(folder);
  await newProof({ path: `${folder}/First proof.aether`, source: 'Theorem: "First result"\nProof:\n    \nQED\n' });
  showDesk("files");
  await openPackDialog(folder);
}

/** Manifests as a workspace backup carries them: entry details keyed by path, not file id. */
function manifestsForBackup() {
  const out = {};
  for (const [folder, manifest] of Object.entries(allManifests())) {
    const entries = {};
    for (const file of filesIn(folder)) {
      if (manifest.entries?.[file.id]) entries[file.path] = manifest.entries[file.id];
    }
    out[folder] = { ...manifest, entries };
  }
  return out;
}

async function restoreManifestsFromBackup(text) {
  const incoming = JSON.parse(text);
  const byPath = new Map(ws.filesSorted().map((f) => [f.path, f.id]));
  for (const manifest of Object.values(incoming)) {
    const entries = {};
    for (const [path, meta] of Object.entries(manifest.entries ?? {})) {
      if (byPath.has(path)) entries[byPath.get(path)] = meta;
    }
    manifest.entries = entries;
  }
  await restoreManifests(incoming);
}

const libraryActions = {
  onOpen: openLibraryEntry,
  onUse: useInProof,
  onInstall: (pack) => installPack(pack, "bundled"),
  onUninstall: uninstallPack,
  onUpdate: (pack) => installPack(pack, "bundled"),
  onUpdateAll: updateAllPacks,
  onExport: exportPack,
  onInstallFile: choosePackFile,
  onInstallRemote: installFromRegistry,
  onPreview: previewRegistryPack,
  onNewPack: () => newPackFromWorkspace(),
};

async function deleteWithUndo(id) {
  const file = ws.model.files.get(id);
  if (!file) return;
  const bundle = await ws.deleteFile(id);
  lastResponse.delete(id);
  await showActive();
  showToast(`Deleted ${ws.basename(file.path)}`, {
    action: "Undo",
    onAction: async () => {
      await ws.restoreFile(bundle);
      await showActive();
    },
  });
}

async function importFiles(fileList) {
  const added = [];
  const packFiles = [];
  let manifestText = null;
  for (const file of fileList) {
    try {
      if (/\.json$/i.test(file.name)) {
        packFiles.push(file);
      } else if (/\.zip$/i.test(file.name)) {
        const entries = await readZip(await file.arrayBuffer());
        for (const entry of entries) {
          if (entry.path === PACK_MANIFESTS_PATH) manifestText = entry.text;
          if (!ACCEPTED_EXTENSIONS.test(entry.path)) continue;
          let path = ws.normalizePath(entry.path.replace(/\.(txt|md|proof)$/i, ".aether"));
          if (ws.pathProblem(ws.withExtension(path))) path = ws.freePath(`${ws.basename(path).replace(/\.aether$/, "")} (imported)`, ws.dirname(path));
          added.push(await ws.createFile({ path, source: entry.text, strict: strictDefault(), open: false }));
        }
      } else if (ACCEPTED_EXTENSIONS.test(file.name)) {
        const text = await readTextFile(file);
        const stem = file.name.replace(/\.(aether|txt|md|proof)$/i, "");
        const path = ws.pathProblem(`${stem}.aether`) ? ws.freePath(stem) : `${stem}.aether`;
        added.push(await ws.createFile({ path, source: text, strict: strictDefault(), open: false }));
      } else {
        showToast(`“${file.name}” is not a proof file (.aether, .txt, .md), a .zip or a .pack.json`, { tone: "warning" });
      }
    } catch (error) {
      showToast(`Could not open ${file.name}: ${error.message}`, { tone: "danger" });
    }
  }
  if (packFiles.length) await installPackFiles(packFiles);
  if (!added.length) return;
  for (const file of added) await ws.updateFile(file.id, { initial: file.source });
  if (manifestText) {
    try {
      await restoreManifestsFromBackup(manifestText);
    } catch (error) {
      showToast(`The backup's pack details could not be read: ${error.message}`, { tone: "warning" });
    }
  }
  ws.openFile(added[added.length - 1].id);
  setView("workspace");
  await showActive();
  showToast(added.length === 1 ? `Opened ${ws.basename(added[0].path)}` : `Added ${added.length} proofs to your workspace`);
}

// Where a workspace backup keeps the details of folders made into packs.
const PACK_MANIFESTS_PATH = "packs/manifests.json";

async function exportWorkspace() {
  await saveActive();
  const files = ws.filesSorted();
  if (!files.length) {
    showToast("There is nothing to export yet.", { tone: "warning" });
    return;
  }
  const entries = files.map((f) => ({ path: f.path, text: f.source, date: new Date(f.updated) }));
  const manifests = manifestsForBackup();
  if (Object.keys(manifests).length) entries.push({ path: PACK_MANIFESTS_PATH, text: `${JSON.stringify(manifests, null, 2)}\n`, date: new Date() });
  const bytes = writeZip(entries);
  const stamp = new Date().toISOString().slice(0, 10);
  downloadBlob(new Blob([bytes], { type: "application/zip" }), `aether-workspace-${stamp}.zip`);
  showToast(`Exported ${files.length} proof${files.length === 1 ? "" : "s"}`);
}

// ---------------------------------------------------------------------------
// Views and the reading pane
// ---------------------------------------------------------------------------

function setView(name, { push = true } = {}) {
  if (!dom.views[name]) name = "workspace";
  document.body.dataset.view = name;
  for (const [key, section] of Object.entries(dom.views)) section.hidden = key !== name;
  for (const button of dom.railButtons) {
    if (button.dataset.view === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  setPref("view", name);
  if (name === "library") {
    renderLibrary();
    refreshRegistry();
  }
  if (name === "settings") renderSettings();
  if (name === "guide" && !currentGuidePage()) openGuidePage(new URLSearchParams(location.search).get("page") ?? "start", { push: false });
  if (push) {
    const params = new URLSearchParams(location.search);
    if (name === "workspace") params.delete("view");
    else params.set("view", name);
    if (name !== "guide") params.delete("page");
    const query = params.toString();
    history.pushState({ view: name }, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
  }
  if (name === "workspace") requestAnimationFrame(() => editor.view.requestMeasure());
}

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(location.search);
  setView(params.get("view") ?? "workspace", { push: false });
  if (params.get("page")) openGuidePage(params.get("page"), { push: false });
});

// Below this width the reading pane floats over the work instead of sitting
// beside it, so it never opens by itself: only the person opens it.
const narrowScreen = window.matchMedia("(max-width: 1100px)");

function showDesk(panel = null) {
  if (!narrowScreen.matches) setDeskOpen(true);
  if (panel) setDeskPanel(panel);
}

function setDeskOpen(open, { persist = true } = {}) {
  document.documentElement.dataset.desk = open ? "open" : "closed";
  dom.deskCollapse.setAttribute("aria-expanded", String(open));
  dom.deskOpen.hidden = open;
  if (persist) setPref("desk", open ? "open" : "closed");
  requestAnimationFrame(() => editor.view.requestMeasure());
}

// A tap on the work beside a floating reading pane puts the pane away.
document.querySelector(".work").addEventListener("pointerdown", () => {
  if (narrowScreen.matches && document.documentElement.dataset.desk === "open") setDeskOpen(false, { persist: false });
});

function setDeskPanel(name) {
  for (const tab of dom.deskTabs) {
    const on = tab.dataset.panel === name;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
  }
  for (const [key, panel] of Object.entries(dom.deskPanels)) panel.hidden = key !== name;
  setPref("deskPanel", name);
  if (name === "history") renderHistory();
}

for (const tab of dom.deskTabs) {
  tab.addEventListener("click", () => setDeskPanel(tab.dataset.panel));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const i = dom.deskTabs.indexOf(tab);
    const next = dom.deskTabs[(i + (event.key === "ArrowRight" ? 1 : dom.deskTabs.length - 1)) % dom.deskTabs.length];
    next.focus();
    setDeskPanel(next.dataset.panel);
    event.preventDefault();
  });
}
dom.deskCollapse.addEventListener("click", () => {
  setDeskOpen(false);
  dom.deskOpen.focus();
});
dom.deskOpen.addEventListener("click", () => {
  setDeskOpen(true);
  dom.deskCollapse.focus();
});
for (const button of dom.railButtons) button.addEventListener("click", () => setView(button.dataset.view));

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

for (const symbol of SYMBOLS) {
  const button = el("button", "symbol", symbol.symbol);
  button.type = "button";
  button.title = `${symbol.label} — or type ${symbol.ascii}`;
  button.setAttribute("aria-label", `Insert ${symbol.label}`);
  button.addEventListener("mousedown", (event) => event.preventDefault()); // keep the caret
  button.addEventListener("click", () => insertSymbol(editor.view, symbol.symbol));
  dom.symbols.append(button);
}

for (const template of TEMPLATES) {
  const item = document.createElement("wa-dropdown-item");
  item.value = template.id;
  item.append(document.createTextNode(template.label));
  const detail = el("span", "dropdown-detail", template.detail);
  detail.slot = "details";
  item.append(detail);
  dom.templatesMenu.append(item);
}
dom.templatesMenu.addEventListener("wa-select", (event) => {
  const id = event.detail?.item?.value;
  if (id) insertTemplate(editor.view, id);
});

dom.strict.addEventListener("change", () => {
  saveActive();
  runCheck();
});

dom.downloadProof.addEventListener("click", async () => {
  const file = active();
  if (!file) return;
  await saveActive();
  const filename = ws.basename(file.path);
  downloadText(file.source, filename);
  showToast(`Downloaded ${filename}`);
});

// ---------------------------------------------------------------------------
// LaTeX & PDF export
// ---------------------------------------------------------------------------

let latexAbortController = null;

/** The timeline and snapshots for the exported report; only the browser knows them. */
async function exportSession() {
  const file = active();
  const snaps = file ? await ws.snapshotsFor(file.id) : [];
  return {
    timeline: ws.model.timeline
      .filter((e) => !e.fileId || e.fileId === file?.id)
      .map(({ verdict, n, ts }) => ({ verdict, n, ts })),
    snapshots: snaps.map(({ name, ts, strict, auto }) => ({ name, ts, strict: Boolean(strict), auto: Boolean(auto) })),
  };
}

async function exportOptions() {
  return {
    source: currentSource(),
    standalone: dom.latexStandalone.checked,
    breakdown: dom.latexBreakdown.checked,
    strictDomains: dom.strict.checked,
    session: await exportSession(),
  };
}

function exportStem() {
  const file = active();
  return file ? ws.basename(file.path).replace(/\.aether$/, "") : state.data?.reports?.[0]?.theorem_name;
}

async function refreshLatexExport() {
  if (!dom.latexDialog.open) return;
  if (latexAbortController) latexAbortController.abort();
  latexAbortController = new AbortController();
  dom.latexOutput.value = "% Generating LaTeX...";
  try {
    const data = await exportLatex({ ...(await exportOptions()), signal: latexAbortController.signal });
    dom.latexOutput.value = data.error ? `% Could not export: ${data.error}` : data.latex;
  } catch (error) {
    if (error.name === "AbortError") return;
    dom.latexOutput.value = `% Error generating LaTeX: ${error.message}`;
  }
}

function openLatexDialog() {
  if (!active()) return;
  dom.latexDialog.open = true;
  refreshLatexExport();
}

dom.exportLatex.addEventListener("click", openLatexDialog);
dom.latexDialog.addEventListener("wa-after-hide", () => {
  latexAbortController?.abort();
  latexAbortController = null;
});
dom.latexStandalone.addEventListener("change", refreshLatexExport);
dom.latexBreakdown.addEventListener("change", refreshLatexExport);
dom.copyLatex.addEventListener("click", async () => {
  const text = dom.latexOutput.value;
  if (!text) return;
  const ok = await copyText(text);
  showToast(ok ? "LaTeX copied to clipboard" : "Could not copy to clipboard", { tone: ok ? "info" : "warning" });
});
dom.downloadTex.addEventListener("click", () => {
  const text = dom.latexOutput.value;
  if (!text) return;
  const filename = texFilename(exportStem());
  downloadText(text, filename);
  showToast(`Downloaded ${filename}`);
});
dom.downloadPdf.addEventListener("click", async () => {
  const originalText = dom.downloadPdf.textContent;
  dom.downloadPdf.disabled = true;
  dom.downloadPdf.textContent = "Compiling PDF...";
  try {
    const blob = await exportPdf(await exportOptions());
    const filename = pdfFilename(exportStem());
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
// Show in Lean
// ---------------------------------------------------------------------------

let leanAbortController = null;
let leanResult = null;

/** Copy, download and open act on a translation, so they wait for one. */
function setLeanActions(ready) {
  for (const button of [dom.copyLean, dom.downloadLean, dom.openLean]) button.disabled = !ready;
}

async function refreshLean() {
  const file = active();
  if (!dom.leanDialog.open || !file) return;
  leanAbortController?.abort();
  const controller = new AbortController();
  leanAbortController = controller;
  leanResult = null;
  setLeanActions(false);
  dom.leanTable.setAttribute("aria-busy", "true");
  dom.leanUntranslated.hidden = true;
  renderLeanMessage(dom.leanRows, "Translating to Lean…");
  const source = currentSource();
  try {
    const data = await exportLean({ source, path: file.path, ...engineContext(file, source), signal: controller.signal });
    if (controller !== leanAbortController) return;
    if (data.error) {
      renderLeanMessage(dom.leanRows, `There is no Lean for this proof yet: ${data.error}`, { error: true });
      return;
    }
    leanResult = data;
    renderLeanRows(dom.leanRows, data, source);
    setLeanActions(true);
    const note = untranslatedNote(data.untranslated);
    dom.leanUntranslated.textContent = note;
    dom.leanUntranslated.hidden = !note;
  } catch (error) {
    if (error.name === "AbortError") return;
    renderLeanMessage(dom.leanRows, `Could not translate the proof: ${error.message}`, { error: true });
  } finally {
    if (controller === leanAbortController) dom.leanTable.setAttribute("aria-busy", "false");
  }
}

function openLeanDialog() {
  if (!active()) return;
  dom.leanDialog.open = true;
  refreshLean();
}

dom.showLean.addEventListener("click", openLeanDialog);
dom.leanDialog.addEventListener("wa-after-hide", () => {
  leanAbortController?.abort();
  leanAbortController = null;
});
dom.copyLean.addEventListener("click", async () => {
  if (!leanResult) return;
  const ok = await copyText(leanResult.lean);
  showToast(ok ? "Lean copied to clipboard" : "Could not copy to clipboard", { tone: ok ? "info" : "warning" });
});
dom.downloadLean.addEventListener("click", () => {
  if (!leanResult) return;
  const filename = leanFilename(exportStem());
  downloadText(leanResult.lean, filename);
  showToast(`Downloaded ${filename}`);
});
dom.openLean.addEventListener("click", () => {
  if (!leanResult) return;
  // The desktop app hands an outside address to the system browser.
  window.open(leanEditorUrl(leanResult.lean), "_blank", "noopener");
});

// ---------------------------------------------------------------------------
// Theme and syntax
// ---------------------------------------------------------------------------

function applyTheme(name, { persist = false } = {}) {
  document.documentElement.dataset.theme = name;
  editor.setTheme(name);
  if (persist) setPref("theme", name);
}

function applySyntax(name, { persist = false } = {}) {
  document.documentElement.dataset.syntax = name;
  dom.syntaxToggle.setAttribute("aria-pressed", String(name === "vivid"));
  editor.setSyntax();
  if (persist) setPref("syntax", name);
}

dom.themeToggle.addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark", { persist: true }));
dom.syntaxToggle.addEventListener("click", () => applySyntax(currentSyntax() === "vivid" ? "mono" : "vivid", { persist: true }));

// ---------------------------------------------------------------------------
// The command palette and global keys
// ---------------------------------------------------------------------------

function paletteItems() {
  const items = [
    { kind: "command", label: "New proof", shortcut: "Alt+N", run: () => newProof() },
    { kind: "command", label: "Go to Proofs", shortcut: "Alt+1", run: () => setView("workspace") },
    { kind: "command", label: "Go to Library", shortcut: "Alt+2", run: () => setView("library") },
    { kind: "command", label: "Go to Guide", shortcut: "Alt+3", run: () => setView("guide") },
    { kind: "command", label: "Go to Settings", shortcut: "Alt+4", run: () => setView("settings") },
    { kind: "command", label: "Show or hide the reading pane", shortcut: "Alt+B", run: () => setDeskOpen(document.documentElement.dataset.desk !== "open") },
    { kind: "command", label: "Toggle strict domains", run: () => dom.strict.shadowRoot?.querySelector("label")?.click() },
    { kind: "command", label: "Switch light / dark theme", run: () => applyTheme(currentTheme() === "dark" ? "light" : "dark", { persist: true }) },
    { kind: "command", label: "Toggle syntax colours", run: () => applySyntax(currentSyntax() === "vivid" ? "mono" : "vivid", { persist: true }) },
    { kind: "command", label: "Toggle typeset maths", keywords: "visual latex render preview", run: () => setVisual(getPref("visual") !== "on") },
    { kind: "command", label: "Export to LaTeX / PDF", run: openLatexDialog },
    { kind: "command", label: "Show in Lean", keywords: "lean mathlib export skeleton", run: openLeanDialog },
    { kind: "command", label: "Download this proof", run: () => dom.downloadProof.click() },
    { kind: "command", label: "Export the workspace as .zip", run: exportWorkspace },
    { kind: "command", label: "Snapshot this proof", run: () => dom.snapshotNow.click() },
    { kind: "command", label: "Next problem", shortcut: "F8", run: () => problemsJump(1) },
    { kind: "command", label: "Check now", run: runCheck },
    ...TEMPLATES.map((t) => ({ kind: "command", label: `Insert template: ${t.label}`, keywords: "template snippet", run: () => insertTemplate(editor.view, t.id) })),
    ...GUIDE_PAGES.map((p) => ({ kind: "command", label: `Guide: ${p.title}`, keywords: "help docs", run: () => (setView("guide"), openGuidePage(p.id)) })),
  ];
  for (const file of ws.filesSorted()) items.push({ kind: "file", label: ws.basename(file.path), detail: ws.dirname(file.path), keywords: file.path, boost: 1, run: () => (setView("workspace"), activate(file.id)) });
  for (const pack of libraryPacks()) {
    for (const entry of pack.entries) {
      items.push({ kind: "entry", label: `${entry.ref} ${entry.title}`, detail: packs.packLabel(pack), keywords: `${pack.courses?.join(" ") ?? ""} ${pack.title} ${entry.kind}`, run: () => openLibraryEntry(pack, entry) });
    }
  }
  return items;
}

// Typeset maths, from Settings or the palette; Settings re-renders so its
// switch follows a change made from the palette.
function setVisual(on) {
  setPref("visual", on ? "on" : "off");
  editor.setVisual(on);
  renderSettings();
}

function problemsJump() {
  const data = active() && lastResponse.get(active().id);
  const first = data && firstProblem(data)[0];
  if (first) editor.goToLine(first.line);
}

window.addEventListener("keydown", (event) => {
  const mod = event.ctrlKey || event.metaKey;
  if (mod && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openPalette();
    return;
  }
  if (event.altKey && !mod) {
    const views = { 1: "workspace", 2: "library", 3: "guide", 4: "settings" };
    if (views[event.key]) {
      event.preventDefault();
      setView(views[event.key]);
    } else if (event.key.toLowerCase() === "n" || event.code === "KeyN") {
      event.preventDefault();
      newProof();
    } else if (event.key.toLowerCase() === "b" || event.code === "KeyB") {
      event.preventDefault();
      setDeskOpen(document.documentElement.dataset.desk !== "open");
    }
  }
});
dom.paletteOpen.addEventListener("click", () => openPalette());

// ---------------------------------------------------------------------------
// Wiring the modules
// ---------------------------------------------------------------------------

initAuditNav();

initExplorer(
  {
    onOpen: (id) => activate(id),
    onDelete: (id) => deleteWithUndo(id),
    onRename: async (id, name) => {
      const file = ws.model.files.get(id);
      try {
        await ws.renameFile(id, `${ws.dirname(file.path) ? `${ws.dirname(file.path)}/` : ""}${name}`);
        await showActive({ check: false });
      } catch (error) {
        showToast(error.message, { tone: "warning" });
        renderExplorer();
      }
    },
    onMove: async (id, folder) => {
      try {
        await ws.moveFile(id, folder);
        await showActive({ check: false });
      } catch (error) {
        showToast(error.message, { tone: "warning" });
      }
    },
    onPack: (folder) => openPackDialog(folder),
    isPack: (folder) => isPackFolder(folder),
    onRenameFolder: async (folder, name) => {
      try {
        const renamed = `${ws.dirname(folder) ? `${ws.dirname(folder)}/` : ""}${name}`;
        await ws.renameFolder(folder, renamed);
        await renameManifestFolder(folder, ws.normalizePath(renamed));
        await showActive({ check: false });
      } catch (error) {
        showToast(error.message, { tone: "warning" });
        renderExplorer();
      }
    },
    onDeleteFolder: async (folder) => {
      const bundle = await ws.deleteFolder(folder);
      await showActive();
      showToast(`Deleted ${folder} and ${bundle.bundles.length} proof${bundle.bundles.length === 1 ? "" : "s"} in it`, {
        action: "Undo",
        onAction: async () => {
          await ws.restoreFolder(bundle);
          await showActive();
        },
      });
    },
  },
  verdicts,
);

initTabs(
  {
    onActivate: (id) => activate(id),
    onClose: async (id) => {
      await saveActive();
      ws.closeTab(id);
      await showActive();
    },
    onMove: (id, index) => {
      ws.moveTab(id, index);
      renderTabs();
    },
  },
  verdicts,
);

dom.fileNew.addEventListener("click", () => newProof());
dom.folderNew.addEventListener("click", async () => {
  try {
    const name = ws.freePath("New folder").replace(/\.aether$/, "");
    await ws.createFolder(name);
    renderExplorer();
    document.querySelector(`.tree-row[data-folder="${CSS.escape(name)}"] .tree-action[aria-label^="Rename"]`)?.click();
  } catch (error) {
    showToast(error.message, { tone: "warning" });
  }
});
dom.workspaceImport.addEventListener("click", () => dom.workspaceImportInput.click());
dom.workspaceImportInput.addEventListener("change", async () => {
  await importFiles([...dom.workspaceImportInput.files]);
  dom.workspaceImportInput.value = "";
});
dom.workspaceExport.addEventListener("click", exportWorkspace);

setupDropZone({
  onDragState: (on) => {
    dom.dropOverlay.hidden = !on;
  },
  onFiles: (files) => importFiles(files),
});

initHistory({
  async onSnapshot() {
    const file = active();
    if (!file || !currentSource().trim()) {
      showToast("There is nothing to snapshot yet.", { tone: "warning" });
      return;
    }
    await saveActive();
    await ws.addSnapshot(file.id, { name: `Snapshot ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` });
    showToast("Snapshot saved");
  },
  async onRestore(snapshot) {
    await snapshotBefore(`Before restoring “${snapshot.name}”`);
    editor.setContent(snapshot.source);
    dom.strict.checked = snapshot.strict;
    await saveActive();
    renderHistory();
    runCheck();
    showToast("Snapshot restored");
  },
  async onReset() {
    const file = active();
    if (!file) return;
    const found = file.origin ? findEntry(file.origin) : null;
    const start = found?.entry.source ?? file.initial ?? "";
    await snapshotBefore("Before reset");
    editor.setContent(start);
    await saveActive();
    if (file.exercise) await ws.updateFile(file.id, { exercise: { revealed: false, guess: null, answer: null } });
    renderNotesPanel();
    runCheck();
    showToast("Reset to where this proof started");
  },
  async onCopyLink() {
    await saveActive();
    const ok = await copyText(permalinkFor(currentSource(), dom.strict.checked));
    showToast(ok ? "Link copied — it reproduces this exact proof" : "Could not reach the clipboard; copy the address bar instead", { tone: ok ? "info" : "warning" });
  },
  async onClearSnapshots() {
    const file = active();
    if (!file) return;
    for (const snap of await ws.snapshotsFor(file.id)) await ws.removeSnapshot(snap.id);
  },
  onCleared() {
    showToast("Cleared this proof's snapshots and history (the proof itself is untouched)");
  },
});

initNotes({
  onGuess: async () => {
    const file = active();
    if (!file) return;
    const line = editor.view.state.doc.lineAt(editor.view.state.selection.main.head).number;
    const answer = file.exercise.answer;
    await ws.updateFile(file.id, { exercise: { ...file.exercise, guess: line, revealed: true, correct: answer != null && line === answer } });
    await afterReveal();
  },
  onReveal: async () => {
    const file = active();
    await ws.updateFile(file.id, { exercise: { ...file.exercise, revealed: true, correct: false } });
    await afterReveal();
  },
  onRetry: async () => {
    const file = active();
    const found = findEntry(file.origin);
    await ws.updateFile(file.id, { exercise: { revealed: false, guess: null, answer: null } });
    if (found) editor.setContent(found.entry.source);
    await saveActive();
    renderNotesPanel();
    runCheck();
  },
  onShowInLibrary: () => setView("library"),
  onFresh: (pack, entry) => openLibraryEntry(pack, entry, { fresh: true, exercise: entry.kind === "trap" }),
  onUnpin: () => {
    pinnedGuide = null;
    db.meta.set("pinnedGuide", null);
    renderNotesPanel();
  },
  onBrowse: () => setView("library"),
});

async function afterReveal() {
  const file = active();
  renderNotesPanel();
  const data = lastResponse.get(file.id);
  if (data) showResponse(file, data);
  const { exercise } = file;
  showToast(exercise.guess == null ? "Answer shown" : exercise.correct ? "Right — that is the step that fails" : `Not quite — it fails on line ${exercise.answer ?? "?"}`, {
    tone: exercise.correct ? "info" : "warning",
  });
}

initGuide({
  onTry: async (source, title) => {
    await newProof({ path: ws.freePath(safeName(`Try — ${title}`), "Scratch"), source });
  },
  onPin: async (pageId) => {
    pinnedGuide = pageId;
    await db.meta.set("pinnedGuide", pageId);
    setView("workspace");
    showDesk("notes");
    renderNotesPanel();
    showToast("Pinned beside the proof");
  },
  onNavigate: (pageId, push) => {
    if (!push) return;
    const params = new URLSearchParams(location.search);
    params.set("view", "guide");
    params.set("page", pageId);
    history.replaceState({ view: "guide" }, "", `${location.pathname}?${params}${location.hash}`);
  },
});

initSettings({
  onTheme: (name) => applyTheme(name, { persist: true }),
  onSyntax: (name) => applySyntax(name, { persist: true }),
  onWrap: (on) => editor.setWrap(on),
  onVisual: (on) => setVisual(on),
  onDesk: (on) => setDeskOpen(on),
  onExport: exportWorkspace,
  countFiles: async () => ws.model.files.size,
  storageSummary: async () => {
    const usage = await db.usage();
    const files = ws.model.files.size;
    const where = ws.model.persistent ? `kept ${kept}` : `not kept — ${holder} will not store data`;
    const size = usage ? ` · ${(usage.used / 1024).toFixed(0)} KB used` : "";
    return `${files} proof${files === 1 ? "" : "s"}, ${where}${size}`;
  },
  onWipe: async () => {
    await db.wipe();
    try {
      for (const key of Object.keys(localStorage)) if (key.startsWith("aether")) localStorage.removeItem(key);
    } catch (error) {
      // Nothing to clear.
    }
    // Wiping includes the migration flag; keep it so the old single-buffer
    // workspace is not imported straight back.
    await db.meta.set("migrated-v1", true);
    location.replace(location.pathname);
  },
});

initPalette(paletteItems);

// Save the last few hundred ms of typing on the way out.
window.addEventListener("beforeunload", () => saveActive());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") saveActive();
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function init() {
  // The static build runs the checker in this browser: start loading it now,
  // while the workspace opens, and say so while it loads.
  warmUp();
  onEngineStatus(({ state, detail }) => {
    if (state === "loading" || state === "restarting") setEngineLoading(`${state === "restarting" ? "Restarting the checker" : "Loading the checker"}${detail ? ` · ${detail}` : ""}`);
    else setEngineLoading(null);
    if (state === "failed") showToast(`The checker could not start in ${holder}: ${detail}`, { tone: "danger", ms: 12000 });
  });
  if (!canExportPdf) {
    dom.downloadPdf.hidden = true;
    document.getElementById("pdf-note").hidden = false;
  }
  applySyntax(currentSyntax());
  await loadSite();
  setDeskOpen(getPref("desk") === "open" && !narrowScreen.matches, { persist: false });
  setDeskPanel(getPref("deskPanel"));

  let catalog = [];
  try {
    catalog = await fetchLibrary();
  } catch (error) {
    showToast(`The pack catalogue could not be loaded: ${error.message}. Installed packs still work.`, { tone: "warning" });
  }
  await packs.load(catalog, site.preinstall ?? null);
  // What the registry offered last time is listed at once; a fresh copy follows.
  refreshRegistry();
  initLibrary(libraryActions, () => {
    const out = new Map();
    for (const file of ws.model.files.values()) {
      if (file.origin) out.set(file.origin, { fileId: file.id, tone: verdicts.get(file.id) ?? null });
    }
    return out;
  });

  await ws.load();
  // Origins recorded before packs had scoped names point at the same entries.
  for (const file of ws.model.files.values()) {
    const migrated = packs.migrateOrigin(file.origin);
    if (migrated !== file.origin) await ws.updateFile(file.id, { origin: migrated });
  }
  await initPackAuthor({
    filesIn,
    onExport: exportPack,
    onInstall: async (pack) => {
      setView("library");
      await installPack(pack, "local");
    },
  });
  pinnedGuide = await db.meta.get("pinnedGuide", null);
  dom.statusStorage.textContent = ws.model.persistent ? `Saved ${kept}` : "Not saved — storage unavailable";
  dom.statusStorage.dataset.ok = String(ws.model.persistent);

  // A link wins: the fragment is what the person clicking it meant to see.
  // An identical proof already in the workspace is reopened, not duplicated,
  // so reloading a page that carries its own link does not multiply files.
  const shared = readPermalink();
  let origin = "restored";
  if (shared) {
    const match = ws.filesSorted().find((f) => f.source === shared.source);
    if (match) ws.openFile(match.id);
    else {
      const file = await ws.createFile({ path: ws.freePath("Shared proof"), source: shared.source, strict: shared.strict, open: true });
      await ws.updateFile(file.id, { initial: shared.source });
      origin = "link";
    }
  } else if (!ws.model.files.size) {
    // First visit: the starting example, beside its notes and the welcome card.
    const found = findEntry(STARTING_ENTRY);
    if (found) {
      const file = await ws.createFile({ path: `Examples/${found.entry.title}.aether`, source: found.entry.source, strict: strictDefault(), open: true });
      await ws.updateFile(file.id, { initial: found.entry.source, origin: STARTING_ENTRY });
      setDeskPanel("notes");
    }
    origin = "first";
  } else if (!ws.model.activeId && ws.model.files.size) {
    ws.openFile(ws.filesSorted()[0].id);
  }

  const params = new URLSearchParams(location.search);
  setView(params.get("view") ?? "workspace", { push: false });
  if (params.get("view") === "guide" && params.get("page")) openGuidePage(params.get("page"), { push: false });
  if (params.get("install")) openPackLink(params.get("install"));

  // The workspace is in place: show it now, and let the check (which in the
  // static build may wait on the checker loading) say "Checking…" itself.
  await showActive({ check: false });
  finishBoot();
  await runCheck();
  if (origin === "link") showToast("Loaded the proof from this link");
}

/** End the loading state (see .boot in styles.css); safe to call twice. */
function finishBoot() {
  const root = document.documentElement;
  if (!("booting" in root.dataset)) return;
  delete root.dataset.booting;
  // The settle-in plays once, not on every later change of view.
  root.dataset.booted = "";
  setTimeout(() => delete root.dataset.booted, 400);
}

// A boot that fails still shows the app, with whatever it reached.
init().finally(finishBoot);
