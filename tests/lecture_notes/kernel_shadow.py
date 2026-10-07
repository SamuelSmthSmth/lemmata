"""Shadow mode: the engine's verdict on each line beside the core tactics' answer.

    uv run python tests/lecture_notes/kernel_shadow.py

For every chain link and deduction in the course packs and the proofs in the
tests, with the kernel at scratch: what the engine said, and which core tactic
(if any) proves the line from the premises it could see.  Inside the core the
tactics decide (stage 3), so two lists matter:

- the tactics prove what the engine refused: a soundness alarm unless the
  engine refused for a reason that is not mathematics (an unknown label);
- the gap: the engine proves, inside the core and from premises the core can
  all read, what no tactic does.  Each is a line a student would see as
  "checked by the solver only".

A line whose premises the core cannot read (a group's axioms, `Bounded(h)`)
is neither: the engine's verdict stands there, labelled so.

Exits 1 on a mathematical alarm or a gap.  Not part of pytest
(tests/test_kernel_shadow.py runs the trap entries, the cheap half).
"""
import ast
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: Refusals that are not about the mathematics: a tactic may prove the line.
NOT_MATHEMATICS = ("Unknown or out-of-scope justification",)


def sources():
    for f in ("mth2008", "mth2010", "notation"):
        for e in json.loads((ROOT / "courses" / f"{f}.json").read_text())["entries"]:
            yield f"{f}/{e['id']} [{e['kind']}]", e["source"]
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and ("Step:" in node.value or "Therefore" in node.value) and "{" not in node.value:
                yield f"{f.name}", node.value


def run(item):
    key, src = item
    from aether import ParseError, ProofChecker
    from aether.kernel import core, review, tactics

    rows = []
    original = review.Kernel._review

    def spy(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed=None):
        goal = obligation
        if witnessed is not None:
            body, var, value = witnessed
            goal = review.substitute_expr(body, var, value)
        el = core.elaborate(goal, ctx)
        verdict = None
        if el is not None:
            verdict = tactics.weakest(el.prop, review._core_premises(ctx, allowed, self._chain, goal))
            if verdict is None:
                verdict = "premises outside" if review._unread_premises(ctx, allowed, self._chain, goal) else "none"
        rows.append((key, result.line, result.status.value, result.backend, verdict, str(goal)[:100], result.message[:120]))
        return original(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed)

    review.Kernel._review = spy
    try:
        ProofChecker(kernel="scratch").check_source(src)
    except (ParseError, Exception):
        pass
    finally:
        review.Kernel._review = original
    return rows


if __name__ == "__main__":
    items = list(sources())
    rows = []
    with ProcessPoolExecutor(8) as pool:
        for r in pool.map(run, items, timeout=900):
            rows.extend(r)
    c = Counter()
    stronger, weaker = [], []
    for key, line, status, backend, verdict, goal, msg in rows:
        if verdict is None:
            c["outside the core"] += 1
        elif verdict == "premises outside":
            c["premises outside the core"] += 1
        elif status == "INVALID" and verdict != "none":
            c["engine INVALID, tactic proves"] += 1
            stronger.append((key, line, verdict, goal, msg))
        elif status != "INVALID" and verdict == "none":
            c["gap: engine valid, no tactic"] += 1
            weaker.append((key, line, backend, goal))
        else:
            c["agree"] += 1
    print(len(rows), "lines:", dict(c))
    print("\n== the tactics prove what the engine refused ==")
    for s in stronger:
        print("  ", s)
    print("\n== the gap: the engine proves, inside the core, what no tactic does (first 40) ==")
    for w in weaker[:40]:
        print("  ", w)
    alarms = [s for s in stronger if not s[4].startswith(NOT_MATHEMATICS)]
    if alarms:
        print(f"\n{len(alarms)} line(s) the tactics prove but the engine refused on the mathematics: check the tactics.")
    if weaker:
        print(f"\n{len(weaker)} line(s) only the solver checks: students would see them as warnings.")
    if alarms or weaker:
        sys.exit(1)
