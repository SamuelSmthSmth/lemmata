"""HTTP/API smoke test for the web UI.

Starts its own server on a free port, exercises every endpoint and the whole
vendored CodeMirror graph over HTTP, then shuts the server down.

Run with:  uv run python ui/verify_server.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STATIC = ROOT / "static"

sys.path.insert(0, str(PROJECT))

from ui.latex_report import export_report_latex  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> bool:
    print(f"  [{'ok ' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)
    return condition


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Server:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> Server:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ui", "--port", str(self.port)],
            cwd=str(PROJECT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, **self.env} if self.env else None,
        )
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{self.base}/api/health", timeout=1)
                return self
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("server did not become healthy")

    def __exit__(self, *exc: object) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def request(self, path: str, method: str = "GET", payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.headers.get("content-type", ""), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get("content-type", ""), err.read()


def guide_checks() -> None:
    """Every runnable example in the in-app Guide produces the verdict it states.

    The Guide's ``<pre class="try" data-expect=...>`` blocks are what a student
    copies first, so they are held to the engine like the bundled examples.
    """
    import html as html_lib

    from aether import ParseError, ProofChecker

    print("== in-app guide examples ==")
    checker = ProofChecker()
    pattern = re.compile(r'<pre class="try" data-expect="([A-Z ]+)">(.*?)</pre>', re.S)
    total = 0
    for page in sorted((STATIC / "guide").glob("*.html")):
        for expect, body in pattern.findall(page.read_text(encoding="utf-8")):
            total += 1
            source = html_lib.unescape(body)
            try:
                reports = checker.check_source(source)
                if not all(r.is_valid for r in reports):
                    got = "INVALID"
                elif any(r.has_warnings for r in reports):
                    got = "WARN"
                else:
                    got = "VALID"
            except ParseError:
                got = "PARSE ERROR"
            check(got == expect, f"{page.name}: {source.splitlines()[0][:50]!r} -> {got} (says {expect})")
    check(total >= 15, f"the guide carries runnable examples ({total})")


def main() -> int:
    with Server() as server:
        print("== pages and static assets ==")
        for path in ("/", "/static/js/main.js", "/static/aether-language.js", "/static/styles.css"):
            status, _, _ = server.request(path)
            check(status == 200, f"GET {path} -> {status}")

        print("== api ==")
        status, _, _ = server.request("/api/health")
        check(status == 200, f"GET /api/health -> {status}")
        # FastAPI's interactive docs are a handy way to poke the API by hand.
        status, _, _ = server.request("/docs")
        check(status == 200, f"GET /docs -> {status} (Swagger UI)")

        status, _, body = server.request("/api/examples")
        examples = json.loads(body)
        check(status == 200 and len(examples) == 19, f"GET /api/examples -> {len(examples)} examples")
        by_id = {e["id"]: e for e in examples}

        print("== GET /api/site ==")
        from ui.site import NAME, TAGLINE, VERSION

        status, _, body = server.request("/api/site")
        site = json.loads(body)
        check(status == 200 and site == {"name": NAME, "tagline": TAGLINE, "version": VERSION}, f"site identity from ui/site.json: {site}")
        status, _, body = server.request("/")
        check(f"<title>{NAME} · {TAGLINE}</title>".encode() in body, "the page <title> carries the site name")

        print("== GET /api/library ==")
        status, _, body = server.request("/api/library")
        packs = json.loads(body)
        codes = [p["code"] for p in packs]
        check(status == 200 and codes[:1] == ["EXAMPLES"], f"library packs: {codes}")
        check({"MTH2008", "MTH2010", "NOTATION"} <= set(codes), "the course packs are served")
        traps = [e for p in packs for e in p["entries"] if e["kind"] == "trap"]
        check(traps and all(e.get("explanation") for e in traps), f"{len(traps)} traps, each with an explanation")
        check(
            all(e["expected"] in ("VALID", "INVALID", "WARN", "PARSE ERROR") for p in packs for e in p["entries"]),
            "every entry's expected verdict is one the UI knows",
        )

        print("== GET /api/capabilities ==")
        from ui.verify_capabilities import PROBES

        status, _, body = server.request("/api/capabilities")
        rows = json.loads(body)
        check(status == 200 and len(rows) == len(PROBES), f"the Guide's matrix serves every pin ({len(rows)} of {len(PROBES)})")
        check(
            [(r["area"], r["name"], r["expect"]) for r in rows] == [(p.area, p.name, p.expect) for p in PROBES],
            "in the pinned order, with the pinned verdicts",
        )

        print("== POST /api/check (workspace imports) ==")
        lemma = 'Theorem: "Reflexive"\nClaim: forall x : Real, x = x\nProof:\n    Given x : Real\n    Step: x = x\nQED\n'
        main_src = 'import "shared/lemma.aether"\nLet y : Real\nStep: y = y\n'
        _, _, body = server.request(
            "/api/check",
            "POST",
            {"source": main_src, "path": "sheets/one.aether", "files": {"shared/lemma.aether": lemma, "sheets/one.aether": main_src}},
        )
        data = json.loads(body)
        # As on disk (cwd), the workspace root is the fallback import root.
        check(data["verdict"] == "VALID", f"a root-relative import resolves from a subfolder ({data['verdict']})")
        _, _, body = server.request(
            "/api/check",
            "POST",
            {"source": main_src.replace("shared/", "missing/"), "path": "sheets/one.aether", "files": {"shared/lemma.aether": lemma}},
        )
        data = json.loads(body)
        check(data["verdict"] == "INVALID", f"a file the workspace does not hold is not found ({data['verdict']})")
        _, _, body = server.request(
            "/api/check",
            "POST",
            {
                "source": main_src.replace('"shared/', '"../shared/'),
                "path": "sheets/one.aether",
                "files": {"shared/lemma.aether": lemma},
            },
        )
        data = json.loads(body)
        first = data["reports"][-1]["results"][0]["message"] if data["reports"] else data
        check(data["verdict"] == "VALID", f"an import from another workspace folder verifies ({data['verdict']}: {first})")

        print("== POST /api/check ==")
        _, _, body = server.request(
            "/api/check", "POST", {"source": by_id["even-square"]["source"], "strict_domains": False}
        )
        data = json.loads(body)
        check(data["verdict"] == "VALID", f"even-square verdict is {data['verdict']}")
        check(data["summary"]["total"] == 8, f"even-square audited {data['summary']['total']} steps")
        step = data["reports"][0]["results"][3]
        check(step["backend"] == "SymPy", f"step 4 backend is {step['backend']}")
        check(bool(step["active_hypotheses"]), "steps carry active_hypotheses")
        check(step["source_line"] is not None, "steps carry source_line")
        check(step.get("diagnostic_range") is not None, "steps carry diagnostic_range")

        print("== POST /api/export/latex ==")
        _, _, body = server.request(
            "/api/export/latex", "POST", {"source": by_id["even-square"]["source"], "standalone": True}
        )
        latex_data = json.loads(body)
        check(bool(latex_data.get("latex")), "LaTeX export produced non-empty output")
        check("\\documentclass" in latex_data["latex"], "LaTeX export contains documentclass")
        check("\\begin{align*}" in latex_data["latex"], "LaTeX export contains align* environment")

        # The report is appended by the UI layer (ui/latex_report.py), not by
        # the engine's exporter, so assert each of its sections is present and
        # that the source listing survives verbatim.
        report = latex_data["latex"]
        for section in (
            "Verification Report",
            "Proof State",
            "Original Proof Source",
        ):
            check(f"\\aesection{{{section}}}" in report, f"report has a {section} section")
        check("\\begin{longtable}" in report, "report typesets its tables with longtable")
        check("Given n : Int" in report, "report includes the original source verbatim")
        check("MultipleOf" in report, "report quotes the canonical statements")

        # The .tex is what a user takes away to edit, so it keeps the plain
        # article presentation: nothing from the designed style may leak into
        # it.  The designed style is generated directly here, because the PDF
        # endpoint's own .tex is compiled away rather than returned.
        for marker in (
            "\\aeverdict",
            "\\aechip",
            "\\aecard",
            "\\begin{aestep}",
            "\\begin{aecode}",
            "\\begin{aefinding}",
        ):
            check(marker not in report, f"the .tex export stays plain (no {marker})")
        check("\\aelabel" in report, "the .tex export keeps its own label macro")

        print("== designed export style ==")
        designed = export_report_latex(
            by_id["even-square"]["source"],
            standalone=True,
            breakdown=True,
            session={"timeline": [{"verdict": "VALID", "n": 2, "ts": 1759100000000}]},
            style="fancy",
        )
        cover, opener, body = designed.partition("\\aesection{")
        check(bool(opener), "the designed style is made of numbered sections")
        check("\\begin{tcolorbox}[aecover]" in cover, "the designed style opens on the cover plate")
        check("VALID" in cover, "the cover carries the verdict")
        check("\\aecard{" in body, "the proof opens with the at-a-glance strip")
        check("\\aepage" in designed, "a section opens a fresh page where the layout wants one")
        check("\\begin{aestep}" in body, "the designed style audits as step rows")
        check("0A5FBF" in designed, "the designed style uses the site accent")
        check(
            re.findall(r"\\aesection\{(\d\d)\}\{([^}]*)\}", designed)
            == [
                ("01", "The Proof"),
                ("02", "Auditor"),
                ("03", "Proof State"),
                ("04", "Session"),
                ("05", "Source"),
                ("06", "About"),
            ],
            "the designed style numbers its sections in reading order",
        )
        check(
            "\\begin{aefinding}" not in designed,
            "a proof that clears has no Findings section",
        )
        check("Given n : Int" in designed, "the designed style includes the source verbatim")
        check(designed.rstrip().endswith("\\end{document}"), "the designed style is a standalone document")

        print("== designed export style (a failing proof) ==")
        broken = export_report_latex(
            by_id["algebraic-blunder"]["source"],
            standalone=True,
            breakdown=True,
            style="fancy",
        )
        check("\\begin{aefinding}" in broken, "a failing step is written up as a finding")
        check(
            re.findall(r"\\aesection\{(\d\d)\}\{([^}]*)\}", broken)[1] == ("02", "Findings"),
            "the findings section slots in ahead of the auditor",
        )

        print("== POST /api/export/latex (breakdown off) ==")
        _, _, body = server.request(
            "/api/export/latex",
            "POST",
            {"source": by_id["even-square"]["source"], "standalone": True, "breakdown": False},
        )
        plain = json.loads(body).get("latex", "")
        check("\\documentclass" in plain, "breakdown off still produces the proof document")
        check("aesection" not in plain, "breakdown off leaves the engine's output untouched")

        print("== POST /api/export/latex (session data) ==")
        _, _, body = server.request(
            "/api/export/latex",
            "POST",
            {
                "source": by_id["even-square"]["source"],
                "standalone": True,
                "session": {
                    "timeline": [{"verdict": "VALID", "n": 2, "ts": 1759100000000}],
                    "snapshots": [{"name": "before edit", "ts": 1759100200000, "auto": True}],
                },
            },
        )
        with_session = json.loads(body).get("latex", "")
        check("\\aesection{Session}" in with_session, "workspace data adds a Session section")
        check("before edit" in with_session, "the snapshot name reaches the report")

        print("== POST /api/export/pdf ==")
        status, ctype, pdf_bytes = server.request(
            "/api/export/pdf",
            "POST",
            {
                "source": by_id["even-square"]["source"],
                "session": {"snapshots": [{"name": "pdf snapshot", "ts": 1759100200000}]},
            },
        )
        check(status == 200, f"POST /api/export/pdf -> {status}")
        check("application/pdf" in ctype, f"PDF content-type is {ctype}")
        check(pdf_bytes.startswith(b"%PDF"), f"PDF bytes header is %PDF ({len(pdf_bytes)} bytes)")

        # The report has to end up in the PDF, not just in the .tex.  Page
        # objects sit in compressed streams, so the pdf bytes cannot be asked
        # how many pages they hold without pulling in a PDF library; comparing
        # the compiled size against the same source without the breakdown is
        # the dependency-free way to show the appendix is really there.
        _, _, plain_bytes = server.request(
            "/api/export/pdf",
            "POST",
            {"source": by_id["even-square"]["source"], "breakdown": False},
        )
        check(
            plain_bytes.startswith(b"%PDF") and len(pdf_bytes) > len(plain_bytes),
            f"the breakdown adds pages to the PDF ({len(plain_bytes)} -> {len(pdf_bytes)} bytes)",
        )


        _, _, body = server.request(
            "/api/check", "POST", {"source": by_id["algebraic-blunder"]["source"]}
        )
        data = json.loads(body)
        check(data["verdict"] == "INVALID", f"algebraic-blunder verdict is {data['verdict']}")
        cex = data["reports"][0]["results"][-1]["counterexample"]
        check(bool(cex), f"counterexample reported: {cex}")

        src = by_id["unguarded-division"]["source"]
        for strict, expected in ((False, "VALID (with domain warnings)"), (True, "INVALID")):
            _, _, body = server.request(
                "/api/check", "POST", {"source": src, "strict_domains": strict}
            )
            got = json.loads(body)["verdict"]
            check(got == expected, f"unguarded-division strict={strict} -> {got}")

        _, _, body = server.request(
            "/api/check", "POST", {"source": by_id["parse-error"]["source"]}
        )
        data = json.loads(body)
        pe = data["parse_error"]
        check(data["verdict"] == "PARSE ERROR", f"parse-error verdict is {data['verdict']}")
        check(
            isinstance(pe["line"], int) and isinstance(pe["col"], int),
            f"parse error carries line/col ({pe['line']}:{pe['col']})",
        )

        _, _, body = server.request("/api/check", "POST", {"source": ""})
        data = json.loads(body)
        check(data["verdict"] == "VALID" and data["summary"]["total"] == 0, "empty source is safe")

        # An unchecked prelude call used to raise TypeError straight out of the
        # engine, so this returned 500 rather than a verdict. A wrong arity is a
        # rejected step, not a server fault.
        status, _, body = server.request(
            "/api/check", "POST", {"source": "Let x : Real\nStep: abs(x, x) = x"}
        )
        data = json.loads(body)
        check(status == 200, f"a malformed call answers {status}, not a server error")
        check(
            data["verdict"] == "INVALID" and "argument" in data["reports"][0]["results"][-1]["message"],
            f"a malformed call is a rejected step: {data['reports'][0]['results'][-1]['message']}",
        )

        print("== vendored CodeMirror graph over HTTP ==")
        modules = sorted((STATIC / "vendor").rglob("*.mjs"))
        check(len(modules) > 40, f"found {len(modules)} vendored modules on disk")
        bad_status, bad_mime = [], []
        for path in modules:
            rel = path.relative_to(STATIC).as_posix()
            status, ctype, _ = server.request(f"/static/{rel}")
            if status != 200:
                bad_status.append(f"{rel} -> {status}")
            # Browsers refuse to execute an ES module served as text/plain.
            if not any(t in ctype for t in ("javascript", "ecmascript")):
                bad_mime.append(f"{rel} -> {ctype or 'none'}")
        check(not bad_status, f"all {len(modules)} modules returned 200 {bad_status[:2]}")
        check(not bad_mime, f"all modules served as JavaScript MIME {bad_mime[:2]}")

        print("== vendored Web Awesome graph over HTTP ==")
        wa_js = sorted((STATIC / "vendor" / "webawesome").rglob("*.js"))
        wa_css = sorted((STATIC / "vendor" / "webawesome").rglob("*.css"))
        check(len(wa_js) > 80, f"found {len(wa_js)} vendored component modules on disk")
        check(len(wa_css) > 20, f"found {len(wa_css)} vendored stylesheets on disk")

        wa_bad_status, wa_bad_js_mime, wa_bad_css = [], [], []
        for path in wa_js:
            rel = path.relative_to(STATIC).as_posix()
            status, ctype, _ = server.request(f"/static/{rel}")
            if status != 200:
                wa_bad_status.append(f"{rel} -> {status}")
            if not any(t in ctype for t in ("javascript", "ecmascript")):
                wa_bad_js_mime.append(f"{rel} -> {ctype or 'none'}")
        for path in wa_css:
            rel = path.relative_to(STATIC).as_posix()
            status, ctype, _ = server.request(f"/static/{rel}")
            if status != 200 or "css" not in ctype:
                wa_bad_css.append(f"{rel} -> {status} {ctype or 'none'}")
        check(not wa_bad_status, f"all {len(wa_js)} component modules returned 200 {wa_bad_status[:2]}")
        check(not wa_bad_js_mime, f"all component modules served as JavaScript {wa_bad_js_mime[:2]}")
        # A stylesheet served as anything but text/css is ignored outright.
        check(not wa_bad_css, f"all {len(wa_css)} stylesheets served as CSS {wa_bad_css[:2]}")

        # The app overrides --wa-* tokens from styles.css, so if the vendored
        # theme ever stops shipping them the palette silently falls apart.
        _, _, theme_css = server.request("/static/vendor/webawesome/styles/themes/default.css")
        check(
            b"--wa-color-surface-default" in theme_css and b"--wa-form-control-height" in theme_css,
            "the vendored theme still defines the tokens the app overrides",
        )

        # Offline guarantee: every import in the vendored tree is relative.
        # (A runtime fetch("https://ka-f.fontawesome.com/...") is a string, not
        # an import, which is exactly why the UI never uses <wa-icon name=...>.)
        import_re = re.compile(r'(?:from|import)\s*\(?\s*"(https?://[^"]+)"')
        remote = [
            f"{path.name} -> {spec}"
            for path in wa_js
            for spec in import_re.findall(path.read_text(encoding="utf-8"))
        ]
        check(not remote, f"no vendored module imports over the network {remote[:2]}")

        print("== vendored fonts over HTTP ==")
        fonts = sorted((STATIC / "vendor" / "fonts").glob("*.woff2"))
        check(len(fonts) >= 2, f"found {len(fonts)} vendored woff2 subsets on disk")
        bad_fonts = []
        for path in fonts:
            rel = path.relative_to(STATIC).as_posix()
            status, ctype, body = server.request(f"/static/{rel}")
            # wOF2 is the format's magic number.  A wrong MIME type or a 404
            # here shows up only as a silently substituted system face.
            if status != 200 or body[:4] != b"wOF2":
                bad_fonts.append(f"{rel} -> {status} {ctype or 'none'}")
        check(not bad_fonts, f"all {len(fonts)} font subsets served as woff2 {bad_fonts[:2]}")

    # A check that runs past its budget must come back as TIMEOUT -- not hang
    # the request -- and the next check must still be answered, by the worker
    # that replaced the killed one or by the other in the pool.
    with Server(env={"AETHER_CHECK_BUDGET": "1"}) as server:
        print("== check budget ==")
        slow = (
            "Let x, y, z : Int\nAssume h1: x^3 + y^3 = z^3\nAssume h2: x * y * z != 0\n"
            "Step: x = 0\nStep: y = 0\nStep: z = 0\n"
        )
        started = time.monotonic()
        status, _, body = server.request("/api/check", "POST", {"source": slow})
        data = json.loads(body)
        took = time.monotonic() - started
        check(status == 200 and data["verdict"] == "TIMEOUT", f"a stalled check answers TIMEOUT ({data.get('verdict')})")
        check(took < 10, f"and promptly ({took:.1f} s for a 1 s budget)")
        check("stopped after 1 s" in (data.get("parse_error") or {}).get("headline", ""), "the headline names the budget")
        status, _, body = server.request("/api/check", "POST", {"source": "Let x : Real\nStep: x + 0 = x\n"})
        data = json.loads(body)
        check(status == 200 and data["verdict"] == "VALID", f"the next check is still answered ({data.get('verdict')})")

    guide_checks()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all server checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
