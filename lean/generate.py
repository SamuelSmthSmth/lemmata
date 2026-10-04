"""Write Generated.lean: every skeleton "Show me in Lean" gives for a pinned proof.

The bundled examples, every course-pack entry, the capability probes and the
Guide's *Try it* proofs are each exported with ``aether.core.lean_export`` into
a namespace of their own, in one file, so a single ``lake env lean
Generated.lean`` (the ``lean`` CI job) holds every skeleton to compiling against
Mathlib.  ``Generated.index.json`` maps the file's line ranges back to the
source each came from; ``--explain <log>`` uses it to name the source of each
Lean error.

    uv run python lean/generate.py
    uv run python lean/generate.py --explain lean.log
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ui"))

OUT = Path(__file__).resolve().parent / "Generated.lean"
INDEX = OUT.with_suffix(".index.json")


def sources() -> list[tuple[str, str]]:
    """``(name, source)`` for every pinned proof that parses."""
    from examples import EXAMPLES  # type: ignore[import-not-found]
    import verify_capabilities as caps  # type: ignore[import-not-found]

    out: list[tuple[str, str]] = [(f"example {ex['id']}", ex["source"]) for ex in EXAMPLES]
    for path in sorted((ROOT / "courses").glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for entry in pack.get("entries", []):
            out.append((f"{pack['name']} {entry['id']}", entry["source"]))
    for probe in caps.PROBES:
        if probe.expect not in ("PARSE_ERROR", "EMPTY", "TIMEOUT"):
            out.append((f"probe {probe.area}: {probe.name}", probe.source))
    pattern = re.compile(r'<pre class="try" data-expect="([A-Z ]+)">(.*?)</pre>', re.S)
    for page in sorted((ROOT / "ui" / "static" / "guide").glob("*.html")):
        for i, (expect, body) in enumerate(pattern.findall(page.read_text(encoding="utf-8")), start=1):
            if expect != "PARSE ERROR":
                out.append((f"guide {page.stem} #{i}", html.unescape(body)))
    return out


def ident(name: str, used: set[str]) -> str:
    base = "S_" + re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    candidate, i = base, 2
    while candidate in used:
        candidate, i = f"{base}_{i}", i + 1
    used.add(candidate)
    return candidate


def generate() -> int:
    from aether import ParseError
    from aether.core.lean_export import export_to_lean

    lines = ["import Mathlib", ""]
    index: list[dict[str, object]] = []
    used: set[str] = set()
    for name, source in sources():
        try:
            export = export_to_lean(source, namespace=f"Lemmata.{ident(name, used)}")
        except ParseError:
            continue
        body = export.lean.splitlines()
        assert body[0] == "import Mathlib", name
        start = len(lines) + 1
        lines.extend(body[1:])
        index.append({"name": name, "from": start, "to": len(lines)})
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    INDEX.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"wrote {len(index)} skeletons, {len(lines)} lines, to {OUT.name}")
    return 0


def explain(log_path: str) -> int:
    """Name the source of each error in a ``lake env lean Generated.lean`` log."""
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    generated = OUT.read_text(encoding="utf-8").splitlines()
    errors = 0
    for match in re.finditer(r"Generated\.lean:(\d+):(\d+): error(?:\([^)]*\))?: (.*)", Path(log_path).read_text(encoding="utf-8")):
        line = int(match.group(1))
        owner = next((e["name"] for e in index if e["from"] <= line <= e["to"]), "?")
        errors += 1
        print(f"{owner}: line {line}: {match.group(3)}")
        print(f"    {generated[line - 1].strip()}")
    print(f"{errors} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--explain":
        sys.exit(explain(sys.argv[2]))
    sys.exit(generate())
