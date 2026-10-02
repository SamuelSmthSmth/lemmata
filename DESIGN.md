---
name: Aether
description: Proof intern — a controlled-natural-language proof checker, typeset like a proof.
colors:
  paper: "#ffffff"
  paper-raised: "#f7f8f9"
  paper-lowered: "#eff1f4"
  rule: "#dde1e6"
  ink: "#16181d"
  ink-quiet: "#646b78"
  proof-blue: "#0a5fbf"
  verified-green: "#157333"
  caveat-amber: "#7d4e00"
  error-red: "#be1824"
  night-paper: "#0e1013"
  night-paper-raised: "#15181c"
  night-paper-lowered: "#1a1e23"
  night-rule: "#262b32"
  night-ink: "#e6e8ec"
  night-ink-quiet: "#868e9c"
  night-proof-blue: "#6cb0ff"
  night-verified-green: "#4ab960"
  night-caveat-amber: "#d9a520"
  night-error-red: "#f2645c"
typography:
  statement:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.45
  body:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.5
  prose:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.5
  verdict:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "1px"
  label:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "9.5px"
    fontWeight: 700
    letterSpacing: "1.3px"
rounded:
  sm: "2px"
  md: "2px"
spacing:
  pane-x: "12px"
  row-y: "8px"
  gutter: "11px"
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
---

# Design System: Aether

## Overview

**Creative North Star: "The Typeset Proof"**

Aether is set the way a printed proof is set, not built the way a dashboard is built. The page is white paper (or near-black at night) divided by hairlines rather than boxes; the formal layer, meaning the proof, its line numbers, the variables, the hypotheses and the verdict, is machine-checked and therefore set in one monospace face, and the only type that breaks that grid is the intern's own prose, where it explains a step in English. The palette stays almost entirely ink and paper so that status colour means something when it appears.

The system's single idea is that **failure is the event**. A step that verifies is the unremarkable case and gets no box, no fill and no colour. A step that fails gets a 2px rail in the margin, and so does every step after it that rests on it, because those rows are flush and consecutive rails read as one continuous line down the margin. The verdict in the header uses the same rail-and-word language, so the whole interface speaks one dialect.

Density is high and deliberate: an instrument, not a web page. Corners are near-square, chrome is minimal, and controls are reduced to ink toggles so that nothing competes with the verdict a proof produces.

**Key Characteristics:**
- Paper and ink, hairline rules, near-square corners (2px).
- One monospace family for everything formal; system sans only for the intern's sentences.
- Status lives in 2px rails and coloured words, never in filled pills or cards.
- Green appears only in the verdict, so red lands when it does.
- Light and dark are equal citizens, each with its own picked palette.

## Colors

A restrained ink-and-paper system with one blue accent and three status hues used only for status.

### Primary
- **Proof Blue** (#0a5fbf; night #6cb0ff): the accent. The CNL keywords that form a proof's skeleton in the default "mono" syntax scheme, links, focus rings, the caret, selection tints and the pending verdict. Never decorative.

### Neutral
- **Paper** (#ffffff; night #0e1013): the page and the editor surface.
- **Paper Raised** (#f7f8f9; night #15181c): tooltips and popovers.
- **Paper Lowered** (#eff1f4; night #1a1e23): hover and selected rows, switch tracks.
- **Rule** (#dde1e6; night #262b32): pane boundaries (the 1px gaps of the layout grid) and pane-head underlines.
- **Hairline** (ink at 8% over paper): row separators inside panes; organises without drawing boxes.
- **Ink** (#16181d; night #e6e8ec): statements, names, types (separated from keywords by weight, not hue).
- **Ink Quiet** (#646b78; night #868e9c): prose explanations, labels, operators. A dimmer derivative (ink-quiet at 62% over paper) carries line numbers, metadata and passing statuses.

### Status
- **Verified Green** (#157333; night #4ab960): the VALID verdict only.
- **Caveat Amber** (#7d4e00; night #d9a520): warnings, meaning unresolved domain obligations.
- **Error Red** (#be1824; night #f2645c): invalid steps, counterexamples, parse errors. Quiet fills use the same hue at 8–11% alpha.

### Named Rules
**The Green Is Rare Rule.** Green appears in the verdict and nowhere else; a passing step's status is set in dim ink. Scarcity is what makes red legible.

**The Two Schemes Rule.** Syntax colour has two schemes over one token vocabulary: "mono" (default; keywords take Proof Blue, everything else is ink or recedes) and "vivid" (one hue per category, picked separately for light and dark). Nothing branches on the scheme except the palette values.

## Typography

**Formal Font:** JetBrains Mono (self-hosted subsets; ui-monospace fallback)
**Prose Font:** the system UI sans stack (-apple-system, Segoe UI, Roboto, …)

**Character:** One working monospace carries every formal mark; the sans appears only where the checker speaks in sentences. There is no display face and no second family to pair.

### Hierarchy
- **Statement** (400, 12.5px, 1.45): proof statements in the auditor and the editor's text.
- **Body** (400, 12.5px, 1.5): the base size of the app.
- **Prose** (400, 11.5px, 1.5): step explanations, empty states; system sans.
- **Verdict** (700, 11px, 1px tracking, uppercase): the header verdict word.
- **Label** (700, 9.5px, 1.3px tracking, uppercase): pane headings; metadata runs 9–10.5px.

### Named Rules
**The Formal-Mono Rule.** Anything the engine checks is set in the monospace; only the intern's sentences use the sans. No italics: the subsets ship none, and a synthesised slant on a mono face reads as a rendering fault.

**Known debt.** The incumbent scale uses eight ad-hoc sizes between 9px and 12.5px. Labels below 11px are under a public product's legibility floor; consolidation onto a tight scale is the first refinement owed.

## Layout

A full-viewport application: a 46px top bar over a CSS grid of panes separated by 1px gaps that show the Rule colour through, so pane boundaries are drawn by the grid itself. Panes are placed by slot (`a`, `b`, `c`), and four arrangements (Columns 1.1 : 1 : 0.85, Stack, Split, Focus) rearrange slots without any rule knowing which pane is which; the DOM order follows the visual order so keyboard and screen-reader order match. Inside a pane: a 30px head (label and rule), then a scroll region. Rows are flush with 8px vertical / 12px horizontal padding and a 22px line-number column. Below the narrow breakpoint the slots dissolve into one stacked column.

## Elevation & Depth

Flat by default. Depth is tonal: paper, raised and lowered surfaces, separated by hairlines. The only shadow in the system is a 1px inset ring marking the selected step, so selection can never be mistaken for a status. Popovers rely on the raised surface and a Rule border rather than drop shadows.

### Named Rules
**The No Boxes Rule.** Organise with hairlines and alignment; never wrap content in cards. A box is reserved for callouts that carry a failure (counterexample, domain warning).

## Shapes

Near-square everywhere (2px radius, Web Awesome's radius scale at 0.3). Rules are 1px; status rails are 2px. Keyboard keys (`kbd`) get a 2px bottom border as their only bevel.

## Components

### Verdict
A rail and a word: 2px left rail plus an uppercase mono word (VALID, INVALID, PARSE ERROR, TIMEOUT) in the status colour, with tabular metadata (statements, valid count, milliseconds, domain mode) in dim ink beside it. Pending shows Proof Blue with a spinner; an outdated verdict dims to 45% opacity while a re-check is outstanding.

### Step Row (signature)
A flush grid row: right-aligned dim line number, then the statement in mono with status and backend set as small type on the right. Valid rows carry nothing else. Warning and invalid rows get a 2px rail at the left edge; rows downstream of a failure carry the rail at 30% strength. Hover lowers the surface; selection adds the inset ring. The explanation sits beneath in prose; counterexamples and domain warnings are the only boxed callouts, with a quiet status fill and a 2px rail.

### Pane Head
A label and a rule, with no fill: an uppercase tracked label in quiet ink, optional note in dim ink, tools aligned right, and a 1px Rule underline. A six-dot grip at the left drags the pane to swap slots.

### Buttons and Toggles
Icon buttons are 24px square and plain (quiet ink, ink on hover), with icons as inline SVG. Switches are reduced to ink toggles (14×26px, square track, no hue) so they never outshout the verdict.

### Inputs
Web Awesome selects at small size, styled through the token layer; focus is a 2px Proof Blue ring.

## Do's and Don'ts

### Do:
- **Do** let a failing step's 2px rail and red word carry the page; keep everything that verified quiet.
- **Do** set every checked artefact (statements, names, types, verdicts, line numbers) in JetBrains Mono and every explanatory sentence in the system sans.
- **Do** separate regions with 1px Rule/Hairline lines and tonal surfaces, not containers.
- **Do** define colour once in the `--wa-*` token layer and alias it; light and dark each get picked values.
- **Do** keep corners at 2px and status rails at 2px.

### Don't:
- **Don't** use green anywhere but the verdict.
- **Don't** wrap rows in cards, give passing steps badges, or use filled status pills.
- **Don't** introduce a display face, italics, or a second sans.
- **Don't** add drop shadows; depth is tonal, and the selected-row inset ring is the only shadow.
- **Don't** fetch anything cross-origin (icons, fonts, scripts): the app makes no runtime network requests.
