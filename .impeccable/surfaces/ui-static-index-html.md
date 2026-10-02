---
version: 1
slug: "ui-static-index-html"
primary_target: "ui/static/index.html"
related_targets: []
---

# Surface: the Aether app (ui/static/index.html)

Scope: the whole single-page app — Workspace, Library, Guide, Settings. Visitor mode: **Operate**.
Audience and job: an undergraduate writing and checking a proof from their module's notes, at a desk, one proof or sheet at a time.
Task: write the proof, see which step fails and why, inspect the proof state, fix, export. Frequent and long; keyboard-heavy.
Content: the student's own files; course-pack entries (MTH2008, MTH2010, Notation) with references and trap explanations; the handbook.
Constraints: keep the incumbent world (DESIGN.md, "The Typeset Proof"); no build step; no runtime network; every view keyboard-operable; light and dark.
Chosen structure: **Notes Beside the Proof** (code-led; locked by the user).
Memorable moment: the entry from the notes ("Example 2.18 — Limits at infinity") open on the left, the student's proof on the right, and the one failing line carrying its rail in both the editor gutter and the auditor.
Unresolved: none.

## Direction contract

THESIS: A study desk, not an IDE — the notes stay open beside the proof. It refuses the category default of a file-tree IDE where reference material lives in another tab and the auditor is a dashboard.

OWN-WORLD: Paper and ink divided by 1px hairlines; JetBrains Mono for everything checked, system sans only for the intern's and the notes' sentences; Proof Blue for keywords and focus only; green only in the verdict; failure as a 2px red rail; 2px corners; no cards, no shadows but the selected-row ring.

STORY: The student opens a pack entry or their own file; reads the statement and hint on the left; writes on the right; the gutter and auditor mark the first broken step with its counterexample; they fix it, see VALID in the status bar, and export or move to the next entry.

FIRST VIEWPORT: Left, a 44px rail (Workspace, Library, Guide, Settings; brand mark on top). Then a 320px reading pane with Files · Notes · History tabs (collapsible to zero). Then the working pane: tab strip, a tool strip (symbols, templates, export), the editor filling the upper ~60%, the auditor below-left and the context strip below-right. A 24px status bar spans the foot: verdict rail-and-word, file path, line:col, strict mode, storage state. Primary action: typing; the verdict is the primary readout.

FORM: Notes Beside the Proof — position 4 on the ranked structure list; seed key 51f8065c. Signature interaction: choosing a Library entry opens it beside a fresh copy of its proof in one move; the failing line is marked in gutter, auditor and status bar at once. Motion: 150–200 ms state transitions only; pane collapse slides; nothing on load.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
