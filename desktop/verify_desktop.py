#!/usr/bin/env python
"""Drive the real desktop app over WebDriver and check what the shell adds.

    uv run python desktop/verify_desktop.py [--skip-build]

The web app itself is covered by ui/verify_browser.py; this checks the same
page inside the desktop shell, on the platform's own webview (WebKitGTK on
Linux), where things can differ from Chrome:

- the checker boots in Pyodide and checks proofs, with the page's
  Content-Security-Policy in force (no inline-script or wasm violations);
- a pack installs from a registry (fetch, CORS, sha256 via crypto.subtle);
- exports are saved to the Downloads folder, and never overwrite;
- links out of the app go to the system browser, and the window stays put;
- the workspace survives quitting and reopening the app.

It builds the app against a local fixture registry (the one
ui/verify_browser.py uses), runs it with a throwaway home (XDG dirs), and
talks WebDriver to `tauri-driver` (cargo install tauri-driver --locked),
which on Linux needs WebKitWebDriver.  With no display it starts a headless
one: `mutter --headless` if present (run it under `xvfb-run` otherwise, as CI
does).  Linux and Windows only: Tauri has no WebDriver for macOS.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
ROOT = DESKTOP.parent
sys.path.insert(0, str(ROOT))

import ui.verify_browser as vb  # noqa: E402  (the fixture registry)

failures: list[str] = []


def check(condition: bool, message: str) -> bool:
    print(f"  {'ok  ' if condition else 'FAIL'} {message}", flush=True)
    if not condition:
        failures.append(message)
    return condition


# ---------------------------------------------------------------------------
# A minimal W3C WebDriver client: all this needs is scripts and sessions.
# ---------------------------------------------------------------------------

DRIVER = ""
SESSION = ""


def wd(method: str, path: str, body: dict | None = None, timeout: float = 120) -> dict:
    data = json.dumps(body if body is not None else {}).encode() if method == "POST" else None
    request = urllib.request.Request(f"{DRIVER}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path}: {err.code} {err.read()[:400]!r}") from None


def js(script: str):
    """Run *script* (an expression, or a promise) in the page and return its JSON value."""
    body = {"script": f"const done = arguments[arguments.length - 1]; Promise.resolve().then(() => ({script})).then(v => done(JSON.stringify(v === undefined ? null : v)), e => done(JSON.stringify({{error: String(e)}})));", "args": []}
    value = wd("POST", f"/session/{SESSION}/execute/async", body)["value"]
    return json.loads(value) if isinstance(value, str) else value


def wait_for(script: str, timeout: float = 60, every: float = 0.3):
    deadline = time.time() + timeout
    value = js(script)
    while time.time() < deadline and not value:
        time.sleep(every)
        value = js(script)
    return value


def start_session(binary: Path) -> None:
    global SESSION
    caps = {"capabilities": {"alwaysMatch": {"tauri:options": {"application": str(binary)}}}}
    SESSION = wd("POST", "/session", caps)["value"]["sessionId"]


def end_session() -> None:
    global SESSION
    if SESSION:
        try:
            wd("DELETE", f"/session/{SESSION}", timeout=20)
        except Exception:  # noqa: BLE001 - the app may already be gone
            pass
        SESSION = ""


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

VERDICT = "(document.querySelector('#verdict')||{}).textContent"


def settle(timeout: float = 90) -> str:
    """The verdict once it describes the buffer (the checker boots on first load)."""
    deadline = time.time() + timeout
    verdict = js(VERDICT)
    while time.time() < deadline and (verdict in ("Checking…", "Loading…", "Ready", None, "") or js("!!document.querySelector('#verdict')?.dataset.stale")):
        time.sleep(0.3)
        verdict = js(VERDICT)
    return verdict


def open_proof(source: str) -> str:
    token = base64.urlsafe_b64encode(source.encode()).decode().rstrip("=")
    js(f"(location.href = new URL('index.html?r={time.time_ns()}#p={token}', location.href).href, 1)")
    time.sleep(1.0)
    wait_for("document.readyState === 'complete' && !!document.querySelector('#verdict')", 30)
    return settle()


def checks(home: Path, downloads: Path, opened: Path, examples: dict[str, str], slow: str, binary: Path) -> None:
    print("== the checker, inside the desktop shell ==")
    wait_for("!!document.querySelector('#verdict')", 60)
    verdict = settle(120)
    meta = js("(document.querySelector('#verdict-meta')||{}).textContent")
    check(verdict == "VALID", f"the starting proof checks in the app ({verdict}: {meta})")
    check(js("location.protocol") in ("tauri:", "http:"), f"from the app's own files ({js('location.origin')})")
    check(js("document.documentElement.dataset.theme") in ("light", "dark"), "the inline theme script ran under the CSP")
    check(js("document.querySelector('meta[name=\"lemmata-engine\"]')?.content") == "browser", "with the engine in the page")
    storage = js("document.querySelector('#status-storage')?.textContent")
    check(storage == "Saved on this computer", f"and says where work is kept as an app would ({storage!r})")
    verdict = open_proof(examples["algebraic-blunder"])
    check(verdict == "INVALID" and "Counterexample" in js("document.querySelector('#audit').textContent"), f"a blunder fails with a counterexample ({verdict})")

    shot = os.environ.get("LEMMATA_TEST_SCREENSHOT")
    if shot:
        Path(shot).write_bytes(base64.b64decode(wd("GET", f"/session/{SESSION}/screenshot")["value"]))
        print(f"  (screenshot: {shot})")

    print("== a check over budget restarts the checker ==")
    js("(localStorage.setItem('aether:check-budget-ms', '1500'), 1)")
    verdict = open_proof(slow)
    check(verdict == "TIMEOUT", f"a check that overruns its budget answers TIMEOUT ({verdict})")
    js("(localStorage.removeItem('aether:check-budget-ms'), 1)")
    verdict = open_proof(examples["even-square"])
    check(verdict == "VALID", f"and a fresh checker answers the next proof ({verdict})")

    print("== a pack from the registry ==")
    js("(document.querySelector(\".rail-button[data-view='library']\").click(), 1)")
    status = wait_for("(() => { const t = document.querySelector('.packs-registry')?.textContent || ''; return t.includes('Registry · 4 packs') ? t : ''; })()", 30)
    status = status or js("document.querySelector('.packs-registry')?.textContent")
    check("Registry · 4 packs" in (status or ""), f"the registry is reachable through the CSP ({status!r})")
    js("(() => { const s = document.querySelector('#library-search'); s.value = 'group basics'; s.dispatchEvent(new Event('input')); return 1; })()")
    time.sleep(0.5)
    js("([...document.querySelectorAll('.registry-row')].find(r => r.textContent.includes('Group basics')).querySelector('.text-button--primary').click(), 1)")
    toast = wait_for("(() => [...document.querySelectorAll('#toast wa-toast-item')].map(t => t.textContent).join(' ').includes('Installed Group basics'))()", 90)
    check(bool(toast), "it installs, its checksum verified by crypto.subtle")

    print("== downloads go to the Downloads folder ==")
    open_proof(examples["even-square"])
    for _ in range(2):
        js("(document.querySelector('#download-proof').click(), 1)")
        time.sleep(1.5)
    saved = sorted(p.name for p in downloads.glob("*")) if downloads.exists() else []
    check(len(saved) == 2, f"two exports of one proof are two files, not one overwritten ({saved})")
    check(all((downloads / n).read_text() == examples["even-square"] for n in saved), "each holding the proof")

    print("== links out of the app ==")
    before = js("location.href")
    # Clicked for real (a scripted click on a target=_blank link is a blocked pop-up).
    for href, target in (("https://example.org/lemmata-test", "_blank"), ("https://example.org/same-window", "")):
        js(f"(() => {{ const a = document.createElement('a'); a.id = 'out-link'; a.href = '{href}'; a.target = '{target}'; a.textContent = 'out';"
           " a.style.cssText = 'position:fixed;top:40%;left:40%;z-index:99999;padding:20px;background:#fff'; document.body.append(a); return 1; })()")
        element = wd("POST", f"/session/{SESSION}/element", {"using": "css selector", "value": "#out-link"})["value"]
        wd("POST", f"/session/{SESSION}/element/{next(iter(element.values()))}/click")
        time.sleep(1.0)
        js("(document.querySelector('#out-link')?.remove(), 1)")
    time.sleep(1.5)
    urls = opened.read_text().split() if opened.exists() else []
    check(urls == ["https://example.org/lemmata-test", "https://example.org/same-window"], f"open in the system browser ({urls})")
    check(js("location.href") == before, "and the app stays where it was")

    print("== the workspace survives a restart ==")
    marker = f"marker-{time.time_ns()}"
    js(f"(() => {{ localStorage.setItem('lemmata-desktop-test', '{marker}'); return 1; }})()")
    js("(document.querySelector(\".rail-button[data-view='workspace']\").click(), 1)")
    files_before = js("[...document.querySelectorAll('#explorer .tree-row--file .tree-label')].map(e => e.textContent).sort()")
    end_session()
    time.sleep(1.0)
    start_session(binary)
    wait_for("!!document.querySelector('#verdict')", 60)
    check(js("localStorage.getItem('lemmata-desktop-test')") == marker, "local settings persist")
    installed = wait_for("(() => { document.querySelector(\".rail-button[data-view='library']\").click(); return document.getElementById('library-packs')?.innerText.includes('Group basics') || ''; })()", 30)
    check(bool(installed), "the pack installed from the registry is still installed (IndexedDB persists)")
    js("(document.querySelector(\".rail-button[data-view='workspace']\").click(), 1)")
    files_after = js("[...document.querySelectorAll('#explorer .tree-row--file .tree-label')].map(e => e.textContent).sort()")
    check(bool(files_before) and files_after == files_before, f"and so are the workspace's files ({files_before} → {files_after})")


def main() -> int:
    global DRIVER
    skip_build = "--skip-build" in sys.argv
    driver_bin = shutil.which("tauri-driver") or str(Path.home() / ".cargo" / "bin" / "tauri-driver")
    if not Path(driver_bin).exists():
        print("needs tauri-driver: cargo install tauri-driver --locked")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="lemmata-desktop-"))
    www = DESKTOP / "build" / "test-www"
    # --skip-build reuses the last test build, so its registry's port too.
    built = www / "static" / "data" / "site.json"
    port = int(json.loads(built.read_text())["registry"].rsplit(":", 1)[1].strip("/")) if skip_build and built.exists() else vb.free_port()
    (tmp / "site.json").write_text(json.dumps({"registry": f"http://127.0.0.1:{port}/"}))
    env = {**os.environ, "LEMMATA_SITE": str(tmp / "site.json")}
    if not skip_build:
        subprocess.run(
            [sys.executable, str(DESKTOP / "build.py"), "--www", str(www), "--", "--no-bundle"],
            env=env,
            check=True,
        )
    binary = DESKTOP / "src-tauri" / "target" / "release" / ("lemmata-desktop.exe" if os.name == "nt" else "lemmata-desktop")

    vb.STATIC = True
    vb.DIST = www
    vb.make_registry(tmp / "registry")
    library = json.loads((www / "static" / "data" / "library.json").read_text())
    examples = {e["id"]: e["source"] for p in library if p["name"] == "core/examples" for e in p["entries"]}
    slow = next(e["source"] for p in library for e in p["entries"] if e["id"] == "partial-geometric-sum-needs-r-1")

    # A throwaway home: fresh storage, a Downloads folder we can read, and a
    # system browser that only writes down what it was asked to open.
    home = tmp / "home"
    downloads = tmp / "Downloads"
    opened = tmp / "opened.txt"
    bin_dir = tmp / "bin"
    for d in (home / ".config", home / ".local" / "share", home / ".cache", bin_dir):
        d.mkdir(parents=True, exist_ok=True)
    (home / ".config" / "user-dirs.dirs").write_text(f'XDG_DOWNLOAD_DIR="{downloads}"\n')
    for name in ("xdg-open", "gio"):
        fake = bin_dir / name
        fake.write_text(f'#!/bin/sh\nfor a; do case "$a" in http*) echo "$a" >> "{opened}";; esac; done\n')
        fake.chmod(0o755)
    run_env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    procs: list[subprocess.Popen] = []
    if sys.platform.startswith("linux") and not os.environ.get("LEMMATA_TEST_VISIBLE"):
        # Keep the window off the user's screen: a headless compositor of our own.
        if shutil.which("mutter") and not os.environ.get("CI"):
            display = f"lemmata-test-{os.getpid()}"
            procs.append(subprocess.Popen(
                ["mutter", "--headless", "--wayland", "--no-x11", "--virtual-monitor", "1280x840", "--wayland-display", display],
                env={k: v for k, v in run_env.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
            time.sleep(2.0)
            run_env.update({"WAYLAND_DISPLAY": display, "GDK_BACKEND": "wayland"})
            run_env.pop("DISPLAY", None)
        elif not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            print("no display: run under xvfb-run, or install mutter")
            return 1

    registry = subprocess.Popen([sys.executable, "-c", vb.CORS_SERVER, str(port), str(tmp / "registry")])
    procs.append(registry)
    driver_port = vb.free_port()
    quiet = {} if os.environ.get("LEMMATA_TEST_LOG") else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    procs.append(subprocess.Popen([driver_bin, "--port", str(driver_port)], env=run_env, **quiet))
    DRIVER = f"http://127.0.0.1:{driver_port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            wd("GET", "/status", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    try:
        start_session(binary)
        checks(home, downloads, opened, examples, slow, binary)
    except Exception as exc:  # noqa: BLE001 - report, then clean up
        check(False, f"the run stopped: {exc}")
    finally:
        end_session()
        for proc in reversed(procs):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all desktop checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
