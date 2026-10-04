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
  night-proof-blue-fill: "#1f6feb"
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
  specimen:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "clamp(2.25rem, 10.3vw, 10rem)"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.04em"
  specimen-tail:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "clamp(1.05rem, 2.6vw, 2rem)"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  site-page-title:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "clamp(2rem, 4vw, 3rem)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  site-headline:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "clamp(1.75rem, 3.2vw, 2.5rem)"
    fontWeight: 600
    lineHeight: 1.12
    letterSpacing: "-0.02em"
  site-body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  site-lede:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  registry-page-title:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "clamp(1.75rem, 3vw, 2.25rem)"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  registry-chapter:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "-0.02em"
  registry-entry-title:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  registry-body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  wordmark:
    fontFamily: "Lemmata Wordmark, Latin Modern Math, Cambria Math, serif"
    fontSize: "1.5em"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0"
rounded:
  sm: "2px"
  md: "2px"
spacing:
  pane-x: "12px"
  row-y: "8px"
  gutter: "11px"
  page-x: "32px"
  page-y: "28px"
  site-page: "1200px"
  site-gutter: "clamp(16px, 4vw, 32px)"
  registry-rail: "288px"
  registry-main: "980px"
  registry-main-x: "clamp(20px, 4vw, 56px)"
  registry-key: "10rem"
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
  app-rail-mark:
    textColor: "{colors.ink}"
    typography: "{typography.wordmark}"
    rounded: "{rounded.sm}"
    size: "32px"
  app-rail-mark-hover:
    backgroundColor: "{colors.paper-lowered}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    size: "32px"
  app-icon:
    backgroundColor: "{colors.proof-blue}"
    textColor: "{colors.paper}"
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
  site-nav:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-quiet}"
    height: "60px"
  site-wordmark:
    textColor: "{colors.ink}"
    typography: "{typography.wordmark}"
  site-specimen:
    textColor: "{colors.ink}"
    typography: "{typography.specimen}"
  site-button-primary:
    backgroundColor: "{colors.proof-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "32px"
  site-button-primary-large:
    backgroundColor: "{colors.proof-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "0 20px"
    height: "44px"
  site-button-outline:
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 20px"
    height: "44px"
  site-button-quiet:
    backgroundColor: "{colors.paper-lowered}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "28px"
  audit-row:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "9px 12px 9px 14px"
  glyph-cell:
    textColor: "{colors.ink}"
    padding: "18px 16px 16px"
  glyph-cell-lit:
    textColor: "{colors.proof-blue}"
    padding: "18px 16px 16px"
  storage-notice:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink-quiet}"
    rounded: "{rounded.sm}"
    padding: "10px 10px 10px 16px"
    width: "min(640px, calc(100% - 32px))"
  command-block:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "12px 12px 12px 16px"
  doc-column:
    backgroundColor: "{colors.paper}"
    width: "760px"
  registry-top-bar:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink-quiet}"
    height: "56px"
    padding: "0 20px"
  registry-rail:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    width: "288px"
  registry-rail-pack:
    textColor: "{colors.ink}"
    padding: "8px 16px"
  registry-rail-pack-current:
    backgroundColor: "{colors.paper-lowered}"
    textColor: "{colors.proof-blue}"
    padding: "8px 16px"
  registry-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "34px"
  registry-button-primary:
    backgroundColor: "{colors.proof-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "34px"
  registry-button-outline:
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "34px"
  registry-entry-key:
    textColor: "{colors.ink-quiet}"
    padding: "10px 16px 10px 0"
    width: "10rem"
  registry-entry-key-lit:
    textColor: "{colors.proof-blue}"
    padding: "10px 16px 10px 0"
    width: "10rem"
  registry-entry-title:
    textColor: "{colors.ink}"
    typography: "{typography.registry-entry-title}"
  registry-source:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.statement}"
    rounded: "{rounded.sm}"
    padding: "10px 14px 10px 0"
  step-hint:
    textColor: "{colors.ink}"
    typography: "{typography.prose}"
  diagnostic-action:
    textColor: "{colors.proof-blue}"
    typography: "{typography.control}"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "24px"
  cited-result-name:
    textColor: "{colors.ink}"
  cited-result-claim:
    textColor: "{colors.ink-quiet}"
    typography: "{typography.control}"
---

<!-- Recorded from the shipped build at commit cdd8ca2 (ui/static/styles.css, index.html, js/). Verification at that commit: axe-core reports zero violations on every view, in both themes and at phone width; the impeccable finish review returned "pass with fixes", and all fixes are applied in cdd8ca2. -->
<!-- Pack-manager refinement recorded from the shipped build (606f4ed, fa70b9c) (styles.css, js/library.js, js/pack-author.js, js/explorer.js, index.html #pack-dialog): Library pack rail and pack head, the pack dialog, the control boundary and secondary-button tokens, toast rules, the explorer's pack folder. -->
<!-- Public site recorded from the shipped build in web/ (assets/site.css, assets/site.js, index.html, partials/, download/, privacy/, terms/, cookies/; screenshots in .impeccable/review/), after the impeccable finish review returned "ship" following one fix batch. An extension of this world, not a new one: every site colour is one of the app's tokens with the same light/dark pairs. Site entries are marked "Public site" below; the app's sections are unchanged. Also recorded: the JetBrains Mono math subset (ui/vendor_fonts.py, ui/static/fonts.css). -->
<!-- Pack registry site recorded from the shipped build in the sibling repo lemmata-packs (tools/pages.py, web/shell.html, web/publish.html, web/assets/site.css, web/assets/site.js, web/assets/fonts/; screenshots in .impeccable/review/packs/), after the impeccable finish review returned "ship" following two fix rounds. Direction: .impeccable/surfaces/registry-index-html.md ("The Library, Online"), with one accepted amendment: entry keys are quiet ink at rest and take Proof Blue only when lit. An extension of this world: every colour is one of the app's tokens with the same light/dark pairs, and the fonts are the app's own subsets. Registry entries are marked "Pack registry site" below; nothing above them changed. -->

<!-- Hints, fixes and citations recorded from the shipped build (ui/static/js/audit.js, context.js, lint.js, fixes.js; ui/static/aether-language.js; styles.css .step-hint, .ctx-hint, .ctx-cite*, .cm-diagnosticAction, .statusbar .verdict-block; screenshots in .impeccable/review/hints/), after the impeccable finish review returned "ship" following two fix rounds. An ordinary extension of the Workspace: new entries are "Hints and Fixes" and "Cited Result" under Components, a sentence on the Status Bar, the Named Once Rule, and their Do's and Don'ts; nothing else changed. -->

<!-- Wordmark and icon recorded from the shipped build (ui/static/fonts.css, ui/vendor_fonts.py, vendor/fonts/latinmodern-wordmark.woff2; ui/build_site.py wordmark(); web/partials/nav.html and footer.html; web/assets/site.css .wm*, site.js; ui/static/index.html, styles.css .rail-mark, js/site.js; ui/static/icon.svg, desktop/icon.svg; lemmata-packs web/shell.html; screenshots in .impeccable/review/wordmark/). An approved brand change requested by the user: there is no logo; the name, typeset as LaTeX sets it, is the mark. The icon is the open tombstone. -->

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
- No logo: the name, typeset as LaTeX sets it ($L\text{emma}t\alpha$), is the mark.

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

### Public site
The site uses the app's palette, light and dark pairs alike, under its own short names (`--accent`, `--invalid`, `--caveat`, …). Three values it names are the app's own, mirrored rather than invented: Caveat Amber's quiet fill (amber at 10%, 13% at night) behind a domain-obligation callout; the modal scrim (ink at 42%, black at 62% at night) behind the open phone menu; and **Proof Blue Fill** (proof-blue by day; night-proof-blue-fill, the app's Web Awesome loud brand fill, at night), the ground of a filled primary button with paper text, because the light night accent cannot carry white text. Green is defined but appears nowhere on the site: no proof there is a whole verdict.

### Pack registry site
The registry (the packs catalogue, a page per pack, the publishing guide) uses the same tokens under the public site's short names, with Proof Blue Fill for its filled buttons. Proof Blue carries the course code in a pack's title, links, the current pack's title in the rail, a lit entry key, and the skeleton keywords of an opened proof; a targeted entry row also takes the quiet blue fill (blue at 8%, 10% at night). Verified Green appears once per page as one word: "Verified" on a pack's verification line, "verified" in the catalogue's figures line, a verdict on the whole pack or the whole registry. There is no red anywhere: a trap is a description, set in bold quiet ink, and nothing on the registry has failed.

### Named Rules
**The Green Is Rare Rule.** Green marks a verdict on a whole proof (the status bar, a history bar, an exercise answer, a Library copy that checks, a pack export whose every entry was just checked, a Guide example's expected result) and nowhere else; a passing step's status is set in dim ink. Scarcity is what makes red legible.

**The Real Failure Rule.** Red means something actually failed. A category that merely describes a hazard, such as a Library entry tagged "Trap", is set in quiet ink; red is kept for the student's copy that fails, the step that fails, and the action that destroys.

**The Two Schemes Rule.** Syntax colour has two schemes over one token vocabulary: "mono" (default; keywords take Proof Blue, everything else is ink or recedes into Ink Quiet and Ink Dim) and "vivid" (one hue per category, picked separately for light and dark; comments and glue words stay dim in both). Nothing branches on the scheme except the palette values.

**The Red Once Rule (public site).** On a page that demonstrates the checker, Error Red appears at one failing step only: its rail, its status word, its counterexample, its tick on the scrub and its readout. A second example teaches with Caveat Amber (an unresolved domain obligation), never a second failure.

**The Lit Key Rule (pack registry site).** An entry's key (Theorem 2.9, Example 2.18) is quiet ink at rest and takes Proof Blue only while something lights it: a search that matches it, the URL targeting it, or the pointer over it. A whole column of blue keys would make the accent a standing state.

## Typography

**Formal Font:** JetBrains Mono (self-hosted subsets; ui-monospace fallback)
**Prose Font:** the system UI sans stack (-apple-system, Segoe UI, Roboto, …)

**Character:** One working monospace carries every formal mark and every piece of chrome; the sans appears only where something speaks in sentences. There is no display face and no second family to pair; the one exception is the name itself (see Wordmark), which is the brand mark rather than text.

**Math subset.** JetBrains Mono ships a third self-hosted subset, cut from the upstream variable font (pinned by sha256) for U+2100–214F, U+2190–21FF and U+2200–22FF, so the notes' symbols (∀ ∃ ∈ ⇒ ≤ ℝ ℤ ℕ) are set in the same face, at every weight on the 100–800 axis, in the editor and on the site alike, instead of falling back to a system font.

**Wordmark.** "Lemmata Wordmark" is a 2.3 KB subset of Latin Modern Math (LaTeX's own face; GUST Font License), vendored by ui/vendor_fonts.py and declared in fonts.css, that holds only the glyphs of 𝐿emma𝑡𝛼: math-italic 𝐿, upright "emma", math-italic 𝑡 and 𝛼, as $L\text{emma}t\alpha$ sets them. It is set at 1.5em of its context, weight 400, no tracking, in ink. It sets the name and nothing else; a site.json name other than Lemmata is set plainly in the mono.

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

### Public site
The site sets the same two families at the scale of a page. Headings are mono 600 with slight negative tracking and balanced wrapping; sentences are the system sans.
- **Specimen** (500, clamp(2.25rem, 10.3vw, 10rem), 1, −0.04em, word spacing −0.28em): the hero's quantifier clauses ("∀ ε > 0, ∃ δ > 0,"), spanning the 1200px measure at most. Each clause is an unbreakable unit, so the line wraps between clauses and never inside one. It is JetBrains Mono, not a display face.
- **Specimen Tail** (400, clamp(1.05rem, 2.6vw, 2rem), 1.3, Ink Quiet): the rest of the claim beneath, about a third of the specimen.
- **Lit symbol**: a symbol the scrub's current step uses turns Proof Blue and moves along the weight axis to 750 (0.35s ease-out), so the specimen answers the control.
- **Site Page Title** (600, clamp(2rem, 4vw, 3rem), 1.08) on reading pages; the hero headline sits a step down (clamp(1.9rem, 2.9vw, 2.6rem), 1.1).
- **Site Headline** (600, clamp(1.75rem, 3.2vw, 2.5rem), 1.12): section heads and the close.
- **Site Body** (sans 16px, 1.6) and **Site Lede** (sans 17px, 1.6, Ink Quiet, about 62ch); reading pages set paragraphs at 16px/1.7 to 68ch.
- Chrome keeps the app's sizes: 11px uppercase tracked labels (scrub label, table heads, footer column heads), 12–13px mono for nav links, buttons, readouts and captions. Literal code turns ligatures off, as the editor does.

### Pack registry site
The registry is a reading surface a step quieter than the landing site: sans body at 15px/1.6, ledes and summaries in Ink Quiet held to 64ch (the lede at 16px, a brief's summary at 14px), trap explanations at 14px to 68ch.
- **Registry Page Title** (600, clamp(1.75rem, 3vw, 2.25rem), 1.15, −0.02em): "Packs", a pack's title (its course code inline before it in Proof Blue), the guide's title; a pack brief on the catalogue sets the same head at 1.25rem.
- **Registry Chapter** (600, 1.25rem): a chapter's number in Ink Dim, its title in ink, its entry count at 12px 400 dim on the right; the guide's numbered steps ("1. Make it in the app") use the same mono 600 at 1.2rem.
- **Registry Entry Title** (600, 15px, −0.01em, mono): one entry's title; the key beside it is 13px mono 600 with tabular figures, the verdict 12px mono.
- **Rail**: 11px uppercase tracked group labels (course codes, Topics), pack titles in 13px mono 600, counts in 12px dim mono; the meta line under a pack title is 12px dim mono.
- Opened source is 13px mono at 1.6 with tab size 4 and ligatures off.

### Named Rules
**The Formal-Mono Rule.** Anything the engine checks, and every piece of chrome, is set in the monospace; only sentences use the sans. No italics: the subsets ship none, and a synthesised slant on a mono face reads as a rendering fault. The wordmark's math italics are the one sanctioned exception, scoped to the name.

**The Name Is The Mark Rule.** There is no logo. The name is set in the Wordmark face (𝐿emma𝑡𝛼) wherever the brand stands: the site's nav and footer, the registry's top bar, and, as its 𝐿 alone, the app rail's top. The face never sets any other text, and its italics never spread to it.

**The Labels Are Not Titles Rule.** Uppercase tracking belongs to 11px section labels only. Page and entry titles are mixed-case mono at weight 600.

## Layout

A full-viewport application shell: a 44px view rail on the left (the wordmark's 𝐿 on top, a link to the public site; Workspace, Library, Guide, Settings; the command palette and theme toggle at the foot), the current view beside it, and a 24px status bar across the foot carrying the verdict rail-and-word, the problem button, caret position, file path and storage state. Only one view occupies the grid at a time.

The Workspace is the study desk: a 320px reading pane (Files, Notes, History) beside the work, collapsible to zero. The work column is an open-proof tab strip, a tool strip (symbols, templates, export), then a CSS grid of panes separated by 1px gaps that show the Rule colour through, so pane boundaries are drawn by the grid itself. Panes are placed by slot (`a`, `b`, `c`), and the arrangements rearrange slots without any rule knowing which pane is which; DOM order follows visual order so keyboard and screen-reader order match. Inside a pane: a 30px head (label and rule), then a scroll region. Rows are flush with 8px vertical / 12px horizontal padding and a 22px line-number column.

Library, Guide and Settings are pages: a centred column (1080px max; 720px for narrow pages) with 28px/32px padding, a title and lede, then content. The Library and the Guide each put a sticky list (packs, contents) beside the body.

**Responsive.** Below 1100px the reading pane overlays the work (min(320px, 86vw)) rather than squeezing it, never opens by itself, and a tap on the work puts it away; the Library and Guide side lists fold above the body; the Library's pack rail becomes an auto-fill grid of even columns (minimum 200px) with its group labels and actions spanning every column. Below 760px the rail becomes a 44px bottom bar (the 𝐿 is hidden with the rest of the rail's top) with labels under each icon (the current view's label in bold), the panes stack and scroll as one page, the symbol strip is hidden, and the status bar keeps only the verdict and the problem button.

**Motion.** Two transitions only: the reading pane collapses by animating the column width (180ms ease), disabled under prefers-reduced-motion; and step rows fade their hover background (0.1s). Nothing animates on load.

**Public site.** A centred page of 1200px between fluid gutters (clamp(16px, 4vw, 32px)) under a 60px sticky nav whose hairline underline is inset to the gutters. Sections open with clamp(72px, 10vw, 128px) of space and a head held to 62ch. The hero puts the specimen across the full measure, closed by a Rule line and a dim mono caption, then an 8:4 grid: the scrub and audit on the left, the pitch (headline, lede, actions) on the right, sticky beside the audit. Further down: a two-column 7:5 grid (a second audit beside a hairline list of facts), the app screenshot (a phone capture at narrow widths), and the reading pages as a 760px column. Below 1080px the hero and reasons grids collapse to one column with the pitch first, the glyph grid goes from 6 to 3 columns, the ways list from 4 to 2, and the footer from 2:1:1:1 to three columns under the brand. Below 720px the nav links fold into a menu, the points and ways lists stack, audit rows drop the status to its own line, the pack table hides its chapter column, the close stacks, and the footer is two columns.

**Pack registry site.** A 56px sticky top bar over a two-column layout: a 288px rail and a main column (980px max, clamp(20px, 4vw, 56px) side padding, 40px above). The rail is sticky at full viewport height and scrolls on its own; its Paper Raised surface and 1px Rule edge are painted by the layout's own background gradient, so they run the page's whole height however long the main column is. In the rail: search, then the packs grouped by their first course code (MTH2008, MTH2010), then Topics, with "Publish a pack" pinned to the foot above a Rule line. Main: a page head closed by a Rule line, then content. Entries hang off a 10rem key column divided by a hairline; each entry is one line. Below 860px the rail folds to the search and a "Browse packs" disclosure (the packs open beneath as an auto-fill grid, minimum 200px) and the top bar keeps only the brand, theme and Open Lemmata. Below 560px the key column stacks above the title and the verdict moves up onto the key's line, so an entry is two lines; below 360px the verdict returns under the title. The publishing guide's rules list goes from two columns to one.

**Pack registry site motion.** The opened entry's chevron turns 90° (0.15s ease); nothing else moves, and reduced motion removes that too.

**Public site motion.** The site has two choreographies, and the scrub comes first: it plays once to the failing step (520ms per step, 900ms onto the failure) the first time the audit is a third on screen, and stops there; under reduced motion it starts on the failure and nothing transitions. The second is the nav's wordmark trading its plain and typeset forms (see Components), which waits for the scrub to stop and runs only near the top of the page; under reduced motion it stands still in the typeset form. Otherwise only state changes ease (colour and background, 0.15–0.4s, cubic-bezier(0.16, 1, 0.3, 1)).

## Elevation & Depth

Flat by default. Depth is tonal: paper, raised and lowered surfaces, separated by 1px Rule borders and hairlines. The only shadow in the system is a 1px inset ring marking the selected step, so selection can never be mistaken for a status. Floating layers separate by surface and border alone: the command palette is a paper dialog on a 1px Rule border over a modal scrim (ink at 42%, black at 62% at night); the arrangement popover sits on Paper Raised with a Rule border; the overlaid reading pane keeps its paper and right border. Toasts are flat, with no countdown ring; an info toast carries no edge rule, and only warning and danger toasts keep a 2px rule (the margin belongs to failure). Dialogs (export, pack) separate their footer from the form with a 1px Rule edge, not a fill.

### Named Rules
**The No Boxes Rule.** Organise with hairlines and alignment; never wrap content in cards. A box is reserved for callouts that carry a failure (counterexample, domain warning).

**The Border, Not Shadow Rule.** Anything that floats is told apart by its surface and a 1px border, plus a scrim when it is modal. Never a drop shadow.

On the public site the same holds: the storage notice floats on Paper Raised with a 1px Rule border, and the open phone menu is a paper panel with a Rule underline over the modal scrim. The scrim is drawn as a 100vmax spread clipped to below the panel; it is the scrim, not a shadow.

The pack registry site is flat too: the top bar and rail are Paper Raised with a 1px Rule edge, and an opened proof sits on Paper Raised inside a 1px Rule border, as the app's editor does. That frame is the editor, a read-only field, not a card.

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

### Hints and Fixes
What to try after a step fails or warns: a sentence and, when the engine has one, a fix.
- **In the auditor row:** each hint is one 12px sans sentence in ink beneath the step's reason (quiet ink), so the actionable sentence is the one that reads darkest. The row is itself a button, so it holds no buttons: no fix, no link.
- **In Context & State:** the sections run Verification (omitted when empty), Domain obligations (omitted when a hint whose fix adds an Assume already states the obligation and where it fails), What to try, Cited result, then variables and hypotheses. What to try sets each hint sentence with its fix beneath as the one primary text button, labelled as the edit it makes ("Add Assume x - 1 ≠ 0", "Use ≥", "Use h1").
- **In the editor:** hint sentences follow the diagnostic's message in the lint tooltip, and each fix is a diagnostic action drawn exactly as the primary text button (24px, 2px corners, 12px mono Proof Blue on a 45% Proof Blue outline, the quiet blue fill on hover, the 2px focus outline inset by 2px).
- **Behaviour:** a fix is one ordinary editor edit, so Ctrl+Z undoes it; if the line has changed since the check, the fix is refused with a warning toast rather than applied to the wrong text.

### Cited Result
What a step leaned on, named as the notes name it. The name in 12px mono 600 ink ("MTH2008 Theorem 1.1 (the triangle inequality)"), its statement beneath in 12px quiet mono in the app's own mono, so `<=` ligates to the notes' sign, then "Open in the Library" (a pack result) or "Open the file" (a workspace import) as a quiet text button pulled left by its own 8px padding, so its first letter aligns with the name. In the editor, the words after `by` or `using`, up to a comma or bracket, are a plain name in ink and never take keyword colours, in either syntax scheme.

**The Named Once Rule.** A cited result has one name and it is the same everywhere: the step's message ("…, by MTH2008 Theorem 1.1 (the triangle inequality)."), the Cited result label and the hypothesis label. A step's reason echoes after its statement in square brackets (`[MTH2008 Theorem 1.1]`, `[h2]`), as the student wrote it.

### Pane Head
A label and a rule, with no fill: an uppercase tracked label in quiet ink, optional note in dim ink, tools aligned right, and a 1px Rule underline. A six-dot grip at the left drags the pane to swap slots.

### View Rail
At the top, the rail mark: a 32px link to site.json's `home` (the public site) holding the wordmark's italic 𝐿 at 24px in ink, a Paper Lowered fill on hover and the 2px Proof Blue focus ring inset, labelled "<name> home page". An institution's own name shows its first letter in mono 700 at 15px instead. Beneath it, a column of 18px line icons in quiet ink on Paper Raised, 40px targets. The current view is the icon in Proof Blue on a 28px Paper Lowered square. On phones it becomes a bottom bar with an 11px label under each icon; the current label turns bold and the square is dropped.

### Tabs
Two kinds, both without boxes. Reading-pane tabs are 11px uppercase labels; the selected one turns ink and gets a 2px Proof Blue underline. Open-proof tabs are 12px mono names divided by hairlines; the active tab takes the page's paper so it joins the editor below, with a 2px Proof Blue rule along its top, and a status dot when its last check failed or warned.

### Status Bar
24px on Paper Raised with a Rule top edge, 11px tabular text in quiet ink. Left to right: the verdict, a red problem button that jumps to the failure, then caret, path and storage state (amber when storage is unavailable). The verdict block never shrinks; on a narrow screen the problem button is what gives way, ending in an ellipsis, so the two never share pixels.

### Buttons
The native family, used wherever a Web Awesome button would be heavier than the job:
- **Icon button:** 24px square, plain, quiet ink with a 14px inline SVG; ink on a lowered fill on hover.
- **Text button:** 24px tall, 12px mono, ink on no fill, lowered fill on hover. **Primary** is Proof Blue text on a 45% Proof Blue outline. **Danger** is red text. **Armed** (the second click of a two-click confirm) fills solid red with paper text.
- **Secondary (Web Awesome):** dialog actions that are not the primary one sit on Paper Lowered with ink text, not on a tinted chip.
- **Focus:** a 2px Proof Blue outline inset by 2px on every native control.

### Segmented Control
One outlined strip of 24px segments divided by Rule lines; 12px mono, quiet ink. The checked segment is Proof Blue text on the quiet blue fill. Used for the Library filters and every choice in Settings.

### Wordmark (signature)
The name as the mark: 𝐿emma𝑡𝛼 in the Wordmark face. Static wherever it stands except the public site's nav, where it is seven slots, each holding the plain letter (mono 700) and its typeset form stacked; JS measures both widths and flips the form. Each letter cross-fades with a 4px blur and a small vertical shift (the plain letter rises 0.25em out, the typeset one settles from 0.18em below), staggered 55ms left to right, the slot widths gliding 0.55s on the site's ease-out. The first flip waits for the scrub to stop on its failing step (at once on pages without the hero), then 1.8–3.6s; after that every 5–11s at random, only while the page is within 240px of the top and the tab is visible. Under reduced motion the typeset form stands still. The wordmark is aria-hidden inside a link that carries the name.

### App Icon
The open tombstone, the box that ends a proof: a white hollow square on a Proof Blue tile. The desktop icon is drawn on a 1024 grid inside the macOS margin (an 824px tile, rx 184; a 350px square, 76px stroke). The favicon is hinted separately on the 16px grid (a full-bleed tile at rx 3; an 8px square at 4,4 with a 2px stroke, crisp edges) and is shared by the pack registry site. It is the only drawn brand mark, and it lives outside the pages: no page shows it.

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

### Public Site
The public site (`web/`) is the same world at the scale of a page. It shares the theme with the app through the one storage key, resolved before first paint so neither flashes the other palette, and its fonts are the app's own files.

- **Specimen (signature).** The claim in the notes' own notation at Specimen scale, symbols lit by the scrub, closed by a Rule line and a two-part dim mono caption.
- **Scrub (signature).** A native range input drawn as a ruler: a 1px Control Border track, a 4px × 22px Proof Blue thumb, and one 1px × 7px tick per audited step, inked once reached; the failing step's tick is 2px × 11px in Error Red. An 11px uppercase label sits above; a 12px tabular mono readout (line, step n of N, status in red at the failure, backend) and a quiet "Replay" text link sit beside. Arrows, Home and End move it; moving it stops the playback.
- **Audit Row.** The app's step row, built from the engine's real report: right-aligned dim line number, the statement in mono, status and backend as 12px lowercase dim text, nested rows indented 22px per depth. The failing row takes the red rail and a bold red status; rows resting on it carry the rail at 30%; a caveat row takes the amber rail, a bold amber status, and a boxed amber callout (quiet amber fill, 2px rail) holding the obligation. The counterexample callout is the loudest thing in the audit (15px mono 600). Rows the scrub has not reached stay legible in Ink Dim with their status and callouts hidden; the current row takes Paper Lowered.
- **Glyph Grid.** A 6-column grid of hairline cells (Rule lines, no boxes): the symbol at clamp(2rem, 3.6vw, 3rem), its ASCII spelling in 12px mono, its name in 13px dim. A symbol the scrub's step uses lights: Proof Blue mark on the quiet blue fill.
- **Pack Table.** A full-width hairline table: 11px uppercase heads, each pack's code in Proof Blue mono, its title in ink, tabular counts in Ink Quiet, rows divided by Rule lines.
- **Points and Ways.** A 2×2 definition list and a 4-column list, both divided only by Rule lines (the ways list adds vertical Rule lines between columns); a mono 600 term, a quiet sans sentence, and a mono text link.
- **Close.** A band between two Rule lines: "QED" in mono 600 at clamp(3rem, 9vw, 6rem) beside a Site Headline, a lede and the primary action.
- **Nav.** The animated Wordmark (in a 15px context, so 22.5px), with no icon; 13px mono links in Ink Quiet, ink on hover; a 32px theme toggle (line sun and moon); the primary button. Below 720px the links become a disclosure under a 32px menu button (Paper Lowered while open): a paper panel of 15px ink links divided by hairlines, over the modal scrim.
- **Site Buttons.** Mono 600, 2px corners, 32px (44px large). **Primary** is a Proof Blue Fill with paper text, darkened 14% toward ink on hover; **Outline** draws the Control Border around ink text, Paper Lowered on hover; **Quiet** sits on Paper Lowered (28px, weight 500) for Dismiss and Copy.
- **Storage Notice.** A non-blocking strip fixed 16px above the foot, up to 640px wide, on Paper Raised with a Rule border: one quiet sentence with a link, and a quiet Dismiss. On the landing page it waits until the hero has scrolled away, so it never covers the first view; dismissal is remembered.
- **Download Platforms.** A hairline list of rows (platform name, a prose sentence, its files as outline buttons). The visitor's own platform adds "your system" in 11px Proof Blue under its name: news, so it takes the accent. A platform with no release says so in 12px dim mono.
- **Command Block.** A copyable one-line command: Paper Raised with a 1px Rule border at 2px, the command in 14px ink mono scrolling sideways, and a quiet Copy button that reports failure in its own label. It behaves as a read-only field, not a container.
- **Reading Pages (Download, Privacy, Terms, Cookies).** A 760px column: Site Page Title, a lede, a dim mono date line, then mono 600 section heads with 56px above, sans paragraphs at 16px/1.7, and hairline tables with 12px uppercase mono heads.
- **Footer.** A brand column (the static Wordmark, one quiet sentence) and three link columns under 11px uppercase heads, then a dim 12px mono meta line (engine version, licences, the Lean notice) above a Rule line.

### Pack Registry Site
The registry (repo lemmata-packs, rendered by tools/pages.py) is the app's Library opened to the public. It shares the theme storage key and the app's font files, resolved before first paint.

- **Top Bar.** 56px on Paper Raised with a Rule underline: the static Wordmark 𝐿emma𝑡𝛼 with "packs" in 400 Ink Quiet, no icon; 13px mono links in Ink Quiet (Browse, Publish a pack, GitHub, About Lemmata), ink on hover and for the current page (Browse on the catalogue); the 32px theme toggle; Open Lemmata as the primary button.
- **Pack Rail (signature).** Groups under 11px uppercase labels; each pack is its title in 13px mono 600 over its counts in 12px dim mono, 8px × 16px, Paper Lowered on hover. The current pack takes the Paper Lowered fill and a bold Proof Blue title, never a left rule. The search field above draws the Control Border on paper (34px, 13px mono, dim placeholder) and focus replaces the border with the Proof Blue outline. "No pack matches." replaces the list when the search empties it.
- **Pack Head.** The course code in Proof Blue inline before the title in Registry Page Title type; a 12px dim mono meta line (version · authors · licence · the pack's name as code) whose separators attach to the item before them, so a wrapped line never starts with one; the summary in Ink Quiet; the verification line in 12px quiet mono where the bold green "Verified" is the only green; then Open in Lemmata (primary) and Download .pack.json (outline). On the catalogue each pack is a brief: the same head at 1.25rem with its title linked, counts and chapters beneath, briefs divided by Rule lines.
- **Registry Buttons.** Mono 600 at 13px, 34px tall, 14px padding, 2px corners. **Primary** is Proof Blue Fill with paper text, darkened 14% toward ink on hover; **Outline** draws the Control Border around ink, Paper Lowered on hover. Text links ("How to publish", "Publish a pack") are 13px mono 600 in Proof Blue, underlined.
- **Key Rail Entry (signature).** A chapter is a mono 600 title over a Rule line with its count on the right; its entries are a list divided by hairlines. Each entry is one line: the key in a 10rem column with a hairline on its right (13px mono 600, Ink Quiet, tabular; Proof Blue when lit, per the Lit Key Rule), then a `<details>` summary holding a 12px chevron (inline SVG, Ink Dim, turns 90° open), the title, and the verdict right-aligned in 12px dim mono ("checks"). A trap's verdict reads "trap · fails, as it should" in bold Ink Quiet, and its explanation follows as one sans line beneath the title. A targeted entry takes the quiet blue fill across the row.
- **Registry Source.** An opened proof is set as the app's editor in the mono scheme: Paper Raised inside a 1px Rule border at 2px, numbered lines (CSS counters) right-aligned in Ink Dim in a 2.75em gutter closed by a hairline and unselectable, skeleton keywords and ∀ ∃ in Proof Blue, glue words (such that, from, where, by) in Ink Dim, everything else ink. The block is focusable and scrolls sideways rather than wrapping.
- **Search.** One field narrows the rail, the catalogue's briefs and a pack's entries together; on a pack page a 12px quiet mono note reports the filter, and on the catalogue a "Matching entries" list appears above the packs: each match a 13px mono 600 link to its entry with its pack in 12px dim mono, title in sans, on a 11rem column divided by hairlines.
- **Publishing Guide.** A 72ch column: numbered mono 600 step heads, ordered steps in quiet sans with ink bold for the UI's own words and literal names in mono, and a 2×2 rules list (mono 600 term, quiet sans sentence) divided only by Rule lines, one column on phones.
- **Footer.** One 13px dim sans sentence (licence, how the registry is checked, the engine version) with its links, above a Rule line.

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
- **Do** set the public site's display specimen in JetBrains Mono, wrapping only between clauses, and let red appear once per demonstration, at its failing step.
- **Do** let the name stand as the mark: 𝐿emma𝑡𝛼 in the Wordmark face at 1.5em, static everywhere but the site nav, and no logo on any page.
- **Do** keep the registry's entry keys in quiet ink until a search, the URL or the pointer lights them, and set every proof it shows as the app's editor sets it in the mono scheme.
- **Do** give a hint's fix exactly one primary text button, labelled as the edit it makes, and set the hint itself as a sentence in ink after the quiet reason.
- **Do** name a cited result once, as the notes name it, and use that name in the message, the Cited result label and the hypothesis label alike.

### Don't:
- **Don't** use green anywhere but a verdict.
- **Don't** use red for anything that has not actually failed or will not actually destroy.
- **Don't** draw a vertical coloured rule at the left of a row for anything but failure or caveat.
- **Don't** wrap rows in cards, give passing steps badges, or use filled status pills.
- **Don't** introduce a display face, italics, a second sans, or text below 11px; the Wordmark face and its italics set the name and nothing else.
- **Don't** add drop shadows; floating layers separate by surface and border, and the selected-row inset ring is the only shadow.
- **Don't** put a button inside an auditor row; the row is the button, and its fixes live in Context & State and the editor tooltip.
- **Don't** fetch anything cross-origin (icons, fonts, scripts): the app makes no runtime network requests.
