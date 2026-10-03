// The Settings view.
//
// Every control writes through prefs.js (small, synchronous, read before first
// paint) and calls back into main.js to apply the change live.  Choices use the
// same segmented control as the Library filters; on/off settings use the same
// switch as Strict domains.  Destructive actions confirm inline, with a second
// click, rather than in a modal.

import { el } from "./format.js";
import { ARRANGEMENTS, layoutApi } from "./layout.js";
import { getPref, setPref } from "./prefs.js";
import { site } from "./site.js";

let handlers = {};

function segmented({ name, label, hint, options, value, onChange }) {
  const field = el("div", "setting");
  const id = `setting-${name}`;
  const text = el("div", "setting-text");
  text.append(el("span", "setting-label", label));
  text.id = `${id}-label`;
  if (hint) text.append(el("span", "setting-hint", hint));
  const group = el("div", "filters");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", text.id);
  for (const [optionValue, optionLabel] of options) {
    const button = el("button", "filter", optionLabel);
    button.type = "button";
    button.setAttribute("role", "radio");
    button.dataset.value = optionValue;
    button.setAttribute("aria-checked", String(optionValue === value));
    button.tabIndex = optionValue === value ? 0 : -1;
    button.addEventListener("click", () => {
      for (const b of group.querySelectorAll(".filter")) {
        b.setAttribute("aria-checked", String(b === button));
        b.tabIndex = b === button ? 0 : -1;
      }
      onChange(optionValue);
    });
    group.append(button);
  }
  group.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const buttons = [...group.querySelectorAll(".filter")];
    const i = buttons.indexOf(document.activeElement);
    const next = buttons[(i + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    next.focus();
    next.click();
    event.preventDefault();
  });
  field.append(text, group);
  return field;
}

function toggle({ name, label, hint, checked, onChange }) {
  const field = el("div", "setting");
  const text = el("div", "setting-text");
  text.id = `setting-${name}-label`;
  text.append(el("span", "setting-label", label));
  if (hint) text.append(el("span", "setting-hint", hint));
  const control = document.createElement("wa-switch");
  control.size = "s";
  control.checked = checked;
  // The label has to be slotted: aria-labelledby on the host cannot reach the
  // input inside its shadow root.  The visible label beside it says the same.
  control.append(el("span", "sr-only", label));
  control.id = `setting-${name}`;
  control.addEventListener("change", () => onChange(control.checked));
  field.append(text, control);
  return field;
}

function action({ label, hint, buttonLabel, tone = "", confirm = null, onClick }) {
  const field = el("div", "setting");
  const text = el("div", "setting-text");
  text.append(el("span", "setting-label", label));
  if (hint) text.append(el("span", "setting-hint", hint));
  const button = el("button", `text-button${tone ? ` text-button--${tone}` : ""}`, buttonLabel);
  button.type = "button";
  let armed = null;
  button.addEventListener("click", async () => {
    if (confirm && !armed) {
      button.textContent = await confirm();
      button.classList.add("is-armed");
      armed = window.setTimeout(() => {
        armed = null;
        button.textContent = buttonLabel;
        button.classList.remove("is-armed");
      }, 5000);
      return;
    }
    window.clearTimeout(armed);
    armed = null;
    button.textContent = buttonLabel;
    button.classList.remove("is-armed");
    onClick();
  });
  field.append(text, button);
  return field;
}

function group(title, ...fields) {
  const section = el("section", "settings-group");
  section.append(el("h2", null, title), ...fields);
  return section;
}

export function initSettings(actions) {
  handlers = actions;
  renderSettings();
}

export function renderSettings() {
  const form = document.getElementById("settings-form");
  const storage = el("p", "setting-hint settings-storage", "Measuring…");
  handlers.storageSummary?.().then((text) => {
    storage.textContent = text;
  });

  form.replaceChildren(
    group(
      "Appearance",
      segmented({
        name: "theme",
        label: "Theme",
        options: [["light", "Light"], ["dark", "Dark"]],
        value: document.documentElement.dataset.theme,
        onChange: (v) => handlers.onTheme?.(v),
      }),
      segmented({
        name: "syntax",
        label: "Syntax colours",
        hint: "Mono colours only the proof's keywords; vivid gives every kind of word its own hue.",
        options: [["mono", "Mono"], ["vivid", "Vivid"]],
        value: getPref("syntax"),
        onChange: (v) => handlers.onSyntax?.(v),
      }),
      segmented({
        name: "editor-size",
        label: "Editor text size",
        options: ["12", "13", "14", "15", "16"].map((v) => [v, `${v}px`]),
        value: getPref("editorSize"),
        onChange: (v) => {
          setPref("editorSize", v);
          document.documentElement.style.setProperty("--editor-size", `${v}px`);
        },
      }),
      toggle({
        name: "wrap",
        label: "Wrap long lines",
        hint: "Off keeps every statement on one line, as the auditor shows it.",
        checked: getPref("wrap") === "on",
        onChange: (on) => {
          setPref("wrap", on ? "on" : "off");
          handlers.onWrap?.(on);
        },
      }),
    ),
    group(
      "Checking",
      toggle({
        name: "strict-default",
        label: "Strict domains for new proofs",
        hint: "An unguarded division or square root is an error, not a warning. Each proof keeps its own setting.",
        checked: getPref("strictDefault") === "on",
        onChange: (on) => setPref("strictDefault", on ? "on" : "off"),
      }),
      segmented({
        name: "debounce",
        label: "Check after typing pauses for",
        options: [["150", "0.15 s"], ["300", "0.3 s"], ["600", "0.6 s"], ["1000", "1 s"]],
        value: getPref("debounce"),
        onChange: (v) => setPref("debounce", v),
      }),
    ),
    group(
      "Layout",
      segmented({
        name: "arrangement",
        label: "Panel arrangement",
        hint: "Where the editor, auditor and context sit beside the reading pane.",
        options: ARRANGEMENTS.map((a) => [a.id, a.label]),
        value: layoutApi.current.arrangement,
        onChange: (v) => layoutApi.setArrangement?.(v),
      }),
      toggle({
        name: "desk",
        label: "Show the reading pane",
        hint: "Files, notes and history beside the proof.",
        checked: getPref("desk") === "open",
        onChange: (on) => handlers.onDesk?.(on),
      }),
    ),
    group(
      "Your work",
      (() => {
        const field = el("div", "setting");
        const text = el("div", "setting-text");
        text.append(el("span", "setting-label", "Storage"), storage);
        field.append(text);
        return field;
      })(),
      action({
        label: "Back up the workspace",
        hint: "Every proof, as a .zip of .aether files. Drop it back onto the window to restore.",
        buttonLabel: "Export .zip",
        onClick: () => handlers.onExport?.(),
      }),
      action({
        label: "Delete everything",
        hint: "Removes every proof, snapshot and setting from this browser. Export first if you want to keep them.",
        buttonLabel: "Delete everything",
        tone: "danger",
        confirm: async () => `Click again to delete ${(await handlers.countFiles?.()) ?? "all"} proofs`,
        onClick: () => handlers.onWipe?.(),
      }),
    ),
    group(
      "About",
      (() => {
        const field = el("div", "setting");
        const text = el("div", "setting-text");
        text.append(
          el("span", "setting-label", site.name),
          el("span", "setting-hint", site.version ? `Version ${site.version}. Steps are checked by SymPy and Z3.` : "Steps are checked by SymPy and Z3."),
        );
        field.append(text);
        return field;
      })(),
    ),
  );
}
