"""Run the lecture-note corpora and report every entry whose verdict is off.

    uv run python tests/lecture_notes/run_corpus.py [filter] [-v] [-j N] [--budget S]

Each entry runs in its own process under a wall-clock budget: Z3 cannot be
interrupted from Python, so an in-process timeout would not fire.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus_algebra import CORPUS as ALGEBRA  # noqa: E402
from corpus_notation_and_soundness import CORPUS as NOTATION  # noqa: E402
from corpus_real_analysis import CORPUS as REAL_ANALYSIS  # noqa: E402

ALL = (
    [("MTH2008", *e) for e in REAL_ANALYSIS]
    + [("MTH2010", *e) for e in ALGEBRA]
    + [("NOTATION", *e) for e in NOTATION]
)


def verdict(source: str, strict: bool = False) -> tuple[str, str]:
    """Fold a document's reports into one verdict, plus a printable report."""
    from aether import ParseError, ProofChecker

    try:
        reports = ProofChecker(strict_domains=strict).check_source(source)
    except ParseError as err:
        return "PARSE", f"line {err.line} col {err.col}: {str(err.message)[:300]}"
    except Exception:  # noqa: BLE001 - a crash is exactly what we want to see
        return "CRASH", traceback.format_exc()[-1500:]
    text = "\n".join(r.format_report() for r in reports)
    if not reports:
        return "EMPTY", text
    if not all(r.is_valid for r in reports):
        return "INVALID", text
    if any(r.has_warnings for r in reports):
        return "WARN", text
    return "VALID", text


def _child(source: str, conn) -> None:
    conn.send(verdict(source))
    conn.close()


def run_one(source: str, budget: float) -> tuple[str, str, float]:
    start = time.time()
    parent, child = mp.Pipe(duplex=False)
    proc = mp.get_context("fork").Process(target=_child, args=(source, child))
    proc.start()
    child.close()
    if parent.poll(budget):
        got, text = parent.recv()
    else:
        got, text = "TIMEOUT", f"no verdict within {budget:.0f}s"
    proc.kill()
    proc.join()
    return got, text, time.time() - start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("filter", nargs="?")
    ap.add_argument("-v", action="store_true", help="print reports for passing entries too")
    ap.add_argument("-j", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--budget", type=float, default=60.0)
    args = ap.parse_args()

    entries = [e for e in ALL if not args.filter or args.filter.lower() in f"{e[0]} {e[1]}".lower()]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(args.j) as pool:
        results = list(pool.map(lambda e: run_one(e[3], args.budget), entries))

    bad = 0
    for (course, name, expect, _src), (got, text, dt) in zip(entries, results):
        ok = got == expect
        bad += not ok
        print(f"[{'ok ' if ok else 'BAD'}] {course} {name:62.62s} want={expect:7s} got={got:7s} {dt:5.1f}s")
        if (not ok or args.v) and text:
            print("      " + text.replace("\n", "\n      "))
    print(f"\n{len(entries) - bad}/{len(entries)} as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
