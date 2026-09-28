// Every element the UI reaches for, looked up once at import time.
//
// Module scripts are deferred until the document is parsed, and the entry
// point is loaded at the end of <body>, so these are all present by now.

export const dom = {
  verdict: document.getElementById("verdict"),
  verdictMeta: document.getElementById("verdict-meta"),
  strict: document.getElementById("strict"),
  examples: document.getElementById("examples"),
  blurb: document.getElementById("example-blurb"),
  audit: document.getElementById("audit"),
  context: document.getElementById("context"),
  contextSub: document.getElementById("context-sub"),
  themeToggle: document.getElementById("theme-toggle"),

  // Workspace panel. The panel is the content of a <wa-popup>, which owns the
  // anchoring and the `active` flag that used to be a `hidden` boolean.
  historyToggle: document.getElementById("history-toggle"),
  historyPopup: document.getElementById("history-popup"),
  historyPanel: document.getElementById("history-panel"),
  historyClose: document.getElementById("history-close"),
  timeline: document.getElementById("timeline"),
  timelineNote: document.getElementById("timeline-note"),
  snapshots: document.getElementById("snapshots"),
  snapshotNow: document.getElementById("snapshot-now"),
  copyLink: document.getElementById("copy-link"),
  resetWorkspace: document.getElementById("reset-workspace"),
  clearHistory: document.getElementById("clear-history"),
  downloadProof: document.getElementById("download-proof"),

  // File drop + notifications
  dropOverlay: document.getElementById("drop-overlay"),
  toast: document.getElementById("toast"),

  // LaTeX & PDF Export dialog
  exportLatex: document.getElementById("export-latex"),
  // <wa-dialog> supplies its own close button and light-dismiss, so there is
  // no dialog-close element to wire up any more.
  latexDialog: document.getElementById("latex-dialog"),
  latexStandalone: document.getElementById("latex-standalone"),
  latexOutput: document.getElementById("latex-output"),
  copyLatex: document.getElementById("copy-latex"),
  downloadTex: document.getElementById("download-tex"),
  downloadPdf: document.getElementById("download-pdf"),
};
