---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: ["web/download/index.html","web/privacy/index.html","web/terms/index.html","web/cookies/index.html"]
---

## Scope
The public site at lemmata.sous.systems: the landing page (`web/index.html`, Persuade) and, inside the same surface, Download, Privacy, Terms and Cookies (Read). The app moves to `/app/`.

## Audience and job
Students first (an undergrad or postgrad with tonight's problem sheet), lecturers and departments second (packs, honest limits, self-hosting). Action: Open Lemmata (`/app/`); secondary: Download. Proof on hand: the engine's own audit of a real proof, rendered at build time (`web/content.py`), the real course packs and their counts. No testimonials, numbers or claims the product does not have. Must not feel like generic SaaS, a dry department page, a different product from the app, or overclaiming.

## Direction contract
THESIS: The notes' own notation is the hero, set at specimen scale, and one scrub control walks the checker's real audit of a real ε–δ proof to the step where δ = ε/2 breaks. Refuses the split hero (copy beside a screenshot) and the centred headline over a row of cards.
OWN-WORLD: Lemmata's paper-and-ink system at display scale: white paper (night #0e1013), ink, Proof Blue for keywords, links and the scrub, Error Red exactly once, at the failing step. JetBrains Mono carries every formal mark including the display specimen; the system sans carries sentences. Hairline rules, 2px corners, 2px rails, no cards: specimen cells divided by hairlines.
STORY: A student recognises the lecturer's notation, watches or drags the audit to the slip and its counterexample, believes "it reads my maths and finds the exact step", and opens the app. Lecturers find packs and self-hosting further down; everyone finds downloads and the CLI.
FIRST VIEWPORT: Nav: mark and name left; Download, Guide, Packs, GitHub, theme; Open Lemmata right. Specimen across the full width: "∀ ε > 0, ∃ δ > 0," at display size, the rest of the claim beneath at a third of it, with small mono readout labels. Below it, eight columns: a ruler-like scrub with a tick per step and a readout (step, status, backend), and the audit revealed to the scrub, its failing row on the red rail with the counterexample. Four columns right: headline, one-line lede, Open Lemmata (primary) and Download. It plays once to the failure and stops; reduced motion starts there.
FORM: The Notation Specimen; my grounded list position 7 (dealt index 7, raised by the variable-font specimen: one control drives the audit, readout and highlighted symbols together); seed key b041e05a.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Signature interaction
The scrub: a native range input (keyboard: arrows, Home, End) with one tick per audited step. Moving it reveals the audit to that step, updates the readout, and lights the symbols that step uses in the glyph grid below. Plays once on load; stops on the failure.

## Unresolved
Final headline wording (copy pass). Download page fills in once installers are released.
