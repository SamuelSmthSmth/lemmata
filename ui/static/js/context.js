// The Context & state pane: what the proof intern knows at the selected step.
//
// Every render here reads from the already-fetched report, so selecting a step
// never re-runs SymPy or Z3.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { bulletList, chipList, el, note, section, splitStepText } from "./format.js";

let handlers = {};

/** `{onFix(fix), onOpenCited(citation)}`: what the pane's buttons do (main.js). */
export function setContextHandlers(next) {
  handlers = next;
}

function textButton(label, tone, onClick) {
  const button = el("button", `text-button${tone === "primary" ? " text-button--primary" : ""}`, label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

/** "What to try": each hint, and its fix as the one action beside it. */
function hintSection(hints) {
  return section(
    "What to try",
    hints.map((hint) => {
      const item = el("div", "ctx-hint");
      item.append(el("p", null, hint.message));
      if (hint.fix) item.append(textButton(hint.fix.label, "primary", () => handlers.onFix?.(hint.fix)));
      return item;
    }),
  );
}

/** "Cited result": what the step leaned on, and the way back to it. */
function citationSection(citation) {
  const item = el("div", "ctx-cite");
  item.append(el("p", "ctx-cite-name", citation.label));
  item.append(el("code", "ctx-cite-claim", citation.claim));
  const inPack = citation.key.startsWith("@");
  item.append(textButton(inPack ? "Open in the Library" : "Open the file", "", () => handlers.onOpenCited?.(citation)));
  return section("Cited result", [item]);
}

export function renderContext() {
  dom.context.replaceChildren();

  if (state.data && state.data.parse_error) {
    dom.contextSub.textContent = "Unavailable";
    dom.context.append(
      el("p", "ctx-empty", "The document does not parse, so no proof state is available."),
    );
    return;
  }

  const entry =
    state.selected !== null && state.selected < state.steps.length
      ? state.steps[state.selected]
      : null;

  if (!entry) {
    dom.contextSub.textContent = "What the intern knows";
    dom.context.append(
      el(
        "p",
        "ctx-empty",
        state.steps.length
          ? "Click a line in the proof, click a step in the auditor, or use the arrow keys — the proof state at that point shows up here."
          : "Nothing to inspect yet.",
      ),
    );
    return;
  }

  const result = entry.result;
  dom.contextSub.textContent = `Line ${result.line ?? "?"}`;
  dom.context.append(el("p", "ctx-title", result.statement));

  // An unanswered exercise: what is known at this line, but not whether it holds.
  if (document.body.dataset.exercise === "hidden") {
    dom.context.append(
      el("p", "ctx-empty", "Verdicts are hidden until you choose the line you think fails."),
      section("Declared variables & types", [chipList(Object.entries(result.active_variables), "No variables in scope.")]),
      section("Active hypotheses & derived facts", [bulletList(result.active_hypotheses, "No hypotheses in scope.")]),
    );
    return;
  }

  const facts = el("dl", "ctx-facts");
  const addFact = (label, value) => {
    facts.append(el("dt", null, label), el("dd", null, value));
  };
  addFact("status", result.status);
  addFact("backend", result.backend);
  addFact("scope depth", result.scope_depth);
  if (entry.theoremName) addFact("theorem", entry.theoremName);
  dom.context.append(facts);

  // The same de-duplication the auditor does, so a failure is not stated twice
  // in the same pane.
  const { message, callouts } = splitStepText(result);
  const verificationNodes = [];
  if (message) verificationNodes.push(el("p", "ctx-empty", message));
  for (const { text, className } of callouts) {
    // Domain obligations have their own section further down this pane.
    if (className === "note--domain") continue;
    verificationNodes.push(note(null, text, className));
  }
  if (verificationNodes.length) dom.context.append(section("Verification", verificationNodes));
  // The reason before the remedy: an unresolved obligation is what "What to
  // try" answers, so it comes first, where Verification is for a failed step.
  // When a hint already says what the obligation needs (and where it fails),
  // the full obligation box would only repeat the auditor's; the hint is the
  // reason and the remedy together.
  const hintCoversDomain = (result.hints ?? []).some((h) => h.fix?.insert_before);
  if (result.domain_warnings.length && !hintCoversDomain) {
    dom.context.append(
      section(
        "Domain obligations",
        // No label: the warning already begins "Unresolved domain obligation: …".
        result.domain_warnings.map((warning) => note(null, warning, "note--domain")),
      ),
    );
  }
  if (result.hints?.length) dom.context.append(hintSection(result.hints));
  if (result.citation) dom.context.append(citationSection(result.citation));

  if (result.subproof_metadata) {
    const meta = result.subproof_metadata;
    const subNodes = [
      el(
        "p",
        "ctx-empty",
        // No tick/cross glyphs: the vendored latin subset has no U+2713 or
        // U+274C, so they would fall back to another face mid-sentence.  The
        // words carry it, and the status colour does the rest.
        `${meta.label || meta.kind} (${meta.step_count} inner steps): ${meta.all_steps_valid ? "all steps verified" : "contains an invalid step"}`,
      ),
    ];
    if (meta.case_condition) {
      subNodes.push(note("condition", meta.case_condition, "note--domain"));
    }
    dom.context.append(section("Subproof structure", subNodes));
  }

  dom.context.append(
    section("Declared variables & types", [
      chipList(Object.entries(result.active_variables), "No variables in scope."),
    ]),
  );

  dom.context.append(
    section("Active hypotheses & derived facts", [
      bulletList(result.active_hypotheses, "No hypotheses in scope."),
    ]),
  );
}
