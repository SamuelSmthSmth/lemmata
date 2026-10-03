// Authoring a pack: a workspace folder *is* the pack.
//
// Its files are the entries, written and checked in the ordinary editor.
// What a pack needs beyond the proofs -- its name, version, course codes, and
// each entry's reference, title, kind and chapter -- is kept in a manifest per
// folder (meta "packManifests"), edited in one dialog.  Entry details are keyed
// by file id, so renaming or moving a file keeps them.
//
// Exporting checks every file *on its own*, exactly as someone who installs
// the pack will see it, and records that verdict as the entry's `expected`,
// so a pack is true by construction.

import { checkProof, validatePack } from "./api.js";
import * as db from "./db.js";
import { el } from "./format.js";
import * as packs from "./packs.js";

let manifests = {}; // folder -> manifest
let handlers = {};
let current = null; // folder open in the dialog

const dialog = () => document.getElementById("pack-dialog");

export async function initPackAuthor(actions) {
  handlers = actions;
  manifests = (await db.meta.get("packManifests", {})) ?? {};
  document.getElementById("pack-export").addEventListener("click", () => finish("export"));
  document.getElementById("pack-install").addEventListener("click", () => finish("install"));
}

const save = () => db.meta.set("packManifests", manifests);

export const isPackFolder = (folder) => Object.hasOwn(manifests, folder);
export const allManifests = () => manifests;

/** Merge manifests restored from a workspace backup. */
export async function restoreManifests(incoming) {
  manifests = { ...manifests, ...incoming };
  await save();
}

/** Keep a manifest with its folder when the folder is renamed. */
export async function renameManifestFolder(oldPath, newPath) {
  let changed = false;
  for (const folder of Object.keys(manifests)) {
    if (folder === oldPath || folder.startsWith(`${oldPath}/`)) {
      manifests[newPath + folder.slice(oldPath.length)] = manifests[folder];
      delete manifests[folder];
      changed = true;
    }
  }
  if (changed) await save();
}

export async function openPackDialog(folder) {
  if (!manifests[folder]) {
    manifests[folder] = packs.newManifest(folder);
    await save();
  }
  current = folder;
  renderForm();
  setStatus("");
  dialog().label = `Pack · ${folder}`;
  dialog().open = true;
}

function setStatus(text, tone = "") {
  const status = document.getElementById("pack-status");
  status.replaceChildren();
  if (Array.isArray(text)) {
    const list = el("ul", "pack-problems");
    for (const line of text) list.append(el("li", null, line));
    status.append(list);
  } else if (text) status.append(el("p", null, text));
  status.dataset.tone = tone;
}

// ---------------------------------------------------------------------------
// The form
// ---------------------------------------------------------------------------

function textField({ label, hint, value, onInput, required = false }) {
  const input = document.createElement("wa-input");
  input.setAttribute("size", "s");
  input.setAttribute("label", label);
  if (hint) input.setAttribute("hint", hint);
  if (required) input.setAttribute("required", "");
  input.value = value ?? "";
  input.addEventListener("input", () => onInput(input.value ?? ""));
  return input;
}

const list = (text) => text.split(",").map((s) => s.trim()).filter(Boolean);

function renderForm() {
  const manifest = manifests[current];
  const update = (changes) => {
    Object.assign(manifest, changes);
    save();
  };
  const form = document.getElementById("pack-form");
  form.replaceChildren();

  const about = el("fieldset", "pack-fields");
  about.append(el("legend", null, "About the pack"));
  about.append(
    textField({ label: "Title", value: manifest.title, required: true, onInput: (v) => update({ title: v }) }),
    textField({ label: "Name", hint: "scope/slug, how the pack is imported: yourname/real-analysis", value: manifest.name, required: true, onInput: (v) => update({ name: v.trim() }) }),
    textField({ label: "Version", hint: "Raise it when you change the pack, so installed copies can update", value: manifest.version, required: true, onInput: (v) => update({ version: v.trim() }) }),
    textField({ label: "Course codes", hint: "Optional, comma-separated: MTH2008", value: manifest.courses.join(", "), onInput: (v) => update({ courses: list(v) }) }),
    textField({ label: "Authors", hint: "Comma-separated", value: manifest.authors.join(", "), onInput: (v) => update({ authors: list(v) }) }),
    textField({ label: "Licence", value: manifest.license, required: true, onInput: (v) => update({ license: v.trim() }) }),
  );
  const summaryId = "pack-summary";
  const summaryLabel = el("label", "pack-label", "Summary");
  summaryLabel.htmlFor = summaryId;
  const summary = el("textarea", "pack-textarea");
  summary.id = summaryId;
  summary.rows = 2;
  summary.value = manifest.summary;
  summary.addEventListener("input", () => update({ summary: summary.value }));
  const summaryField = el("div", "pack-summary-field");
  summaryField.append(summaryLabel, summary);
  about.append(summaryField);
  form.append(about);

  const files = handlers.filesIn?.(current) ?? [];
  const entries = el("fieldset", "pack-fields pack-entries");
  entries.append(el("legend", null, `Entries · ${files.length} ${files.length === 1 ? "proof" : "proofs"} in ${current}`));
  if (!files.length) entries.append(el("p", "pack-empty", "Add proofs to this folder in the workspace; each becomes an entry."));
  for (const file of files) entries.append(entryRow(manifest, file));
  form.append(entries);
}

function entryRow(manifest, file) {
  const meta = (manifest.entries[file.id] ??= {});
  const name = file.path.split("/").pop().replace(/\.aether$/, "");
  const write = (changes) => {
    Object.assign(meta, changes);
    save();
  };
  const row = el("div", `pack-entry${meta.kind === "trap" ? " is-trap" : ""}`);
  row.append(el("p", "pack-entry-file", name));

  const field = (label, key, placeholder) => {
    const wrap = el("label", "pack-cell");
    wrap.append(el("span", "pack-cell-label", label));
    const input = el("input", "pack-input");
    input.value = meta[key] ?? "";
    input.placeholder = placeholder;
    input.addEventListener("input", () => write({ [key]: input.value }));
    wrap.append(input);
    return wrap;
  };
  const kindWrap = el("label", "pack-cell pack-cell--kind");
  kindWrap.append(el("span", "pack-cell-label", "Kind"));
  const kind = el("select", "pack-input");
  for (const [value, label] of [["proof", "Proof"], ["trap", "Trap"]]) {
    const option = el("option", null, label);
    option.value = value;
    kind.append(option);
  }
  kind.value = meta.kind === "trap" ? "trap" : "proof";
  kind.addEventListener("change", () => {
    write({ kind: kind.value });
    row.classList.toggle("is-trap", kind.value === "trap");
  });
  kindWrap.append(kind);

  row.append(
    field("Reference", "ref", name),
    field("Title", "title", name),
    field("Chapter", "chapter", manifest.title),
    kindWrap,
  );
  const explain = field("What is wrong (shown after the student finds it)", "explanation", "The step that fails, and why");
  explain.classList.add("pack-cell--explain");
  row.append(explain);
  return row;
}

// ---------------------------------------------------------------------------
// Export and install
// ---------------------------------------------------------------------------

function verdictOf(response) {
  return response.verdict === "VALID (with domain warnings)" ? "WARN" : response.verdict;
}

async function finish(action) {
  const folder = current;
  const manifest = manifests[folder];
  const files = handlers.filesIn?.(folder) ?? [];
  const exportButton = document.getElementById("pack-export");
  const installButton = document.getElementById("pack-install");
  exportButton.disabled = installButton.disabled = true;
  try {
    const verdicts = new Map();
    for (const [i, file] of files.entries()) {
      setStatus(`Checking ${i + 1} of ${files.length}: ${file.path.split("/").pop()}`);
      const sources = packs.importsFromPacks(file.source) ? packs.importSources(packs.installedPacks()) : null;
      try {
        verdicts.set(file.id, verdictOf(await checkProof({ source: file.source, strictDomains: false, files: sources, path: file.path })));
      } catch (error) {
        verdicts.set(file.id, "UNREACHABLE");
      }
    }
    const { pack, problems } = packs.buildPack(manifest, files, verdicts);
    if (problems.length) {
      setStatus(problems, "invalid");
      return;
    }
    const { pack: valid, errors } = await validatePack(pack);
    if (!valid) {
      setStatus(errors.map((e) => e.replace(/^entries\[(\d+)\]/, (_, i) => pack.entries[i]?.title ?? `entry ${i}`)), "invalid");
      return;
    }
    if (action === "export") {
      handlers.onExport?.(valid);
      setStatus(`Exported ${packs.packToFile(valid).filename}: ${valid.entries.length} entries, each recorded with the verdict it gives.`, "valid");
    } else {
      dialog().open = false;
      await handlers.onInstall?.(valid);
    }
  } finally {
    exportButton.disabled = installButton.disabled = false;
  }
}
