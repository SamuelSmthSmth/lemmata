"""The site's identity and configuration, read from ``ui/site.json``.

One file says what this copy of the app is called, how it is branded and where
it finds packs.  The server title, the page ``<title>``, the LaTeX/PDF report
and (through ``/api/site`` or the static build's ``static/data/site.json``)
the frontend all read it from here.  An institution hosting its own copy
writes its own file and points ``LEMMATA_SITE`` at it; nothing else changes.
Code identifiers -- the ``aether`` package, ``.aether`` files, storage keys --
are not the brand and do not follow it.

Fields (all optional; the defaults below are this repository's own site):

* ``name``, ``tagline`` -- what the product is called.
* ``accent`` -- ``{"light": "#rrggbb", "dark": "#rrggbb"}``, the one colour a
  site may brand; the rest of the palette is the design system's.
* ``registry`` -- the pack registry's base URL (its ``index.json`` lives
  there); ``""`` turns the registry off.
* ``preinstall`` -- the bundled packs a first visit installs.
* ``accounts`` -- ``{"url": "https://<ref>.supabase.co", "key": "<publishable key>"}``,
  the Supabase project that signs students in and syncs their work
  (``supabase/migrations/``).  Absent, there is no account UI and work stays
  in the browser.  It is not defaulted: a copy of this site that leaves it out
  never talks to this repository's project.  The key is the *publishable*
  (anon) one, which is meant to be public; never the secret key.
"""

from __future__ import annotations

import json
import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

SITE_FILE = Path(os.environ.get("LEMMATA_SITE") or Path(__file__).resolve().parent / "site.json")

_DEFAULTS: dict[str, Any] = {
    "name": "Lemmata",
    "tagline": "Proof intern",
    "accent": {"light": "#0a5fbf", "dark": "#6cb0ff"},
    "registry": "https://samuelsmthsmth.github.io/lemmata-packs/",
    # Where the app's name in the rail leads: the site the app belongs to.
    "home": "https://lemmata.sous.systems/",
    "preinstall": ["core/examples", "core/mth2008", "core/mth2010", "core/notation"],
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# The accent colours links, the caret, focus rings and the current item, so it
# must read as text on the paper of its theme (WCAG AA, 4.5:1).
_PAPER = {"light": "#ffffff", "dark": "#0e1013"}


def _luminance(hex_colour: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _accent(theme: str, value: Any) -> str:
    fallback = _DEFAULTS["accent"][theme]
    if not (isinstance(value, str) and _HEX.match(value)):
        return fallback
    if contrast(value, _PAPER[theme]) < 4.5:
        print(
            f"site.json: the {theme} accent {value} has {contrast(value, _PAPER[theme]):.1f}:1 contrast on its "
            f"paper ({_PAPER[theme]}); text needs 4.5:1, so the default {fallback} is used instead.",
            file=sys.stderr,
        )
        return fallback
    return value


def _load() -> dict[str, Any]:
    try:
        data = json.loads(SITE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    site: dict[str, Any] = {}
    for key in ("name", "tagline", "home"):
        site[key] = str(data.get(key) or _DEFAULTS[key])
    accent = data.get("accent") if isinstance(data.get("accent"), dict) else {}
    site["accent"] = {theme: _accent(theme, accent.get(theme)) for theme in _DEFAULTS["accent"]}
    registry = data.get("registry", _DEFAULTS["registry"])
    site["registry"] = (registry.rstrip("/") + "/") if isinstance(registry, str) and registry.strip() else ""
    preinstall = data.get("preinstall", _DEFAULTS["preinstall"])
    site["preinstall"] = [p for p in preinstall if isinstance(p, str)] if isinstance(preinstall, list) else list(_DEFAULTS["preinstall"])
    site["accounts"] = _accounts(data.get("accounts"))
    return site


def _accounts(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    url = value.get("url") if isinstance(value, dict) else None
    key = value.get("key") if isinstance(value, dict) else None
    if not (isinstance(url, str) and url.startswith("https://") and isinstance(key, str) and key.strip()):
        print("site.json: accounts needs an https url and a key; accounts are off.", file=sys.stderr)
        return None
    if key.startswith("sb_secret_") or '"service_role"' in _jwt_payload(key):
        print("site.json: accounts.key is a secret key, which must never reach a browser; accounts are off.", file=sys.stderr)
        return None
    return {"url": url.rstrip("/"), "key": key.strip()}


def _jwt_payload(token: str) -> str:
    """The middle of a JWT, decoded (a legacy anon or service_role key), or ""."""
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        return ""
    try:
        return base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)).decode("utf-8", "replace")
    except ValueError:
        return ""


def _engine_version() -> str:
    try:
        return version("aether")
    except PackageNotFoundError:
        return "0.0.0"


SITE = _load()
NAME = SITE["name"]
TAGLINE = SITE["tagline"]
VERSION = _engine_version()
