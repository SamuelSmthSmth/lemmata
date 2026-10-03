---
name: Lemmata
description: Proof intern — a controlled-natural-language proof checker, typeset like a proof.
colors:
  paper: "#ffffff"
  paper-raised: "#f7f8f9"
  paper-lowered: "#eff1f4"
  rule: "#dde1e6"
  control-border: "#8a909c"
  ink: "#16181d"
  ink-quiet: "#555b6a"
  ink-dim: "#666c7a"
  proof-blue: "#0a5fbf"
  verified-green: "#157333"
  caveat-amber: "#7d4e00"
  error-red: "#be1824"
  night-paper: "#0e1013"
  night-paper-raised: "#15181c"
  night-paper-lowered: "#1a1e23"
  night-rule: "#262b32"
  night-control-border: "#646b77"
  night-ink: "#e6e8ec"
  night-ink-quiet: "#9ba3b0"
  night-ink-dim: "#7f8795"
  night-proof-blue: "#6cb0ff"
  night-verified-green: "#4ab960"
  night-caveat-amber: "#d9a520"
  night-error-red: "#f2645c"
typography:
  title:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.25
  entry-title:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.35
  statement:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  body:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.45
  prose:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  prose-reading:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  verdict:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "1px"
  label:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.09em"
rounded:
  sm: "2px"
  md: "2px"
spacing:
  pane-x: "12px"
  row-y: "8px"
  gutter: "11px"
  page-x: "32px"
  page-y: "28px"
components:
  verdict-valid:
    textColor: "{colors.verified-green}"
    typography: "{typography.verdict}"
    padding: "2px 0 2px 8px"
  verdict-invalid:
    textColor: "{colors.error-red}"
    typography: "{typography.verdict}"
    padding: "2px 0 2px 8px"
  step-row:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.statement}"
    padding: "8px 12px 8px 14px"
  pane-head:
    textColor: "{colors.ink-quiet}"
    typography: "{typography.label}"
    padding: "5px 12px"
    height: "30px"
  note-counterexample:
    backgroundColor: "{colors.error-red}"
    textColor: "{colors.error-red}"
    rounded: "{rounded.sm}"
    padding: "5px 8px"
  app-rail:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink-quiet}"
    width: "44px"
  app-rail-current:
    backgroundColor: "{colors.paper-lowered}"
    textColor: "{colors.proof-blue}"
    rounded: "{rounded.sm}"
    size: "28px"
  reading-pane:
    backgroundColor: "{colors.paper}"
    width: "320px"
  desk-tab:
    textColor: "{colors.ink-quiet}"
    typography: "{typography.label}"
    padding: "0 9px"
  desk-tab-selected:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
  proof-tab-active:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    padding: "0 6px 0 12px"
  status-bar:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink-quiet}"
    height: "24px"
    padding: "0 10px 0 12px"
  text-button:
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "24px"
  text-button-primary:
    textColor: "{colors.proof-blue}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "24px"
  text-button-armed:
    backgroundColor: "{colors.error-red}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    height: "24px"
  icon-button:
    textColor: "{colors.ink-quiet}"
    rounded: "{rounded.sm}"
    size: "24px"
  filter:
    textColor: "{colors.ink-quiet}"
    typography: "{typography.control}"
    padding: "0 10px"
    height: "24px"
  filter-checked:
    textColor: "{colors.proof-blue}"
    typography: "{typography.control}"
    padding: "0 10px"
    height: "24px"
  page-title:
    textColor: "{colors.ink}"
    typography: "{typography.title}"
  button-secondary:
    backgroundColor: "{colors.paper-lowered}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  form-control:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
    height: "28px"
  packs-group-label:
    textColor: "{colors.ink-quiet}"
    typography: "{typography.label}"
  pack-flag:
    textColor: "{colors.proof-blue}"
  pack-title:
    textColor: "{colors.ink}"
    typography: "{typography.entry-title}"
  pack-dialog:
    backgroundColor: "{colors.paper}"
    width: "760px"
---

<!-- Recorded from the shipped build at commit cdd8ca2 (ui/static/styles.css, index.html, js/). Verification at that commit: axe-core reports zero violations on every view, in both themes and at phone width; the impeccable finish review returned "pass with fixes", and all fixes are applied in cdd8ca2. -->
<!-- Pack-manager refinement recorded from the shipped build (606f4ed, fa70b9c) (styles.css, js/library.js, js/pack-author.js, js/explorer.js, index.html #pack-dialog): Library pack rail and pack head, the pack dialog, the control boundary and secondary-button tokens, toast rules, the explorer's pack folder. -->

# Design System: Lemmata

## Overview

**Creative North Star: "The Typeset Proof"**

Lemmata is set the way a printed proof is set, not built the way a dashboard is built. The page is white paper (or near-black at night) divided by hairlines rather than boxes; the formal layer, meaning the proof, its line numbers, the variables, the hypotheses and the verdict, is machine-checked and therefore set in one monospace face, and the only type that breaks that grid is prose: the intern explaining a step, the course notes stating a theorem, the handbook teaching the language. The palette stays almost entirely ink and paper so that status colour means something when it appears.

The system's single idea is that **failure is the event**. A step that verifies is the unremarkable case and gets no box, no fill and no colour. A step that fails gets a 2px rail in the margin, and so does every step after it that rests on it, because those rows are flush and consecutive rails read as one continuous line down the margin. The same rail marks the failing line in the editor gutter, and the verdict in the status bar uses the same rail-and-word language, so the whole interface speaks one dialect.

The app is a study desk, not an IDE: a narrow view rail, a reading pane where the notes stay open beside the proof, and the working panes. Density is high and deliberate: an instrument, not a web page. Corners are near-square, chrome is minimal, and controls are reduced to ink toggles and outlined words so that nothing competes with the verdict a proof produces.

**Key Characteristics:**
- Paper and ink, hairline rules, near-square corners (2px).
- One monospace family for everything formal; system sans only for sentences.
- Status lives in 2px rails and coloured words, never in filled pills or cards.
- The left margin belongs to the failure rail; current-item marks use ink, weight and a lowered fill instead.
- Green appears only in verdicts, so red lands when it does.
- Light and dark are equal citizens, each with its own picked palette.

## Colors

A restrained ink-and-paper system with one blue accent and three status hues used only for status.

### Primary
- **Proof Blue** (proof-blue; night-proof-blue): the accent. The CNL keywords that form a proof's skeleton in the default "mono" syntax scheme, links, focus rings, the caret, selection tints, the current view's icon in the rail, the selected reading-pane tab and the active proof tab's top rule, a checked segment, the primary text button, the "update" flag on a pack with a newer version, and the pending or exercise verdict. Never decorative, and never a standing state: a flag takes the accent only when it is news (an update), so an available pack that is merely not installed carries no flag at all.

### Neutral
- **Paper** (paper; night-paper): the page, the editor, the reading pane, the command palette.
- **Paper Raised** (paper-raised; night-paper-raised): the view rail, the status bar, the arrangement popover, tooltips.
- **Paper Lowered** (paper-lowered; night-paper-lowered): hover and selected rows, the current view's square in the rail, the current pack in the Library and current page in the Guide, switch tracks, and the fill of a secondary (Web Awesome neutral) button.
- **Rule** (rule; night-rule): pane and shell boundaries (the 1px gaps of the layout grid, the rail's and status bar's edges), pane-head underlines, segmented-control dividers.
- **Control Border** (control-border; night-control-border): the one boundary every form control draws, native or Web Awesome; it clears 3:1 on paper and night paper so an empty field is still findable. Never used for layout lines, which stay Rule.
- **Hairline** (ink at 8% over paper): row separators inside panes; organises without drawing boxes.
- **Ink** (ink; night-ink): statements, names, types (separated from keywords by weight, not hue), page titles.
- **Ink Quiet** (ink-quiet; night-ink-quiet): prose explanations, section labels, operators, unselected tabs and controls, ledes.
- **Ink Dim** (ink-dim; night-ink-dim): the quietest text that is still text: line numbers, metadata, the file path, passing statuses, the editor placeholder, glue words and comments. Both quiet steps clear 4.5:1 on every surface they sit on, in both themes.

### Status
- **Verified Green** (verified-green; night-verified-green): verdicts only.
- **Caveat Amber** (caveat-amber; night-caveat-amber): warnings, meaning unresolved domain obligations; an unavailable storage state.
- **Error Red** (error-red; night-error-red): invalid steps, counterexamples, parse errors, a copy that fails, destructive actions. Quiet fills use the same hue at 8–11% alpha.

### Named Rules
**The Green Is Rare Rule.** Green marks a verdict on a whole proof (the status bar, a history bar, an exercise answer, a Library copy that checks, a pack export whose every entry was just checked, a Guide example's expected result) and nowhere else; a passing step's status is set in dim ink. Scarcity is what makes red legible.

**The Real Failure Rule.** Red means something actually failed. A category that merely describes a hazard, such as a Library entry tagged "Trap", is set in quiet ink; red is kept for the student's copy that fails, the step that fails, and the action that destroys.

**The Two Schemes Rule.** Syntax colour has two schemes over one token vocabulary: "mono" (default; keywords take Proof Blue, everything else is ink or recedes into Ink Quiet and Ink Dim) and "vivid" (one hue per category, picked separately for light and dark; comments and glue words stay dim in both). Nothing branches on the scheme except the palette values.

## Typography

**Formal Font:** JetBrains Mono (self-hosted subsets; ui-monospace fallback)
**Prose Font:** the system UI sans stack (-apple-system, Segoe UI, Roboto, …)

**Character:** One working monospace carries every formal mark and every piece of chrome; the sans appears only where something speaks in sentences. There is no display face and no second family to pair.

### Hierarchy
- **Title** (600, 20px, 1.25, mono, no uppercase): page titles in the Library, Guide and Settings. A title, not a label: it outranks the uppercase section labels beneath it.
- **Entry Title** (600, 14px, 1.35, mono): the title of a note open in the reading pane.
- **Statement** (400, 13px, 1.45): proof statements in the auditor and the editor's text; 13px is also the app's base size.
- **Control** (400, 12px): tabs, text buttons, segments, Guide table of contents.
- **Prose** (400, 12px, 1.5, sans): step explanations, editor diagnostics, empty states.
- **Prose Reading** (400, 14px, 1.55–1.65, sans; 15px for the Guide lede): page ledes and the handbook; Library blurbs and pack notes sit a step down at 13px. Ledes hold to about 62ch.
- **Verdict** (700, 11px, 1px tracking, uppercase): the verdict word.
- **Label** (700, 11px, 0.09em tracking, uppercase): pane heads, reading-pane tabs, context sections, the Guide contents heading. Metadata (line numbers, status bar, step status) is 11px unbolded.

The scale is consolidated: 11, 12 and 13px for UI chrome; 13–15px for reading prose (13px in the reading pane and Library, 14–15px on full pages); 20px for page titles. Nothing in the app is set below 11px.

### Named Rules
**The Formal-Mono Rule.** Anything the engine checks, and every piece of chrome, is set in the monospace; only sentences use the sans. No italics: the subsets ship none, and a synthesised slant on a mono face reads as a rendering fault.

**The Labels Are Not Titles Rule.** Uppercase tracking belongs to 11px section labels only. Page and entry titles are mixed-case mono at weight 600.

## Layout

A full-viewport application shell: a 44px view rail on the left (brand mark on top; Workspace, Library, Guide, Settings; the command palette and theme toggle at the foot), the current view beside it, and a 24px status bar across the foot carrying the verdict rail-and-word, the problem button, caret position, file path and storage state. Only one view occupies the grid at a time.

The Workspace is the study desk: a 320px reading pane (Files, Notes, History) beside the work, collapsible to zero. The work column is an open-proof tab strip, a tool strip (symbols, templates, export), then a CSS grid of panes separated by 1px gaps that show the Rule colour through, so pane boundaries are drawn by the grid itself. Panes are placed by slot (`a`, `b`, `c`), and the arrangements rearrange slots without any rule knowing which pane is which; DOM order follows visual order so keyboard and screen-reader order match. Inside a pane: a 30px head (label and rule), then a scroll region. Rows are flush with 8px vertical / 12px horizontal padding and a 22px line-number column.

Library, Guide and Settings are pages: a centred column (1080px max; 720px for narrow pages) with 28px/32px padding, a title and lede, then content. The Library and the Guide each put a sticky list (packs, contents) beside the body.

**Responsive.** Below 1100px the reading pane overlays the work (min(320px, 86vw)) rather than squeezing it, never opens by itself, and a tap on the work puts it away; the Library and Guide side lists fold above the body; the Library's pack rail becomes an auto-fill grid of even columns (minimum 200px) with its group labels and actions spanning every column. Below 760px the rail becomes a 44px bottom bar with labels under each icon (the current view's label in bold), the panes stack and scroll as one page, the symbol strip is hidden, and the status bar keeps only the verdict and the problem button.

**Motion.** Two transitions only: the reading pane collapses by animating the column width (180ms ease), disabled under prefers-reduced-motion; and step rows fade their hover background (0.1s). Nothing animates on load.

## Elevation & Depth

Flat by default. Depth is tonal: paper, raised and lowered surfaces, separated by 1px Rule borders and hairlines. The only shadow in the system is a 1px inset ring marking the selected step, so selection can never be mistaken for a status. Floating layers separate by surface and border alone: the command palette is a paper dialog on a 1px Rule border over a modal scrim (ink at 42%, black at 62% at night); the arrangement popover sits on Paper Raised with a Rule border; the overlaid reading pane keeps its paper and right border. Toasts are flat, with no countdown ring; an info toast carries no edge rule, and only warning and danger toasts keep a 2px rule (the margin belongs to failure). Dialogs (export, pack) separate their footer from the form with a 1px Rule edge, not a fill.

### Named Rules
**The No Boxes Rule.** Organise with hairlines and alignment; never wrap content in cards. A box is reserved for callouts that carry a failure (counterexample, domain warning).

**The Border, Not Shadow Rule.** Anything that floats is told apart by its surface and a 1px border, plus a scrim when it is modal. Never a drop shadow.

## Shapes

Near-square everywhere (2px radius, Web Awesome's radius scale at 0.3). Rules are 1px; status rails, the gutter lint marker, the reading-pane tab underline and the active proof tab's top rule are 2px. The one round form is the 6px status dot on a file tab or tree row, shown only for warning or failure. Keyboard keys (`kbd`) get a 2px bottom border as their only bevel.

### Named Rules
**The Margin Belongs To Failure Rule.** A vertical coloured rule at the left edge of a row means a failure (red) or a caveat (amber), and nothing else. Current items (the rail's view, the Library pack, the Guide page) are marked by ink, weight, accent text or a lowered fill, never by a left rule. Horizontal 2px accent rules mark selected tabs.

**The One Boundary Rule.** Every form control (Web Awesome input, native input, select and textarea alike) draws the same 1px Control Border at 2px radius; focus replaces it with the 2px Proof Blue outline. A field never borrows the Rule colour, which is too faint to find an empty control by.

## Components

### Verdict
A rail and a word: 2px left rail plus an uppercase mono word (VALID, INVALID, PARSE ERROR, TIMEOUT) in the status colour, with tabular metadata (statements, valid count, milliseconds, domain mode) in dim ink beside it. It lives in the status bar. Pending and exercise states show Proof Blue; an outdated verdict dims while a re-check is outstanding.

### Step Row (signature)
A flush grid row: right-aligned dim line number, then the statement in mono with status and backend set as 11px type on the right. Valid rows carry nothing else. Warning and invalid rows get a 2px rail at the left edge; rows downstream of a failure carry the rail at 30% strength. Hover lowers the surface; selection adds the inset ring. The explanation sits beneath in prose; counterexamples and domain warnings are the only boxed callouts, with a quiet status fill and a 2px rail.

### Editor Gutter
Diagnostics wear the auditor's rail: the lint gutter is 8px wide and each marker is a 2px bar (red for error, amber for warning, blue for info). The diagnostic tooltip speaks in prose with a 2px status rail. The placeholder and comments are Ink Dim.

### Pane Head
A label and a rule, with no fill: an uppercase tracked label in quiet ink, optional note in dim ink, tools aligned right, and a 1px Rule underline. A six-dot grip at the left drags the pane to swap slots.

### View Rail
A column of 18px line icons in quiet ink on Paper Raised, 40px targets. The current view is the icon in Proof Blue on a 28px Paper Lowered square. On phones it becomes a bottom bar with an 11px label under each icon; the current label turns bold and the square is dropped.

### Tabs
Two kinds, both without boxes. Reading-pane tabs are 11px uppercase labels; the selected one turns ink and gets a 2px Proof Blue underline. Open-proof tabs are 12px mono names divided by hairlines; the active tab takes the page's paper so it joins the editor below, with a 2px Proof Blue rule along its top, and a status dot when its last check failed or warned.

### Status Bar
24px on Paper Raised with a Rule top edge, 11px tabular text in quiet ink. Left to right: the verdict, a red problem button that jumps to the failure, then caret, path and storage state (amber when storage is unavailable).

### Buttons
The native family, used wherever a Web Awesome button would be heavier than the job:
- **Icon button:** 24px square, plain, quiet ink with a 14px inline SVG; ink on a lowered fill on hover.
- **Text button:** 24px tall, 12px mono, ink on no fill, lowered fill on hover. **Primary** is Proof Blue text on a 45% Proof Blue outline. **Danger** is red text. **Armed** (the second click of a two-click confirm) fills solid red with paper text.
- **Secondary (Web Awesome):** dialog actions that are not the primary one sit on Paper Lowered with ink text, not on a tinted chip.
- **Focus:** a 2px Proof Blue outline inset by 2px on every native control.

### Segmented Control
One outlined strip of 24px segments divided by Rule lines; 12px mono, quiet ink. The checked segment is Proof Blue text on the quiet blue fill. Used for the Library filters and every choice in Settings.

### Toggles and Web Awesome
Switches are reduced to ink toggles (square track, no hue) so they never outshout the verdict. Web Awesome supplies the switch, dropdown, input, dialog, tooltip, popup and toast, styled only through the token layer and exported parts; the app's own icons are inline SVG.

### Pack Manager (Library)
The Library's side list is a pack manager, still set as a list rather than cards. At its top, quiet text buttons ("Install from file…", "New pack…"); then two groups under 11px uppercase labels, Installed and Available, set apart by space alone. When updates exist, the Installed label carries a primary text button ("Update all N") on its right. Each pack row is its code, its title in prose and its entry count; a pack with a newer version adds the word "update" in Proof Blue beneath, never a badge.

The open pack's head is its title in Entry Title type, a 12px mono meta line in quiet ink (version · authors · licence · entry count, tabular), the prose summary, then a row of text buttons pulled left by the buttons' own padding so the first word aligns with the title. "Check all entries" reports in one prose line, quiet while every entry still gives its recorded verdict and red only when one drifts; each entry then carries a word tag, "as recorded" in dim ink or "now X, pack says Y" in red.

### Pack Dialog
A pack's details open in a paper dialog up to 760px wide. Fields sit in a two-column grid (one column on phones) under 11px uppercase legends; each entry is a hairline-divided row of its file name and the cells it is listed under. All inputs share the One Boundary. The footer sits below a 1px Rule edge and holds a prose status line (quiet while checking, red for problems, green for an export whose entries all checked) above the secondary install and primary export buttons. In the explorer, a folder that is a pack shows the word "pack" in 11px dim ink after its name, and its row actions gain a "Pack details" box icon drawn in the same 16px stroke family as rename and delete.

### Notes Entry
The reading pane's Notes tab: a dim source reference, the entry title in 14px mono 600, the statement in 13px prose, then the student's answer as a rail and a sentence (green when right, red when wrong).

### Exercise Mode
While an exercise is open and uncommitted, every verdict signal is withheld: step status, messages, rails, counterexample callouts, the report verdict and the open file's status dot. Statements remain, and the status bar verdict shows the exercise state in Proof Blue.

### Browser Surfaces
The parts the page did not draw are themed too: text selection takes the Proof Blue selection tint, the caret and native accent colour are Proof Blue, scrollbars are ink at 22% on a transparent track, and links underline at 1px with a 0.18em offset.

## Do's and Don'ts

### Do:
- **Do** let a failing step's 2px rail and red word carry the page; keep everything that verified quiet.
- **Do** set every checked artefact (statements, names, types, verdicts, line numbers) and all chrome in JetBrains Mono, and every sentence in the system sans.
- **Do** separate regions with 1px Rule/Hairline lines and tonal surfaces, not containers.
- **Do** mark a current item with ink, weight, accent text or a Paper Lowered fill; mark a selected tab with a horizontal 2px accent rule.
- **Do** define colour once in the `--wa-*` token layer and alias it; light and dark each get picked values, and quiet text clears 4.5:1 on every surface.
- **Do** keep corners at 2px and status rails at 2px.
- **Do** use the segmented control for a choice among a few options, and the native text and icon buttons for actions.
- **Do** give every form control the one Control Border, and give a flag the accent only when it is news.

### Don't:
- **Don't** use green anywhere but a verdict.
- **Don't** use red for anything that has not actually failed or will not actually destroy.
- **Don't** draw a vertical coloured rule at the left of a row for anything but failure or caveat.
- **Don't** wrap rows in cards, give passing steps badges, or use filled status pills.
- **Don't** introduce a display face, italics, a second sans, or text below 11px.
- **Don't** add drop shadows; floating layers separate by surface and border, and the selected-row inset ring is the only shadow.
- **Don't** fetch anything cross-origin (icons, fonts, scripts): the app makes no runtime network requests.
