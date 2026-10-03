"""What the site's pages show that the engine and the repo produce.

Nothing here is written by hand: the landing page's audits are the checker's
real output for real proofs, run at build time; the symbol grid is the app's
own symbol table (ui/static/js/complete.js); the pack figures are counted from
the packs.  ui/build_site.py calls build() and fills the pages'
``{{ placeholders }}`` with what it returns; web/verify_web.py checks the
built page against the engine again.

The one liberty taken is typographic: the engine's messages spell Greek
letters as `\\delta` and `epsilon`, and they are set here as δ and ε.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from html import escape
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent

# The landing page's specimen: Definition 2.6's shape for lim 3x = 6 as x → 2,
# with the slip students make: δ = ε/2, which is too big by half.
HERO_PROOF = """\
Theorem: "lim 3x = 6 as x → 2"
Claim: ∀ ε > 0, ∃ δ > 0, ∀ x ∈ ℝ, |x − 2| < δ ⇒ |3·x − 6| < ε
Proof:
    Given ε : ℝ where ε > 0
    Let δ = ε / 2
    Subproof:
        Given x : ℝ
        Assume |x − 2| < δ
        Step: |3·x − 6| = 3·|x − 2|
        Step: < 3·δ
        Step: = ε
    Therefore ∃ δ > 0, ∀ x ∈ ℝ, |x − 2| < δ ⇒ |3·x − 6| < ε [witness: ε / 2]
QED
"""

# A second audit, in amber: an assumption the proof never states.
DOMAIN_PROOF = """\
Theorem: "Cancelling a factor"
Proof:
    Given x : Real
    Step: (x^2 - 1) / (x - 1) = x + 1
QED
"""

# The same proof with the assumption stated, which checks clean.
DOMAIN_GUARDED = DOMAIN_PROOF.replace("    Step:", "    Assume x != 1\n    Step:")

RELEASES_API = "https://api.github.com/repos/SamuelSmthSmth/lemmata/releases/latest"

GREEK = [(r"\\epsilon", "ε"), (r"\\delta", "δ"), (r"\bepsilon\b", "ε"), (r"\bdelta\b", "δ"), (r"!=", "≠")]


def typeset(text: str) -> str:
    for pattern, symbol in GREEK:
        text = re.sub(pattern, symbol, text)
    return text


def symbols() -> list[dict[str, str]]:
    """The app's symbol strip, read from its source so the two never disagree."""
    source = (ROOT / "ui" / "static" / "js" / "complete.js").read_text(encoding="utf-8")
    pattern = re.compile(r'\{ symbol: "([^"]+)", ascii: "((?:[^"\\]|\\.)*)", label: "([^"]+)" \}')
    return [
        {"symbol": s, "ascii": a.encode().decode("unicode_escape"), "label": label}
        for s, a, label in pattern.findall(source)
    ]


def check(source: str) -> dict:
    from ui.engine_jobs import check_payload

    return check_payload(source, False)


def steps(result: dict) -> list[dict]:
    """Every audited statement in order, a subproof's steps in place of its summary row."""
    out: list[dict] = []

    def walk(rows: list[dict], depth: int) -> None:
        for row in rows:
            nested = (row.get("subproof_metadata") or {}).get("sub_results") or row.get("sub_results") or []
            if nested:
                walk(nested, depth + 1)
            else:
                out.append({**row, "depth": depth})

    for report in result["reports"]:
        walk(report["results"], 0)
    return out


def source_lines(source: str) -> list[str]:
    return source.rstrip("\n").split("\n")


def audit_html(source: str, result: dict, symbol_set: list[dict[str, str]]) -> tuple[str, int]:
    """The audit as the app sets it, and the index of the first failing step.

    Rows carry data-step, data-status and data-symbols (the symbols that line
    uses, for the glyph grid to light); everything is visible without script.
    """
    lines = source_lines(source)
    rows = []
    first_fail = -1
    for i, step in enumerate(steps(result)):
        status = step["status"]
        if status == "INVALID" and first_fail < 0:
            first_fail = i
        downstream = first_fail >= 0 and i > first_fail
        classes = ["audit-row", f"is-{status.lower()}"] + (["is-downstream"] if downstream else [])
        text = lines[step["line"] - 1].strip() if step.get("line") else typeset(step["statement"])
        used = " ".join(s["symbol"] for s in symbol_set if s["symbol"] in text)
        why = ""
        if status == "WARNING" and step.get("domain_warnings"):
            warning = typeset(step["domain_warnings"][0]).replace("Unresolved domain obligation: ", "")
            why = f'<p class="audit-why">Unresolved domain obligation</p><p class="audit-caveat">{escape(warning)}</p>'
        elif status != "VALID" and not downstream:
            message = typeset(step["message"].split(" Counterexample")[0])
            why = f'<p class="audit-why">{escape(message)}</p>'
            if step.get("counterexample"):
                why += f'<p class="audit-counterexample">Counterexample: {escape(typeset(step["counterexample"]).replace("Counterexample at ", ""))}</p>'
        if step["backend"] == "QED":
            # The claim is checked last, at QED: say so, or line 2 after line 12 reads as a bug.
            statement = f'<span class="audit-statement"><span class="audit-at">at QED</span> <code>{escape(text)}</code></span>'
        else:
            statement = f'<code class="audit-statement">{escape(text)}</code>'
        rows.append(
            f'<li class="{" ".join(classes)}" data-step="{i}" data-status="{escape(status)}" data-backend="{escape(step["backend"])}"'
            f' data-line="{step["line"]}" data-symbols="{escape(used)}" style="--depth: {step["depth"]}">'
            f'<span class="audit-line">{step["line"]}</span>'
            f"{statement}"
            f'<span class="audit-status">{escape(status.lower())} · {escape(step["backend"])}</span>'
            f"{why}</li>"
        )
    return "\n".join(rows), first_fail


def _glyph(symbol: str) -> str:
    """A superscript is shown on a base letter, or it floats above the line alone."""
    if symbol[0] in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻":
        return f'<span class="glyph-base">a</span>{escape(symbol)}'
    return escape(symbol)


def symbol_grid_html(symbol_set: list[dict[str, str]]) -> str:
    return "\n".join(
        f'<li class="glyph" data-symbol="{escape(s["symbol"])}">'
        f'<span class="glyph-mark" aria-hidden="true">{_glyph(s["symbol"])}</span>'
        f'<code class="glyph-ascii">{escape(s["ascii"])}</code>'
        f'<span class="glyph-label">{escape(s["label"])}</span></li>'
        for s in symbol_set
    )


def claim_html(source: str, symbol_set: list[dict[str, str]]) -> tuple[str, str]:
    """The proof's Claim, split after its quantifier prefix, each symbol marked.

    Returns the display line ("∀ ε > 0, ∃ δ > 0,") and the rest, so the page
    sets the part students recognise at specimen size.
    """
    claim = next(line for line in source_lines(source) if line.startswith("Claim:")).removeprefix("Claim:").strip()
    head, _, tail = claim.partition(", ∀ x")
    tail = "∀ x" + tail
    marks = {s["symbol"] for s in symbol_set}

    def mark(text: str) -> str:
        return "".join(f'<span class="sym" data-symbol="{escape(ch)}">{escape(ch)}</span>' if ch in marks else escape(ch) for ch in text)

    clauses = [c.strip() for c in (head + ",").split(",") if c.strip()]
    head_html = " ".join(f'<span class="clause">{mark(c)},</span>' for c in clauses)
    return head_html, mark(tail)


def pack_figures() -> dict[str, str]:
    from aether.packs import load_packs

    packs = {p["name"]: p for p in load_packs(ROOT / "courses")}
    out = {}
    for key, name in (("mth2008", "core/mth2008"), ("mth2010", "core/mth2010"), ("notation", "core/notation")):
        pack = packs[name]
        out[f"{key}_entries"] = str(len(pack["entries"]))
        out[f"{key}_traps"] = str(sum(e["kind"] == "trap" for e in pack["entries"]))
        out[f"{key}_proofs"] = str(sum(e["kind"] == "proof" for e in pack["entries"]))
        out[f"{key}_title"] = escape(pack["title"])
        out[f"{key}_chapters"] = str(len(pack["chapters"]))
    return out


def latest_release() -> dict | None:
    """The newest public desktop release, or None (none yet, or offline)."""
    if os.environ.get("LEMMATA_OFFLINE"):
        return None
    request = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read())
    except Exception:  # noqa: BLE001 - no release yet, a private repo, or no network
        return None
    return {"tag": data.get("tag_name", ""), "assets": [a["name"] for a in data.get("assets", [])]}


DOWNLOAD = "https://github.com/SamuelSmthSmth/lemmata/releases/latest/download/"

# Versionless copies the release workflow attaches, so these links stay valid.
DESKTOP_FILES = {
    "linux": [("AppImage", "Lemmata_amd64.AppImage"), (".deb", "Lemmata_amd64.deb"), (".rpm", "Lemmata.x86_64.rpm")],
    "windows": [("Installer (.exe)", "Lemmata_x64-setup.exe"), (".msi", "Lemmata_x64_en-US.msi")],
    "macos": [(".dmg (Apple silicon and Intel)", "Lemmata_universal.dmg")],
}


def desktop_links(release: dict | None) -> dict[str, str]:
    """Each platform's download buttons, or the honest "not yet" until a release has them."""
    have = set(release["assets"]) if release else set()
    out = {}
    for os_, files in DESKTOP_FILES.items():
        links = [
            f'<a class="button button--outline" href="{DOWNLOAD}{name}">{escape(label)}</a>'
            for label, name in files
            if name in have
        ]
        out[f"desktop_{os_}"] = "\n".join(links) or '<span class="state-coming">First release coming soon</span>'
    return out


def build() -> dict[str, str]:
    symbol_set = symbols()
    hero = check(HERO_PROOF)
    hero_rows, hero_fail = audit_html(HERO_PROOF, hero, symbol_set)
    hero_steps = steps(hero)
    failing = hero_steps[hero_fail]
    domain = check(DOMAIN_PROOF)
    domain_rows, _ = audit_html(DOMAIN_PROOF, domain, symbol_set)
    guarded = check(DOMAIN_GUARDED)
    release = latest_release()
    released = bool(release and release["assets"])
    claim_head, claim_tail = claim_html(HERO_PROOF, symbol_set)
    return {
        "hero_claim_head": claim_head,
        "hero_claim_tail": claim_tail,
        "hero_audit": hero_rows,
        "hero_step_count": str(len(hero_steps)),
        "hero_last_index": str(len(hero_steps) - 1),
        "hero_fail_index": str(hero_fail),
        "hero_fail_line": str(failing["line"]),
        "hero_verdict": escape(hero["verdict"]),
        "domain_audit": domain_rows,
        "domain_verdict": escape(domain["verdict"]),
        "guarded_verdict": escape(guarded["verdict"]),
        "symbol_grid": symbol_grid_html(symbol_set),
        "symbol_count": str(len(symbol_set)),
        "release_tag": escape(release["tag"]) if release else "",
        "release_state": "released" if released else "coming",
        **desktop_links(release),
        **pack_figures(),
    }
