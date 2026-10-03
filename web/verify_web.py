#!/usr/bin/env python
"""Check the public site: its links, its claims, and the moves it makes.

    uv run python web/verify_web.py

Builds the site (ui/build_site.py, offline) into a temporary folder and checks:

- every page is filled in (no {{ placeholder }} left) and every internal link
  and asset on every page resolves to a built file;
- the landing page's audit is what the engine says today: the same steps,
  in the same order, with the same statuses, failing at the same line;
- the symbol grid is the app's own symbol table, and the footer's version
  is the engine's;
- the root vercel.json carries the hosting rules ui/build_site.py writes
  (the /static/ rewrite that keeps old engine URLs working, the headers);
- the CLI installer is valid sh;
- in a real browser (agent-browser, when installed): a permalink from before
  the move (/#p=...) opens in the app at /app/, the storage notice shows once
  and stays dismissed, the scrub stops on the failing step, and the pages
  scroll no wider than a phone.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "ui"), str(WEB)]

failures: list[str] = []


def check(condition: bool, message: str) -> bool:
    print(f"  [{'ok ' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)
    return condition


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []
        self.statuses: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])
        if tag == "li" and "audit-row" in (a.get("class") or "") and a.get("data-line"):
            self.statuses.append((a["data-line"], a["data-status"]))


def resolve(site: Path, page: Path, ref: str) -> Path | None:
    """The built file an internal reference points at, or None for external ones."""
    if re.match(r"^[a-z]+:", ref) or ref.startswith("#") or ref.startswith("//"):
        return None
    path = ref.split("#")[0].split("?")[0]
    target = (page.parent / path).resolve() if not path.startswith("/") else (site / path.lstrip("/")).resolve()
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def static_checks(site: Path) -> None:
    import build_site
    import content

    print("== pages, links and assets ==")
    pages = sorted(site.glob("**/index.html"))
    pages = [p for p in pages if "app" not in p.relative_to(site).parts]
    check(len(pages) == 5, f"five pages built ({', '.join(p.relative_to(site).as_posix() for p in pages)})")
    for page in pages:
        html = page.read_text(encoding="utf-8")
        rel = page.relative_to(site).as_posix()
        check("{{" not in html, f"{rel}: every placeholder filled")
        parser = Links()
        parser.feed(html)
        missing = [r for r in parser.refs if (t := resolve(site, page, r)) is not None and not t.exists()]
        check(not missing, f"{rel}: {len(parser.refs)} links and assets, all internal ones resolve {missing[:4] if missing else ''}")

    print("== the landing page tells the truth ==")
    home = (site / "index.html").read_text(encoding="utf-8")
    parser = Links()
    parser.feed(home)
    hero_statuses = parser.statuses[: len(content.steps(content.check(content.HERO_PROOF)))]
    engine = [(str(s["line"]), s["status"]) for s in content.steps(content.check(content.HERO_PROOF))]
    check(hero_statuses == engine, f"the hero audit is the engine's: {len(engine)} steps, first failure at line {next(l for l, s in engine if s == 'INVALID')}")
    domain = [(str(s["line"]), s["status"]) for s in content.steps(content.check(content.DOMAIN_PROOF))]
    check(parser.statuses[len(engine):] == domain and any(st == "WARNING" for _, st in domain), "and so is the domain-warning audit, in amber")
    check(content.check(content.DOMAIN_GUARDED)["verdict"] == "VALID", "and stating the assumption, as the page says, makes it check clean")
    check(home.count('class="audit-counterexample"') == 1, "red appears once on the page: at the hero's failing step")
    counterexample = content.typeset(next(s for s in content.steps(content.check(content.HERO_PROOF)) if s["status"] == "INVALID")["counterexample"])
    check(counterexample in home.replace("&lt;", "<").replace("&gt;", ">"), f"the counterexample shown is the engine's ({counterexample})")
    symbols = content.symbols()
    check(len(symbols) >= 18 and all(f'data-symbol="{s["symbol"]}"' in home for s in symbols), f"the symbol grid is the app's symbol table ({len(symbols)} symbols)")
    from ui.site import VERSION

    check(f"Engine {VERSION}" in home, f"the footer names engine {VERSION}")

    print("== hosting ==")
    root_config = json.loads((ROOT / "vercel.json").read_text())
    for key in ("rewrites", "headers", "trailingSlash", "cleanUrls"):
        check(root_config.get(key) == build_site.VERCEL[key], f"vercel.json `{key}` matches ui/build_site.py")
    check("ui/build_site.py" in root_config.get("buildCommand", ""), "Vercel builds the whole site")
    check(json.loads((site / "vercel.json").read_text()) == build_site.VERCEL, "the built site carries the same rules")
    check(not (site / "app" / "vercel.json").exists(), "and the app under /app/ has none of its own")
    check((site / "app" / "static" / "engine" / "engine.zip").exists(), "the engine the registry's CI fetches is at /app/static/engine/")
    for script in ("install.sh", "install.ps1"):
        check((site / script).exists(), f"/{script} is published")
    check(subprocess.run(["sh", "-n", str(site / "install.sh")]).returncode == 0, "install.sh is valid sh")


def browser_checks(site: Path) -> None:
    ab = shutil.which("agent-browser")
    if not ab:
        print("== browser checks skipped: agent-browser is not installed ==")
        return
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(site)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = {**os.environ, "AGENT_BROWSER_SESSION": f"verify-web-{os.getpid()}"}
    base = f"http://127.0.0.1:{port}"

    def run(*args: str) -> str:
        return subprocess.run([ab, *args], env=env, capture_output=True, text=True, timeout=60).stdout.strip()

    def js(expr: str):
        out = run("eval", expr)
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return out

    try:
        time.sleep(0.8)
        print("== in a browser ==")
        run("set", "viewport", "1280", "900")
        run("open", f"{base}/?r=1#p=TGV0IHggOiBSZWFs")
        deadline = time.time() + 10
        while time.time() < deadline and "/app/" not in str(js("location.pathname")):
            time.sleep(0.3)
        check(js("location.pathname") == "/app/" and js("location.hash") == "#p=TGV0IHggOiBSZWFs", f"an old /#p= link opens in the app ({js('location.pathname')}{js('location.hash')})")

        js("(localStorage.removeItem('lemmata-storage-notice'), 1)")
        run("open", f"{base}/?r=2")
        time.sleep(1.0)
        check(js("document.querySelector('.notice').hidden") is True, "the storage notice keeps off the hero, so it never covers the failing step")
        js("(scrollTo(0, document.querySelector('.notation').offsetTop + 400), 1)")
        time.sleep(0.8)
        check(js("document.querySelector('.notice').hidden") is False, "and shows once the hero is scrolled away, on a first visit")
        run("click", "[data-notice-dismiss]")
        run("open", f"{base}/download/?r=3")
        time.sleep(1.0)
        check(js("document.querySelector('.notice').hidden") is True, "and stays dismissed, on every page")

        run("open", f"{base}/?r=4")
        time.sleep(1.0)
        run("eval", "(document.querySelector('.run').scrollIntoView(), 1)")
        fail = js("Number(document.querySelector('.run').dataset.fail)")
        deadline = time.time() + 12
        while time.time() < deadline and js("Number(document.querySelector('#scrub').value)") != fail:
            time.sleep(0.4)
        time.sleep(0.6)
        check(js("Number(document.querySelector('#scrub').value)") == fail, f"the scrub plays to the failing step ({fail}) and stops")
        check("invalid" in str(js("document.querySelector('#scrub-readout').textContent")), "and its readout names it invalid")
        check(js("document.querySelectorAll('.specimen .sym.is-lit').length") > 0, "lighting the symbols that step uses")
        js("(() => { const s = document.querySelector('#scrub'); s.value = '0'; s.dispatchEvent(new Event('input')); return 1 })()")
        check(js("document.querySelectorAll('.audit-row.is-ahead').length") > 0 and "Line 4" in str(js("document.querySelector('#scrub-readout').textContent")), "dragging back to the start hides what is not yet checked")

        run("set", "viewport", "390", "844")
        for page in ("", "download/", "privacy/", "terms/", "cookies/"):
            run("open", f"{base}/{page}?r={time.time_ns()}")
            time.sleep(0.8)
            wide = js("document.documentElement.scrollWidth")
            check(wide == 390, f"/{page} fits a phone ({wide}px)")
    finally:
        run("close")
        server.terminate()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lemmata-site-"))
    site = tmp / "site"
    env = {**os.environ, "LEMMATA_OFFLINE": "1"}
    built = subprocess.run([sys.executable, str(ROOT / "ui" / "build_site.py"), "--out", str(site)], env=env, capture_output=True, text=True)
    if built.returncode:
        print(built.stdout[-2000:], built.stderr[-2000:])
        return 1
    os.environ["LEMMATA_OFFLINE"] = "1"
    try:
        static_checks(site)
        browser_checks(site)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all site checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
