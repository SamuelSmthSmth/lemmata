// The Context & state pane: what the proof intern knows at the selected step.
//
// Every render here reads from the already-fetched report, so selecting a step
// never re-runs SymPy or Z3.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { bulletList, chipList, el, note, section, splitStepText } from "./format.js";

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
  dom.context.append(section("Verification", verificationNodes));

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

  if (result.domain_warnings.length) {
    dom.context.append(
      section(
        "Domain obligations",
        // No label: the warning already begins "Unresolved domain obligation: …".
        result.domain_warnings.map((warning) => note(null, warning, "note--domain")),
      ),
    );
  }
}
