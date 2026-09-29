"""HTTP/API smoke test for the Aether UI.

Starts its own server on a free port, exercises every endpoint and the whole
vendored CodeMirror graph over HTTP, then shuts the server down.

Run with:  uv run python ui/verify_server.py
"""

from __future__ import annotations

import json
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
    def __init__(self) -> None:
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> Server:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ui", "--port", str(self.port)],
            cwd=str(PROJECT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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
