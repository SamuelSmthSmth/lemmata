#!/usr/bin/env python
"""Build the desktop app: the static site in a Tauri shell.

    uv run python desktop/build.py                 installers for this OS
    uv run python desktop/build.py --dev           run it, without bundling
    uv run python desktop/build.py --identifier ac.example.proofs --icon logo.png
    uv run python desktop/build.py -- --bundles deb   (anything after -- goes to `tauri build`)

What it does:

1. vendors Pyodide (``ui/vendor_pyodide.py``; a no-op once done);
2. writes the static build to ``desktop/build/www`` (``ui/build_static.py``),
   so the app is exactly the website, with the checker in the page;
3. names the app from ``site.json`` (``LEMMATA_SITE`` picks another file, as
   for the static build) and versions it as the engine, in a generated Tauri
   config, ``desktop/build/tauri.generated.json``;
4. runs ``tauri build`` (or ``tauri dev``) with that config.

An institution's copy is the same command with its own ``LEMMATA_SITE``, an
``--identifier`` (so it installs beside, not over, this one) and an
``--icon`` (a square PNG, at least 512 px).

Needs Rust (https://rustup.rs), Node, and on Linux the WebKitGTK 4.1
development files.  Installers land in
``desktop/src-tauri/target/release/bundle/``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

DESKTOP = Path(__file__).resolve().parent
ROOT = DESKTOP.parent
BUILD = DESKTOP / "build"
WWW = BUILD / "www"
DEFAULT_IDENTIFIER = "systems.sous.lemmata"

sys.path.insert(0, str(ROOT))


def run(*cmd: str | Path, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def tool_env() -> dict[str, str]:
    """The environment with rustup's cargo on PATH even when the shell profile lacks it."""
    env = dict(os.environ)
    cargo = Path.home() / ".cargo" / "bin"
    if shutil.which("cargo") is None and cargo.is_dir():
        env["PATH"] = f"{cargo}{os.pathsep}{env.get('PATH', '')}"
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dev", action="store_true", help="run the app (tauri dev) instead of building installers")
    parser.add_argument("--identifier", default=DEFAULT_IDENTIFIER, help=f"reverse-DNS app id (default {DEFAULT_IDENTIFIER})")
    parser.add_argument("--icon", type=Path, help="a square PNG to make the app's icons from")
    parser.add_argument("--skip-site", action="store_true", help="reuse the built site as it is")
    parser.add_argument("--www", type=Path, default=WWW, help="where to write the static site (default desktop/build/www)")
    parser.add_argument("tauri_args", nargs="*", help="passed on to tauri build / dev (put them after --)")
    args = parser.parse_args()

    env = tool_env()
    npx = shutil.which("npx", path=env["PATH"])
    if shutil.which("cargo", path=env["PATH"]) is None or npx is None:
        print("The desktop build needs Rust (https://rustup.rs) and Node (npx) on PATH.")
        return 1

    if not args.skip_site:
        run(sys.executable, ROOT / "ui" / "vendor_pyodide.py")
        run(sys.executable, ROOT / "ui" / "build_static.py", "--out", args.www)
        (args.www / "vercel.json").unlink(missing_ok=True)
        # Mark the page as the app's copy, so its copy says "on this computer" (js/site.js).
        page = args.www / "index.html"
        html = page.read_text(encoding="utf-8")
        page.write_text(html.replace("<head>", '<head>\n    <meta name="lemmata-shell" content="desktop" />', 1), encoding="utf-8")

    # Read the site after the build, from the same file it used.
    from ui.site import NAME, SITE, SITE_FILE, VERSION

    config: dict = {
        "productName": NAME,
        "version": VERSION,
        "identifier": args.identifier,
        "build": {"frontendDist": str(args.www.resolve())},
    }
    # The page may fetch only its own files and https:, so a registry served
    # over plain http (an intranet, or the tests' local one) is allowed by name.
    registry = urlsplit(SITE.get("registry") or "")
    if registry.scheme == "http" and registry.netloc:
        config["app"] = {"security": {"csp": {"connect-src": f"'self' https: http://{registry.netloc}"}}}
    if args.icon:
        icons = BUILD / "icons"
        run(npx, "tauri", "icon", args.icon.resolve(), "-o", icons, cwd=DESKTOP, env=env)
        config["bundle"] = {
            "icon": [str(icons / n) for n in ("32x32.png", "128x128.png", "128x128@2x.png", "icon.icns", "icon.ico")]
        }
    generated = BUILD / "tauri.generated.json"
    BUILD.mkdir(exist_ok=True)
    generated.write_text(json.dumps(config, indent=2) + "\n")
    print(f"desktop app: {NAME} {VERSION} ({args.identifier}), site from {SITE_FILE}")

    if not (DESKTOP / "node_modules" / ".bin").is_dir():
        run(shutil.which("npm", path=env["PATH"]) or "npm", "ci", cwd=DESKTOP, env=env)
    command = "dev" if args.dev else "build"
    run(npx, "tauri", command, "--config", generated, *args.tauri_args, cwd=DESKTOP, env=env)
    if not args.dev:
        print(f"installers: {DESKTOP / 'src-tauri' / 'target' / 'release' / 'bundle'} (or target/<triple>/release/bundle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
