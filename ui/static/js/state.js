// The UI's mutable state, in one place.
//
// `state` is exported as a single object and mutated in place rather than
// reassigned, so every module can hold the same reference.

export const state = {
  data: null,
  steps: [],
  selected: null,
  seq: 0,
  controller: null,
  timer: null,
  saveTimer: null,
  // Which bundled example the buffer came from, so its blurb can come back
  // after a reload.  Null once the buffer has been edited into something else.
  exampleId: null,
};

// Keyed by example id, filled by loadExamples().
export const examplesById = new Map();

// The auditor renders reports as one flat list of steps, so selections can be
// addressed by a single index.
export function flatten(data) {
  const flat = [];
  for (const report of data.reports) {
    for (const result of report.results) {
      flat.push({ result, theoremName: report.theorem_name });
    }
  }
  return flat;
}
