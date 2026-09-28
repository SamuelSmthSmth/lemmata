// The Context & state pane: what the proof intern knows at the selected step.
//
// Every render here reads from the already-fetched report, so selecting a step
// never re-runs SymPy or Z3.

import { dom } from "./dom.js";
import { state } from "./state.js";
import { bulletList, chipList, el, note, section } from "./format.js";

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

  const verificationNodes = [];
  if (result.message) verificationNodes.push(el("p", "ctx-empty", result.message));
  if (result.counterexample) {
    verificationNodes.push(note("counterexample", result.counterexample, "note--counterexample"));
  }
  dom.context.append(section("Verification", verificationNodes));

  if (result.subproof_metadata) {
    const meta = result.subproof_metadata;
    const subNodes = [
      el(
        "p",
        "ctx-empty",
        `${meta.label || meta.kind} (${meta.step_count} inner steps): ${meta.all_steps_valid ? "all steps verified ✓" : "contains invalid steps ❌"}`,
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
        result.domain_warnings.map((warning) => note("unresolved", warning, "note--domain")),
      ),
    );
  }
}
