#!/usr/bin/env python
"""Vendor the CodeMirror 6 ESM dependency graph for fully offline use.

CodeMirror 6 is a graph of interdependent ESM packages that share singleton
state.  Facets such as ``indentUnit`` only take effect if every package sees
the *same* copy of ``@codemirror/state``, so bundling each package on its own
would inline duplicate copies and silently break that shared state.

esm.sh already dedupes correctly: it rewrites each dependency to a canonical
absolute path pinned to an exact version, e.g.
``/@codemirror/state@6.7.6/es2022/state.mjs``.  So rather than bundling, we
mirror that graph to disk and rewrite each absolute import to a relative one.
Every importer converges on the same file, preserving dedup, and nothing is
fetched at runtime.

Run with:  uv run python ui/vendor_codemirror.py
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request
from collections import deque
from pathlib import Path

ESM_BASE = "https://esm.sh"
ROOT = Path(__file__).resolve().parent
ESM_DIR = ROOT / "static" / "vendor" / "esm"

# Entry points, requested as package roots.  esm.sh answers a root request with
# a JS stub that side-effect-imports dependencies and re-exports the one
# version-pinned module, which is what makes the walk below converge.
#
# NOTE: do not import shared symbols from the `codemirror` meta-package stub.
# It re-exports *all* of its dependencies, so names like ``EditorView`` are
# ambiguous across star-exports and get omitted.  Only ``basicSetup`` /
# ``minimalSetup`` / ``EditorView`` are safe there; see ui/static/js/editor.js, which
# imports each symbol from its owning package instead.
ENTRIES = [
    "codemirror@6.0.2",
    "@codemirror/state@6",
    "@codemirror/view@6",
    "@codemirror/language@6",
    "@codemirror/commands@6",
    "@codemirror/search@6",
    "@lezer/highlight@1",
]

# Matches `from"/abs/path"` and bare `import"/abs/path"`: how esm.sh rewrites
# every external dependency.
IMPORT_RE = re.compile(r'(?:from|import)\s*"([^"]+)"')


def fetch(path: str) -> str:
    url = f"{ESM_BASE}{path}"
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed host
        return resp.read().decode("utf-8")


def local_name(path: str) -> str:
    """Map an esm.sh absolute path to a local relative path.

    ``^`` is not a legal RFC 3986 path character, so a static file server would
    need it percent-encoded.  Sanitize it here; because every import rewrite
    goes through this same function, the graph stays internally consistent.
    """
    clean = path.split("?", 1)[0].lstrip("/")
    if not clean.endswith(".mjs") and not clean.endswith(".js"):
        # Package roots get a JS stub (not an HTTP redirect), so name it.
        clean += ".mjs"
    return clean.replace("^", "_")


def main() -> int:
    ESM_DIR.mkdir(parents=True, exist_ok=True)

    queue: deque[str] = deque(f"/{entry}" for entry in ENTRIES)
    seen: set[str] = set()
    external: set[str] = set()

    while queue:
        path = queue.popleft()
        name = local_name(path)
        if name in seen:
            continue
        seen.add(name)

        dest = ESM_DIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        source = fetch(path)

        def rewrite(match: re.Match[str], dest: Path = dest) -> str:
            target = match.group(1)
            if target.startswith(("http://", "https://")):
                external.add(target)
                return match.group(0)
            if not target.startswith("/"):
                return match.group(0)
            dep = local_name(target)
            queue.append(target)
            # Relative path from this file's directory to the dependency.
            rel = os.path.relpath(ESM_DIR / dep, dest.parent).replace("\\", "/")
            if not rel.startswith("."):
                rel = "./" + rel
            return match.group(0).replace(f'"{target}"', f'"{rel}"')

        dest.write_text(IMPORT_RE.sub(rewrite, source), encoding="utf-8")

    total = sum(1 for _ in ESM_DIR.rglob("*.mjs"))
    print(f"vendored {total} modules into {ESM_DIR.relative_to(ROOT.parent)}")
    if external:
        print(f"WARNING: {len(external)} unresolved external import(s):")
        for url in sorted(external):
            print(f"  {url}")
        return 1
    print("no external imports remain - fully offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
