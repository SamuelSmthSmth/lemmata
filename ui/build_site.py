#!/usr/bin/env python
"""Build the whole public site: the landing pages, with the app under /app/.

    dist/
      index.html, download/, privacy/, terms/, cookies/   the site (web/)
      install.sh, install.ps1                            the CLI installer
      assets/                                            the site's CSS, JS, images
      app/                                               the app (ui/build_static.py)
      vercel.json                                        headers and rewrites

The app keeps the origin it always had, so the work students saved there is
still theirs at /app/; links from before the move are carried over (an old
``/#p=`` permalink by the landing page's first script, an old ``/static/``
path by a rewrite).

Pages are plain HTML in ``web/``.  ``{{ name }}`` placeholders are filled
here: the site's name, tagline and version from site.json (so an
institution's build brands these pages too), ``{{ root }}`` (the path back to
the site root, so the site works under a sub-path), the shared partials in
``web/partials/``, and content computed from the engine itself, such as the
landing page's audit, which is the checker's real output for a real proof.

Run with:  uv run python ui/vendor_pyodide.py   (once)
           uv run python ui/build_site.py [--out DIR]
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date
from html import escape
from pathlib import Path

UI = Path(__file__).resolve().parent
ROOT = UI.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

# What the site's own files are, and which of web/ are not pages.
NOT_PAGES = {"partials"}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

# The site's hosting rules; the root vercel.json carries the same, and
# web/verify_web.py checks that the two agree.
VERCEL = {
    "cleanUrls": False,
    "trailingSlash": True,
    "rewrites": [
        # Before the site, the app lived at the root: its engine URLs still work.
        {"source": "/static/:path*", "destination": "/app/static/:path*"},
    ],
    "headers": [
        {
            "source": "/app/static/vendor/(.*)",
            "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}],
        },
        {
            "source": "/app/static/(js|engine|data|guide)/(.*)",
            "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}],
        },
        {
            "source": "/install.(sh|ps1)",
            "headers": [{"key": "Content-Type", "value": "text/plain; charset=utf-8"}],
        },
    ],
}


def fill(text: str, values: dict[str, str], where: str) -> str:
    def one(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"{where}: no value for {{{{ {key} }}}}")
        return values[key]

    return PLACEHOLDER.sub(one, text)


def versioned(html: str) -> str:
    """Tag every link to web/assets/ with a hash of the file, so a changed
    stylesheet, script or screenshot is never served from a stale cache."""
    import hashlib

    def tag(match: re.Match) -> str:
        path = WEB / "assets" / match.group(2)
        if not path.is_file():
            return match.group(0)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
        return f"{match.group(1)}assets/{match.group(2)}?v={digest}"

    return re.sub(r'((?:\.\./)*|\./)assets/([\w./-]+\.(?:css|js|webp|png|svg))', tag, html)


def pages() -> list[Path]:
    return sorted(
        p for p in WEB.rglob("*.html") if not (set(p.relative_to(WEB).parts) & NOT_PAGES)
    )


def render(out: Path, computed: dict[str, str]) -> list[str]:
    """Write every page of web/ into *out*; return their paths."""
    from ui.site import NAME, TAGLINE, VERSION

    partials = {p.stem: p.read_text(encoding="utf-8") for p in (WEB / "partials").glob("*.html")}
    written = []
    for page in pages():
        rel = page.relative_to(WEB)
        depth = len(rel.parts) - 1
        values = {
            "name": escape(NAME),
            "tagline": escape(TAGLINE),
            "version": escape(VERSION),
            "year": str(date.today().year),
            "updated": "3 October 2026",
            "root": "../" * depth or "./",
            **computed,
        }
        # Partials may use every value, and pages every partial.
        values.update({f"partial_{k}": fill(v, values, f"partials/{k}.html") for k, v in partials.items()})
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        html = versioned(fill(page.read_text(encoding="utf-8"), values, str(rel)))
        if "{{" in html:
            raise ValueError(f"{rel}: a placeholder was left unfilled near {html[html.index('{{'):][:40]!r}")
        target.write_text(html, encoding="utf-8")
        written.append(rel.as_posix())
    for asset in WEB.rglob("*"):
        rel = asset.relative_to(WEB)
        # (Provenance sidecars, *.webp.json, stay in the repo; they are not the site.)
        if (
            asset.is_file()
            and asset.suffix not in (".html", ".py", ".pyc")
            and not re.search(r"\.(png|webp|jpe?g)\.json$", asset.name)
            and not (set(rel.parts) & (NOT_PAGES | {"__pycache__"}))
        ):
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, target)
    return written


# The name as LaTeX sets it, $L\\text{emma}t\\alpha$: one slot per letter, the
# plain letter and its typeset form stacked, so the two can trade places.
WORDMARK = list(zip("Lemmata", ["𝐿", "e", "m", "m", "a", "𝑡", "𝛼"]))


def wordmark(name: str, *, animate: bool) -> str:
    """The site's name as a wordmark: typeset (static), or trading forms (the nav)."""
    if name != "Lemmata":  # an institution's own name is set plainly
        return f'<span class="wm-name">{escape(name)}</span>'
    if not animate:
        return '<span class="wm wm--static" aria-hidden="true">' + "".join(t for _, t in WORDMARK) + "</span>"
    slots = "".join(
        f'<span class="wm-slot" style="--i: {i}"><span class="wm-plain">{p}</span><span class="wm-tex">{t}</span></span>'
        for i, (p, t) in enumerate(WORDMARK)
    )
    return f'<span class="wm" data-wordmark aria-hidden="true">{slots}</span>'


def computed_content() -> dict[str, str]:
    """Content the pages show that the engine itself produces (see web/content.py)."""
    sys.path.insert(0, str(WEB))
    try:
        import content  # web/content.py
    finally:
        sys.path.pop(0)
    from ui.site import NAME

    return {
        **content.build(),
        "wordmark_nav": wordmark(NAME, animate=True),
        "wordmark_static": wordmark(NAME, animate=False),
    }


def main(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]).resolve() if "--out" in argv else ROOT / "dist"
    import build_static  # ui/build_static.py

    # dist/.vercel links the folder to its Vercel project; keep it across rebuilds.
    link = None
    if (out / ".vercel").exists():
        link = out.parent / ".vercel-link.tmp"
        shutil.rmtree(link, ignore_errors=True)
        shutil.move(out / ".vercel", link)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    status = build_static.main(["--out", str(out / "app")])
    if status:
        return status
    (out / "app" / "vercel.json").unlink(missing_ok=True)
    written = render(out, computed_content())
    (out / "vercel.json").write_text(json.dumps(VERCEL, indent=2) + "\n", encoding="utf-8")
    if link is not None:
        shutil.move(link, out / ".vercel")
    print(f"built the site: {len(written)} pages ({', '.join(written)}) with the app at app/")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(UI))
    sys.exit(main(sys.argv[1:]))
