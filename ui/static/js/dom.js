// Every element the UI reaches for, looked up once at import time.
//
// Module scripts are deferred until the document is parsed, and the entry
// point is loaded at the end of <body>, so these are all present by now.
// layout.js looks its own controls up itself: it has to stay importable in
// Node, where this module cannot be evaluated.

const byId = (id) => document.getElementById(id);

export const dom = {
  // Shell
  railButtons: [...document.querySelectorAll(".rail-button[data-view]")],
  views: {
    workspace: byId("view-workspace"),
    library: byId("view-library"),
    guide: byId("view-guide"),
    settings: byId("view-settings"),
  },
  themeToggle: byId("theme-toggle"),
  paletteOpen: byId("palette-open"),

  // Reading pane
  desk: byId("desk"),
  deskTabs: [...document.querySelectorAll(".desk-tab")],
  deskPanels: {
    files: byId("desk-files"),
    notes: byId("desk-notes"),
    history: byId("desk-history"),
  },
  deskCollapse: byId("desk-collapse"),
  deskOpen: byId("desk-open"),
  explorer: byId("explorer"),
  fileNew: byId("file-new"),
  folderNew: byId("folder-new"),
  workspaceImport: byId("workspace-import"),
  workspaceImportInput: byId("workspace-import-input"),
  workspaceExport: byId("workspace-export"),
  notes: byId("notes"),

  // History (inside the reading pane)
  historyPanel: byId("history-panel"),
  timeline: byId("timeline"),
  timelineNote: byId("timeline-note"),
  snapshots: byId("snapshots"),
  snapshotNow: byId("snapshot-now"),
  copyLink: byId("copy-link"),
  resetWorkspace: byId("reset-workspace"),
  clearHistory: byId("clear-history"),

  // Working pane
  tabs: byId("tabs"),
  templatesMenu: byId("templates-menu"),
  symbols: byId("symbols"),
  strict: byId("strict"),
  syntaxToggle: byId("syntax-toggle"),
  downloadProof: byId("download-proof"),
  editorPath: byId("editor-path"),
  exerciseBanner: byId("exercise-banner"),
  editor: byId("editor"),
  welcome: byId("welcome"),
  audit: byId("audit"),
  context: byId("context"),
  contextSub: byId("context-sub"),

  // Library
  librarySearch: byId("library-search"),
  libraryFilters: byId("library-filters"),
  libraryPacks: byId("library-packs"),
  libraryList: byId("library-list"),

  // Guide and settings
  guideToc: byId("guide-toc"),
  guideArticle: byId("guide-article"),
  settingsForm: byId("settings-form"),

  // Status bar
  verdict: byId("verdict"),
  verdictMeta: byId("verdict-meta"),
  statusProblem: byId("status-problem"),
  statusPos: byId("status-pos"),
  statusFile: byId("status-file"),
  statusStorage: byId("status-storage"),

  // Overlays
  dropOverlay: byId("drop-overlay"),
  toast: byId("toast"),
  palette: byId("palette"),
  paletteInput: byId("palette-input"),
  paletteList: byId("palette-list"),

  // LaTeX & PDF export dialog.  <wa-dialog> supplies its own close button and
  // light-dismiss, so there is no close element to wire up.
  exportLatex: byId("export-latex"),
  latexDialog: byId("latex-dialog"),
  latexStandalone: byId("latex-standalone"),
  latexBreakdown: byId("latex-breakdown"),
  latexOutput: byId("latex-output"),
  copyLatex: byId("copy-latex"),
  downloadTex: byId("download-tex"),
  downloadPdf: byId("download-pdf"),

  // "Show in Lean": the proof beside its Lean 4 skeleton.
  showLean: byId("show-lean"),
  leanDialog: byId("lean-dialog"),
  leanUntranslated: byId("lean-untranslated"),
  leanTable: byId("lean-table"),
  leanRows: byId("lean-rows"),
  copyLean: byId("copy-lean"),
  downloadLean: byId("download-lean"),
  openLean: byId("open-lean"),
};
