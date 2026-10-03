"""The product's user-visible identity, read from ``ui/site.json``.

The name is provisional, so it lives in exactly one place: the server title,
the page ``<title>``, the LaTeX/PDF report and (through ``/api/site``) the
frontend all read it from here.  An institution hosting its own copy edits
``site.json`` and nothing else.  Code identifiers -- the ``aether`` package,
``.aether`` files, storage keys -- are not the brand and do not follow it.
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SITE_FILE = Path(__file__).resolve().parent / "site.json"

_DEFAULTS = {"name": "Lemmata", "tagline": "Proof intern"}


def _load() -> dict[str, str]:
    try:
        data = json.loads(SITE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {key: str(data.get(key) or fallback) for key, fallback in _DEFAULTS.items()}


def _engine_version() -> str:
    try:
        return version("aether")
    except PackageNotFoundError:
        return "0.0.0"


SITE = _load()
NAME = SITE["name"]
TAGLINE = SITE["tagline"]
VERSION = _engine_version()
