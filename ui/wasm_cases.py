"""Every verdict the repo pins, as one list a native run and a Pyodide run share.

``ui/verify_wasm.mjs`` asks the same question of the engine twice, once under
CPython and once inside Pyodide (WebAssembly), and the static build is only
trusted if every answer agrees with what the repo records.  The cases are:

* every course-pack entry (``courses/*.json``), judged as
  ``tests/test_lecture_notes.py`` judges it;
* every bundled example and example file, judged as ``ui/verify_examples.py``;
* every capability probe, judged as ``ui/verify_capabilities.py`` (including
  the strict-domain verdict where a probe pins one).

This module imports nothing the browser lacks: the capability probes are read
from ``verify_capabilities.py`` without importing it (that file imports
``multiprocessing`` for its own sweeper).

Run natively:  uv run python ui/wasm_cases.py   (prints JSON: verdict and ms per case)
"""

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path
from typing import Any

UI = Path(__file__).resolve().parent
ROOT = UI.parent


def _probes() -> list[dict[str, Any]]:
    """The Probe(...) calls in verify_capabilities.py, read as literals."""
    tree = ast.parse((UI / "verify_capabilities.py").read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Probe":
            args = [ast.literal_eval(a) for a in node.args]
            kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
            area, name, source, expect = args[:4]
            out.append({"area": area, "name": name, "source": source, "expect": expect, "strict": kwargs.get("strict", "")})
    return out


def cases() -> list[dict[str, Any]]:
    from aether.packs import entry_level, load_packs

    from ui.examples import EXAMPLE_FILE_VERDICTS, EXAMPLES
    from ui.verify_examples import EXPECTATIONS

    out: list[dict[str, Any]] = []
    for pack in load_packs(ROOT / "courses"):
        for entry in pack["entries"]:
            expected = "PARSE" if entry["expected"] == "PARSE ERROR" else entry["expected"]
            out.append({"id": f"{pack['name']}/{entry['id']}", "judge": "pack", "strict": False, "level": entry_level(pack, entry), "source": entry["source"], "expected": expected})
    for example in EXAMPLES:
        kind = EXPECTATIONS[example["id"]][0]
        out.append({"id": f"example/{example['id']}", "judge": "example", "strict": False, "source": example["source"], "expected": kind})
        if kind == "WARN":
            out.append({"id": f"example/{example['id']} (strict)", "judge": "example", "strict": True, "source": example["source"], "expected": "INVALID"})
    for path in sorted((ROOT / "examples").glob("*.aether")):
        out.append({"id": f"examples/{path.name}", "judge": "example", "strict": False, "source": path.read_text(encoding="utf-8"), "expected": EXAMPLE_FILE_VERDICTS.get(path.name, "VALID")})
    for probe in _probes():
        label = f"probe/{probe['area']}/{probe['name']}"
        out.append({"id": label, "judge": "probe", "strict": False, "source": probe["source"], "expected": probe["expect"]})
        if probe["strict"]:
            out.append({"id": f"{label} (strict)", "judge": "probe", "strict": True, "source": probe["source"], "expected": probe["strict"]})
    return out


def judge(case: dict[str, Any], checker) -> str:
    """The verdict in the vocabulary of the gate that pins this case."""
    from aether import ParseError

    try:
        reports = checker.check_source(case["source"])
    except ParseError:
        return {"pack": "PARSE", "example": "PARSE_ERROR", "probe": "PARSE_ERROR"}[case["judge"]]
    if case["judge"] == "probe":
        statuses = [r.status.value for report in reports for r in report.results]
        if not statuses:
            return "EMPTY"
        if all(s == "VALID" for s in statuses):
            return "VALID"
        return "INVALID" if "INVALID" in statuses else "WARN"
    if any(not r.is_valid for r in reports):
        return "INVALID"
    if any(r.has_warnings for r in reports):
        return "WARN"
    return "VALID"


def run(only: str = "", progress=None) -> dict[str, Any]:
    """Judge every case (or those whose id contains *only*) with warm checkers."""
    from aether import ProofChecker

    started = time.perf_counter()
    from aether.packs import kernel_for

    checkers: dict = {}

    def checker_for(case):
        key = (case["strict"], case.get("level", "off"))
        if key not in checkers:
            checkers[key] = ProofChecker(strict_domains=key[0], kernel=kernel_for(key[1]))
        return checkers[key]

    checker_for({"strict": False})
    checker_for({"strict": True})
    warm_ms = (time.perf_counter() - started) * 1000
    results = []
    selected = [c for c in cases() if only in c["id"]]
    for i, case in enumerate(selected):
        checker = checker_for(case)
        t0 = time.perf_counter()
        try:
            got = judge(case, checker)
        except Exception as exc:  # noqa: BLE001 - a crash is a finding
            got = f"CRASH {type(exc).__name__}: {exc}"[:200]
        ms = (time.perf_counter() - t0) * 1000
        result = {"id": case["id"], "expected": case["expected"], "got": got, "ms": round(ms, 1)}
        if got != case["expected"]:
            # Asked again of the same warm checker, so the report shows the cause.
            try:
                result["report"] = "\n".join(r.format_report() for r in checker.check_source(case["source"]))
            except Exception as exc:  # noqa: BLE001
                result["report"] = f"{type(exc).__name__}: {exc}"
        checker.clear_cache()
        results.append(result)
        if progress:
            progress(i + 1, len(selected), case["id"], got, ms)
    return {"python": sys.version.split()[0], "checkers_ms": round(warm_ms, 1), "results": results}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "")))
