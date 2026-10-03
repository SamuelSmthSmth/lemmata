// The Notes panel: what sits beside the proof.
//
// For a file opened from the Library it is that entry: the module code, the
// notes' reference, the title, and (for a trap) the exercise and, once the
// student has committed to a line, the explanation.  Otherwise it can hold a
// page pinned from the Guide.  The exercise state itself lives on the file
// (`file.exercise`), so it survives a reload.

import { el } from "./format.js";
import { packLabel } from "./packs.js";

let handlers = {};

export function initNotes(actions) {
  handlers = actions;
}

function action(label, onClick, tone = "") {
  const b = el("button", `text-button${tone ? ` text-button--${tone}` : ""}`, label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

/**
 * Render the panel.
 *  - `found`: {pack, entry} for the active file's origin, or null
 *  - `file`: the active file
 *  - `pinned`: {title, node} for a pinned guide page, or null
 */
export function renderNotes({ found, file, pinned }) {
  const root = document.getElementById("notes");
  root.replaceChildren();

  if (found && file) {
    const { pack, entry } = found;
    const chapter = pack.chapters.find((c) => c.id === entry.chapter);
    const card = el("article", "note-entry");
    // The notes' own numbering is the heading; where it comes from follows it.
    card.append(el("h2", "note-ref", entry.ref));
    card.append(el("p", "note-title", entry.title));
    card.append(el("p", "note-source", `${packLabel(pack) === pack.title ? pack.title : `${packLabel(pack)} ${pack.title}`}${chapter ? ` · ${chapter.title}` : ""}`));
    if (entry.blurb) card.append(el("p", "note-text", entry.blurb));

    if (entry.kind === "trap") {
      const exercise = file.exercise ?? null;
      if (exercise && !exercise.revealed) {
        card.append(
          el("p", "note-text", "One step of this proof does not hold. Read it, then click the line you think fails — in the editor or in the auditor — and choose it below."),
        );
        const pick = el("div", "note-pick");
        pick.append(el("span", "note-pick-label", exercise.guess ? `Your answer: line ${exercise.guess}` : "No line chosen yet"));
        pick.append(action("Choose the caret's line", () => handlers.onGuess?.(), "primary"));
        pick.append(action("Show the answer", () => handlers.onReveal?.()));
        card.append(pick);
      } else {
        if (exercise?.revealed) {
          const right = exercise.correct;
          card.append(
            el(
              "p",
              `note-verdict ${right ? "is-right" : "is-wrong"}`,
              exercise.guess == null
                ? `The step that fails is on line ${exercise.answer ?? "?"}.`
                : right
                  ? `Line ${exercise.guess} — that is the step that fails.`
                  : `Not line ${exercise.guess}: the step that fails is on line ${exercise.answer ?? "?"}.`,
            ),
          );
        }
        card.append(el("h3", "note-subhead", "Why it fails"));
        card.append(el("p", "note-text", entry.explanation));
        if (exercise?.revealed) card.append(action("Try it again", () => handlers.onRetry?.()));
      }
    }
    const tools = el("div", "note-tools");
    tools.append(action("Find in the Library", () => handlers.onShowInLibrary?.(pack, entry)));
    tools.append(action("Start a fresh copy", () => handlers.onFresh?.(pack, entry)));
    card.append(tools);
    root.append(card);
  }

  if (pinned) {
    const page = el("article", "note-pinned");
    const head = el("div", "note-pinned-head");
    head.append(el("h2", "note-ref", pinned.title), action("Unpin", () => handlers.onUnpin?.()));
    page.append(head, pinned.node);
    root.append(page);
  }

  if (!found && !pinned) {
    const empty = el("div", "notes-empty");
    empty.append(
      el("p", null, "Nothing beside this proof yet."),
      el("p", "notes-empty-sub", "Open an entry from the Library to keep its statement here while you work, or pin a page of the Guide."),
    );
    empty.append(action("Browse the Library", () => handlers.onBrowse?.()));
    root.append(empty);
  }
}
