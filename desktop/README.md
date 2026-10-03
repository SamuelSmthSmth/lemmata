# The desktop app

The website's static build (`ui/build_static.py`) in a native window, made
with [Tauri 2](https://v2.tauri.app). The checker runs inside the page, in
Pyodide, exactly as on the website. So the app works **offline** from the first
launch, keeps work **on this computer**, and gives the same verdicts as the
site. It is about 15 MB to download and uses the system's own webview
(WebKitGTK, WebView2, WKWebView), not a bundled browser.

```bash
uv run python desktop/build.py            # installers for this OS
uv run python desktop/build.py --dev      # run it, without bundling
uv run python desktop/verify_desktop.py   # drive the real app over WebDriver (Linux, Windows)
```

You need Rust (`rustup`), Node and, on Linux, the WebKitGTK 4.1 development
files. Installers land in `desktop/src-tauri/target/release/bundle/`:
- Linux: `.deb`, `.rpm`, `.AppImage`;
- Windows: `.msi` and an NSIS `.exe`;
- macOS: `.dmg`, built as a universal binary in CI.

## What the shell adds

The page is the website's page. It gets **no IPC**: there are no capabilities,
and it calls nothing in the shell. The shell (`src-tauri/src/lib.rs`) provides
only what a browser otherwise would:

- **Exports** (`.aether`, `.zip`, `.pack.json`, `.tex`) go to the Downloads
  folder under the page's file name, and never overwrite an existing file.
- **Links out of the app**, such as the registry's GitHub page, open in the
  system browser.
  - Links that open a new window are turned into ordinary navigations by an
    initialisation script.
  - Every webview reports navigations to the shell; not every one reports new
    windows (WebKitGTK under automation, for one).
- **The wording** of where work is kept. `build.py` marks the page
  `<meta name="lemmata-shell" content="desktop">`, and `js/site.js` makes
  "Saved in this browser" read "Saved on this computer".

A strict Content-Security-Policy applies (`tauri.conf.json`):
- **Scripts:** only the app's own, plus `wasm-unsafe-eval` for Pyodide. Tauri
  hashes the page's one inline script at build time.
- **Network:** only `https:`, for the pack registry. A registry that
  `site.json` names over plain `http` is added by name.

## An institution's copy

Use the same `site.json` as the website, set with `LEMMATA_SITE`. It supplies
the app's name, its accent colour, its registry and the packs a first launch
installs. Add an identifier, so your app installs beside this one rather than
over it, and optionally an icon (a square PNG of at least 512 px):

```bash
LEMMATA_SITE=proof-lab.json uv run python desktop/build.py --identifier ac.example.prooflab --icon logo.png
```

The version is the engine's (`pyproject.toml`).

## Releases

`.github/workflows/desktop.yml` runs in two modes:
- **On every relevant push:** it builds the app on Linux and runs
  `verify_desktop.py` under `xvfb-run`.
- **On a `v*` tag or a manual run:** it builds installers on Linux, Windows
  and macOS. A tag also drafts a GitHub release with them attached.

The installers are **not code-signed** yet:
- Windows SmartScreen warns on the first launch.
- On macOS the app is ad-hoc signed, so it opens with right-click → Open.

Signing needs an Apple Developer ID and a Windows code-signing certificate.
Automatic updates (Tauri's updater) need a signing key and a public release
URL. Both wait for a public release channel.

## The icon

`icon.svg` is the mark: an L whose foot ends in ∎, the tombstone that closes a
proof. `src-tauri/icons/` is generated from it:

```bash
rsvg-convert -w 1024 -h 1024 desktop/icon.svg -o /tmp/icon.png
cd desktop && npx tauri icon /tmp/icon.png -o src-tauri/icons
```

Then delete the `android/`, `ios/` and `Square*` files. The same mark is the
website's favicon (`ui/static/icon.svg`).
