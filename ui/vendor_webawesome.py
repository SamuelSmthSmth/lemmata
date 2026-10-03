#!/usr/bin/env python
"""Vendor the Web Awesome component graph for fully offline use.

Web Awesome ships ``dist-cdn/``, a pre-bundled build meant to be loaded
directly in the browser with no bundler -- which is exactly this project's
constraint.  We could fetch it from their CDN at runtime, but that would break
the "no network at runtime" promise (and the app would not work offline), so we
mirror the files to disk instead, the same way ``vendor_codemirror.py`` does.

The trick that makes this safe is that ``dist-cdn`` never bundles a dependency
twice: every file imports its dependencies by *relative, content-hashed* path::

    components/switch/switch.js -> ../../chunks/chunk.SVFNJFHB.js

so several components converge on one shared chunk and exactly one copy of Lit
is ever loaded.  (Loading a second copy of Lit would silently break
``customElements`` registration.)  Because the paths are already relative, we
can copy the graph verbatim -- no import rewriting, just the tree it lives in.

Only the files reachable from the components the UI actually uses are copied.
The whole ``dist-cdn`` tree is 13 MB across ~1200 files (it also carries React
wrappers, type declarations and docs); the reachable subgraph is a few hundred
KB.  ``styles/`` is small and is copied whole, minus the TypeScript sources and
declarations that ship alongside it and are never loaded.

No npm is involved: the package is fetched from the npm registry as a tarball
and read with the standard library.

Run with:  uv run python ui/vendor_webawesome.py
"""

from __future__ import annotations

import io
import posixpath
import re
import shutil
import sys
import tarfile
import urllib.request
from collections import deque
from pathlib import Path

PACKAGE = "@awesome.me/webawesome"
VERSION = "3.14.0"
TARBALL_URL = f"https://registry.npmjs.org/{PACKAGE}/-/webawesome-{VERSION}.tgz"

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "static" / "vendor" / "webawesome"

# Everything inside the tarball lives under this prefix.
PREFIX = "package/dist-cdn/"

# The components the UI uses.  Adding one here is all it takes to vendor it;
# its chunks are picked up automatically because they are reachable.
#
# `badge` is deliberately absent: the auditor used to render a status pill and a
# backend pill on every row, and set the status as type instead (see styles.css),
# so the component is not needed at all.
COMPONENTS = [
    "button",
    "dialog",
    "dropdown",
    "dropdown-item",
    "icon",
    "input",
    "popup",
    "spinner",
    "switch",
    "toast",
    "toast-item",
    "tooltip",
]

# `webawesome.js` is the barrel entry: it exports setBasePath() (required when
# self-hosting, so components can find their icons) and allDefined().
ENTRIES = ["webawesome.js", *(f"components/{name}/{name}.js" for name in COMPONENTS)]

# Whole-tree copies: the token layer, the component styles and the load-bearing
# utilities.  Small (a few hundred KB) and not worth subsetting file by file.
WHOLE_DIRS = ["styles"]

# The styles directory also ships TypeScript sources and declarations for the
# same stylesheets.  Nothing loads them at runtime, so copying the tree whole
# would put a dozen dead files in the repository.
SKIP_SUFFIXES = (".ts", ".tsx", ".map")

# Matches `from"..."`, bare `import"..."`, and dynamic `import("...")`.
IMPORT_RE = re.compile(r'(?:from|import)\s*\(?\s*"([^"]+)"')


def fetch_tarball() -> tarfile.TarFile:
    print(f"fetching {PACKAGE}@{VERSION} ...")
    with urllib.request.urlopen(TARBALL_URL, timeout=180) as resp:  # noqa: S310 - fixed host
        blob = resp.read()
    print(f"  {len(blob) / 1_000_000:.1f} MB")
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")


def build_index(tar: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    """Map each `dist-cdn`-relative path to its tarball member."""
    index: dict[str, tarfile.TarInfo] = {}
    for member in tar.getmembers():
        if member.isfile() and member.name.startswith(PREFIX):
            index[member.name[len(PREFIX) :]] = member
    if not index:
        raise SystemExit(f"tarball contained nothing under {PREFIX!r}")
    return index


def read_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = tar.extractfile(member)
    if handle is None:  # pragma: no cover - members are regular files
        raise SystemExit(f"could not read {member.name}")
    return handle.read()


def resolve(specifier: str, importer: str) -> str | None:
    """Resolve a relative specifier from `importer` to a dist-cdn path.

    Absolute URLs and bare package specifiers return None; `dist-cdn` contains
    none of either, and the caller reports any that appear.
    """
    if specifier.startswith(("http://", "https://", "data:")):
        return None
    if not specifier.startswith((".", "/")):
        return None
    base = posixpath.dirname(importer)
    resolved = posixpath.normpath(posixpath.join(base, specifier))
    # Refuse anything that would escape the tree.
    if resolved.startswith("..") or resolved.startswith("/"):
        return None
    return resolved


def main() -> int:
    tar = fetch_tarball()
    index = build_index(tar)
    # Start from an empty tree (only once the download has succeeded), so a
    # component dropped from COMPONENTS takes its now-unreachable chunks with it.
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)

    queue: deque[str] = deque(ENTRIES)
    seen: set[str] = set()
    unresolved: set[str] = set()

    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)

        member = index.get(path)
        if member is None:
            unresolved.add(path)
            continue

        source = read_member(tar, member)
        dest = DEST / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source)

        for specifier in IMPORT_RE.findall(source.decode("utf-8", "replace")):
            dep = resolve(specifier, path)
            if dep is None:
                unresolved.add(f"{path} -> {specifier}")
                continue
            queue.append(dep)

    # The stylesheets are tiny and interdependent; copy them whole.
    for directory in WHOLE_DIRS:
        for path, member in index.items():
            if not path.startswith(f"{directory}/"):
                continue
            if path.endswith(SKIP_SUFFIXES):
                continue
            dest = DEST / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_member(tar, member))
            seen.add(path)

    # Attribution: MIT requires the licence travel with the copy.
    license_member = index.get("LICENSE.md") or tar.getmember("package/LICENSE.md")
    (DEST / "LICENSE.md").write_bytes(read_member(tar, license_member))
    (DEST / "VERSION").write_text(f"{PACKAGE} {VERSION}\n", encoding="utf-8")

    copied = sorted(p for p in seen if (DEST / p).is_file())
    size = sum((DEST / p).stat().st_size for p in copied) + (
        DEST / "LICENSE.md"
    ).stat().st_size
    print(f"vendored {len(copied)} files, {size / 1024:.0f} KB into "
          f"{DEST.relative_to(ROOT.parent)}")
    for name in COMPONENTS:
        if not (DEST / "components" / name / f"{name}.js").is_file():
            print(f"ERROR: component {name!r} did not resolve", file=sys.stderr)
            return 1

    if unresolved:
        print(f"NOTE: {len(unresolved)} unresolved specifier(s):", file=sys.stderr)
        for item in sorted(unresolved):
            print(f"  {item}", file=sys.stderr)
        return 1
    print("no unresolved imports - fully offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
