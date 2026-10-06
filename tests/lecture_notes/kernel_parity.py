"""Every pinned course-pack entry with the proof kernel off and on: where do they disagree?

    uv run python tests/lecture_notes/kernel_parity.py [exam|course|scratch]

Each disagreement is listed with the kernel's findings.  At ``course`` there
should be none: the level is calibrated on these packs (see
``aether.kernel.policy``).  At ``exam`` the differences are the notes'
one-line evaluations of limits, derivatives and series.  Not part of pytest:
it checks all 133 entries twice (about a minute on 8 processes).
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEVEL = sys.argv[1] if len(sys.argv) > 1 else "course"


def verdict(reports):
    if not reports:
        return "EMPTY"
    if any(not r.is_valid for r in reports):
        return "INVALID"
    if any(r.has_warnings for r in reports):
        return "WARN"
    return "VALID"


def run(args):
    key, src = args
    from aether import ProofChecker, ParseError

    out = {"key": key}
    for name, kernel in (("off", None), ("on", LEVEL)):
        t = time.perf_counter()
        try:
            reports = ProofChecker(kernel=kernel).check_source(src)
            out[name] = verdict(reports)
            if kernel:
                out["findings"] = [
                    f"L{s.line} [{s.backend}] {s.message[:150]}"
                    for r in reports for s in r.all_results
                    if s.status.value == "INVALID" and s.backend.startswith("Kernel")
                ]
        except ParseError:
            out[name] = "PARSE"
        out[f"{name}_ms"] = round((time.perf_counter() - t) * 1000)
    return out


def main():
    jobs = []
    for f in ("mth2008", "mth2010", "notation"):
        pack = json.loads((ROOT / "courses" / f"{f}.json").read_text())
        for e in pack["entries"]:
            jobs.append((f"{f}/{e['id']} ({e['kind']}, {e['expected']})", e["source"]))
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [(j[0], pool.submit(run, j)) for j in jobs]
        for key, fut in futures:
            try:
                results.append(fut.result(timeout=120))
            except FutureTimeout:
                results.append({"key": key, "off": "TIMEOUT", "on": "TIMEOUT"})
    same = [r for r in results if r["off"] == r["on"]]
    diff = [r for r in results if r["off"] != r["on"]]
    print(f"{len(results)} entries at kernel={LEVEL}: {len(same)} agree, {len(diff)} differ")
    off_ms = sum(r.get("off_ms", 0) for r in results)
    on_ms = sum(r.get("on_ms", 0) for r in results)
    print(f"time: off {off_ms / 1000:.1f}s, on {on_ms / 1000:.1f}s")
    for r in diff:
        print(f"\n{r['key']}: {r['off']} -> {r['on']}")
        for f in r.get("findings", []):
            print(f"    {f}")


if __name__ == "__main__":
    main()
