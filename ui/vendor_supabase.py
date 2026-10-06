#!/usr/bin/env python
"""Vendor supabase-js, the client for accounts and sync, for offline-first use.

Supabase publishes a self-contained build (``dist/umd/supabase.js``) that
assigns one ``var supabase``.  We save it as an ES module by appending the
exports the app uses, so it loads like every other module here and only when
``site.json`` configures accounts (``js/account.js`` imports it lazily).  The
esm.sh bundle would also do, but it pulls in Node shims (buffer, process,
events, tty) that this build does without.

Run with:  uv run python ui/vendor_supabase.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

VERSION = "2.117.2"
URL = f"https://cdn.jsdelivr.net/npm/@supabase/supabase-js@{VERSION}/dist/umd/supabase.js"
OUT = Path(__file__).resolve().parent / "static" / "vendor" / "supabase" / "supabase.mjs"

FOOTER = "\nexport default supabase;\nexport const createClient = supabase.createClient;\n"


def main() -> int:
    with urllib.request.urlopen(URL, timeout=60) as resp:  # noqa: S310 - fixed host
        body = resp.read().decode("utf-8")
    if not body.startswith("var supabase="):
        print(f"{URL} is not the expected build (it should begin 'var supabase=').", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = f"/* @supabase/supabase-js {VERSION} (MIT), from {URL}; see ui/vendor_supabase.py */\n"
    OUT.write_text(header + body + FOOTER, encoding="utf-8")
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]
    print(f"wrote {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT} ({len(body) // 1024} KB, sha256 {digest}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
