#!/usr/bin/env python
"""Build the static site: the whole app, with the checker running in the browser.

``dist/`` is a folder of plain files that any web server can host -- Vercel, a
university's own server, or a desktop shell -- with no Python behind it.  The
engine runs inside the page, in Pyodide (``js/engine-worker.js``), and what the
development server computes on request is computed once, here:

    dist/
      index.html                 the page, named from ui/site.json, marked
                                 <meta name="lemmata-engine" content="browser">
      static/                    ui/static/, including vendor/pyodide/
      static/engine/engine.zip   the `aether` package and the UI's job modules
      static/data/library.json   the bundled pack catalogue      (GET /api/library)
      static/data/capabilities.json  the capability matrix       (GET /api/capabilities)
      static/data/site.json      name, tagline, version          (GET /api/site)
      vercel.json                cache headers for Vercel

This is a distribution step only.  Development needs no build: ``python -m ui``
serves ui/static/ as it is.

Run with:  uv run python ui/vendor_pyodide.py   (once)
           uv run python ui/build_static.py [--out DIR]
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from html import escape
from pathlib import Path

UI = Path(__file__).resolve().parent
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

# What the browser's Python needs besides the engine: the jobs and what they import.
UI_MODULES = ["__init__.py", "engine_jobs.py", "latex_report.py", "site.py", "site.json"]

VERCEL = {
    "cleanUrls": False,
    "headers": [
        {
            # Pyodide, the wheels and the vendored libraries never change under
            # the same path: they are re-vendored into place with new names.
            "source": "/static/vendor/(.*)",
            "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}],
        },
        {
            "source": "/static/(js|engine|data|guide)/(.*)",
            "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}],
        },
    ],
}


def engine_zip(target: Path) -> int:
    """The `aether` package and the UI's job modules, as /engine/{aether,ui} in Pyodide."""
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / "src" / "aether").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, f"aether/{path.relative_to(ROOT / 'src' / 'aether').as_posix()}")
                count += 1
        for name in UI_MODULES:
            archive.write(UI / name, f"ui/{name}")
            count += 1
    return count


def main(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]).resolve() if "--out" in argv else ROOT / "dist"
    vendor = UI / "static" / "vendor" / "pyodide"
    if not (vendor / "pyodide.mjs").exists():
        print("Pyodide is not vendored yet: run `uv run python ui/vendor_pyodide.py` first.")
        return 1

    from ui.app import capabilities, library
    from ui.site import NAME, SITE, TAGLINE, VERSION

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(UI / "static", out / "static", ignore=shutil.ignore_patterns("__pycache__"))

    wheels = sorted(p.name for p in (vendor / "wheels").glob("*.whl"))
    (out / "static" / "vendor" / "pyodide" / "wheels.json").write_text(json.dumps(wheels) + "\n")

    data = out / "static" / "data"
    data.mkdir()
    (data / "library.json").write_text(json.dumps(library(), ensure_ascii=False))
    (data / "capabilities.json").write_text(json.dumps(capabilities(), ensure_ascii=False))
    (data / "site.json").write_text(json.dumps({**SITE, "version": VERSION}, ensure_ascii=False))

    (out / "static" / "engine").mkdir()
    files = engine_zip(out / "static" / "engine" / "engine.zip")

    html = (UI / "static" / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(NAME)} · {escape(TAGLINE)}</title>", html, count=1)
    marker = '    <meta name="lemmata-engine" content="browser" />\n'
    html = html.replace('    <meta name="viewport"', marker + '    <meta name="viewport"', 1)
    if marker not in html:
        print("index.html has no viewport meta to place the engine marker beside")
        return 1
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "vercel.json").write_text(json.dumps(VERCEL, indent=2) + "\n")

    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"built {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {total / 1e6:.1f} MB")
    print(f"  {len(library())} packs, {len(capabilities())} capability rows, engine archive of {files} files")
    print(f"  serve it with:  python -m http.server --directory {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
