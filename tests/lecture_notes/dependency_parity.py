"""Every pinned course-pack entry with the dependency audit and trace off and on.

    uv run python tests/lecture_notes/dependency_parity.py [exam|course|scratch]

``ProofChecker(dependencies=True, trace=True)`` must not change a single
line's verdict, message or counterexample: the audit only reads what the
check did.  This checks that on every entry, line by line, and reports what
the audit costs and how often it can say everything a line used.  With a
kernel level, both runs use it.  Not part of pytest: it checks all entries
twice (about a minute on 8 processes).
"""
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEVEL = sys.argv[1] if len(sys.argv) > 1 else None


def lines(reports):
    return [
        (s.line, s.status.value, s.backend, s.message, s.counterexample)
        for r in reports
        for s in r.all_results
    ]


def run(args):
    key, src = args
    from aether import ParseError, ProofChecker

    out = {"key": key}
    for name, extra in (("off", {}), ("on", {"dependencies": True, "trace": True})):
        t = time.perf_counter()
        try:
            reports = ProofChecker(kernel=LEVEL, **extra).check_source(src)
            out[name] = lines(reports)
            if extra:
                steps = [s for r in reports for s in r.all_results if s.status.value != "INVALID"]
                out["complete"] = sum(s.premises_complete for s in steps)
                out["checked"] = len(steps)
                out["partial"] = Counter(s.backend for s in steps if not s.premises_complete)
                out["events"] = sum(len(s.trace) for r in reports for s in r.all_results)
        except ParseError:
            out[name] = "PARSE"
        out[f"{name}_ms"] = round((time.perf_counter() - t) * 1000)
    return out


def main():
    jobs = []
    for f in ("mth2008", "mth2010", "notation"):
        pack = json.loads((ROOT / "courses" / f"{f}.json").read_text())
        for e in pack["entries"]:
            jobs.append((f"{f}/{e['id']}", e["source"]))
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [(j[0], pool.submit(run, j)) for j in jobs]
        for key, fut in futures:
            try:
                results.append(fut.result(timeout=180))
            except FutureTimeout:
                results.append({"key": key, "off": "TIMEOUT", "on": "TIMEOUT"})
    diff = [r for r in results if r["off"] != r["on"]]
    print(f"{len(results)} entries (kernel={LEVEL}): {len(results) - len(diff)} identical, {len(diff)} differ")
    off_ms = sum(r.get("off_ms", 0) for r in results)
    on_ms = sum(r.get("on_ms", 0) for r in results)
    print(f"time: off {off_ms / 1000:.1f}s, on {on_ms / 1000:.1f}s ({(on_ms / max(off_ms, 1) - 1) * 100:+.0f}%)")
    complete = sum(r.get("complete", 0) for r in results)
    checked = sum(r.get("checked", 0) for r in results)
    print(f"premises: complete for {complete} of {checked} lines that checked")
    partial = sum((r.get("partial", Counter()) for r in results), Counter())
    print("  partial, by backend:", ", ".join(f"{b} {n}" for b, n in partial.most_common()))
    print(f"trace: {sum(r.get('events', 0) for r in results)} events")
    slowest = sorted(results, key=lambda r: r.get("on_ms", 0) - r.get("off_ms", 0), reverse=True)[:5]
    print("largest added cost:", ", ".join(f"{r['key']} +{r.get('on_ms', 0) - r.get('off_ms', 0)}ms" for r in slowest))
    for r in diff:
        print(f"\n{r['key']}:")
        if not isinstance(r["off"], list) or not isinstance(r["on"], list):
            print(f"    {r['off']} -> {r['on']}")
            continue
        for a, b in zip(r["off"], r["on"]):
            if a != b:
                print(f"    off {a}\n    on  {b}")
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
