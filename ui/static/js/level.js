// The checking level: how big a step the proof kernel accepts as one line.
//
// Each proof keeps its own level, as it keeps Strict domains and Show
// working; Settings chooses the level of new proofs.  "Off" checks as the
// engine always has: every true line passes.  The others are the kernel's
// levels (aether.kernel.policy): a line that is true but needs more than the
// level allows (a quantified statement decided in one line, a divisibility
// by checking remainders, at Exam an evaluation not worked) is refused, with
// what to write instead, and a line that cites its premises may use only
// those.

import { dom } from "./dom.js";
import { el } from "./format.js";
import { getPref } from "./prefs.js";

export const LEVELS = [
  { id: "off", label: "Off", detail: "Every true line passes, however big the step." },
  { id: "exam", label: "Exam", detail: "No leaps; a derivative, limit or sum is worked, not written down." },
  { id: "course", label: "Course", detail: "No leaps; standard results may be written down, as the notes do." },
  { id: "scratch", label: "Scratch", detail: "Anything the solvers decide; a citation still means what it says." },
];

const IDS = new Set(LEVELS.map((l) => l.id));
let current = "off";

/** A stored or linked level, checked: anything unknown is the default. */
export function validLevel(id, fallback = defaultLevel()) {
  return IDS.has(id) ? id : fallback;
}

export function defaultLevel() {
  return getPref("levelDefault");
}

export function getLevel() {
  return current;
}

/** The level a proof is checked at.  Every proof made since levels exist
 *  stores one (the Settings default when it was made); a proof without one
 *  was made before them and was checked without the kernel, so it stays Off
 *  rather than taking today's default and turning red unasked. */
export function levelOf(file) {
  return validLevel(file?.level, "off");
}

/** What the API's `kernel` field takes: null for Off. */
export function kernelFor(level) {
  return level === "off" ? null : level;
}

export function setLevel(id) {
  current = validLevel(id);
  const level = LEVELS.find((l) => l.id === current);
  dom.levelButton.textContent = `Level: ${level.label}`;
  dom.levelButton.dataset.level = current;
  for (const item of dom.levelMenu.querySelectorAll("wa-dropdown-item")) {
    item.checked = item.value === current;
  }
  // Exam already refuses what Show working would warn about (a derivative,
  // limit or sum written down, a divisibility by remainders), so at Exam the
  // switch says so and stands aside; the proof keeps its own setting for the
  // other levels.
  const exam = current === "exam";
  dom.working.disabled = exam;
  dom.workingTip.textContent = exam
    ? "The Exam level already asks for the working: a step that skips it is refused"
    : "A step that skips the working a question asks for (the product rule, a sum's closed form) gets a warning";
}

/** Fill the menu; *onChange* runs after the user picks a level. */
export function initLevelMenu(onChange) {
  for (const level of LEVELS) {
    const item = document.createElement("wa-dropdown-item");
    item.type = "checkbox";
    item.value = level.id;
    item.append(document.createTextNode(level.label));
    const detail = el("span", "dropdown-detail", level.detail);
    detail.slot = "details";
    item.append(detail);
    dom.levelMenu.append(item);
  }
  dom.levelMenu.addEventListener("wa-select", (event) => {
    const id = event.detail?.item?.value;
    if (!id || id === current) {
      setLevel(current); // a checkbox item toggles itself; put the mark back
      return;
    }
    setLevel(id);
    onChange(id);
  });
  setLevel(current);
}
