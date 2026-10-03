---
version: 1
slug: "registry-index-html"
primary_target: "registry/index.html"
related_targets: []
---

## Scope
The public pack registry site (repo SamuelSmthSmth/lemmata-packs, built by tools/build_index.py with tools/site.py and web/): the catalogue, a page per pack, and a publishing guide. Operate (find a pack, read it, open it in the app) with Read for the guide.

## Audience and job
Students and authors equally. A student searching "MTH2008" finds the pack, sees every entry by the notes' numbering, reads a proof, and opens it in Lemmata to install (`/app/?install=<name>`). An author sees how packs are verified and follows Publish a pack. Proof on hand: the packs, their counts, the engine version and date of the last verification. No claims beyond that.

## Direction contract
THESIS: The registry is the app's Library opened to the public: a pack rail by course beside the open pack, so browsing here and installing in the app are one motion. Refuses the card-grid marketplace and the bare file listing it replaces.
OWN-WORLD: Lemmata's paper and ink, Proof Blue for keys, links, the current pack's text and Open in Lemmata; Verified Green only for a whole pack's verification verdict; no red (traps are described in quiet ink). JetBrains Mono for every formal mark and all chrome, the system sans for sentences; hairlines, 2px corners, the current pack marked by a lowered fill, never a left rule.
STORY: A student recognises their module in the rail, opens it, scans its chapters by the notes' own numbers, reads a proof, and opens it in Lemmata. An author sees every entry is checked by the engine students use and follows the publishing guide.
FIRST VIEWPORT: Header: mark and "Lemmata packs" left; Browse, Publish a pack, Open Lemmata right. A 280px rail: search, then packs grouped by course (MTH2008, MTH2010, then topics) with title and counts; Publish a pack at its foot. Main: on a pack page, the pack head (course, title, version, authors, licence, the verified line in green, Open in Lemmata primary and Download .pack.json), then chapters whose entries hang off a key column of the notes' numbering. On the front page: the registry's figures in one line, the search's theorem matches, and every pack's head in brief.
FORM: The Library, Online; my grounded list position 1 (dealt index 1, raised by the centre-rail reference page: the notes' numbering as a key rail down each chapter); seed key a05febfc.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Signature interaction
The key rail: every entry's reference (Example 2.18, Theorem 1.1) set as a mono key down a hairline column beside its chapter; typing in the rail's search narrows packs and lights matching keys, and theorem matches link straight to their entry.
