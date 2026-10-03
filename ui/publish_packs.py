#!/usr/bin/env python
"""Publish the bundled course packs to a checkout of the pack registry.

``courses/*.json`` stays the source of truth -- the engine's tests check every
entry there -- and the registry (``SamuelSmthSmth/lemmata-packs``) is how an
edited pack reaches students without a new release of the app.  This copies
each pack to ``packs/<name>.pack.json`` in the registry checkout, after
validating it.  Raise a pack's ``version`` before publishing a change, or
browsers that installed the old copy will not be offered it as an update.

Run with:  uv run python ui/publish_packs.py ../lemmata-packs
Then commit and open a PR there; its CI re-checks every entry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aether.packs import load_packs  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    registry = Path(argv[0]).resolve()
    if not (registry / "tools" / "build_index.py").exists():
        print(f"{registry} does not look like a checkout of the pack registry")
        return 1
    for pack in load_packs(ROOT / "courses"):
        target = registry / "packs" / f"{pack['name']}.pack.json"
        source = next(p for p in (ROOT / "courses").glob("*.json") if json.loads(p.read_text(encoding="utf-8")).get("name") == pack["name"])
        target.parent.mkdir(parents=True, exist_ok=True)
        before = target.read_bytes() if target.exists() else None
        target.write_bytes(source.read_bytes())
        state = "unchanged" if before == target.read_bytes() else ("updated" if before else "added")
        print(f"  {pack['name']} v{pack['version']}: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
