#!/usr/bin/env python
"""Vendor the typeface, for fully offline use.

The app has no network at runtime, which rules out a font CDN, so the face it
is typeset in lives on disk -- vendored the same way the Web Awesome components
(`vendor_webawesome.py`) and the CodeMirror graph are.

`@fontsource` packages ship the same subset files the CDN serves, so the browser
downloads only the ranges whose characters are actually on the page.  Two are
vendored:

  latin  -- ASCII, the punctuation the interface uses, and U+2191 / U+2193,
            which are the arrow keys named in the auditor's hint
  greek  -- epsilon and delta.  In a proof checker shipped with an
            epsilon-delta continuity example, Greek is not decoration.

The face is JetBrains Mono, chosen because its ligatures render `!=`, `<=`, `>=`
and `=>` as the symbols a mathematician actually reads.  Those substitutions
come from the `calt` feature and apply wherever the font is used -- see
fonts.css, and `editor.js`, which turns them back off in the editor itself so
that what you type is what you see.

A third subset, **math**, is cut here from JetBrains Mono's own release (the
font has the symbols; no published subset carries them): the quantifiers,
relations, arrows and the double-struck ℝ ℤ ℕ ℚ ℂ that lecture notes are
written in, U+2100-214F, U+2190-21FF and U+2200-22FF.  Without it those fall
back to whatever system font has them, which shows at the landing page's
display sizes and in the editor alike.  The source file is pinned by sha256.

No npm is involved: the tarball comes straight from the npm registry and is read
with the standard library.  Cutting the math subset needs fontTools:

Run with:  uv run --with fonttools --with brotli python ui/vendor_fonts.py
"""

from __future__ import annotations

import io
import sys
import tarfile
import urllib.request
from pathlib import Path

PACKAGE = "@fontsource-variable/jetbrains-mono"
VERSION = "5.3.0"
TARBALL_URL = f"https://registry.npmjs.org/{PACKAGE}/-/jetbrains-mono-{VERSION}.tgz"

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "static" / "vendor" / "fonts"

PREFIX = "package/"
# `-wght-` is the variable file: one file covers the whole 100-800 weight axis,
# which is cheaper than shipping a static file per weight.
SUBSETS = ["latin", "greek"]

# The math subset, cut from the upstream variable font (the release fontsource
# 5.3.0 packages).
MATH_URL = "https://github.com/JetBrains/JetBrainsMono/raw/v2.304/fonts/variable/JetBrainsMono%5Bwght%5D.ttf"
MATH_SHA256 = "662a196d58f1183bf2d77428b6d5283fe3f45161ab021bea4036bc98e5cac016"
MATH_RANGES = "U+2100-214F,U+2190-21FF,U+2200-22FF"
MATH_FILE = "jetbrains-mono-math-wght-normal.woff2"


def vendor_math() -> int:
    import hashlib

    try:
        from fontTools import subset
    except ImportError:
        print("ERROR: cutting the math subset needs fontTools: uv run --with fonttools --with brotli python ui/vendor_fonts.py", file=sys.stderr)
        return 0
    with urllib.request.urlopen(MATH_URL, timeout=180) as resp:  # noqa: S310 - fixed host
        blob = resp.read()
    if hashlib.sha256(blob).hexdigest() != MATH_SHA256:
        print("ERROR: the upstream font does not match its pinned sha256", file=sys.stderr)
        return 0
    source = DEST / "upstream.ttf"
    source.write_bytes(blob)
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    font = subset.load_font(str(source), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=subset.parse_unicodes(MATH_RANGES))
    subsetter.subset(font)
    subset.save_font(font, str(DEST / MATH_FILE), options)
    source.unlink()
    size = (DEST / MATH_FILE).stat().st_size
    print(f"  {MATH_FILE} ({size / 1024:.0f} KB, cut from JetBrains Mono v2.304)")
    return size


def main() -> int:
    print(f"fetching {PACKAGE}@{VERSION} ...")
    with urllib.request.urlopen(TARBALL_URL, timeout=180) as resp:  # noqa: S310 - fixed host
        blob = resp.read()
    print(f"  {len(blob) / 1024:.0f} KB")
    tar = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")

    members = {m.name: m for m in tar.getmembers() if m.isfile()}
    DEST.mkdir(parents=True, exist_ok=True)
    total = 0

    for subset in SUBSETS:
        name = f"jetbrains-mono-{subset}-wght-normal.woff2"
        member = members.get(f"{PREFIX}files/{name}")
        if member is None:
            print(f"ERROR: {name} is not in the package", file=sys.stderr)
            return 1
        data = tar.extractfile(member).read()  # type: ignore[union-attr]
        (DEST / name).write_bytes(data)
        total += len(data)
        print(f"  {name} ({len(data) / 1024:.0f} KB)")

    math = vendor_math()
    if not math:
        return 1
    total += math

    # OFL requires the licence to travel with the font.
    licence = members.get(f"{PREFIX}LICENSE")
    if licence is not None:
        (DEST / "LICENSE").write_bytes(tar.extractfile(licence).read())  # type: ignore[union-attr]
    (DEST / "VERSION").write_text(f"{PACKAGE} {VERSION}\nmath subset: JetBrains Mono v2.304 (sha256 {MATH_SHA256[:12]})\n", encoding="utf-8")

    print(f"vendored {total / 1024:.0f} KB of woff2 into {DEST.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
