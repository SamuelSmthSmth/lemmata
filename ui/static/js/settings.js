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
import { holder, site } from "./site.js";

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

// ---------------------------------------------------------------------------
// Account (js/account.js): sign in, and what sync is doing
// ---------------------------------------------------------------------------

function ago(at) {
  const seconds = Math.round((Date.now() - at) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `at ${new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

/** One sentence on what sync is doing, for the signed-in row and the status bar. */
export function syncSentence(status) {
  const waiting = status.pending ? ` · ${status.pending} ${status.pending === 1 ? "change" : "changes"} waiting` : "";
  if (status.state === "syncing") return "Syncing…";
  if (status.state === "synced") return `Synced ${ago(status.at)}${waiting}`;
  if (status.state === "error") {
    const why = navigator.onLine === false ? "you are offline" : status.error?.message || "the account could not be reached";
    return `Not synced: ${why}. Your changes are kept ${holder === "this app" ? "here" : "in this browser"} and sent when it is back.`;
  }
  return "Connecting…";
}

/** Refresh the signed-in row's sentence without rebuilding the form. */
export function updateAccountStatus(account) {
  const line = document.getElementById("account-status");
  if (line && account.user) {
    line.textContent = syncSentence(account.status);
    line.dataset.tone = account.status.state === "error" ? "warning" : "";
  }
}

function accountFields(account) {
  if (account.user) {
    const who = el("div", "setting");
    const text = el("div", "setting-text");
    const status = el("span", "setting-hint account-status", syncSentence(account.status));
    status.id = "account-status";
    status.setAttribute("role", "status");
    text.append(el("span", "setting-label account-email", account.user.email ?? "Signed in"), status);
    const now = el("button", "text-button", "Sync now");
    now.type = "button";
    now.addEventListener("click", () => handlers.onSyncNow?.());
    who.append(text, now);
    return [
      who,
      action({
        label: "Sign out",
        hint: `Your proofs stay ${holder === "this app" ? "here" : "in this browser"}; sign in again to carry on syncing.`,
        buttonLabel: "Sign out",
        onClick: () => handlers.onSignOut?.(),
      }),
      action({
        label: "Download my data",
        hint: "Everything the account holds (proofs, history, packs and settings) as one .json file.",
        buttonLabel: "Download .json",
        onClick: () => handlers.onDownloadAccount?.(),
      }),
      action({
        label: "Delete account",
        hint: `Deletes the account and everything synced to it, for good. ${holder === "this app" ? "This app" : "This browser"} keeps its own copy.`,
        buttonLabel: "Delete account",
        tone: "danger",
        confirm: async () => "Click again to delete your account",
        onClick: () => handlers.onDeleteAccount?.(),
      }),
    ];
  }

  const intro = el("div", "setting");
  const introText = el("div", "setting-text");
  introText.append(
    el("span", "setting-label", "Sync with an account"),
    el("span", "setting-hint", `Your proofs, history, packs, settings and panel layout, the same on every device you sign in on. Without an account, everything stays ${holder === "this app" ? "in this app" : "in this browser"}.`),
  );
  intro.append(introText);
  const fields = [intro];

  const named = { google: "Google", azure: "Microsoft", github: "GitHub", discord: "Discord" };
  if (account.providers.length) {
    const row = el("div", "setting");
    const text = el("div", "setting-text");
    text.id = "account-providers-label";
    text.append(el("span", "setting-label", "Sign in with"));
    const buttons = el("div", "account-providers");
    buttons.setAttribute("role", "group");
    buttons.setAttribute("aria-labelledby", text.id);
    for (const id of account.providers) {
      const button = el("button", "text-button", named[id] ?? id);
      button.type = "button";
      button.dataset.provider = id;
      button.addEventListener("click", () => handlers.onSignInWith?.(id));
      buttons.append(button);
    }
    row.append(text, buttons);
    fields.push(row);
  }

  if (account.email) {
    const form = el("form", "setting account-email-form");
    const text = el("div", "setting-text");
    const hint = el("span", "setting-hint", "We email you a link that signs you in. Open it in this browser.");
    hint.setAttribute("role", "status");
    text.append(el("span", "setting-label", account.providers.length ? "Or by email" : "Sign in by email"), hint);
    const controls = el("div", "account-email-controls");
    const input = document.createElement("wa-input");
    input.setAttribute("size", "s");
    input.setAttribute("type", "email");
    input.setAttribute("label", "Email address");
    input.setAttribute("autocomplete", "email");
    input.setAttribute("placeholder", "you@university.ac.uk");
    input.setAttribute("required", "");
    input.id = "account-email-input";
    const send = el("button", "text-button text-button--primary", "Email me a link");
    send.type = "submit";
    controls.append(input, send);
    form.append(text, controls);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const email = String(input.value ?? "").trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        hint.textContent = "That does not look like an email address.";
        hint.dataset.tone = "danger";
        input.focus();
        return;
      }
      send.disabled = true;
      hint.dataset.tone = "";
      hint.textContent = "Sending…";
      try {
        await handlers.onSignInWithEmail?.(email);
        hint.textContent = `Sent to ${email}. Open the link in this browser to finish signing in.`;
      } catch (error) {
        hint.textContent = `Not sent: ${error.message}.`;
        hint.dataset.tone = "danger";
      } finally {
        send.disabled = false;
      }
    });
    fields.push(form);
  }
  return fields;
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
      toggle({
        name: "visual",
        label: "Typeset the maths",
        hint: "Shows each expression as it prints: fractions, powers, roots. Move the caret into one to edit what you wrote.",
        checked: getPref("visual") === "on",
        onChange: (on) => handlers.onVisual?.(on),
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
      toggle({
        name: "working-default",
        label: "Show your working for new proofs",
        hint: "A step that skips the working a question asks for, like the product rule or a sum's closed form, gets a warning naming it. Each proof keeps its own setting.",
        checked: getPref("workingDefault") === "on",
        onChange: (on) => setPref("workingDefault", on ? "on" : "off"),
      }),
      segmented({
        name: "level-default",
        label: "Checking level for new proofs",
        hint: "How big a step one line may take. Course and Exam refuse a line that is true but skips the argument (a whole ε–δ statement at once, a divisibility by checking remainders); Exam also wants a derivative, limit or sum worked. Each proof keeps its own level.",
        options: [["off", "Off"], ["exam", "Exam"], ["course", "Course"], ["scratch", "Scratch"]],
        value: getPref("levelDefault"),
        onChange: (v) => setPref("levelDefault", v),
      }),
      toggle({
        name: "audit",
        label: "What each line used",
        hint: "Each check records what every line was proved from and what it asked SymPy and Z3: the arcs in the auditor, Used in Context & state, and the Trace tab. Checking takes about a tenth longer.",
        checked: getPref("audit") === "on",
        onChange: (on) => {
          setPref("audit", on ? "on" : "off");
          handlers.onAudit?.(on);
        },
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
    ...(handlers.account?.()?.available ? [group("Account", ...accountFields(handlers.account()))] : []),
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
        hint: handlers.account?.()?.user
          ? `Removes every proof, snapshot and setting from ${holder} and signs it out. Your account keeps its copy.`
          : `Removes every proof, snapshot and setting from ${holder}. Export first if you want to keep them.`,
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
